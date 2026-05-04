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
>
> **已注入测试数据：** 10 个真实测试用户（2026-04-23 ~ 2026-05-03，11 天完整行为数据）
> 运行 `python scripts/seed_realistic_may_2026.py` 重置，再运行 `python scripts/seed_avatar_habits.py` 补充使用习惯数据。

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

Task-G 要把这些能力串成一个持续运行的闭环：

```text
用户发布/记录内容
→ 记忆系统抽取兴趣、需求、边界、近期状态
→ 更新分身侧写和对外名片
→ 分身按设定频率冲浪广场/社交内容
→ 分身匹配候选用户或帖子
→ 生成匹配解释、开场建议、评论草稿或搭子推荐
→ 用户审批/忽略/发起聊天
→ 反馈继续反哺匹配排序
```

核心原则：

- **用户授权优先**：分身不能在未开启的情况下自动发布、私聊或暴露隐私。
- **公开信息匹配**：分身侧只使用用户允许进入分身名片的摘要、标签、社交意图和边界，不直接泄露日记/聊天原文。
- **低打扰**：默认生成推荐和草稿，不默认自动发布。
- **可解释**：每条推荐必须能说明为什么匹配、匹配的是哪类需求、风险点是什么。
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
# 匹配时使用的对方分身名片

match_type = Column(String, default="post")
# post / user / need / comment_thread

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

### 4.2 候选召回

先不要一上来全量 AI 评分，先做可解释的召回：

1. **帖子召回**
   - 最近 7 天广场帖子
   - 频道在 `enabled_channels`
   - 排除自己发的帖子
   - 尊重 `school_only`
   - 尊重 `allow_agent_reply`

2. **用户召回**
   - 有公开/可匹配 `AvatarCard`
   - 近 14 天有广场、评论、日记转公开意图或社交行为
   - 未被拉黑、未被 dismiss

3. **需求召回**
   - 从 `MemoryFact` 或 `AvatarMemory` 中找 `need`
   - `match_status = searching`
   - 未过期
   - `need_type` 相同或互补

4. **互动召回**
   - 对方评论过相似帖子
   - 双方都参与过同一话题
   - 对方曾点赞/评论过用户帖子

### 4.3 粗排评分

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

- `interest_overlap_score`
  - 标签重合
  - 同义词/近义词归一化
  - 近期兴趣权重更高

- `intent_match_score`
  - buddy 对 buddy：高
  - help 对 capable/helper：高
  - dating 需更严格边界：中高但需风险检查
  - share 对同兴趣：中

- `context_score`
  - 同校 +15
  - 同地点/同活动 +10
  - 时间窗口匹配 +10
  - `school_only` 不匹配则直接过滤

- `social_safety_score`
  - 边界不冲突
  - 没有敏感话题冲突
  - 没有过高打扰风险
  - 未超过对方分身响应频率

- `freshness_score`
  - 近 24 小时内容最高
  - 超过 7 天逐步降权
  - 过期需求直接过滤

- `feedback_score`
  - 用户曾聊天/批准类似推荐：加分
  - 用户曾 dismiss 类似推荐：扣分

### 4.4 精排与解释生成

粗排后取 Top 20，再调用 AI 或规则模板生成：

- `match_reasons`
- `agent_conversation`
- `risk_flags`
- `suggested_opening`
- `recommended_action`

示例：

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

### 4.5 分身对话边界

允许：

- 两个分身交换公开名片信息
- 生成 1-2 轮「模拟寒暄」
- 给用户看推荐理由和开场白

不允许：

- 分身替用户承诺见面
- 分身未经允许发送私聊
- 分身透露日记、聊天、素材原文
- 分身使用敏感信息作为推荐理由

默认状态：

- 只生成 `AvatarMatch`
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

- `matchType`
- `intentType`
- `minScore`
- `status`

返回中新增：

- `targetUserId`
- `intentType`
- `confidence`
- `riskFlags`
- `suggestedOpening`
- `expiresAt`
- `updatedAt`

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
      "generatedMatches": 2,
      "generatedActions": 1,
      "startedAt": 1710000000000
    }
  ],
  "total": 12
}
```

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

### 11.2 接口测试

覆盖：

- `GET /api/avatar/status` 新字段
- `PUT /api/avatar/status` 更新频率和开关
- `POST /api/avatar/matches/rebuild`
- `GET /api/avatar/matches` 筛选
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
- [x] 在 `match_action` / `approve_action` / `reject_action` 中调用 `update_bandit_feedback()`，触发实时反馈更新。
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

### Phase 5：分身规则匹配（✅ 已实现）

- [x] 扩展 `AvatarMatch`：`target_user_id` / `match_type` / `intent_type` / `risk_flags` 等（见迁移 `b3c5e7f9a1d2`）。
- [x] 帖子通道 + 用户通道双路召回与规则打分（`app/avatar/service.py`）。
- [x] `GET /api/avatar/matches` 返回扩展字段。
- [ ] 按需补全单元测试覆盖边界场景。

### Phase 6：AI 精排与开场建议（✅ 已实现）

- [x] AI 精排 prompt + Mock 降级（`MINIMAX_MOCK=true`）。
- [x] `suggested_opening` / `ai_refined` / `risk_flags` 落库。
- [x] `POST /api/avatar/matches/rebuild` 触发规则 + 精排流水线（`rebuild_avatar_matches`）。
- [ ] 对高风险推荐的产品层二次确认（前端）待联调。

### Phase 7：社交闭环（✅ 已实现）

- [x] 新增 `POST /api/avatar/matches/{match_id}/start-chat`（`start_chat_from_match`）。
- [x] 自动解析目标用户：用户型匹配用 `target_user_id`，帖子型匹配用帖子作者。
- [x] 防重复创建：已有 pending/accepted 的 `social.Match` 时直接复用，返回 `is_duplicate=True`。
- [x] 用户可自定义开场白（`opening_message`），不传则自动使用 Phase 6 AI 建议开场白，写入 `match_report`。
- [x] 成功创建后触发 Bandit 最强正向反馈（+10，高于 chat 操作 +5），闭环反哺推荐质量。
- [x] `AvatarMatch.status` 更新为 `"chatting"`。
- [ ] 前端联调：确认弹窗编辑开场白 → 跳转至搭子详情页（前端）。

验收：

- `POST /api/avatar/matches/{matchId}/start-chat` 返回 `socialMatchId` 非空。
- 同一对用户连续调用两次，第二次返回 `isDuplicate=true`，不创建重复申请。
- 用户始终掌握最终社交动作，分身不默认发送任何消息。
- 开场白出现在 `social.Match.match_report` 字段里。

---

## 十三、验收标准

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
