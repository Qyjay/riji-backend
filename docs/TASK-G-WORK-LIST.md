# TASK-G 工作清单与联调指南

> **主规格文档：** [TASK-G-AVATAR-MATCHING-SCHEDULER.md](./TASK-G-AVATAR-MATCHING-SCHEDULER.md)  
> **种子数据：** [REALISTIC_USER_DATA_2026_MAY.md](./REALISTIC_USER_DATA_2026_MAY.md)  
> **接口契约：** 仓库根目录 [API-SPEC.md](../API-SPEC.md) §11.7.4（Phase 8）

本文档是 TASK-G 的**可执行清单**与 **Phase 1～8 整体联调步骤**；与主文档 §十二实施阶段对齐，并标注与主文档差异（实现已收敛或接口名不同处）。

---

## 一、阶段总览

| 阶段 | 内容 | 清单状态 |
|------|------|----------|
| Phase 1 | 分身状态扩展、`AvatarUsageStat`、`AvatarSurfLog`、`usage-events`、`surf-logs` | ✅ |
| Phase 2 | 反馈加权 → `personalizedSurfPlan.feedbackHours` | ✅ |
| Phase 3 | UCB Bandit、`run_avatar_surf_for_user`、Bandit 反馈 | ✅ |
| Phase 4 | `scripts/run_avatar_scheduler.py` 外部调度 + `POST /avatar/surf/trigger` Swagger 触发 | ✅ |
| Phase 8A | Top-10 AtoA 会话、探针对话、`probe-log` / `atoa/sessions` / `mutual-matches`、SurfLog AtoA 字段 | ✅ |
| Phase 8B | `POST /avatar/atoa/{id}/continue` | ✅ |
| Phase 8C | `POST /avatar/atoa/{id}/decide`；对方响应使用 **`POST /social/buddy/{requestId}/respond`**（非主文档草案路径 `confirm-buddy`） | ✅（接口与草案名不同） |

---

## 二、分阶段工作清单（对照 §十二）

### Phase 1

- [x] `AvatarStatus`：频率、时间窗、`personalized_surf_plan`、`next_surf_at`、`quiet_mode`、`auto_match_enabled` 等
- [x] `avatar_usage_stats` + `POST /avatar/usage-events`
- [x] `avatar_surf_logs` + `GET /avatar/surf-logs`（含 Phase 8A 扩展字段，见 API-SPEC）
- [x] `GET/PUT /avatar/status`

### Phase 2

- [x] `_get_feedback_hour_scores` + 叠加进 `_compute_personalized_surf_plan`
- [x] `approve_action` / `reject_action` / AtoA `decide=connect` → `update_bandit_feedback`（或历史匹配状态参与 `_get_feedback_hour_scores`）
- [x] `scripts/seed_avatar_habits.py` 注入使用习惯（可选，与 `seed_realistic_may_2026` 配合）

### Phase 3

- [x] UCB 重排 `surfSlots`、`banditArms`、`totalPulls`
- [x] `run_avatar_surf_for_user` 内 Bandit pull

### Phase 4

- [x] `scripts/run_avatar_scheduler.py`：`--user`、`--dry-run`、`--report`
- [x] `surf_lock_until` 幂等锁

### Phase 8A

- [x] 表：`avatar_atoa_sessions`、`avatar_atoa_interactions`；`avatar_matches` / `avatar_surf_logs` 扩展字段（Alembic）
- [x] `_recall_atoa_candidates`、`_score_all_atoa_candidates`、`_build_atoa_session`、`_simulate_atoa_conversation`、`_write_atoa_interaction`
- [x] `run_avatar_surf_for_user` → `_refresh_matches_async` 内 AtoA 主路径 + 兜底 post/user
- [x] `GET /avatar/probe-log`、`GET /avatar/atoa/sessions`、`GET /avatar/mutual-matches`
- [x] 冷启动：全库除自己外 `auto_match_enabled=True` 的用户数 < 阈值时跳过 AtoA（见 `service._ATOA_COLD_START_MIN_USERS`）
- [ ] 种子脚本已支持 `avatar_cards.visibility=public` 与 `auto_match_enabled`（`seed_realistic_may_2026.py`）；联调前务必重跑种子

### Phase 8B

- [x] `POST /avatar/atoa/{interactionId}/continue`
- [ ] 对话 JSON 内 `phase` 字段与主文档「每组带 phase」——以实现为准（续聊追加轮次；前端可按条数或后续增强 phase）

### Phase 8C

- [x] `POST /avatar/atoa/{interactionId}/decide`（`block` | `connect`）
- [x] `connect` → `decide_atoa_outcome` 内直接创建 `social.Match`；`triggered_match_id` 存 **`social.Match.id`**
- [x] 接收方 **`POST /social/buddy/{requestId}/respond`** → `respond_buddy` 内同步 `AtoaInteraction.outcome` 为 `connect_confirmed` / `connect_rejected`
- [ ] 主文档中的 **replacement 补位**、**`_apply_block_penalty` 全量双向降分**、**独立 `confirm-buddy` 路由**——当前实现为简化版（`block` 同步 dismiss atoa match、无 replacement 载荷）；后续可对齐 TASK-G §8C 全量行为

### 自动化测试

- [x] `tests/test_avatar_atoa.py`（AtoA 服务与部分路由）
- [ ] 调度与端到端：按需 `pytest tests/ -k avatar` 或 CI 全量

---

## 三、Phase 1～8 整体联调步骤

**环境：** 仓库根目录；`MINIMAX_MOCK=false`、`LLM_PROVIDER=vivo` 且配置有效 Key 时走真实蓝心；Mock 联调则 `MINIMAX_MOCK=true`。

> 下表路径均相对于 **`/api`**（例如 `GET /avatar/status` 即 `GET /api/avatar/status`）。所有请求带 `Authorization: Bearer <token>`，token 由 `POST /api/auth/login` 获取后填入 Swagger 右上角 **Authorize**。

---

### 0. 准备数据与库

```powershell
# Windows
cd e:\catalogo\riji\riji-backend
venv\Scripts\python.exe -m alembic upgrade head
venv\Scripts\python.exe scripts/seed_realistic_may_2026.py
venv\Scripts\python.exe scripts/seed_avatar_habits.py   # 可选：usage_stats + 个性化计划
venv\Scripts\uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Swagger：`http://127.0.0.1:8000/docs`

**登录获取 token：**

| 步骤 | 方法 | 路径 | 要点 | 解释 |
|------|------|------|------|------|
| 0.1 | POST | `/auth/login` | Body：`{"username":"xu_yining","password":"password123"}` | 拿到响应里的 `token`，复制后在 Swagger 右上角 **Authorize** 填 `Bearer <token>`，否则后续接口都会 401。 |

---

### Phase 1（分身状态初始化）

> 目的：确认分身已开启、能采集使用习惯，让冲浪计划进入 personalized 模式。

| 步骤 | 方法 | 路径 | 要点 | 解释 |
|------|------|------|------|------|
| 1 | GET | `/avatar/status` | 应有 `surfFrequency`、`nextSurfAt`、`personalizedSurfPlan`、`autoMatchEnabled` 等 | 查看分身初始状态，重点确认 `autoMatchEnabled=true`。如果是 false，后续 surf/trigger 会被跳过（分身根本不出动）。 |
| 2 | PUT | `/avatar/status` | Body：`{"isActive":true,"autoMatchEnabled":true,"autoCommentEnabled":true,"quietMode":false}` | 显式打开分身、允许自动匹配、关闭静默模式。如果上一步发现 autoMatchEnabled 已经是 true 可跳过。 |
| 3 | POST | `/avatar/usage-events` | Body：`{"event_type":"app_open","timestamp":1746350400000,"active_ms":0,"page":"plaza"}` | 上报「我打开了 App」事件。后端按 weekday×hour 聚合到 `AvatarUsageStat`，作为 Bandit 学习「该用户什么时段最活跃」的原料。可以再发一条 `active_ping`（带 `active_ms:60000`）模拟心跳。 |
| 4 | GET | `/avatar/status` | 检查 `personalizedSurfPlan.mode` | 上报几条 usage-events 后，`mode` 应从 `cold_start` 变为 `personalized`，`preferredHours` 与上报时段对应。代表 Phase 1 数据采集生效。 |
| 5 | GET | `/avatar/surf-logs` | `total=0` | 此时还没冲浪，日志为空属于正常。冲浪触发后再回来看。 |

---

### Phase 2 + 3（反馈与 Bandit 验收）

> 目的：观察 Bandit 基线，等 Phase 8C 决策后回来对比，确认反馈闭环。Phase 2/3 真正生效需要先做 Phase 4 触发冲浪。

| 步骤 | 方法 | 路径 | 要点 | 解释 |
|------|------|------|------|------|
| 1 | GET | `/avatar/status` | 记录 `personalizedSurfPlan.banditArms` 和 `feedbackHours` 当前值 | **基线快照**。Phase 4 冲浪触发后 `totalPulls` 会 +1，但具体小时的 `totalReward` 还没变（因为还没决策）。把这一刻的数值记下来，等 Phase 8C `decide` 后再来对比。 |
| 2 | GET | `/avatar/probe-log` | 取一条 AtoA 互动 `id` | Phase 8B/8C 测试用。复制其中一条 `outcome=pending_user_decision` 的 `id` 备用。 |

> 真正的反馈写入发生在 Phase 8C 的 `decide` 接口里：`connect=+10`、`block=-3`，会按"上次冲浪发生在几点"归到对应小时的 Bandit 臂。完成 Phase 8C 后回到本步骤复查 `banditArms[hour_X].totalReward` 是否变化。

---

### Phase 4（触发冲浪 — 必须先做，Phase 2/3/8A 都依赖此结果）

> 目的：让分身真正"出动一次"，这是 AtoA 探针、Bandit pull、SurfLog 写入的总入口。

**方式 A — 命令行调度器（适合定时部署）**

```bash
python scripts/run_avatar_scheduler.py --report          # 看所有用户冲浪状态
python scripts/run_avatar_scheduler.py --user xu_yining  # 只跑 xu_yining
# 若提示 skipped：用 --report 确认 next_surf_at > now，重新种子或等待窗口
```

**方式 B — Swagger 触发（推荐联调用，跳过时间窗口限制）**

| 步骤 | 方法 | 路径 | 要点 | 解释 |
|------|------|------|------|------|
| 1 | POST | `/avatar/surf/trigger` | 无 Body | 立即触发一次完整冲浪。后端会：① AtoA 探针扫描候选 → ② 生成分身对话写入 `atoa_interactions` → ③ Bandit 记录 pull → ④ 写 `AvatarSurfLog` → ⑤ 更新 `last_surf_at` / `next_surf_at`。**响应里 `atoaScanned > 0` 才算成功**，若为 0 说明全库满足 `autoMatchEnabled=true` 的用户数低于阈值（重跑种子）。 |
| 2 | GET | `/avatar/surf-logs` | `items[0].status=success` | 验收冲浪日志已写入；`scannedAtoaPairs > 0`、`top10SessionId` 非空。 |
| 3 | GET | `/avatar/status` | `lastSurfAt` 已更新，`dailySurfCount +1`，`nextSurfAt` 重新计算 | 确认状态字段同步推进。完成后再回到 Phase 2+3 步骤 1 做基线快照。 |

---

### Phase 8A（AtoA 初次探针 — 验收冲浪产物）

> 目的：确认两个分身真的"对上话"了，并产生供用户审阅的探针条目。前提：已完成 Phase 4 冲浪。

| 步骤 | 方法 | 路径 | 要点 | 解释 |
|------|------|------|------|------|
| 1 | GET | `/avatar/atoa/sessions?limit=5` | `candidateCount`、`pendingCount` | 看 Top-10 候选池本次冲浪开了几个会话。`pendingCount` = 等用户决策的条数。复制 `id` 即 `sessionId`（用来在 probe-log 里筛选同一会话的互动）。 |
| 2 | GET | `/avatar/probe-log?outcome=pending_user_decision&limit=20` | `conversation` 非空 | **核心验收点**。每条返回 `userBName`（候选对方）、`scoreA/scoreB`（双方分身打分）、`conversation`（分身代你聊的对话内容）。Mock 模式是模板对话，真实蓝心模式是 LLM 生成。复制一条 `id` 作为 `{interactionId}` 用于 Phase 8B/8C。 |
| 3 | GET | `/avatar/surf-logs` | `scannedAtoaPairs`、`surfReport`、`top10SessionId` | 这里能看到本次冲浪的 AtoA 报告文本：扫了多少对、生成了多少条互动。 |
| 4 | GET | `/avatar/mutual-matches?limit=20` | 双向达标项 | 双方分数都过阈值才会出现。冷启动数据不足时可能为空属正常；有结果说明已形成"对方分身也觉得你不错"的双向推荐。 |

---

### Phase 8B（继续聊 — 让分身多聊一轮）

> 目的：用户觉得对话太短，想看分身再深聊几句。

| 步骤 | 方法 | 路径 | 要点 | 解释 |
|------|------|------|------|------|
| 1 | POST | `/avatar/atoa/{interactionId}/continue` | 无 Body；`{interactionId}` 用 8A 步骤 2 复制的 id | 后端基于已有对话再追加 ≤3 轮（每轮 avatar_a + avatar_b 各一条）。响应里 `interactionPhase` 从 1 变 2，`newTurns` 是本次新增内容，`conversation` 是合并后的全量对话。**只有发起方（user_a）能调**，且 outcome 必须仍为 `pending_user_decision`，否则 400/403。 |

---

### Phase 8C（打断 / 结交 — 完整闭环验收）

> 目的：用户最终拍板。`block` = 不感兴趣，`connect` = 想认识，后者会真正落库一条搭子申请，由对方决定是否接受。

#### 路线 A：屏蔽（block）

| 步骤 | 方法 | 路径 | Body | 解释 |
|------|------|------|------|------|
| A1 | POST | `/avatar/atoa/{interactionId}/decide` | `{"decision":"block"}` | 响应 `{"outcome":"blocked","socialMatchId":null}`。同时这条 atoa 互动的 `outcome` 写为 `blocked`，对应的 `AvatarMatch`（matchType=atoa）被 dismiss。 |
| A2 | GET | `/avatar/probe-log` | 找到刚才的 `id` | 该条 `outcome` 现在应为 `blocked`，验证决策同步成功。 |
| A3 | GET | `/avatar/status` | 对比 Phase 2+3 步骤 1 的基线 | `feedbackHours` 中"上次冲浪发生那一小时"的分数应下降；`banditArms` 里对应小时的 `meanReward` 也下降。说明负反馈写入成功。 |

#### 路线 B：结交（connect — 推荐用两个账号完整跑）

**用户 A 发起：**

| 步骤 | 方法 | 路径 | Body | 解释 |
|------|------|------|------|------|
| B1 | POST | `/avatar/atoa/{interactionId}/decide` | `{"decision":"connect","openingMessage":"我们都喜欢夜跑，要不要约一起？"}` | 后端在 `social.Match` 表落一条 `matchType=buddy`、`status=pending` 记录，开场白写入 `match_report`，触发 Bandit 反馈 +10。响应 `{"outcome":"connected","socialMatchId":"..."}`，**复制这个 socialMatchId**，下游所有引用都靠它。 |
| B2 | GET | `/social/matches?include_pending=true` | 看到刚创建的 `pending` | 验收 social.Match 真的写进去了；`id == socialMatchId`。 |

**切换到用户 B（候选对方）：**

| 步骤 | 方法 | 路径 | Body | 解释 |
|------|------|------|------|------|
| B3 | POST | `/auth/login` | `{"username":"<用户B>","password":"password123"}` | 用户 B 的用户名可以在 B1 之前调 `GET /avatar/probe-log` 看 `userBName` 反查出对应种子用户名。重新 Authorize。 |
| B4 | GET | `/social/matches?include_pending=true` | 看到来自 A 的 `pending` 申请 | 含 `match_report`（A 的开场白）。 |
| B5 | POST | `/social/buddy/{socialMatchId}/respond` | `{"accept":true}` 或 `false` | **路径里的 id 必须是 B1 拿到的 `socialMatchId`，不能用 `interactionId` 或 `userBId`**，否则 404。accept=true → 状态变 `accepted`；false → `rejected`。 |

**切换回用户 A 验收：**

| 步骤 | 方法 | 路径 | Body | 解释 |
|------|------|------|------|------|
| B6 | POST | `/auth/login` | A 的账号 | 重新 Authorize 切回 A。 |
| B7 | GET | `/avatar/probe-log` | 找到那条 connect 的互动 | `outcome` 已从 `connected` 同步为 `connect_confirmed`（B 同意）或 `connect_rejected`（B 拒绝）；`triggeredMatchId == socialMatchId`。这一步证明 Phase 8C 的"对方响应同步回探针"完整闭环。 |
| B8 | GET | `/avatar/status` | 再次对比 Phase 2+3 基线 | `banditArms[hour_X].totalReward` 应增加 ~10；`feedbackHours` 对应小时分数显著上升。说明正向反馈写入成功，下次该时段的 UCB 排序优先级会提升。 |

---

### 一图速查：Phase ↔ 接口

```
Phase 1   GET/PUT /avatar/status   +   POST /avatar/usage-events
                │
                ▼
Phase 4   POST /avatar/surf/trigger    （唯一入口，触发以下全部）
                │
                ├──► Phase 8A   GET /avatar/probe-log
                │               GET /avatar/atoa/sessions
                │               GET /avatar/mutual-matches
                │               GET /avatar/surf-logs
                │
                │   用户审阅 probe-log，对单条做：
                │
                ├──► Phase 8B   POST /avatar/atoa/{id}/continue   （想多聊）
                │
                └──► Phase 8C   POST /avatar/atoa/{id}/decide
                                 ├── block    → outcome=blocked
                                 └── connect  → 写 social.Match
                                                 │
                                                 ▼
                                  POST /social/buddy/{socialMatchId}/respond
                                                 │
                                                 ▼
                                  probe-log 同步 connect_confirmed / connect_rejected
                                                 │
                                                 ▼
                                  Phase 2+3：banditArms / feedbackHours 更新
```

---

### 回归：自动化测试

```bash
pytest tests/test_avatar_atoa.py -v
pytest tests/ -k "avatar" -v --tb=short
```

---

## 四、与主 TASK-G 文档的差异备忘

| 主题 | TASK-G 草案 | 当前实现 |
|------|-------------|----------|
| 对方确认结交 | `POST /api/social/matches/{id}/confirm-buddy` | 使用已有 **`POST /social/buddy/{requestId}/respond`** |
| `decide` 返回体 | 草案含 `replacement` | 当前 `block` 仅返回 `outcome` + `social_match_id: null` |

主文档 §十二 Phase 8 小节中的 `[ ]` 以**代码与本文档「二」节勾选**为准；后续迭代可回填主文档。
