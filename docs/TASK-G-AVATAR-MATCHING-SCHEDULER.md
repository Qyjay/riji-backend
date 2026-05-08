# TASK-G：AI 分身匹配与定时冲浪（搭子发现）

> **负责人：** Backend / Avatar
>
> **模块：** `app/avatar/`、`app/plaza/`、`app/social/`、`app/memory/`
>
> **前置阅读：** [TASK-E-PLAZA.md](./TASK-E-PLAZA.md) → [TASK-D-SOCIAL.md](./TASK-D-SOCIAL.md) → [MEMORY_SYSTEM_GUIDE.md](./MEMORY_SYSTEM_GUIDE.md)
>
> **分支名：** `feat/avatar-match-scheduler`
>
> **优先级：** P1
>
> **目标：** 用户在广场、日记、素材、聊天等场景留下内容后，分身能基于可公开的用户意图和偏好进行匹配与推荐，低打扰地发现搭子，并按用户允许的频率定时冲浪、生成推荐和行动草稿。

> ### 当前进度
>
> | 阶段 | 内容 | 状态 |
> |---|---|---|
> | Phase 1 | 补齐配置与日志（AvatarUsageStat / AvatarSurfLog / 使用习惯采集 API） | ✅ 已完成 |
> | Phase 2 | 个性化冲浪 — 反馈加权（历史 chat/dismiss/approve/reject 折算小时奖惩分） | ✅ 已完成 |
> | Phase 3 | 个性化冲浪 — UCB Bandit（探索与利用权衡，banditArms 持久化） | ✅ 已完成 |
> | Phase 4 | 方案B 外部调度器（run_avatar_surf_for_user + scripts/run_avatar_scheduler.py） | ✅ 已完成 |
> | Phase 5 | 分身规则匹配（三路信号宽召回 + 多维规则打分，帖子 + 用户双通道） | ✅ 已完成 |
> | Phase 6 | AI 精排与开场建议（MiniMax 精排 top-10，生成自然理由 + 开场白） | ✅ 已完成 |
> | Phase 7 | 社交闭环（推荐 → 搭子申请，一键 start-chat + Bandit 最强反馈） | ✅ 已完成 |
> | Phase 8A | Top-10 粗筛 + AtoA 初始对话（后台按评分取最高10位候选，逐一进行分身对话1-3轮，outcome=pending_user_decision） | ✅ 已实现（联调清单见 [task-g-worklist.md](./task-g-worklist.md)） |
> | Phase 8B | 用户继续聊（用户手动触发追加1-3轮分身对话，可循环多次回到决策点） | ✅ 已实现 |
> | Phase 8C | 用户最终决策（打断 / 结交；结交走 `POST /social/buddy/{id}/respond` 同步探针终态） | ✅ 已实现（与 §十二草案差异见 worklist） |
>
> **已注入测试数据：** 10 个真实测试用户（2026-04-23 ~ 2026-05-03，11 天完整行为数据）
> 运行 `python scripts/seed_realistic_may_2026.py` 重置，再运行 `python scripts/seed_avatar_habits.py` 补充使用习惯数据。
>
> **执行清单与 Phase 1～8 联调步骤（维护版）：** [task-g-worklist.md](./task-g-worklist.md)

---

## 一、需求概述

当前分身已有以下能力：

- 分身记忆库：`AvatarMemory`
- 分身状态：`AvatarStatus`
- 分身推荐：`AvatarMatch`
- 分身侧写：`AvatarProfile`
- 对外名片：`AvatarCard`
- 行动草稿/审批：`AgentAction`
- 手动触发自动冲浪：`POST /api/avatar/actions/auto-surf`

Task-G 要把这些能力串成一个持续运行的闭环。

### 架构演进

**Phase 1-7 的原始闭环（已完成）：**

```text
用户发布/记录内容
→ 记忆抽取 → 更新分身名片
→ 分身冲浪 → 规则打分（标签/回帖/侧写相似度）→ AI精排
→ 直接生成 AvatarMatch 推送给用户
→ 用户审批/start-chat
```

**Phase 8 AtoA 搭子模式闭环（当前目标架构）：**

```text
用户发布/记录内容
→ 记忆抽取 → 更新分身名片（AvatarCard）
→ 分身按设定频率冲浪
→ [Phase 8A] 后台粗筛：规则评分取最高10位候选，写入 AtoaSession
→ [Phase 8A] 对每位候选，分身 A 与分身 B 进行 1-3 轮 AtoA 对话
    └── 写入 AtoaInteraction(outcome="pending_user_decision")，对方不可见
→ 用户在「分身动态」依次查看每段对话，手动做出三种决策：
    ├── [Phase 8B] 继续聊 → 分身再进行 1-3 轮 → 回到决策点（可循环）
    ├── [Phase 8C] 打断 → 双方互相降分 + 从剩余候选补入新的第11位（不重复前10人）
    └── [Phase 8C] 结交 → 用户发出搭子申请 → 对方确认 → 社交闭环
→ Bandit 正向/负向反馈 → 推荐质量持续优化
```

**关键架构变化：**

| 角色 | Phase 5-6 | Phase 8 AtoA搭子模式 |
|------|-----------|---------------------|
| 规则打分（标签/回帖/侧写） | 主排序依据 | 粗筛 Top-10 候选的评分依据 |
| AI 精排（MiniMax） | 精排决定最终推荐列表 | 驱动分身对话内容生成 |
| AtoA 双向对话 | 不存在 | **核心交互机制**，用户可读每轮对话 |
| 候选池管理 | 无状态，每次冲浪重新全量扫描 | 有状态 AtoaSession，记录已展示的10人和排除列表 |
| 用户与推荐结果的关系 | 被动接收 | 全程手动介入，每段对话都有决策点 |
| "打断"的后果 | 单方降权 | **双向降分** + 自动从排名11位起补入新候选 |
| 社交闭环 | 一键 start-chat（单方触发） | 用户发申请 + **对方手动确认**（双方同意） |

核心原则：

- **用户授权优先**：分身不能在未开启的情况下自动发布、私聊或暴露隐私。
- **公开信息匹配**：分身侧只使用用户允许进入分身名片的摘要、标签、社交意图和边界，不直接泄露日记/聊天原文。
- **用户全程掌控**：分身只负责「找人、聊天」，每段对话后必须等用户手动决策才能推进。
- **可解释且可监察**：用户随时可以看到「分身和谁聊了什么」，不只是看最终推荐理由。
- **打断双向生效**：用户选择打断时，双方互相从对方的候选池中降分，不再主动推荐对方。
- **结交需双方确认**：用户发出结交申请后，必须由对方用户手动确认，分身不替用户做出承诺。
- **可回滚**：所有分身动作落 `AgentAction` 审计记录。

---

## 二、产品场景

### 2.1 用户发布广场内容后

用户发布「找搭子 / 求助 / 分享 / 恋爱」帖子后：

1. 后端将帖子写入 `plaza_posts`。
2. 记忆系统抽取：
   - 话题标签：如「图书馆自习」「夜跑」「考研」「失眠」
   - 社交意图：如 `buddy`、`help`、`dating`、`share`
   - 时效性：如「今晚」「本周末」「长期」
   - 边界：如「只限本校」「不想被打扰」「仅女生」
3. 分身生成或刷新对外名片。
4. 触发一次轻量分身匹配：
   - 找相似需求的人
   - 找互补能力的人
   - 找同校/同时间/同兴趣的人
5. 返回推荐列表或生成行动草稿。

### 2.2 用户写日记/素材后

用户写日记或上传素材后，不应直接把私密内容拿去社交匹配，而是：

1. 先进入长期记忆系统。
2. 只抽取可社交化的结构化信息：
   - 兴趣偏好
   - 生活习惯
   - 当前目标
   - 社交需求
   - 明确边界
3. 只有在用户开启「允许分身用于社交推荐」后，才进入 `AvatarCard`。
4. 分身匹配只读取 `AvatarCard` + 可公开行为摘要，不读取日记原文。

### 2.3 分身自动冲浪

当用户开启分身冲浪后：

1. 定时任务定期扫描活跃用户。
2. 根据用户频率设置决定是否执行。
3. 分身浏览新帖子、新评论、潜在搭子。
4. 生成 `AvatarMatch` 推荐或 `AgentAction` 草稿。
5. 前端展示「分身今天帮你看到了什么」。

---

## 三、数据模型 TODO

> 原则：现有字段只增不删；新增字段用 Alembic 迁移。

### 3.1 扩展 `avatar_status`

当前已有：

- `is_active`
- `browsed_count`
- `matched_count`
- `chatting_count`
- `last_active_at`
- `enabled_channels`
- `enabled_actions`
- `match_range`

建议新增字段：

```python
surf_frequency = Column(String, default="medium")
# low / medium / high / custom

surf_window = Column(Text, default='{"start":"09:00","end":"23:00","timezone":"Asia/Shanghai"}')
# 允许冲浪时间段，避免半夜打扰

next_surf_at = Column(BigInteger, default=0)
# 下次允许被调度的时间

last_surf_at = Column(BigInteger, default=0)
# 上次实际冲浪时间

daily_surf_count = Column(Integer, default=0)
# 今日冲浪次数，配合自然日重置

daily_action_count = Column(Integer, default=0)
# 今日生成草稿/发布动作数

quiet_mode = Column(Boolean, default=False)
# 用户手动暂停分身

auto_match_enabled = Column(Boolean, default=True)
# 是否允许自动生成 AvatarMatch

auto_comment_enabled = Column(Boolean, default=False)
# 是否允许自动生成评论草稿

auto_publish_enabled = Column(Boolean, default=False)
# 是否允许自动发布，默认必须关闭
```

### 3.2 扩展 `avatar_matches`

当前匹配只围绕 `post_id`，建议扩展为既支持「帖子匹配」，也支持「人-人/分身-分身匹配」：

```python
target_user_id = Column(String, nullable=True)
# 分身匹配到的目标用户

target_avatar_card_id = Column(String, nullable=True)
# 匹配时使用的对方分身名片快照 ID

match_type = Column(String, default="post")
# post / user / need / comment_thread / atoa

intent_type = Column(String, default="")
# buddy / help / dating / share / study / sport / emotion_support

confidence = Column(Float, default=0.0)
# 置信度 0-1

risk_flags = Column(Text, default="[]")
# JSON: string[]，如 privacy_risk / age_gap / school_mismatch / stale_need

source = Column(String, default="scheduler")
# scheduler / post_publish / manual_refresh / profile_update

expires_at = Column(BigInteger, nullable=True)
# 时效型搭子的过期时间

updated_at = Column(BigInteger, nullable=True)
```

#### Phase 8 新增字段（AtoA 专属）

```python
their_score = Column(Integer, default=0)
# 对方分身视角给「我」的规则打分（AtoA 专用）

their_reasons = Column(Text, default="[]")
# JSON: string[]，对方视角的匹配理由（显示给用户："TA 的分身觉得你们合适是因为…"）

is_mutual = Column(Boolean, default=False)
# 是否双向达标：my score >= 阈值 AND their score >= 阈值

peer_match_id = Column(String, nullable=True)
# 对方用户的那条 AvatarMatch 的 ID，双向关联（atoa 型专用）
```

> **说明：**
> - `match_type="atoa"` 的记录一定成对出现：A→B 一条，B→A 一条，通过 `peer_match_id` 相互指向。
> - `is_mutual=False` 的 `atoa` 记录**不应推送给用户**，只保留用于后续刷新（对方分身再次冲浪后可能变为 True）。
> - 旧的 `match_type="user"` 记录保持原有逻辑不受影响，仅新增 `atoa` 通道。

### 3.3 新增 `avatar_usage_stats`

用于后台学习用户 App 使用时间和习惯。第一版不保存完整行为流水，只按「星期几 + 小时」聚合，降低隐私风险。

```python
class AvatarUsageStat(Base):
    __tablename__ = "avatar_usage_stats"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    weekday = Column(Integer, nullable=False)            # 0=周一 ... 6=周日
    hour = Column(Integer, nullable=False)               # 0-23，Asia/Shanghai
    open_count = Column(Integer, default=0)              # 打开/回到前台次数
    active_ms = Column(BigInteger, default=0)            # 累计活跃时长
    page_weights = Column(Text, default="{}")            # JSON: plaza/diary/chat 等页面权重
    last_seen_at = Column(BigInteger, default=0)
    updated_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index("ix_avatar_usage_stats_user_weekday_hour", "user_id", "weekday", "hour", unique=True),
        Index("ix_avatar_usage_stats_user_seen", "user_id", "last_seen_at"),
    )
```

事件来源：

- `app_open`：用户打开 App。
- `app_resume`：用户回到前台。
- `active_ping`：前端每隔一段时间上报仍在活跃。
- `app_close`：用户离开 App 时补充本次活跃时长。
- `page_view`：记录当前主要页面，用于判断用户更常在广场、日记、聊天还是分身页活跃。

聚合用途：

- 学习用户常用 App 的小时段。
- 学习用户偏好的内容场景。
- 在用户开启自动冲浪后，提前 10-30 分钟预热推荐。
- 避免在用户长期不活跃或睡眠时段打扰。

### 3.4 新增 `avatar_surf_logs`

用于调试、限流和前端展示「分身今天干了什么」：

```python
class AvatarSurfLog(Base):
    __tablename__ = "avatar_surf_logs"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    trigger = Column(String, nullable=False)
    # scheduler / post_publish / manual / profile_update

    status = Column(String, default="success")
    # success / skipped / failed

    scanned_posts = Column(Integer, default=0)
    scanned_users = Column(Integer, default=0)
    generated_matches = Column(Integer, default=0)
    generated_actions = Column(Integer, default=0)
    skipped_reason = Column(String, default="")
    error_message = Column(Text, default="")
    started_at = Column(BigInteger, nullable=False)
    finished_at = Column(BigInteger, nullable=True)

    __table_args__ = (
        Index("ix_avatar_surf_logs_user_time", "user_id", "started_at"),
    )
```

### 3.5 新增或扩展用户公开授权

需要明确哪些记忆可以进入社交匹配：

```python
avatar_social_enabled = Column(Boolean, default=False)
# 是否允许分身使用画像参与社交推荐

avatar_public_memory_scope = Column(Text, default='["interest","need","habit"]')
# 允许进入 AvatarCard 的记忆类别

avatar_sensitive_topics = Column(Text, default="[]")
# 用户不希望被用于匹配/推荐的话题
```

如果不想改 `user_settings`，也可以先放在 `AvatarStatus.match_range` 的 JSON 配置里，但长期建议独立字段。

### 3.6 新增 `avatar_atoa_sessions`（Phase 8 搭子模式候选池会话）

每次冲浪触发一次 Top-10 粗筛后，写入一条 `AtoaSession`，记录本次展示给用户的10位候选和已排除候选列表，用于「打断后补位」的去重逻辑。

```python
class AvatarAtoaSession(Base):
    __tablename__ = "avatar_atoa_sessions"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    candidate_ids = Column(Text, default="[]")
    # JSON: string[]，本次粗筛的10位候选用户 ID（按评分降序排列）

    excluded_ids = Column(Text, default="[]")
    # JSON: string[]，用户已「打断」或已「结交申请」的候选 ID，补位时不再重复出现

    score_snapshot = Column(Text, default="{}")
    # JSON: {user_id: score}，粗筛时各候选的规则评分快照，补位时从同一评分池中选第11+位

    status = Column(String, default="active")
    # active   — 会话进行中，仍有候选未决策
    # completed — 10位候选全部决策完毕（可发起下一次冲浪）
    # superseded — 被更新的冲浪会话替代（用户手动刷新或调度触发新一轮）

    surf_log_id = Column(String, nullable=True)
    # 关联的 AvatarSurfLog.id

    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index("ix_atoa_sessions_user", "user_id", "created_at"),
        Index("ix_atoa_sessions_status", "user_id", "status"),
    )
```

**字段说明：**

| 字段 | 用途 |
|------|------|
| `candidate_ids` | 初始Top-10，有序，用于前端「还剩几位未决策」进度展示 |
| `excluded_ids` | 打断/结交后追加，补位时排除，保证10人内不重复 |
| `score_snapshot` | 快照便于补位时直接取第11、12...位，不需要重新全量评分 |
| `status=active` | 当前正在进行的会话，同一用户同时只有一个 active |
| `status=completed` | 10位全决策后置为 completed，触发下一次冲浪重新粗筛 |

### 3.7 新增 `avatar_atoa_interactions`（Phase 8 AtoA 探针互动日志）

这张表是 AtoA 搭子模式的核心可观察层：每次「分身与一位候选分身进行对话」都写入一条记录，用户在「分身动态」页可以依次查看每段对话并手动决策。

```python
class AvatarAtoaInteraction(Base):
    __tablename__ = "avatar_atoa_interactions"

    id = Column(String, primary_key=True, default=_uuid)
    initiator_id = Column(String, ForeignKey("users.id"), nullable=False)
    # 触发本次探针的冲浪用户（谁的冲浪任务写了这条记录）

    session_id = Column(String, ForeignKey("avatar_atoa_sessions.id"), nullable=True)
    # 所属的 AtoaSession（Top-10 粗筛会话），用于补位逻辑和进度追踪

    user_a_id = Column(String, ForeignKey("users.id"), nullable=False)
    user_b_id = Column(String, ForeignKey("users.id"), nullable=False)
    # user_a 始终是 initiator（当前用户），user_b 是候选搭子

    interaction_type = Column(String, default="card_exchange")
    # card_exchange  — 双方名片对比（最常见）

    outcome = Column(String, default="pending_user_decision")
    # pending_user_decision — 分身对话已完成（≥1轮），等待用户手动决策  ← 初始状态
    # continuing            — 用户选择「继续聊」，分身正在进行续聊轮次
    # blocked               — 用户选择「打断」，双向降分，已排除出候选池
    # connected             — 用户选择「结交」，已发出搭子申请，等待对方确认
    # connect_confirmed     — 对方用户已确认，社交闭环完成
    # connect_rejected      — 对方用户拒绝了结交申请

    score_a = Column(Integer, default=0)
    # A 视角对 B 的规则评分（来自粗筛阶段的快照）

    score_b = Column(Integer, default=0)
    # B 视角对 A 的评分（B 端冲浪时补填，或由系统估算）

    shared_topics = Column(Text, default="[]")
    # JSON: string[]，双方名片中重合的兴趣词/话题词

    reasons_a = Column(Text, default="[]")
    # JSON: string[]，A 视角的匹配理由（展示给 A）

    risk_flags = Column(Text, default="[]")
    # JSON: string[]，探针过程中发现的风险（边界冲突/学校不匹配等）

    conversation = Column(Text, default="[]")
    # JSON: [{role: "avatar_a", content: "...", phase: 1}, {role: "avatar_b", content: "...", phase: 1}, ...]
    # 所有轮组的对话内容，续聊时追加（含 phase 标记，前端可分组展示）
    # 每个 phase 最多 3 轮（1轮 = avatar_a + avatar_b 各一条消息）

    interaction_phase = Column(Integer, default=1)
    # 当前是第几轮组（每轮组 ≤3 轮对话），用户每次「继续聊」+1

    user_decision = Column(String, nullable=True)
    # 用户最近一次手动决策：null（未决策）/ "continue" / "block" / "connect"

    triggered_match_id = Column(String, nullable=True)
    # outcome=connected 时，关联的 social.Match.id（搭子申请记录）

    is_visible_to_a = Column(Boolean, default=True)
    # A 是否可以在「分身动态」看到此条记录（始终 True）

    is_visible_to_b = Column(Boolean, default=False)
    # B 是否可以看到（默认不可见；outcome=connected 或 connect_confirmed 时置 True）

    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index("ix_atoa_interactions_initiator", "initiator_id", "created_at"),
        Index("ix_atoa_interactions_pair", "user_a_id", "user_b_id"),
        Index("ix_atoa_interactions_outcome", "outcome"),
        Index("ix_atoa_interactions_session", "session_id"),
    )
```

**outcome 枚举完整说明：**

| outcome | 含义 | 用户可操作 |
|---------|------|-----------|
| `pending_user_decision` | 分身初次对话完成（1-3轮），等待用户决策 | 继续聊 / 打断 / 结交 |
| `continuing` | 用户点了「继续聊」，分身续聊中（异步生成） | 等待中 |
| `blocked` | 用户选择「打断」，双向降分，候选已排除 | 不可再操作 |
| `connected` | 用户已发出结交申请，等对方确认 | 可撤回申请 |
| `connect_confirmed` | 对方已确认，社交闭环完成 | 跳转搭子详情 |
| `connect_rejected` | 对方拒绝了结交申请 | 可选重新开始/放弃 |

`AvatarSurfLog` 新增字段：

```python
scanned_atoa_pairs = Column(Integer, default=0)
# 本次冲浪进入 AtoA 探针的候选对数（即 Top-10 实际生成的对话数）
top10_session_id = Column(String, nullable=True)
# 本次冲浪创建的 AtoaSession.id
```

---

## 四、分身匹配算法设计

### 4.1 输入数据

我的分身：

- `AvatarCard.public_summary`
- `AvatarCard.interest_tags`
- `AvatarCard.social_intent`
- `AvatarCard.conversation_style`
- `AvatarCard.boundaries`
- `AvatarStatus.enabled_channels`
- `AvatarStatus.match_range`
- 近期 `MemoryFact` 中允许社交使用的 `interest / need / habit / boundary`

对方分身：

- 对方 `AvatarCard`
- 对方公开帖子 `PlazaPost`
- 对方公开评论 `PlazaComment`
- 对方是否允许分身回复：`allow_agent_reply`
- 对方是否仅本校可见：`school_only`

上下文：

- 同校/跨校
- 帖子频道
- 时间有效性
- 用户是否已经 dismiss/chat
- 是否已有 `Match` 或 `SocialMessage`
- 是否已经对同一帖子生成过草稿

### 4.2 宽召回（Phase 8 后的定位：仅作过滤器）

> **Phase 8 后架构变化**：召回层不再是排序依据，只负责快速排除明显不匹配的候选，通过的候选全部进入 AtoA 探针。召回阈值宜宽不宜严。

**召回通过条件（满足任意一条即进入 AtoA 探针候选池）：**

1. **帖子召回**（保留，作为候选入口）
   - 最近 7 天广场帖子
   - 频道在 `enabled_channels`
   - 排除自己发的帖子
   - 尊重 `school_only`
   - 尊重 `allow_agent_reply`

2. **用户召回**（保留，作为候选入口）
   - 有公开/可匹配 `AvatarCard`（`visibility != "private"`）
   - 近 14 天有广场、评论、日记转公开意图或社交行为
   - 未被拉黑、未被 dismiss
   - **AtoA 专用门槛**：`AvatarStatus.auto_match_enabled = True`

3. **需求召回**
   - 从 `MemoryFact` 或 `AvatarMemory` 中找 `need`
   - `match_status = searching`，未过期
   - `need_type` 相同或互补

4. **互动召回**
   - 对方评论过相似帖子
   - 双方都参与过同一话题
   - 对方曾点赞/评论过用户帖子

**召回后的去向：**

```text
召回候选池
  ├── 对方 auto_match_enabled=True  → 进入 AtoA 探针通道（§4.6）
  └── 对方 auto_match_enabled=False → 退回旧的规则打分通道（§4.3，作为兜底）
```

> 旧的规则打分通道（§4.3）作为**兜底**：在 AtoA 用户基数不足时，仍生成 `match_type="post"/"user"` 推荐，保证推荐列表不为空。

### 4.3 规则粗排评分（兜底通道，仅对 `auto_match_enabled=False` 的候选使用）

> **Phase 8 后定位**：此通道仅对未开启 AtoA 的用户生效，作为过渡期兜底。当系统中 AtoA 用户达到一定比例后，此通道可逐步停用。

建议总分 100 分：

```text
score =
  interest_overlap_score * 0.25
+ intent_match_score     * 0.25
+ context_score          * 0.20
+ social_safety_score    * 0.15
+ freshness_score        * 0.10
+ feedback_score         * 0.05
```

评分维度：

- `interest_overlap_score`：标签重合，同义词归一化，近期兴趣权重更高
- `intent_match_score`：buddy↔buddy 最高，dating 需严格边界检查
- `context_score`：同校 +15，同活动 +10，`school_only` 不匹配则直接过滤
- `social_safety_score`：边界不冲突，无敏感话题冲突
- `freshness_score`：近 24 小时最高，超过 7 天降权
- `feedback_score`：历史 chat/dismiss 记录加减分

### 4.4 精排与解释生成（兜底通道 AI 精排）

> **Phase 8 后定位**：AI 精排仍保留，但主要用途从「决定推荐排序」转变为「为 AtoA 互动记录生成自然语言摘要文案」。

粗排后取 Top 20，调用 AI 生成：

- AtoA 互动的 `reasons_a` / `reasons_b` 自然语言描述
- 兜底通道的 `match_reasons` / `suggested_opening`
- 高风险推荐的 `risk_flags` 解释文案

```json
{
  "matchScore": 86,
  "intentType": "study_buddy",
  "matchReasons": [
    "你们都在找晚间自习搭子",
    "同校且都提到图书馆",
    "对方最近也在准备考试"
  ],
  "riskFlags": [],
  "recommendedAction": "show_recommendation",
  "suggestedOpening": "嗨，我也想找晚自习搭子，你一般几点去图书馆？"
}
```

### 4.6 AtoA 搭子模式：Top-10 粗筛 + 分身对话 + 用户决策

> Phase 8 的核心交互机制：分身不再自动替用户做决定，而是先粗筛出评分最高的10位候选，逐一与每位候选的分身进行1-3轮对话，然后由用户手动决策每一段对话的去向。

#### 核心流程（三步）

```text
Step 1 — 后台 Top-10 粗筛（无用户交互）
  规则评分（§4.3）取 score 最高的10位候选（排除已blocked/excluded的人）
  → 写入 AtoaSession(candidate_ids=[...], score_snapshot={...})
  → 对10位候选并发执行 Step 2

Step 2 — 分身对话生成（无用户交互，后台完成）
  对每位候选 B：
    [规则预筛] school_only / visibility / 兴趣词最低重合 → 未通过跳过
    [分身对话] _simulate_atoa_conversation(card_a, card_b, max_rounds=3)
      → 分身A（用 card_a 人设）先发言
      → 分身B（用 card_b 人设）回应
      → 最多生成 3 轮（1轮 = A说 + B说）
    写入 AtoaInteraction(outcome="pending_user_decision", is_visible_to_b=False)

Step 3 — 用户逐条决策（用户主导）
  用户在「分身动态」页依次看每段对话，并选择：
    ① 继续聊 → Phase 8B
    ② 打断   → Phase 8C（block + 补位）
    ③ 结交   → Phase 8C（connect + 对方确认）
```

#### Top-10 粗筛候选前提条件

候选用户（对方）必须满足**全部**以下条件，否则不进入 Top-10：

| 条件 | 字段 | 说明 |
|------|------|------|
| 对方分身在线 | `AvatarStatus.is_active = True` | 对方开启了分身 |
| 对方允许自动匹配 | `AvatarStatus.auto_match_enabled = True` | 对方分身愿意参与推荐 |
| 对方名片可见 | `AvatarCard.visibility != "private"` | 对方名片已对外公开 |
| 未被我 blocked | `AtoaInteraction.outcome != "blocked"` for this pair | 我没有打断过对方 |
| 不在本次 Session 排除列表 | `user_b_id not in session.excluded_ids` | 防止补位时重复 |
| 不是自己 | `candidate.id != user_id` | 硬过滤 |
| 尊重 `school_only` | 同上 §4.2 | 同上 |

#### 打分维度（粗筛评分，决定候选排名）

```text
score =
  interest_overlap_score * 0.25
+ intent_match_score     * 0.25
+ context_score          * 0.20
+ social_safety_score    * 0.15
+ freshness_score        * 0.10
+ feedback_score         * 0.05

AtoA 附加分：
  both_have_avatar_card  * 10   # 双方都有 AvatarCard
+ complementary_intent   * 12   # 意图互补
+ boundary_no_conflict   * 8    # 边界不冲突
+ both_school_match      * 5    # 同校
```

#### 互补意图判定表

| 我的意图 | 对方意图 | 附加分 | 说明 |
|----------|----------|--------|------|
| `buddy` | `buddy` | +12 | 双方都想找搭子，最强互补 |
| `help` | `buddy` / `share` | +10 | 求助 vs 愿意帮忙/分享 |
| `share` | `share` | +8 | 双向分享 |
| `dating` | `dating` | +12 | 双向恋爱意向，需同时过风险检查 |
| `study` | `study` | +10 | 学习搭子 |
| `buddy` | `dating` | +4 | 意图不对称，弱互补 |
| 任意 | 对方未填写意图 | 0 | 无法判断，不加分也不减分 |

#### 打断（block）的双向降分机制

用户选择「打断」后，系统对该对的双方互相进行降分处理：

```text
打断发生后：
  A 侧：
    interaction.outcome = "blocked"
    session.excluded_ids.append(B.id)
    对 B 的 feedback_score -= BLOCK_PENALTY（默认 -10）
    Bandit 负向反馈（-5）
  B 侧（对方感知层面）：
    B 的 AvatarMatch / AtoaInteraction 中，若有对应 A→B 记录：
      其 score_snapshot 中 A 的评分降低（模拟「A 不感兴趣了」信号）
    B 的下一次粗筛时，A 不再进入 B 的 Top-10（B 对应候选池中 A 的分数已降至不入选）
    is_visible_to_b 保持 False（B 不知道发生了打断）

补位逻辑：
  从 session.score_snapshot 中，取排名第11、12...位的候选（按原始评分排序）
  过滤掉 session.excluded_ids 中的所有人
  取第一个未排除的候选 → 生成新的分身对话 → 写入新 AtoaInteraction
  session.candidate_ids 追加新候选 ID（可选，用于前端进度展示）
```

#### 结交（connect）的双方确认机制

```text
用户 A 选择「结交」后：
  创建 social.Match(
    user_id        = A,
    target_user_id = B,
    match_type     = "buddy",
    status         = "pending",   ← 等对方确认，不是立即成功
    opening_message = "..."       ← 用户可自定义开场白
  )
  interaction.outcome = "connected"
  interaction.triggered_match_id = Match.id
  interaction.is_visible_to_b = True  ← 对方可以看到这段分身对话

对方 B 收到结交申请后，在搭子申请页手动操作：
  确认 → social.Match.status = "accepted"
         interaction.outcome = "connect_confirmed"
         Bandit 最强正向反馈（+10）
  拒绝 → social.Match.status = "rejected"
         interaction.outcome = "connect_rejected"
         Bandit 负向反馈（-3，弱于打断）
```

### 4.7 搭子模式完整冲浪流程（Phase 8 目标）

> 这是 Phase 8 重构后 `run_avatar_surf_for_user()` 的完整执行序列。

```text
run_avatar_surf_for_user(user_id, trigger)
│
├─ [1] 前置检查（与 Phase 4 相同）
│     quiet_mode / is_active / 时间窗口 / daily_surf_count 上限 / surf_lock_until
│     额外检查：是否有 active AtoaSession 且全部候选都已决策
│       → 全部决策完毕才允许新一轮粗筛
│
├─ [2] 宽召回：生成候选池（§4.2，保留）
│     帖子召回 + 用户召回 + 需求召回 + 互动召回
│     → 候选列表（含帖子型候选 + 用户型候选）
│
├─ [3] 分流
│     ├─ 对方 auto_match_enabled=True  → AtoA 搭子模式队列
│     └─ 对方 auto_match_enabled=False → 兜底规则打分队列
│
├─ [4A] AtoA 搭子模式（§4.6）
│     [粗筛] 规则打分取 Top-10（排除 excluded_ids，排除已有 active interaction 的人）
│     创建 AtoaSession(candidate_ids=Top10, score_snapshot=各候选分数)
│     对每位候选：
│       [规则预筛] → 未通过跳过（不消耗 AI）
│       [分身对话] _simulate_atoa_conversation(card_a, card_b, max_rounds=3)
│       写 AtoaInteraction(outcome="pending_user_decision", session_id=session.id)
│     surf_log.top10_session_id = session.id
│
├─ [4B] 兜底规则打分（§4.3，仅对 auto_match_enabled=False 的候选）
│     _rule_score_user_match / _build_match_for_post
│     → 生成 match_type="post"/"user" 的 AvatarMatch（保留旧逻辑，不受影响）
│
├─ [5] Agent 汇报摘要生成
│     统计本次冲浪：
│       粗筛候选数 / 生成对话数 / 兜底推荐数
│     生成 surf_report 文案（写入 AvatarSurfLog）
│     示例："分身今天为你找到了10位潜在搭子，已生成对话供你查看。"
│
├─ [6] 更新调度状态
│     next_surf_at / last_surf_at / daily_surf_count / Bandit pull
│
└─ [7] 写 AvatarSurfLog（含 scanned_atoa_pairs / top10_session_id）
```

**补位触发（独立于冲浪调度）：**
```text
POST /api/avatar/atoa/{interaction_id}/decide (decision="block")
  → 在事务内完成：
    1. 记录打断 + 降分
    2. 从 session.score_snapshot 取补位候选
    3. 生成新的分身对话（同步或异步）
    4. 写入新 AtoaInteraction
    5. 更新 session.candidate_ids / excluded_ids
```

### 4.5 分身对话边界

允许：

- 两个分身交换公开名片信息
- 生成最多3轮「模拟寒暄」（每轮 = A说一句 + B说一句）
- 续聊时参考历史对话上下文，追加新轮次
- 用户在「分身动态」页查看每段对话，并手动决策

不允许：

- 分身替用户承诺见面
- 分身未经允许发送私聊
- 分身透露日记、聊天、素材原文
- 分身使用敏感信息作为推荐理由
- 单向探针结果对被探查方可见（`is_visible_to_b=False`，除非双向达标）

默认状态：

- 只生成 `AvatarMatch` 和 `AvatarAtoaInteraction`
- 不创建 `Match`
- 不发送 `SocialMessage`
- 不发布评论

用户点击「想认识 / 发起聊天」后，才进入 `social.Match` 流程。

---

## 五、定时任务设计

### 5.1 调度目标

需要解决两个问题：

1. **什么时候冲浪**
   - 不要每次请求都实时重算。
   - 不要所有用户同一时间冲浪。
   - 不要夜间打扰。

2. **冲浪做什么**
   - 刷新推荐
   - 生成评论草稿
   - 更新分身活跃状态
   - 记录 surf log

### 5.2 个性化冲浪频率算法

用户开启自动冲浪后，默认不再使用固定档位，而是使用 `surf_frequency="adaptive"`：

```text
前端上报 App 使用事件
→ 后端按 weekday + hour 聚合使用习惯
→ 识别用户常打开 App 的高峰小时
→ 在高峰前 10-30 分钟预热冲浪
→ 根据样本量、打开次数、活跃时长动态调整每日上限
→ 写回 personalized_surf_plan + next_surf_at
```

输入：

- `open_count`：用户在某小时打开/回到前台次数。
- `active_ms`：用户在某小时累计活跃时长。
- `page_weights`：用户常用页面，如 `plaza`、`diary`、`chat`、`avatar`。
- `last_seen_at`：近期行为权重更高。

第一版评分：

```text
hour_score =
  open_count * 3
+ active_minutes
+ recent_bonus
```

计划生成：

- 取 Top 3-4 个高分小时作为 `preferredHours`。
- 对每个高峰小时生成一个提前预热槽位：如用户常在 `21:00` 打开 App，则 `20:45` 预热。
- 低样本用户使用冷启动计划：午间、傍晚、晚间各一次。
- 活跃用户提高每日推荐上限，低活跃用户降低打扰频率。

示例输出：

```json
{
  "mode": "personalized",
  "confidence": 0.72,
  "preferredHours": [12, 18, 21],
  "surfSlots": [
    {"hour": 11, "minute": 45, "reason": "你通常在 12:00 后使用 App，提前为你预热推荐"},
    {"hour": 17, "minute": 45, "reason": "你通常在 18:00 后使用 App，提前为你预热推荐"},
    {"hour": 20, "minute": 45, "reason": "你通常在 21:00 后使用 App，提前为你预热推荐"}
  ],
  "quietHours": [0, 1, 2, 3, 4, 5, 6, 7],
  "dailyLimit": 5,
  "minIntervalMinutes": 120
}
```

保留手动档位作为兜底：

| 档位 | 含义 | 间隔 | 每日上限 | 单次扫描 |
|------|------|------|----------|----------|
| `adaptive` | 根据用户 App 使用习惯自动计划 | 动态 | 3-8 次 | 动态 |
| `low` | 安静模式 | 6 小时 | 2 次 | 20 帖 / 20 用户 |
| `medium` | 默认 | 2 小时 | 5 次 | 50 帖 / 50 用户 |
| `high` | 活跃找搭子 | 30 分钟 | 12 次 | 80 帖 / 80 用户 |
| `custom` | 自定义 | 用户设置 | 用户设置 | 后端限制最大值 |

硬限制：

- 单用户每天最多生成 10 条 `AvatarMatch` 新推荐。
- 单用户每天最多生成 5 条 `AgentAction` 草稿。
- 自动发布默认 0，除非用户显式开启。
- 全局每分钟处理用户数需要限流，避免 Mock 关闭时打爆 MiniMax。

### 5.3 时间窗口

默认：

```json
{
  "start": "09:00",
  "end": "23:00",
  "timezone": "Asia/Shanghai"
}
```

规则：

- 当前时间不在窗口内：跳过，更新 `next_surf_at` 到下一个窗口开始。
- 用户 `quiet_mode=true`：跳过。
- 用户 `is_active=false`：跳过。
- 用户近期没有任何可匹配信息：跳过。
- 用户今天达到上限：跳过。

### 5.4 调度实现方案

#### 方案 A：进程内轻量调度（推荐第一版）

适合当前 FastAPI + SQLite 小规模项目：

- 使用 `asyncio.create_task()` 在应用启动时拉起后台循环。
- 每 60 秒扫描一次 `AvatarStatus.next_surf_at <= now` 的用户。
- 每批最多处理 N 个用户。
- 每个用户执行 `run_avatar_surf_for_user()`。
- 使用 DB 字段做幂等和频率控制。

优点：

- 实现简单。
- 不引入 Redis/Celery。
- 适合 Demo 和课程项目。

风险：

- 多进程部署会重复调度。
- 服务重启期间不会执行。
- SQLite 并发能力有限。

#### 方案 B：外部脚本 + 系统 cron

新增脚本：

```text
scripts/run_avatar_scheduler.py
```

由 Windows 任务计划程序 / Linux cron 每分钟执行一次。

优点：

- 不依赖 Web 进程生命周期。
- 更容易调试。

风险：

- 部署配置多一步。
- 仍需 DB 幂等锁。

#### 方案 C：Celery / APScheduler / Redis 队列

适合正式生产，但当前阶段不建议优先上。

建议路线：

```text
第一版：方案 A 或 B
后续用户量上来：迁移到 Celery / APScheduler + Redis
```

### 5.5 幂等与并发控制

新增轻量锁字段或使用日志状态：

```python
surf_lock_until = Column(BigInteger, default=0)
```

执行前：

1. 查询 `surf_lock_until < now`
2. 设置 `surf_lock_until = now + 5 * 60 * 1000`
3. 提交
4. 执行冲浪
5. 更新 `last_surf_at / next_surf_at / surf_lock_until=0`

失败时：

- 写 `AvatarSurfLog(status="failed")`
- `next_surf_at` 延后 30 分钟
- 不重复生成已存在的 match/action

---

## 六、接口 TODO

### 6.1 修改 `GET /api/avatar/status`

响应新增：

```json
{
  "surfFrequency": "medium",
  "surfWindow": {"start": "09:00", "end": "23:00", "timezone": "Asia/Shanghai"},
  "nextSurfAt": 1710000000000,
  "lastSurfAt": 1710000000000,
  "dailySurfCount": 2,
  "dailyActionCount": 1,
  "quietMode": false,
  "autoMatchEnabled": true,
  "autoCommentEnabled": false,
  "autoPublishEnabled": false
}
```

### 6.2 修改 `PUT /api/avatar/status`

请求允许更新：

```json
{
  "isActive": true,
  "enabledChannels": ["buddy", "help", "share"],
  "enabledActions": ["browse", "match", "comment"],
  "surfFrequency": "medium",
  "surfWindow": {"start": "09:00", "end": "23:00"},
  "quietMode": false,
  "autoMatchEnabled": true,
  "autoCommentEnabled": false,
  "autoPublishEnabled": false
}
```

校验：

- `autoPublishEnabled=true` 必须要求 `autoCommentEnabled=true`
- 自动发布必须二次确认，第一版可后端禁止
- `surfWindow` 不能超过 16 小时
- `custom` 间隔不能低于 15 分钟

### 6.3 新增 `POST /api/avatar/usage-events`

前端上报 App 使用习惯，用于后台学习用户的私人化冲浪时间。

请求：

```json
{
  "event_type": "app_open",
  "timestamp": 1710000000000,
  "active_ms": 0,
  "page": "plaza"
}
```

事件类型：

- `app_open`
- `app_resume`
- `active_ping`
- `app_close`
- `page_view`

响应：

```json
{
  "recorded": true,
  "personalizedSurfPlan": {
    "mode": "personalized",
    "preferredHours": [12, 18, 21],
    "surfSlots": [{"hour": 20, "minute": 45, "reason": "你通常在 21:00 后使用 App，提前为你预热推荐"}],
    "dailyLimit": 5,
    "minIntervalMinutes": 120
  },
  "nextSurfAt": 1710000000000,
  "recordedAt": 1710000000000
}
```

实现要求：

- 不保存完整行为流水，只聚合到 `avatar_usage_stats`。
- 页面名只保留短标签，如 `plaza`、`diary`、`chat`。
- 每次上报后刷新 `personalized_surf_plan`。
- 当 `autoMatchEnabled=true` 或 `autoCommentEnabled=true` 时，刷新 `nextSurfAt`。

### 6.4 新增 `POST /api/avatar/matches/rebuild`

手动重新生成分身推荐（规则宽召回 + AI 精排）。

```json
{
  "source": "manual",
  "limit": 10
}
```

返回：

```json
{
  "generated": 3,
  "updated": 5,
  "skippedReason": ""
}
```

### 6.5 扩展 `GET /api/avatar/matches`

支持 query：

- `matchType`（新增 `atoa` 枚举值）
- `intentType`
- `minScore`
- `status`
- `isMutual`（`true` / `false`，仅 AtoA 型有意义）

返回中新增：

- `targetUserId`
- `intentType`
- `confidence`
- `riskFlags`
- `suggestedOpening`
- `expiresAt`
- `updatedAt`
- `theirScore`（对方视角打分，仅 `matchType=atoa` 有值）
- `theirReasons`（对方视角理由，仅 `matchType=atoa` 有值）
- `isMutual`（是否双向达标，仅 `matchType=atoa` 有值）
- `peerMatchId`（对方那条记录的 ID，仅 `matchType=atoa` 有值）

### 6.8 新增 `GET /api/avatar/matches/mutual`

专门返回 AtoA 双向达标的推荐列表，用于前端「分身互相看上了」专区展示。

支持 query：

- `intentType`
- `limit`（默认 20）
- `offset`

请求示例：

```
GET /api/avatar/matches/mutual?intentType=buddy&limit=10
```

返回：

```json
{
  "items": [
    {
      "id": "match_xxx",
      "matchType": "atoa",
      "isMutual": true,
      "matchScore": 78,
      "theirScore": 65,
      "targetUserId": "user_yyy",
      "targetDisplayName": "晚风",
      "targetPublicSummary": "备考中，喜欢图书馆自习",
      "targetInterestTags": ["自习", "考研", "轻音乐"],
      "intentType": "buddy",
      "matchReasons": ["你们都在备考，时间偏好相近", "同校且都提到图书馆"],
      "theirReasons": ["TA 的分身觉得你学习氛围稳定，适合做自习搭子"],
      "suggestedOpening": "我也在备考，要不要一起去图书馆自习？",
      "riskFlags": [],
      "createdAt": 1710000000000
    }
  ],
  "total": 3
}
```

> **注意**：此接口只返回 `is_mutual=True` 的记录，过滤掉单方达标的 AtoA 记录。

### 6.6 新增 `POST /api/avatar/matches/{match_id}/start-chat`

用户确认后，才创建真实社交搭子请求：

1. 检查 `AvatarMatch.status != dismissed`
2. 检查目标用户存在
3. 创建 `Match(match_type="buddy", status="pending")`
4. 可选创建首条 `SocialMessage`，但建议第一版只返回开场白，让用户确认发送
5. 更新 `AvatarMatch.status = chatting`

### 6.7 新增 `GET /api/avatar/surf-logs`

用于前端展示和调试：

```json
{
  "items": [
    {
      "trigger": "scheduler",
      "status": "success",
      "scannedPosts": 50,
      "scannedUsers": 20,
      "scannedAtoaPairs": 12,
      "upgradedToMutual": 2,
      "generatedMatches": 2,
      "generatedActions": 1,
      "surfReport": "分身今天探了 12 对候选，其中 2 对双向达标，已为你生成推荐。",
      "startedAt": 1710000000000
    }
  ],
  "total": 12
}
```

### 6.9 新增 `GET /api/avatar/probe-log`（Phase 8 新增）

用户监察分身探针活动的核心接口，对应前端「分身动态」页。

支持 query：

- `outcome`（`mutual` / `one_sided` / `incompatible` / `all`，默认 `all`）
- `limit`（默认 20）
- `offset`

返回：

```json
{
  "items": [
    {
      "id": "interaction_xxx",
      "interactionType": "card_exchange",
      "outcome": "mutual",
      "targetUserId": "user_yyy",
      "targetDisplayName": "晚风",
      "targetPublicSummary": "备考中，喜欢图书馆自习",
      "sharedTopics": ["自习", "考研"],
      "scoreA": 78,
      "scoreB": 65,
      "reasonsA": ["你们都在备考，时间偏好相近", "同校且都提到图书馆"],
      "riskFlags": [],
      "conversation": [
        {"role": "avatar_a", "content": "我在找晚间自习搭子，你通常几点去图书馆？"},
        {"role": "avatar_b", "content": "我一般八点多，偏安静型，你有备考计划吗？"}
      ],
      "triggeredMatchId": "match_zzz",
      "isVisibleToB": true,
      "createdAt": 1710000000000,
      "readableOutcome": "双方分身都觉得你们合适，已为你生成推荐 ✓"
    },
    {
      "id": "interaction_aaa",
      "interactionType": "card_exchange",
      "outcome": "one_sided",
      "targetUserId": "user_bbb",
      "targetDisplayName": "山谷",
      "targetPublicSummary": "喜欢爬山，周末活跃",
      "sharedTopics": ["运动", "户外"],
      "scoreA": 52,
      "scoreB": null,
      "reasonsA": ["你们都提到户外运动", "对方最近在找运动搭子"],
      "riskFlags": [],
      "conversation": [
        {"role": "avatar_a", "content": "我也喜欢户外，你最近有计划爬山吗？"},
        {"role": "avatar_b", "content": "有想法，不过还没确定时间。"}
      ],
      "triggeredMatchId": null,
      "isVisibleToB": false,
      "createdAt": 1710000000000,
      "readableOutcome": "你的分身对 TA 感兴趣，等待对方分身回应中…"
    }
  ],
  "summary": {
    "totalProbed": 12,
    "mutualCount": 2,
    "oneSidedCount": 5,
    "incompatibleCount": 5
  },
  "total": 12
}
```

**字段说明：**

| 字段 | 说明 |
|------|------|
| `outcome=mutual` | 双向达标，`triggeredMatchId` 有值，用户可以直接 start-chat |
| `outcome=one_sided` | 只有我的分身感兴趣，`scoreB=null`（等对方冲浪后补填） |
| `outcome=incompatible` | 双方得分均低，探针认为不合适 |
| `conversation` | 两个分身的实际对话内容，前端可展示为对话气泡，是最直观的匹配依据 |
| `readableOutcome` | 前端可直接展示的自然语言描述 |
| `isVisibleToB` | 对方是否已经能看到这条互动（仅 mutual 时为 true） |

**权限规则：**
- 用户只能看自己作为 `user_a`（initiator）的探针记录
- `outcome=mutual` 时，对方也能在自己的 probe-log 里看到对应记录（`user_a/user_b` 互换）
- `one_sided` 不通知被探查方

---

## 七、服务层 TODO

### 7.1 `avatar/service.py`

新增核心方法：

```python
def collect_avatar_match_inputs(db, user_id) -> dict:
    """收集当前用户允许用于社交匹配的画像、名片、记忆和状态。"""

def collect_candidate_posts(db, user, status, limit=80) -> list[PlazaPost]:
    """召回可匹配广场帖子。"""

def collect_candidate_users(db, user, status, limit=80) -> list[User]:
    """召回可参与分身匹配的用户。"""

def score_match_candidate(my_card, their_card, context) -> dict:
    """规则粗排，返回 score/reasons/risk_flags/intent_type。"""

async def refine_match_with_ai(match_context) -> dict:
    """可选 AI 精排，生成解释和开场白；Mock 模式必须可用。"""

def upsert_avatar_match(db, user_id, candidate, match_data) -> AvatarMatch:
    """创建或更新推荐，避免重复。"""

async def rebuild_avatar_matches(db, user_id, source="scheduler", limit=10) -> dict:
    """重新生成分身推荐并触发 AI 精排。"""

async def run_avatar_surf_for_user(db, user_id, trigger="scheduler") -> dict:
    """执行一次完整冲浪：频率检查、召回、匹配、草稿、日志。"""

def compute_next_surf_at(status, now_ms) -> int:
    """根据频率档位和时间窗口计算下次冲浪时间。"""
```

#### Phase 8 新增方法（AtoA 搭子模式核心）

```python
def _score_all_atoa_candidates(
    db: Session,
    user_id: str,
    candidates: list[User],
) -> list[dict]:
    """
    对召回的所有 AtoA 候选批量规则评分（§4.6 打分维度）。
    返回 [{user: User, score: int, shared_topics: [...], intent_type: str}, ...]
    按 score 降序排列，用于 Top-10 粗筛。
    排除：session.excluded_ids 中的候选、已有 active AtoaInteraction 的候选。
    """

def _build_atoa_session(
    db: Session,
    user_id: str,
    top10_candidates: list[dict],
    surf_log_id: str,
) -> AvatarAtoaSession:
    """
    创建新的 AtoaSession：
      - 若已有 status="active" 的 session 且 candidate_ids 中仍有 pending_user_decision 的 interaction，
        则不新建（返回已有 session）
      - 写入 candidate_ids（Top-10 用户 ID 有序列表）和 score_snapshot（各候选分数）
    """

def _collect_interaction_signals_for_pair(
    db: Session, user_a_id: str, user_b_id: str
) -> dict:
    """
    收集 A 与 B 之间的双向互动信号（评论/点赞/共同帖子）。
    返回 {comment_a_to_b, comment_b_to_a, like_a_to_b, same_post_overlap, has_social_match}。
    用于为 _score_all_atoa_candidates() 提供信号补充分。
    """

async def _simulate_atoa_conversation(
    card_a: AvatarCard,
    card_b: AvatarCard,
    max_rounds: int = 3,
    prior_conversation: list[dict] | None = None,
) -> list[dict]:
    """
    【AtoA 核心】用蓝心大模型模拟两个分身之间最多 max_rounds 轮对话。

    初次调用（prior_conversation=None）：
      1. 用 card_a 的 social_intent + interest_tags + conversation_style 构建「分身A的人设」
      2. 用 card_b 的同上字段构建「分身B的人设」
      3. 分身A先发言（基于自己需求向分身B探路，1-2句话）
      4. 分身B根据自己的人设自然回应（1-2句话）
      5. 重复最多 max_rounds 轮
      返回 [{role: "avatar_a", content: "...", phase: 1}, {role: "avatar_b", content: "...", phase: 1}, ...]

    续聊调用（prior_conversation 非 None）：
      AI 参考历史上下文，从上次停止的地方继续对话，生成 max_rounds 轮新内容
      新轮次的 phase = max(prior_conversation 中的 phase) + 1

    Prompt 约束：
      - 只能使用 AvatarCard 上的公开信息，不涉及日记/聊天/素材原文
      - 语气自然口语化，每轮 1-2 句话
      - 不替用户做承诺（不说"我们下周见面吧"等）

    Mock 模式（MINIMAX_MOCK=true）：
      根据双方 interest_tags 交集生成固定模板对话
      示例：[
        {"role": "avatar_a", "content": "我也在找自习搭子，你一般几点去图书馆？", "phase": 1},
        {"role": "avatar_b", "content": "我通常晚上八点多，偶尔打卡到十一点。", "phase": 1}
      ]
    """

async def _generate_atoa_interaction(
    db: Session,
    session_id: str,
    user_a: User,
    user_b: User,
    score_a: int,
    shared_topics: list[str],
    reasons_a: list[str],
    risk_flags: list[str],
) -> Optional[AvatarAtoaInteraction]:
    """
    规则预筛 → 通过 → 调用 _simulate_atoa_conversation 生成对话 → 写入 AtoaInteraction。

    规则预筛（廉价，过不了不消耗 AI）：
      - school_only / visibility 硬过滤
      - interest_tags 至少1个共同词
      - 意图不完全冲突
      → 未通过：返回 None，不消耗 AI

    写入 AtoaInteraction：
      outcome = "pending_user_decision"
      is_visible_to_b = False（始终，对方不知道）
      session_id = session_id
    """

def _apply_block_penalty(
    db: Session,
    user_a_id: str,
    user_b_id: str,
) -> None:
    """
    打断时双向降分：
      A 侧：在 A 的候选评分中将 B 的分数降低（feedback_score -= BLOCK_PENALTY=10）
      B 侧：在 B 的候选评分中将 A 的分数降低（模拟「A 不感兴趣」信号，使 A 下次不进 B 的 Top-10）
    整个过程对 B 不可见（不写任何 B 能看到的记录）。
    """

def _get_replacement_candidate(
    db: Session,
    session: AvatarAtoaSession,
) -> Optional[User]:
    """
    从 session.score_snapshot 中找排名最高的、
    不在 session.excluded_ids 中的、尚未有 AtoaInteraction 的候选。
    即：取评分快照中第11、12...位中第一个未排除的候选。
    若无候选可用，返回 None（此时 session.status 应置为 completed）。
    """

async def continue_atoa_conversation(
    db: Session,
    user_id: str,
    interaction_id: str,
) -> AvatarAtoaInteraction:
    """
    用户选择「继续聊」后追加对话轮次：
      1. 校验 interaction 存在且 user_a_id == user_id
      2. 前置检查：outcome == "pending_user_decision"
      3. 读取 interaction.conversation 作为 prior_conversation
      4. 调用 _simulate_atoa_conversation(max_rounds=3, prior_conversation=...)
      5. 将新轮次追加到 interaction.conversation
      6. interaction_phase += 1
      7. user_decision = "continue"
      8. outcome 保持 "pending_user_decision"
    """

async def decide_atoa_outcome(
    db: Session,
    user_id: str,
    interaction_id: str,
    decision: str,  # "block" | "connect"
    opening_message: Optional[str] = None,
) -> dict:
    """
    用户手动决策：打断 或 结交。

    decision="block"（打断）：
      - interaction.outcome = "blocked", user_decision = "block", is_visible_to_b = False
      - 调用 _apply_block_penalty(user_a_id, user_b_id)
      - session.excluded_ids.append(user_b_id)
      - 调用 _get_replacement_candidate(session)
        → 若有：生成新 AtoaInteraction，返回 {"replacement": {"interaction_id": "...", ...}}
        → 若无：session.status = "completed"，返回 {"replacement": null}
      - Bandit 负向反馈 -5

    decision="connect"（结交）：
      - 创建 social.Match(status="pending", opening_message=opening_message)
      - interaction.outcome = "connected", user_decision = "connect", is_visible_to_b = True
      - interaction.triggered_match_id = social_match.id
      - 返回 {"social_match_id": "..."}
    """

def get_probe_log(
    db: Session,
    user_id: str,
    outcome: Optional[str] = None,
    session_id: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """
    返回用户可查看的 AtoaInteraction 列表（分身动态页）。
    - 返回 user_a_id=user_id 的记录
    - 附带 targetUser 的名片摘要、shared_topics、readableOutcome 描述文案
    - readableOutcome 示例：
        pending_user_decision → "分身和 TA 聊了3轮，等你决定下一步"
        blocked → "你选择了打断，已为你补入新候选"
        connected → "你已发出结交申请，等对方确认"
        connect_confirmed → "对方确认了，你们成为搭子！"
    """

def generate_surf_report(
    db: Session,
    user_id: str,
    atoa_stats: dict,
    fallback_stats: dict,
) -> str:
    """
    生成本次冲浪的 Agent 汇报摘要文案（写入 AvatarSurfLog.surf_report）。
    示例："分身今天为你找到了10位潜在搭子，已生成对话供你查看。还有3条传统推荐。"
    Mock 模式：返回固定模板文案。
    """
```

### 7.2 `plaza/service.py`

在用户发布帖子后可选触发轻量刷新：

```text
create_post()
→ ingest_plaza_post()
→ maybe_refresh_avatar_card()
→ enqueue_or_mark_avatar_surf_due(trigger="post_publish")
```

注意：

- 不要在发帖接口里同步跑大量 AI。
- 可只把 `next_surf_at` 设置为 `now + 1min`。
- 或仅对当前用户做规则匹配，不调用 AI。

### 7.3 `memory/ingestion.py`

需要保证以下来源能生成用于匹配的结构化信息：

- `plaza_post`
- `plaza_comment`
- `diary`
- `chat_session`
- `material`
- `social_message`

重点抽取：

- `interest`
- `need`
- `habit`
- `boundary`
- `social_intent`
- `recent_state`

---

## 八、算法 TODO 清单

### 8.1 标签标准化

- 建立轻量标签归一化函数。
- 同义词合并：
  - 自习 / 学习 / 图书馆 → `study`
  - 跑步 / 夜跑 / 健身 → `sport`
  - 考研 / 备考 / 复习 → `exam`
  - 失眠 / 情绪低落 / 想聊天 → `emotion_support`
- 标签最多保留 Top 20。

### 8.2 需求时效判断

- 文本包含「今晚 / 明天 / 周末 / 长期」时生成 `expires_at`。
- 无时效词：
  - buddy 默认 14 天
  - help 默认 7 天
  - dating 默认 30 天
  - share 默认 3 天

### 8.3 负反馈学习

用户行为映射：

- `dismiss`：同类推荐降权
- `chat`：同类推荐加权
- `approve_action`：评论/互动类加权
- `reject_action`：同类行动草稿降权
- 长期未点击：轻微降权

第一版可不建复杂模型，先写入 `input_context` 或 `match_reasons` 中，后续再独立表。

### 8.4 风险过滤

硬过滤：

- 自己匹配自己
- 对方 `school_only=true` 且不同校
- 对方未开启分身社交
- 对方名片 `visibility=private`
- 用户已 dismiss
- 内容过期

软风险：

- 敏感话题
- 恋爱/情感类过度主动
- 对方没有足够公开信息
- AI 理由可能泄露隐私

软风险不一定过滤，但需要写入 `risk_flags`，前端可弱化展示或要求二次确认。

---

## 九、安全与隐私要求

### 9.1 必须遵守

- 不把日记、聊天、素材原文放进 `AvatarMatch.match_reasons`。
- 不把私密记忆直接写入 `AvatarCard.public_summary`。
- 不在用户未确认时创建真实私聊。
- 不在用户未开启时自动评论。
- 不在 Mock 关闭时无节制调用 MiniMax。

### 9.2 推荐文案边界

推荐理由应该写：

```text
你们都提到过图书馆自习，时间也比较接近。
```

不要写：

```text
对方昨晚在日记里写自己很孤独，所以适合和你聊天。
```

### 9.3 审计

所有自动行为必须记录：

- 为什么触发
- 看了多少候选
- 生成了什么
- 是否跳过
- 是否失败
- AI 输入中使用了哪些类型的信息，不记录私密原文

---

## 十、Mock 模式要求

`MINIMAX_MOCK=true` 时：

- `refine_match_with_ai()` 返回稳定、可预测的假数据。
- 自动冲浪不会消耗真实 API。
- 测试中可固定：
  - match score
  - reasons
  - suggested opening
  - agent conversation

示例 Mock：

```json
{
  "matchReasons": ["你们有相似的学习目标", "都偏好低压力交流"],
  "suggestedOpening": "我也在找自习搭子，要不要先约一次图书馆？",
  "riskFlags": [],
  "confidence": 0.82
}
```

---

## 十一、测试 TODO

### 11.1 单元测试

新增 `tests/test_avatar_match_rebuild.py`（建议命名，可按仓库惯例调整）：

- 标签归一化
- 需求过期时间计算
- 同校过滤
- `school_only` 过滤
- `visibility=private` 过滤
- `dismiss` 后不再推荐
- 重复候选 upsert 不生成重复记录
- 风险 flags 生成
- `compute_next_surf_at()` 不跨越 quiet window

新增 `tests/test_avatar_atoa.py`（AtoA 专项测试）：

- `_recall_atoa_candidates()` 过滤：对方未开启 `auto_match_enabled` 时不召回
- `_recall_atoa_candidates()` 过滤：对方 `AvatarCard.visibility=private` 时不召回
- `_recall_atoa_candidates()` 过滤：对方已 dismiss 我时不召回
- `_score_atoa_pair()` 对称性：score_AB 和 score_BA 用各自 inputs，不能互换
- `_score_atoa_pair()` 互补意图加分：buddy+buddy 比 buddy+dating 分数更高
- `_score_atoa_pair()` 双方均低于阈值时返回 `None`
- `_score_atoa_pair()` 仅一方达标时返回 `is_mutual=False`（不返回 None）
- `_upsert_atoa_match_pair()` 原子写入：A→B 和 B→A 同时存在，且 `peer_match_id` 互相指向
- `_upsert_atoa_match_pair()` 重复调用时 upsert 不生成新记录
- `_sync_atoa_mutual_flag()` 升级：B 冲浪后分数上升，A→B 和 B→A 的 `is_mutual` 同时变 True
- A dismiss B 后：A→B 状态变 `dismissed`，B→A 的 `is_mutual` 同步变 False
- `get_mutual_matches()` 只返回 `is_mutual=True` 且 status != `dismissed` 的记录

### 11.2 接口测试

覆盖：

- `GET /api/avatar/status` 新字段
- `PUT /api/avatar/status` 更新频率和开关
- `POST /api/avatar/matches/rebuild`
- `GET /api/avatar/matches` 筛选（含 `matchType=atoa` 和 `isMutual=true`）
- `GET /api/avatar/matches/mutual` 只返回互相达标记录
- `POST /api/avatar/matches/{id}/start-chat`
- `GET /api/avatar/surf-logs`

### 11.3 调度测试

覆盖：

- inactive 用户跳过
- quiet mode 跳过
- 时间窗口外跳过
- 达到每日上限跳过
- 到达 `next_surf_at` 时执行
- 执行失败写入 failed log
- Mock 模式不调用真实 API

---

## 十二、实施阶段

### Phase 1：补齐配置与日志

- [x] 扩展 `AvatarStatus` 频率、时间窗、个性化计划、开关字段。
- [x] 新增 `AvatarUsageStat`，按 weekday + hour 聚合用户 App 使用习惯。
- [x] 新增 `AvatarSurfLog`。
- [x] Alembic 迁移。
- [x] 更新 `AvatarStatusOut` / `UpdateStatusRequest`。
- [x] 更新 `GET/PUT /api/avatar/status`。
- [x] 新增 `POST /api/avatar/usage-events`，用于学习用户私人化冲浪时间。
- [x] 新增 `GET /api/avatar/surf-logs`。
- [x] 补测试。

验收：

- 用户可以配置分身是否冲浪、是否安静模式、是否自动匹配/评论。
- 后端能根据 App 使用习惯生成 `personalizedSurfPlan` 和 `nextSurfAt`。
- 后端能记录并查询每次冲浪结果。

### Phase 2：个性化冲浪 — 反馈加权（✅ 已完成 2026-05-03）

> 把用户的历史行为反馈折算成「小时维度奖励分」，叠加进使用习惯基础分，让分身在用户更愿意接受推荐的时段优先冲浪。

- [x] 新增 `_get_feedback_hour_scores(db, user_id, now_ms)`：扫描 7 天内的 `AvatarMatch` 和 `AgentAction`，按反馈发生小时聚合奖惩分。
  - `AvatarMatch.status = 'chatting'` → 该小时 +5（用户主动开聊，信号最强）
  - `AvatarMatch.status = 'dismissed'` → 该小时 -2（用户主动拒绝，轻惩罚）
  - `AgentAction.status = 'published'` → 该小时 +4（用户批准草稿）
  - `AgentAction.status = 'rejected'` → 该小时 -2（用户拒绝草稿）
- [x] 在 `_compute_personalized_surf_plan()` 中将 `feedback_scores × 3` 叠加进 `hour_scores`，同步体现在 `surfSlots` 的排序和描述文案中。
- [x] `personalized_surf_plan` 新增 `feedbackHours` 字段，前端可据此展示「哪些时段奖励最高」。
- [x] 在 `approve_action` / `reject_action` / `start_chat_from_match` 中调用 `update_bandit_feedback()`，触发实时反馈更新。
- [x] 补种子数据：`scripts/seed_avatar_habits.py`，为 10 个真实测试用户注入 `AvatarUsageStat`，开启 `auto_match_enabled=True` + 写入历史 `AvatarSurfLog`。

验收：

- `personalized_surf_plan.feedbackHours` 字段可见。
- 用户 chat 某条推荐后，其发生小时的 `hour_scores` 增加，下次刷新计划时该时段排序更靠前。
- 用户 dismiss 后，该时段排序适度下降。

---

### Phase 3：个性化冲浪 — UCB Bandit 探索与利用（✅ 已完成 2026-05-03）

> 在反馈加权基础上引入 UCB1 算法（Upper Confidence Bound），让分身在「已知高奖励时段」和「尚未充分探索的时段」之间自动权衡。避免陷入局部最优，确保每个合理时段都被探索过至少一次。

**UCB1 公式：**

```
UCB1(k) = mean_reward(k) + C × sqrt( ln(N) / n_k )
```

- `mean_reward(k)` — 该时间槽历史平均奖励
- `N` — 总冲浪次数（跨所有时段）
- `n_k` — 该时间槽已探索次数
- `C = 1.4` — 探索系数（可调）

**实现内容：**

- [x] 新增 `_ucb_score(mean_reward, arm_pulls, total_pulls)` — UCB1 公式，`arm_pulls=0` 时返回 `+inf`（优先探索未知臂）。
- [x] 新增 `_ucb_reorder_slots(surf_slots, bandit_arms, total_pulls)` — 按 UCB 分数对 `surfSlots` 降序排列。
- [x] `_compute_personalized_surf_plan()` 末尾：当 `totalPulls > 0` 时，用 UCB 分数覆盖时段排序。
- [x] `personalized_surf_plan` 新增 `banditArms`、`totalPulls`、`lastRewardAt` 字段持久化臂状态。
- [x] 新增 `update_bandit_feedback(db, user_id, reward)` — 反馈归因到 `last_surf_at` 所在小时，更新该臂的 `total_reward` 和 `mean_reward`。
- [x] 新增 `run_avatar_surf_for_user(db, user_id, trigger)` — 单用户完整冲浪循环：锁检查 → 刷新匹配 → 记录 Bandit pull → 更新 `next_surf_at` → 写 `AvatarSurfLog`。

验收：

- `personalized_surf_plan.banditArms` 中能看到各臂的 `pulls / total_reward / mean_reward`。
- 冷启动时未探索时段得到 `+inf` 优先级，逐步被探索。
- 用户持续在同一时段给正向反馈后，该臂 `mean_reward` 上升，排序稳定靠前。
- 用户持续给负向反馈后，该臂被其他臂超越。

---

### Phase 4：方案B 外部调度器（✅ 已完成 2026-05-03）

> 采用「方案B：外部独立脚本 + 系统定时任务」，将调度与 FastAPI 进程完全解耦，避免单点故障和进程内资源竞争。

- [x] 实现 `compute_next_surf_at_from_plan()`（Phase 1 已完成）。
- [x] 实现 `run_avatar_surf_for_user(db, user_id, trigger)`（Phase 3 完成）。
- [x] 新建 `scripts/run_avatar_scheduler.py`，支持：
  - `--report` — 打印所有用户冲浪状态概览（next_surf_at / confidence / bandit pulls）
  - `--user <username>` — 只调度单个用户（联调专用）
  - `--dry-run` — 只打印计划，不写入数据库
- [x] 幂等锁 `surf_lock_until`：调度前上锁 5 分钟，防止重复触发；超时 10 分钟强制清除。
- [x] 写入 `AvatarSurfLog`（trigger / status / generated_matches / started_at / finished_at）。
- [x] 每日冲浪次数 `daily_surf_count` 累加（每日上限由 `personalized_surf_plan.dailyLimit` 控制）。

配置参考：

```
# Windows Task Scheduler（每 5 分钟执行一次）
任务名称: RijiAvatarScheduler
触发器: 每 5 分钟重复
操作: E:\catalogo\riji\riji-backend\venv\Scripts\python.exe
参数: E:\catalogo\riji\riji-backend\scripts\run_avatar_scheduler.py

# Linux cron
*/5 * * * * /path/to/venv/bin/python /path/to/scripts/run_avatar_scheduler.py >> /var/log/riji-scheduler.log 2>&1
```

验收：

- 分身可以按个性化计划自动冲浪。
- 达到 `dailyLimit` 或未到 `next_surf_at` 时自动跳过。
- 服务重启后不会重复刷爆（幂等锁保护）。
- 每次冲浪有日志可查，支持调试复盘。

---

### Phase 5：分身规则匹配（✅ 已实现 → Phase 8A 后降格为兜底通道）

> **架构变更说明**：Phase 5 的规则打分逻辑在 Phase 8A 后不再是主路径，改为对 `auto_match_enabled=False` 用户的兜底通道。已完成代码无需删除，只需在 `_refresh_matches()` 中增加分流逻辑。

- [x] 扩展 `AvatarMatch`：`target_user_id` / `match_type` / `intent_type` / `risk_flags` 等（见迁移 `b3c5e7f9a1d2`）。
- [x] 帖子通道 + 用户通道双路召回与规则打分（`app/avatar/service.py`）。
- [x] `GET /api/avatar/matches` 返回扩展字段。
- [ ] 按需补全单元测试覆盖边界场景。
- [ ] **Phase 8A 重构**：在召回层增加分流，`auto_match_enabled=True` 的候选转入 AtoA 探针，`False` 的候选保留现有规则打分。

### Phase 6：AI 精排与开场建议（✅ 已实现 → Phase 8B 后改为文案生成器）

> **架构变更说明**：Phase 6 的 AI 精排在 Phase 8B 后不再决定推荐排序，而是专门为 AtoA 互动记录生成自然语言摘要和 `surf_report` 文案，以及为兜底通道推荐生成开场白。

- [x] AI 精排 prompt + Mock 降级（`MINIMAX_MOCK=true`）。
- [x] `suggested_opening` / `ai_refined` / `risk_flags` 落库。
- [x] `POST /api/avatar/matches/rebuild` 触发规则 + 精排流水线（`rebuild_avatar_matches`）。
- [ ] 对高风险推荐的产品层二次确认（前端）待联调。
- [ ] **Phase 8B 重构**：将精排入口扩展，支持为 AtoA `reasons_a/b` 生成自然语言文案，以及生成 `surf_report` 汇报摘要。

### Phase 7：社交闭环（✅ 已实现 → Phase 8C 后扩展支持 AtoA 型）

- [x] 新增 `POST /api/avatar/matches/{match_id}/start-chat`（`start_chat_from_match`）。
- [x] 自动解析目标用户：用户型匹配用 `target_user_id`，帖子型匹配用帖子作者。
- [x] 防重复创建：已有 pending/accepted 的 `social.Match` 时直接复用，返回 `is_duplicate=True`。
- [x] 用户可自定义开场白（`opening_message`），不传则自动使用 Phase 6 AI 建议开场白，写入 `match_report`。
- [x] 成功创建后触发 Bandit 最强正向反馈（+10，高于 chat 操作 +5），闭环反哺推荐质量。
- [x] `AvatarMatch.status` 更新为 `"chatting"`。
- [ ] 前端联调：确认弹窗编辑开场白 → 跳转至搭子详情页（前端）。
- [ ] **Phase 8C**：start-chat 对 `match_type="atoa"` 的记录直接使用 `target_user_id`，不依赖帖子作者。

验收：

- `POST /api/avatar/matches/{matchId}/start-chat` 返回 `socialMatchId` 非空。
- 同一对用户连续调用两次，第二次返回 `isDuplicate=true`，不创建重复申请。
- 用户始终掌握最终社交动作，分身不默认发送任何消息。
- 开场白出现在 `social.Match.match_report` 字段里。

---

### Phase 8A：Top-10 粗筛 + AtoA 初始对话

> **定位**：搭子模式的数据基础 + 后台主路径。后台按评分取最高10位候选，逐一与每位候选的分身进行1-3轮对话，结果展示给用户等待手动决策。

#### 完整流程图

```
[冲浪触发]
    ↓
[宽召回] 帖子 + 用户 + 需求 + 互动（同 Phase 5，保留）
    ↓
[分流]
  对方 auto_match_enabled=True  → [Top-10 粗筛]
  对方 auto_match_enabled=False → [兜底规则打分]（现有逻辑不变）
    ↓
[Top-10 粗筛]
  规则评分 → 取最高10位 → 排除 excluded_ids
  → 写入 AtoaSession(candidate_ids=Top10, score_snapshot=评分快照)
    ↓
[分身对话生成]（对每位候选并发执行）
  规则预筛 → 通过 → _simulate_atoa_conversation(max_rounds=3)
  → 写入 AtoaInteraction(outcome="pending_user_decision", is_visible_to_b=False)
    ↓
[surf_report 生成 + AvatarSurfLog 写入]
用户在「分身动态」查看对话，进入 8B / 8C 决策
```

#### 8A.1 数据迁移

- [ ] Alembic 新迁移：新增 `avatar_atoa_sessions` 表（见 §3.6）。
- [ ] Alembic 新迁移：新增 `avatar_atoa_interactions` 表（见 §3.7）。
- [ ] Alembic 新迁移：`avatar_matches` 表新增 `their_score`、`their_reasons`、`is_mutual`、`peer_match_id`、`target_avatar_card_id` 字段。
- [ ] Alembic 新迁移：`avatar_surf_logs` 表新增 `scanned_atoa_pairs`、`top10_session_id`、`surf_report` 字段。

#### 8A.2 服务层

- [ ] 实现 `_score_all_atoa_candidates(db, user_id, candidates)` — 对召回候选批量规则评分（§4.6打分维度），返回带 score 的有序列表。
- [ ] 实现 `_build_atoa_session(db, user_id, top10_candidates, score_snapshot, surf_log_id)` — 创建 AtoaSession，若已有 active session 则检查是否全部决策完毕后再新建。
- [ ] 实现 `_collect_interaction_signals_for_pair(db, user_a_id, user_b_id)` — 收集双向行为信号（评论/点赞/共同帖子）。
- [ ] 实现 `_simulate_atoa_conversation(card_a, card_b, max_rounds=3, prior_conversation=None)` — **AtoA 核心**：用蓝心大模型模拟两个分身之间对话；
  - 初次调用：`prior_conversation=None`，分身A先发言，分身B回应，最多3轮
  - 续聊调用：传入 `prior_conversation`，AI参考历史上下文续聊
  - 每轮附加 `phase: int` 标记，前端可分组展示
  - Mock 模式：基于 interest_tags 交集生成固定模板
- [ ] 实现 `_write_atoa_interaction(db, session_id, user_a_id, user_b_id, score_a, shared_topics, reasons_a, risk_flags, conversation)` — 写入 AtoaInteraction（`outcome="pending_user_decision"`，`is_visible_to_b=False`）。
- [ ] 实现 `_apply_block_penalty(db, user_a_id, user_b_id)` — 打断时双向降分：A侧对B的 feedback_score -= 10，B侧下次粗筛时A评分对应降低（写入 AvatarMatch 或独立降分记录）。
- [ ] 实现 `_get_replacement_candidate(db, session)` — 从 `session.score_snapshot` 取第11+位候选（排除 `excluded_ids`），返回补位候选 User 或 None。
- [ ] **重构 `_refresh_matches()`** / **`run_avatar_surf_for_user()`**：
  ```
  召回 → 分流
    → AtoA 通道：_score_all_atoa_candidates → Top-10 → _build_atoa_session
                  → 对每位候选：规则预筛 + _simulate_atoa_conversation + _write_atoa_interaction
    → 兜底通道：_rule_score_user_match / _build_match_for_post（保留不变）
  ```
- [ ] 冷启动守卫：系统中 `auto_match_enabled=True` 用户数 < 3 时，AtoA 通道静默跳过，使用兜底通道。
- [ ] 实现 `generate_surf_report(db, user_id, atoa_stats, fallback_stats)` — 生成汇报文案。
  - 示例："分身今天为你找到了10位潜在搭子，已生成对话供你查看，还有3条传统推荐。"

#### 8A.3 接口层

- [ ] 新增 `GET /api/avatar/probe-log` — 用户监察自己作为 `user_a_id` 的所有 AtoaInteraction；
  - 支持 `?outcome=pending_user_decision&session_id=xxx&limit=20&offset=0`
  - 返回：`conversation`（所有轮次）、`interaction_phase`、`score_a`、`shared_topics`、`reasons_a`、`risk_flags`、`readableOutcome` 文案
- [ ] 新增 `GET /api/avatar/atoa/sessions` — 返回用户当前 active session 信息（候选进度：10位中几位已决策）。

#### 8A.4 测试

- [ ] `_score_all_atoa_candidates()` 对 `auto_match_enabled=False` 的候选不返回。
- [ ] `_build_atoa_session()` — 已有 active session 且未全部决策时不新建。
- [ ] `_write_atoa_interaction()` — `outcome` 初始值为 `pending_user_decision`，`is_visible_to_b=False`。
- [ ] `_get_replacement_candidate()` — 不返回 `excluded_ids` 中的候选。
- [ ] 兜底通道在 `auto_match_enabled=False` 候选上仍正常运作，不受 AtoA 影响。
- [ ] `GET /api/avatar/probe-log` 只返回 `user_a_id=current_user` 的记录。

验收：

- 冲浪后 `AtoaSession` 表有记录，`candidate_ids` 包含10位候选 ID（不足10位时按实际数量）。
- 每位候选对应一条 `AtoaInteraction(outcome="pending_user_decision")`，`conversation` 非空（≥1轮）。
- `AvatarSurfLog` 中 `scanned_atoa_pairs` 有值，`surf_report` 文案写入。
- 兜底通道推荐（`match_type="post"/"user"`）在 `auto_match_enabled=False` 候选上正常生成，不受影响。

---

### Phase 8B：用户决策 — 继续聊（追加对话轮次）

> **定位**：用户查看分身初次对话后，选择「继续聊」触发分身再进行1-3轮对话，返回决策点。可循环多次。

#### 完整决策循环图

```
[8A] 分身初次对话 (≤3轮)
          ↓
    outcome = pending_user_decision
          ↓
    ┌─────────────────────────────────────────────────────┐
    │ 用户手动决策（在「分身动态」页）                         │
    └──┬────────────────────┬────────────────────┬────────┘
       │                    │                    │
  [继续聊 - 8B]         [打断 - 8C]          [结交 - 8C]
  分身续聊(≤3轮)       双向降分+补位        发申请+对方确认
  回到决策点(可循环)
```

#### 8B.1 接口层

- [ ] **新增** `POST /api/avatar/atoa/{interaction_id}/continue`
  - 权限：`user_a_id == current_user.id`，否则 403
  - 前置条件：`outcome == "pending_user_decision"`（blocked/connected 时返回业务错误）
  - 逻辑：调用 `continue_atoa_conversation(db, user_id, interaction_id)`
  - 返回：更新后的 `AtoaInteraction`（含新增对话轮次，`interaction_phase` 已+1）
- [ ] 更新 `GET /api/avatar/surf-logs` 响应字段（`scannedAtoaPairs` / `top10SessionId` / `surfReport`）

#### 8B.2 服务层

- [ ] 实现 `continue_atoa_conversation(db, user_id, interaction_id)`:
  1. 校验 interaction 存在且 `user_a_id == user_id`
  2. 前置检查：`outcome == "pending_user_decision"`
  3. 读取当前 `interaction.conversation` 作为 `prior_conversation`
  4. 以续聊模式调用 `_simulate_atoa_conversation(card_a, card_b, max_rounds=3, prior_conversation=prior_conversation)`
  5. 将新生成的 ≤3 轮对话（带 `phase=interaction_phase+1` 标记）追加到 `interaction.conversation`
  6. `interaction.interaction_phase += 1`
  7. `interaction.outcome = "pending_user_decision"`（保持等待用户决策）
  8. `interaction.user_decision = "continue"`

#### 8B.3 测试

- [ ] 测试 `continue`：`conversation` 长度增加，`interaction_phase` +1，outcome 仍为 `pending_user_decision`。
- [ ] 测试新追加轮次的 `phase` 标记比前一轮 +1（前端分组用）。
- [ ] 测试 `user_b` 调用 → 403。
- [ ] 测试 `outcome=blocked` 时调用 → 返回业务错误。
- [ ] 测试 `outcome=connected` 时调用 → 返回业务错误。
- [ ] 测试连续续聊3次不报错，每次正确追加。

验收：

- 用户点「继续聊」后，`probe-log` 里对应记录的 `conversation` 追加了新轮次。
- `interaction_phase` 正确累加，前端可据此按 phase 分组展示对话。
- 连续续聊多次不出错，每次新追加 ≤3 轮。

---

### Phase 8C：用户决策 — 打断（双向降分+补位） / 结交（发申请+对方确认）

> **定位**：用户在任意决策点做出最终结论。打断会触发双向降分并自动补入新候选；结交会向对方发出搭子申请，需对方手动确认才完成社交闭环。

#### 8C.1 接口层

- [ ] **新增** `POST /api/avatar/atoa/{interaction_id}/decide`
  - Body: `{"decision": "block" | "connect", "opening_message": "...（connect 时可选）"}`
  - 权限：`user_a_id == current_user.id`，否则 403
  - 前置条件：`outcome not in ["blocked", "connected", "connect_confirmed", "connect_rejected"]`（已终态不允许重复决策）
  - **`block`（打断）**：
    - `interaction.outcome = "blocked"`，`interaction.is_visible_to_b = False`
    - 调用 `_apply_block_penalty(db, user_a_id, user_b_id)` — 双向降分
    - 将 `user_b_id` 追加至 `session.excluded_ids`
    - 调用 `_get_replacement_candidate(db, session)` — 取补位候选（排除前10人+所有 excluded_ids）
    - 若补位候选存在：生成新 AtoaInteraction（`outcome="pending_user_decision"`）并追加到 session
    - Bandit 负向反馈（-5）
    - 返回：`{"outcome": "blocked", "replacement": {"interaction_id": "...", "target_user_id": "..."} | null}`
  - **`connect`（结交）**：
    - 创建 `social.Match(status="pending")` — 发出搭子申请，等对方确认
    - `interaction.outcome = "connected"`，`interaction.is_visible_to_b = True`
    - `interaction.triggered_match_id = social_match.id`
    - 返回：`{"outcome": "connected", "social_match_id": "..."}`

- [ ] **新增** `POST /api/social/matches/{match_id}/confirm-buddy`（对方确认/拒绝接口，对方使用）
  - Body: `{"action": "accept" | "reject"}`
  - 权限：`target_user_id == current_user.id`
  - `accept` → `social.Match.status = "accepted"`，`interaction.outcome = "connect_confirmed"`，Bandit +10
  - `reject` → `social.Match.status = "rejected"`，`interaction.outcome = "connect_rejected"`，Bandit -3

#### 8C.2 服务层

- [ ] 实现 `decide_atoa_outcome(db, user_id, interaction_id, decision, opening_message)`:
  1. 校验 interaction 存在且 `user_a_id == user_id`
  2. 前置检查：outcome 不在终态列表中
  3. 若 `decision == "block"`:
     - 调用 `_apply_block_penalty(db, user_id, interaction.user_b_id)`
     - `interaction.outcome = "blocked"` / `user_decision = "block"` / `is_visible_to_b = False`
     - 更新 session：`excluded_ids.append(user_b_id)`
     - 补位：`_get_replacement_candidate(db, session)` → 若有，生成新分身对话
  4. 若 `decision == "connect"`:
     - 创建 `social.Match(user_id=A, target_user_id=B, status="pending", opening_message=opening_message)`
     - `interaction.outcome = "connected"` / `user_decision = "connect"` / `is_visible_to_b = True`
     - `interaction.triggered_match_id = social_match.id`

- [ ] 实现 `confirm_buddy_request(db, current_user_id, match_id, action)`:
  1. 校验 match 存在且 `target_user_id == current_user_id`
  2. 前置检查：`match.status == "pending"`
  3. 若 `action == "accept"` → `match.status = "accepted"`，同步更新 AtoaInteraction.outcome → `"connect_confirmed"`，Bandit +10
  4. 若 `action == "reject"` → `match.status = "rejected"`，`interaction.outcome = "connect_rejected"`，Bandit -3

#### 8C.3 服务层方法更新

- [ ] 更新 `_apply_block_penalty(db, user_a_id, user_b_id)`:
  - A 侧：在 `AvatarMatch(user_id=A, target_user_id=B)` 中降低 `match_score`（或写入 `feedback_score -= 10`）
  - B 侧：在 B 的候选池评分中将 A 的评分降低（模拟「B 对 A 也不感兴趣」信号），使 A 下次不进入 B 的 Top-10
  - 注意：整个过程对 B **不可见**（B 不知道被打断）

#### 8C.4 测试

- [ ] `decide=block`：
  - interaction.outcome 变 `blocked`，is_visible_to_b 保持 False
  - session.excluded_ids 包含 user_b_id
  - A 对 B 的评分降低（feedback_score 变化）
  - 返回 replacement 候选（若有），新 AtoaInteraction 出现在 probe-log
- [ ] `decide=block`，补位候选不存在（所有候选已排除）：返回 `"replacement": null`，session.status 变 `completed`。
- [ ] `decide=connect`：产生 social_match_id，interaction.is_visible_to_b=True，social.Match.status="pending"。
- [ ] 对方 `accept`：social.Match.status="accepted"，interaction.outcome="connect_confirmed"。
- [ ] 对方 `reject`：social.Match.status="rejected"，interaction.outcome="connect_rejected"。
- [ ] 重复 decide（已 blocked/connected）→ 返回业务错误。
- [ ] 无权限用户（user_b）调用 decide → 403。
- [ ] 非申请接收方调用 confirm → 403。

验收：

- `decide=block` 后，interaction.outcome=blocked，B 侧评分降低，session.excluded_ids 更新，自动补位（若有候选）。
- `decide=connect` 后，social_match_id 非空，social.Match.status="pending"，对方可在申请列表看到。
- 对方确认后，`interaction.outcome="connect_confirmed"`，可在搭子列表看到。
- 打断操作对 B 完全不可见（is_visible_to_b=False 始终保持）。

---

## 十三、验收标准

**基础验收（Phase 1-7 已交付）：**

- [x] 用户不开启分身社交时，不生成分身推荐。
- [ ] 用户只开启推荐时，只生成 `AvatarMatch`，不评论、不私聊。
- [ ] 用户开启评论草稿时，只生成 `AgentAction(status="draft")`。
- [ ] 自动发布默认关闭。
- [ ] 每条推荐都有 `matchScore`、`matchReasons`、`intentType`。
- [ ] 匹配不会泄露日记/聊天/素材原文。
- [ ] 支持 Mock 模式。
- [ ] 有频率限制、每日上限、时间窗口。
- [ ] 有 surf logs 可查。
- [ ] 测试覆盖核心算法、接口和调度跳过逻辑。

**Phase 8A：Top-10 粗筛 + AtoA 初始对话：**

- [ ] AtoA 通道只在对方 `auto_match_enabled=True` 且 `AvatarCard.visibility != private` 时运行。
- [ ] 每次冲浪后 `AtoaSession` 表有记录，`candidate_ids` 包含最多10位候选 ID（按评分降序）。
- [ ] 每位候选对应一条 `AtoaInteraction(outcome="pending_user_decision")`，`conversation` 非空（≥1轮），`is_visible_to_b=False`。
- [ ] `AvatarSurfLog` 中有 `scanned_atoa_pairs` 和 `surf_report` 字段，值正确。
- [ ] 兜底通道（规则打分）在 `auto_match_enabled=False` 候选上仍正常运作，现有 `post`/`user` 推荐不受影响。
- [ ] `GET /api/avatar/probe-log` 返回当前用户的所有 AtoaInteraction（含 conversation、shared_topics、reasons_a）。
- [ ] 已有 active session 且未全部决策完毕时，不重复新建 session（幂等保护）。

**Phase 8B：用户继续聊：**

- [ ] `POST /api/avatar/atoa/{id}/continue` 成功追加 ≤3 轮新对话，`interaction_phase` +1，outcome 保持 `pending_user_decision`。
- [ ] 新追加轮次的 `phase` 标记比前一轮 +1。
- [ ] 续聊后 `conversation` 长度增加，新内容连贯。
- [ ] `user_b` 调用 continue → 403。
- [ ] `outcome=blocked` 或 `outcome=connected` 时调用 continue → 返回业务错误。

**Phase 8C：打断（双向降分+补位） / 结交（发申请+对方确认）：**

- [ ] `decide=block`：
  - interaction.outcome=blocked，is_visible_to_b 保持 False（B 不知道被打断）
  - session.excluded_ids 包含被打断的 user_b_id
  - A 对 B 的评分降低，B 下次粗筛时 A 不再进入 Top-10
  - 自动补位：返回 `replacement` 非 null（若还有候选）；无候选时返回 null，session.status=completed
- [ ] `decide=connect`：
  - 创建 social.Match(status="pending")，返回 social_match_id 非空
  - interaction.outcome=connected，is_visible_to_b=True（对方可查看分身对话）
- [ ] 对方 `accept`：social.Match.status="accepted"，interaction.outcome="connect_confirmed"。
- [ ] 对方 `reject`：social.Match.status="rejected"，interaction.outcome="connect_rejected"。
- [ ] 重复 decide（已为终态）→ 返回业务错误。
- [ ] 无权限用户（user_b）调用 decide → 403。
- [ ] 非申请接收方调用 confirm → 403。

---

## 十四、风险与后续

### 14.1 技术风险

- SQLite + 后台调度并发能力有限。
- 多进程部署会导致重复任务。
- AI 精排成本不可控。
- 多 head migration 需要后续整理。

### 14.2 产品风险

- 用户可能不希望日记内容参与社交。
- 分身主动评论容易让用户感到越界。
- 恋爱/情感类匹配需要更严格边界。
- 推荐理由如果写得太具体，会让用户误以为隐私被暴露。

### 14.3 后续增强

- 引入向量检索做相似兴趣召回。
- 引入 Redis/Celery 做正式调度。
- 加入拉黑/屏蔽/举报闭环。
- 将用户反馈训练成更个性化的排序权重。
- 增加「分身今日报告」：浏览了什么、跳过了什么、推荐了什么。
