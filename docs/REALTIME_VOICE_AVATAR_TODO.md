# Avalin 实时语音分身实施 Todo

> 使用方式：每次只把一个 Task Card 交给 AI 实现。
> 后端规格：`docs/REALTIME_VOICE_AVATAR_SPEC.md`
> 前端规格：`../../riji-frontend/docs/REALTIME_VOICE_AVATAR_FRONTEND_SPEC.md`

---

## 0. 执行规则

### 0.1 每个 AI 回合的固定要求

将下面模板与一个 Task Card 一起发给 AI：

```text
只实现任务 <TASK_ID>，不要提前实现后续任务。

开始前：
1. 完整阅读该任务引用的 Spec 章节。
2. 阅读任务列出的现有文件。
3. 检查工作区已有改动，不覆盖无关改动。

实现要求：
1. 遵循现有 FastAPI / uni-app / SQLAlchemy / Pinia 模式。
2. 不改变任务范围外的业务行为。
3. 新增必要测试。
4. 不把密钥、Token、原始音频或私密记忆写入日志。

完成后：
1. 运行任务指定的验证命令。
2. 汇报修改文件、测试结果和剩余风险。
3. 仅当验收标准全部满足时，把 Todo 中该项标记为完成。
```

### 0.2 提交纪律

- 一个 Task Card 对应一个 commit。
- 协议改动先改 Spec，再改代码。
- 后端事件类型未稳定前，不开始正式前端页面。
- 不允许使用真实火山 API 运行常规单元测试。
- 真实 API 冒烟只能在 `INT-002` 之后执行。
- P0 不开放任何 R3 工具。

### 0.3 全局门槛

开始前确认：

- [x] 火山引擎新版控制台已开通豆包实时语音模型 3.0 全双工。
- [x] 已获得测试 API Key，但未写入 Git。
- [x] 本地 Python 版本、`websockets==12.0` 可用。
- [x] H5 开发使用 localhost；生产要求 HTTPS/WSS。
- [x] 后端和前端当前测试基线已记录。

建议记录：

```bash
cd riji-backend && .venv/bin/pytest -q
cd riji-frontend && npm run type-check && npm test && npm run build:h5
```

---

# Phase 1：后端基础与契约

## BE-001 配置与 Health API

**优先级**：P0
**依赖**：无
**Spec**：后端 §6、§18

- [x] 在 `app/config.py` 增加全部实时语音配置。
- [x] 更新 `.env.example` 和 `.env.production.example`。
- [x] 新增 `app/realtime_voice/__init__.py`。
- [x] 新增 `app/realtime_voice/router.py`。
- [x] 实现 `GET /api/realtime-voice/health`。
- [x] 在 `app/main.py` 注册 router。
- [x] Feature Flag 关闭时 Health 仍返回 200，但 `enabled=false`。
- [x] Health 不返回 API Key。

**建议文件**

```text
app/config.py
app/main.py
app/realtime_voice/__init__.py
app/realtime_voice/router.py
app/realtime_voice/schemas.py
.env.example
.env.production.example
tests/test_realtime_voice_health.py
```

**验收**

```bash
.venv/bin/pytest -q tests/test_realtime_voice_health.py
```

Health 响应至少包含：

```json
{
  "enabled": false,
  "configured": false,
  "provider": "volcengine_duplex",
  "activeSessions": 0,
  "maxSessions": 5
}
```

**禁止**

- 不建立上游 WebSocket。
- 不实现 Ticket。
- 不打印配置值。

---

## BE-002 数据模型与迁移

**优先级**：P0
**依赖**：BE-001
**Spec**：后端 §13

- [x] 新增 `RealtimeVoiceSession`。
- [x] 新增 `RealtimeToolCall`。
- [x] 在 `app/models/__init__.py` 和 `init_db()` 导入。
- [x] 新增 Alembic migration。
- [x] migration 同时兼容 SQLite 和 MySQL。
- [x] 增加唯一约束 `(voice_session_id, provider_call_id)`。
- [x] 增加 Spec 要求的索引。

**建议文件**

```text
app/models/realtime_voice.py
app/models/__init__.py
app/database.py
alembic/versions/<revision>_add_realtime_voice.py
tests/test_realtime_voice_models.py
```

**验收**

```bash
.venv/bin/alembic upgrade head
.venv/bin/pytest -q tests/test_realtime_voice_models.py
```

额外执行一次全新 SQLite 数据库升级测试。

---

## BE-003 短期 Ticket

**优先级**：P0
**依赖**：BE-001
**Spec**：后端 §5

- [x] 实现 `POST /api/realtime-voice/tickets`。
- [x] Ticket 包含 `aud/sub/jti/exp/platform/audio format`。
- [x] 默认 60 秒过期。
- [x] 实现一次性 JTI 消费缓存。
- [x] 同一 Ticket 第二次使用必须拒绝。
- [x] Feature Flag 关闭时返回 503。
- [x] 未配置 API Key 时返回 503。
- [x] 非法 voice 使用默认值或明确 400。

**建议文件**

```text
app/realtime_voice/tickets.py
app/realtime_voice/router.py
app/realtime_voice/schemas.py
tests/test_realtime_voice_tickets.py
```

**验收**

```bash
.venv/bin/pytest -q tests/test_realtime_voice_tickets.py
```

测试必须覆盖：正常、过期、篡改、aud 错误、重放、未认证、功能关闭。

---

## BE-004 Avalin WebSocket 协议类型

**优先级**：P0
**依赖**：BE-001
**Spec**：后端 §8

- [x] 定义所有客户端上行事件。
- [x] 定义所有服务端下行事件构造器。
- [x] 严格校验事件 `type` 和字段。
- [x] 限制单个 `audio.append` Base64 长度。
- [x] 生成服务端 `eventId`。
- [x] 未知事件返回明确协议错误。
- [x] 状态不允许的事件返回明确错误。

**建议文件**

```text
app/realtime_voice/protocol.py
app/realtime_voice/schemas.py
tests/test_realtime_voice_protocol.py
```

**验收**

```bash
.venv/bin/pytest -q tests/test_realtime_voice_protocol.py
```

**禁止**

- 不连接豆包。
- 不访问数据库。
- 不实现业务工具。

---

## BE-005 Provider 抽象与 Fake Provider

**优先级**：P0
**依赖**：BE-004
**Spec**：后端 §4、§19.2

- [x] 定义 `RealtimeVoiceProvider` Protocol。
- [x] 定义 Provider Session Config 与标准化 Event。
- [x] 实现 `FakeRealtimeVoiceProvider`。
- [x] Fake 支持脚本化 ASR/Text/Audio/Tool/Error。
- [x] Fake 支持记录客户端发来的 audio/cancel/close/tool result。
- [x] 测试不需要网络。

**建议文件**

```text
app/realtime_voice/provider.py
app/realtime_voice/fake_provider.py
tests/test_realtime_voice_fake_provider.py
```

**验收**

```bash
.venv/bin/pytest -q tests/test_realtime_voice_fake_provider.py
```

---

## BE-006 豆包全双工 Provider

**优先级**：P0
**依赖**：BE-005
**Spec**：后端 §7、§9

- [x] 使用 `wss://openspeech.bytedance.com/api/v3/duplex/realtime/dialogue`。
- [x] 请求头使用 `X-Api-Key`。
- [x] 实现 `session.create/update/close`。
- [x] 实现 `input_audio_buffer.append/commit`。
- [x] 实现 `response.cancel`。
- [x] 实现 `conversation.item.create` Tool 结果回传。
- [x] 映射全部 P0 下行事件。
- [x] 保存 `X-Tt-Logid`。
- [x] 任何日志不得包含 Key 或音频 Base64。
- [x] 4xx 不自动重试；5xx 交给 Session 层。

**建议文件**

```text
app/realtime_voice/volcengine.py
app/realtime_voice/config.py
tests/test_volcengine_realtime_provider.py
```

**验收**

```bash
.venv/bin/pytest -q tests/test_volcengine_realtime_provider.py
```

使用 Mock WebSocket 验证事件，不调用真实 API。

---

# Phase 2：实时会话骨架

## BE-007 会话持久化

**优先级**：P0
**依赖**：BE-002、BE-005
**Spec**：后端 §13

- [x] 实现 Voice Session 创建、更新、关闭。
- [x] 复用或创建 `ChatSession`。
- [x] `asr.done` 幂等保存用户消息。
- [x] `assistant.text.done` 幂等保存分身消息。
- [x] delta 不落库。
- [x] 关闭后按设置调用 `close_and_materialize`。
- [x] 不保存 PCM/Base64。

**建议文件**

```text
app/realtime_voice/persistence.py
tests/test_realtime_voice_persistence.py
```

**验收**

```bash
.venv/bin/pytest -q tests/test_realtime_voice_persistence.py
```

---

## BE-008 WebSocket Gateway 基础转发

**优先级**：P0
**依赖**：BE-003、BE-004、BE-005、BE-007
**Spec**：后端 §3、§8、§14

- [x] 实现 `/ws/realtime-avatar?ticket=...`。
- [x] 消费一次性 Ticket。
- [x] 单用户只允许一个连接。
- [x] 实现 client reader、provider reader、watchdog。
- [x] Fake Provider 下完成 PCM 上下行。
- [x] 转发字幕、回复文本和音频。
- [x] 支持客户端 `response.cancel`。
- [x] 支持 `session.close`。
- [x] 任一 Task 异常时正确取消其他 Task。
- [x] 所有数据库 Session 在结束时关闭。

**建议文件**

```text
app/realtime_voice/router.py
app/realtime_voice/session.py
app/realtime_voice/registry.py
tests/test_realtime_voice_websocket.py
```

**验收**

```bash
.venv/bin/pytest -q tests/test_realtime_voice_websocket.py
```

先只注入 Fake Provider。真实 Provider 由 Feature Flag 显式选择。

---

## BE-009 Prompt 与基础会话上下文

**优先级**：P0
**依赖**：BE-008
**Spec**：后端 §10

- [x] 新增语音专用系统提示词。
- [x] 限制语音回复长度。
- [x] 明确没有 Tool 证据不能声称记得。
- [x] 明确 R3 禁止行为。
- [x] 初始只注入安全画像摘要和边界，不注入全部记忆。
- [x] 最多初始化最近 6 轮文本会话历史。
- [x] 历史注入符合成对 QA 要求。

**建议文件**

```text
app/realtime_voice/prompts.py
app/realtime_voice/config.py
tests/test_realtime_voice_prompts.py
```

**验收**

```bash
.venv/bin/pytest -q tests/test_realtime_voice_prompts.py
```

---

# Phase 3：Tool Router 与记忆

## BE-010 Tool Registry 与 Policy Guard

**优先级**：P0
**依赖**：BE-008
**Spec**：后端 §11.1、§11.4、§17

- [x] 定义 Tool 注册结构。
- [x] 定义 R0/R1/R2/R3。
- [x] Provider 只收到当前启用工具的 JSON Schema。
- [x] Pydantic 校验参数并拒绝未知字段。
- [x] Tool Result 统一 `{ok,data,error}`。
- [x] Tool Result 最大 4000 字符。
- [x] R3 不允许注册。
- [x] 每个 Tool 使用独立 DB Session。
- [x] 只读 Tool 最大并发 3，写 Tool 串行。

**建议文件**

```text
app/realtime_voice/tools.py
app/realtime_voice/policy.py
app/realtime_voice/tool_schemas.py
tests/test_realtime_voice_tool_policy.py
```

**验收**

```bash
.venv/bin/pytest -q tests/test_realtime_voice_tool_policy.py
```

---

## BE-011 Tool Call 审计与幂等

**优先级**：P0
**依赖**：BE-002、BE-010
**Spec**：后端 §9.3、§13.2

- [x] 收到 Function Call 立即创建审计记录。
- [x] `(session, provider_call_id)` 幂等。
- [x] 重复调用返回已有结果，不重复执行业务。
- [x] 状态覆盖 received/running/succeeded/failed。
- [x] 多 Tool Call 聚合回传，保留全部 `call_id`。
- [x] arguments/result 日志脱敏。

**建议文件**

```text
app/realtime_voice/tools.py
app/realtime_voice/persistence.py
tests/test_realtime_voice_tool_audit.py
```

**验收**

```bash
.venv/bin/pytest -q tests/test_realtime_voice_tool_audit.py
```

---

## BE-012 `search_personal_memory`

**优先级**：P0
**依赖**：BE-010、BE-011
**Spec**：后端 §11.2

- [x] 包装 `retrieve_memories()`。
- [x] `user_id` 只能取当前会话。
- [x] source type 白名单。
- [x] topK 最大 6。
- [x] snippet 最大 240 字。
- [x] 返回日记 Deep Link。
- [x] 生成前端 `tool.result` 证据数据。
- [x] 无结果返回空数组，不抛业务异常。
- [x] 增加跨用户泄漏测试。

**建议文件**

```text
app/realtime_voice/tools.py
app/realtime_voice/tool_schemas.py
tests/test_realtime_voice_memory_tool.py
```

**验收**

```bash
.venv/bin/pytest -q tests/test_realtime_voice_memory_tool.py
```

---

## BE-013 `get_memory_document`

**优先级**：P0
**依赖**：BE-012
**Spec**：后端 §11.2

- [x] 只允许读取本会话 RAG 返回过的 document ID。
- [x] 校验 document 所属用户。
- [x] 内容最大 800 字。
- [x] 返回来源、标题、日期和 Deep Link。
- [x] 非法 ID 不暴露资源是否存在。

**验收**

```bash
.venv/bin/pytest -q tests/test_realtime_voice_memory_tool.py
```

---

# Phase 4：语音找人任务

> 完成状态：2026-08-18 已实现并通过专项测试。

## BE-014 `draft_social_mission`

**优先级**：P0
**依赖**：BE-010
**Spec**：后端 §11.2、§20.2、§20.3

- [x] 包装 `parse_mission_text()`。
- [x] 不写数据库。
- [x] 返回可展示 summary。
- [x] 返回最多 3 个待确认问题。
- [x] 将草稿暂存在 Voice Session 内存上下文。
- [x] 对“每天想看电影”等歧义增加测试。
- [x] questions 非空时拒绝 create 工具。

**建议文件**

```text
app/realtime_voice/tools.py
app/realtime_voice/tool_schemas.py
tests/test_realtime_voice_mission_tools.py
```

**验收**

```bash
.venv/bin/pytest -q tests/test_realtime_voice_mission_tools.py
```

---

## BE-015 `create_social_mission_draft`

**优先级**：P0
**依赖**：BE-014
**Spec**：后端 §11.2

- [x] 只接受当前 Voice Session 内的草稿 ID/hash。
- [x] 复用 `create_mission()`。
- [x] source 标记为 `natural_language` 或新增 `realtime_voice`。
- [x] 强制 `autoPublish=false`。
- [x] 强制 `autoConnect=false`。
- [x] 状态只能是 draft。
- [x] 返回确认摘要和确认 ID。

**验收**

```bash
.venv/bin/pytest -q tests/test_realtime_voice_mission_tools.py
```

---

## BE-016 Confirmation Manager

**优先级**：P0
**依赖**：BE-011、BE-015
**Spec**：后端 §12

- [x] 实现确认对象、签名 Token、TTL。
- [x] 绑定 user/session/action/resource/hash。
- [x] 同一用户话轮不得创建并执行 R2。
- [x] 支持 `confirmation.resolve`。
- [x] 支持下一语音话轮的 Token。
- [x] approve/reject 幂等。
- [x] 过期、篡改、重复、摘要变化全部拒绝。
- [x] 审计 confirmation channel：screen/voice。

**建议文件**

```text
app/realtime_voice/confirmations.py
app/realtime_voice/policy.py
app/realtime_voice/session.py
tests/test_realtime_voice_confirmations.py
```

**验收**

```bash
.venv/bin/pytest -q tests/test_realtime_voice_confirmations.py
```

---

## BE-017 `start_social_mission`

**优先级**：P0
**依赖**：BE-016
**Spec**：后端 §11.2

- [x] 风险等级 R2。
- [x] 没有合法确认 Token 时不执行。
- [x] 复用 `start_mission()`。
- [x] 返回真实 scanned/matched 数量。
- [x] 返回任务详情 Deep Link。
- [x] 不自动发帖。
- [x] 不自动 probe 候选。
- [x] 不自动 connect。

**验收**

```bash
.venv/bin/pytest -q tests/test_realtime_voice_mission_tools.py
```

关键测试：

```text
draft -> 未确认 -> status 仍 draft
draft -> 确认 -> status searching/awaiting_user
```

---

## BE-018 任务查询与导航工具

**优先级**：P0
**依赖**：BE-017
**Spec**：后端 §11.2

- [x] `list_social_missions`。
- [x] `get_social_mission_progress`。
- [x] `open_app_page`。
- [x] 路由白名单。
- [x] 最多返回 3 个候选摘要。
- [x] 不返回内部评分、私密卡片或其他用户私密数据。

**验收**

```bash
.venv/bin/pytest -q tests/test_realtime_voice_mission_tools.py
```

---

# Phase 5：后端稳定性与部署

> 完成状态：2026-08-18 已实现；单进程并发限制明确使用 Session Registry，
> 扩展到多 Worker 前必须迁移 Redis。

## BE-019 重连、超时与优雅关闭

**优先级**：P0
**依赖**：BE-008、BE-011
**Spec**：后端 §15

- [x] 5xx 最多重连 2 次。
- [x] 4xx 不重试。
- [x] 9 分钟空闲关闭。
- [x] 20 分钟最长时长。
- [x] 关闭先发上游 `session.close`。
- [x] 等待 `session.closed` 最多 3 秒。
- [x] 异常关闭仍落库 transcript/usage/error。
- [x] 不重放已 commit 的音频。

**验收**

```bash
.venv/bin/pytest -q tests/test_realtime_voice_reliability.py
```

---

## BE-020 限流、背压和日志

**优先级**：P0
**依赖**：BE-019
**Spec**：后端 §14、§16、§17

- [x] 单进程全局并发 Session Registry（不是协程内临时 Semaphore）。
- [x] 单用户一会话。
- [x] 输入队列上限。
- [x] Tool 超时。
- [x] 结构化日志。
- [x] 日志脱敏测试。
- [x] 基础指标采集。
- [x] Health 返回 active/max。

**验收**

```bash
.venv/bin/pytest -q tests/test_realtime_voice_limits.py tests/test_realtime_voice_logging.py
```

---

## BE-021 Nginx 与 Docker

**优先级**：P0
**依赖**：BE-020
**Spec**：后端 §18

- [x] `/ws/` 增加 `proxy_buffering off`。
- [x] read/send timeout 调整为 900 秒。
- [x] Docker 环境变量示例补齐。
- [x] 容器网络依赖仅为上游 443，无新增服务依赖。
- [x] 不增加不必要的独立容器。
- [x] 更新 README 启动说明。

**建议文件**

```text
deploy/nginx/default.conf
docker-compose.yml
README.md
```

**验收**

```bash
docker compose config
```

---

## BE-022 后端完整回归

**优先级**：P0 Gate
**依赖**：BE-001 至 BE-021

- [x] 新增实时语音测试全部通过。
- [x] 原有完整测试通过。
- [x] Alembic 全新库升级、回滚实时语音迁移并重新升级通过。
- [x] 临时 MySQL 空库在线迁移至 head 通过（34 张表）。
- [x] OpenAPI 无意外破坏。
- [x] Feature Flag 关闭时原系统行为不变。

**验收**

```bash
.venv/bin/pytest -q
.venv/bin/alembic heads
```

完成本项后，才能进入正式前端联调。

---

# Phase 6：前端协议、Store 与 Fake

> 完成状态：2026-08-18 已实现并通过 TypeScript 与专项测试。

## FE-001 前端协议类型与 REST API

**优先级**：P0
**依赖**：BE-004 契约稳定
**Spec**：前端 §8

- [x] 新增 Ticket/Health API。
- [x] 定义全部 Client/Server Event 判别联合类型。
- [x] 实现事件运行时守卫。
- [x] 未知事件可忽略并记录。
- [x] WS URL 正确适配 http/https。

**建议文件**

```text
src/services/realtime/voice-api.ts
src/services/realtime/voice-protocol.ts
src/services/realtime/voice-errors.ts
```

**验收**

```bash
npm run type-check
npm test
```

---

## FE-002 WebSocket Client

**优先级**：P0
**依赖**：FE-001
**Spec**：前端 §8.2

- [x] 获取 Ticket 后建立连接。
- [x] Ticket 不落 Storage。
- [x] 发送事件自动带 eventId。
- [x] 正常 close。
- [x] 区分服务端 error 与 socket error。
- [x] 支持注入 Fake Socket。
- [x] 不包含任何火山 API Key。

**建议文件**

```text
src/services/realtime/voice-socket.ts
src/services/realtime/__tests__/voice-socket.test.ts
```

---

## FE-003 Realtime Voice Store

**优先级**：P0
**依赖**：FE-001、FE-002
**Spec**：前端 §7

- [x] 实现完整状态。
- [x] 实现合法状态转换。
- [x] 合并 ASR/Text delta。
- [x] 管理 evidence/tool/confirmation。
- [x] 不把 PCM 放入响应式状态。
- [x] 不持久化 Store。
- [x] reset 清空所有会话状态。

**建议文件**

```text
src/stores/realtime-voice.ts
```

**验收**

```bash
npm run type-check
npm test
```

---

## FE-004 Fake Audio Adapter

**优先级**：P0
**依赖**：FE-003
**Spec**：前端 §9、§15.2

- [x] 定义 `RealtimeAudioAdapter`。
- [x] 实现 Fake。
- [x] 可生成固定 PCM 帧。
- [x] 可检查播放队列。
- [x] interrupt 清空队列。
- [x] dispose 后不能继续输出事件。

**建议文件**

```text
src/services/realtime/audio/types.ts
src/services/realtime/audio/fake-audio.ts
```

---

## FE-005 Fake 会话端到端

**优先级**：P0 Gate
**依赖**：FE-002、FE-003、FE-004

- [x] 无页面情况下完成 Fake Socket + Fake Audio + Store。
- [x] 覆盖连接、字幕、音频、打断、Tool、确认和关闭。
- [x] 资源无泄漏。

完成后再开发 UI，避免视觉层掩盖协议问题。

---

# Phase 7：H5 音频

> 完成状态：2026-08-18 已实现并通过 AudioWorklet Fake 验证。

## FE-006 PCM 工具

**优先级**：P0
**依赖**：FE-004

- [x] Float32 -> int16 PCM。
- [x] Base64 编解码。
- [x] 采样率转换。
- [x] 音量 RMS。
- [x] 对齐、边界、空帧测试。

**建议文件**

```text
src/services/realtime/audio/pcm.ts
```

---

## FE-007 H5 麦克风采集

**优先级**：P0
**依赖**：FE-006
**Spec**：前端 §9.1

- [x] getUserMedia 权限。
- [x] AudioWorklet。
- [x] 16 kHz 单声道 PCM。
- [x] 20 ms 帧。
- [x] 麦克风开关。
- [x] 页面销毁停止所有 Track。
- [x] Safari 用户手势处理。

**建议文件**

```text
src/services/realtime/audio/h5-audio.ts
src/static/audio-worklets/pcm-capture.js
```

---

## FE-008 H5 PCM 播放器

**优先级**：P0
**依赖**：FE-006
**Spec**：前端 §9.1、§9.3

- [x] 24 kHz PCM 队列缓冲。
- [x] 80-120 ms 预缓冲。
- [x] 连续 Worklet 流式播放。
- [x] 扬声器静音。
- [x] interrupt 立即清空。
- [x] 最大缓冲 2 秒。
- [x] AudioContext 完整销毁。

**建议文件**

```text
src/services/realtime/audio/h5-audio.ts
src/static/audio-worklets/pcm-playback.js
```

---

# Phase 8：前端页面

> 完成状态：2026-08-18 已实现，并完成浏览器移动/桌面手机框、
> 375px、横屏、减少动态效果和大字体 Visual QA。

## FE-009 通话页壳与路由

**优先级**：P0
**依赖**：FE-005
**Spec**：前端 §2、§3、§4

- [x] 新增 `pages/chat/voice-call`。
- [x] 注册 `pages.json`。
- [x] 自定义导航栏。
- [x] 稳定的头部、字幕区、底部控制栏。
- [x] 安全区适配。
- [x] 不显示 TabBar。
- [x] 先使用 Fake Store 渲染状态。

**验收**

```bash
npm run type-check
npm run build:h5
```

---

## FE-010 声音脉络与状态

**优先级**：P0
**依赖**：FE-009
**Spec**：前端 §3、§4、§6.1

- [x] 固定高度声音脉络。
- [x] listening/speaking 使用不同语义。
- [x] 最大 30 FPS。
- [x] reduced-motion 静态替代。
- [x] connecting/thinking 不使用无限装饰动画。
- [x] 状态文字始终可见。

---

## FE-011 实时字幕

**优先级**：P0
**依赖**：FE-003、FE-009
**Spec**：前端 §5.2、§5.3、§6.2

- [x] 用户 ASR delta。
- [x] 分身 Text delta。
- [x] done 后冻结记录。
- [x] 最近 20 条。
- [x] 用户/分身不只靠颜色区分。
- [x] Delta 更新不抖动控制栏。

---

## FE-012 记忆证据

**优先级**：P0
**依赖**：BE-012、FE-011
**Spec**：前端 §5.5

- [x] 展示来源、标题、日期、摘要。
- [x] 最多 3 条。
- [x] 不显示内部 ID 和评分。
- [x] Deep Link 白名单。
- [x] 打开日记前正确关闭通话。
- [x] 空结果不显示空卡片。

---

## FE-013 找人任务摘要与确认

**优先级**：P0
**依赖**：BE-016、BE-017、FE-011
**Spec**：前端 §5.6、§6.3

- [x] 展示活动、时间、地点、人数、搜索范围。
- [x] 有 questions 时不显示确认按钮。
- [x] 确认和修改两个动作。
- [x] 显示“不会自动发帖或申请认识”。
- [x] 处理 TTL 过期。
- [x] 支持 screen confirmation。
- [x] 支持 voice confirmation 后同步 UI。

---

## FE-014 通话控制与打断

**优先级**：P0
**依赖**：FE-008、FE-009
**Spec**：前端 §5.4、§6.4

- [x] 麦克风开关。
- [x] 扬声器静音。
- [x] 结束通话。
- [x] `asr.started` 本地立即 interrupt。
- [x] 发送 `response.cancel`。
- [x] 所有按钮至少 48dp。
- [x] 可访问名称和键盘触发。

---

## FE-015 入口接入

**优先级**：P0
**依赖**：FE-009
**Spec**：前端 §2.1

- [x] AI 对话页增加语音通话入口。
- [x] 找朋友页“语音说”进入 `mode=social_mission`。
- [x] 使用 DoodleIcon，不使用 Emoji。
- [x] 首次点击建立 AudioContext。
- [x] Feature Flag 关闭时隐藏入口。

---

## FE-016 生命周期、错误与摘要

**优先级**：P0
**依赖**：FE-014
**Spec**：前端 §10、§11

- [x] onHide 暂停；30 秒后关闭。
- [x] onUnload/dispose 无资源泄漏。
- [x] 权限拒绝。
- [x] 5xx 重连状态。
- [x] 4xx 明确退出。
- [x] 结束摘要。
- [x] 错误 Live Region。
- [x] 无模糊“发生错误”文案。

---

## FE-017 前端完整回归

**优先级**：P0 Gate
**依赖**：FE-001 至 FE-016

- [x] 协议、Store、Fake Audio 测试。
- [x] TypeScript 通过。
- [x] 现有前端测试通过。
- [x] H5 生产构建通过。
- [x] 375px、横屏和桌面手机模拟宽度验证。
- [x] reduced-motion 验证。
- [x] 大字体验证。

**验收**

```bash
npm run type-check
npm test
npm run build:h5
```

---

# Phase 9：vivo Android

## APP-001 UTS 插件骨架

**优先级**：P1
**依赖**：FE-005

- [ ] 创建 `uni_modules/avalin-realtime-audio`。
- [ ] 与 `RealtimeAudioAdapter` 接口一致。
- [ ] 增加 RECORD_AUDIO 权限。
- [ ] 增加 MODIFY_AUDIO_SETTINGS。
- [ ] 定义错误码和生命周期。

---

## APP-002 AudioRecord

**优先级**：P1
**依赖**：APP-001

- [ ] 16 kHz / mono / PCM 16-bit。
- [ ] 20 ms 输出帧。
- [ ] 麦克风开关。
- [ ] 权限拒绝和设备占用。
- [ ] stop/dispose 不泄漏线程。

---

## APP-003 AudioTrack

**优先级**：P1
**依赖**：APP-001

- [ ] 24 kHz / mono / PCM 16-bit / stream mode。
- [ ] 播放缓冲。
- [ ] interrupt 清空。
- [ ] Audio Focus。
- [ ] 扬声器静音。

---

## APP-004 vivo 真机音频场景

**优先级**：P1 Gate
**依赖**：APP-002、APP-003

- [ ] 内置麦克风与扬声器。
- [ ] 蓝牙耳机。
- [ ] 来电中断。
- [ ] App 切后台。
- [ ] 锁屏。
- [ ] Wi-Fi/移动网络切换。
- [ ] 20 分钟资源稳定性。

---

# Phase 10：联调与决赛验收

## INT-001 Fake Provider 全链路

**依赖**：BE-022、FE-017

- [ ] Ticket -> WS -> 音频 -> 字幕 -> 音频。
- [ ] 记忆证据。
- [ ] Mission 草稿。
- [ ] Confirmation。
- [ ] 打断。
- [ ] 关闭与 transcript。

不使用真实 API。

---

## INT-002 真实豆包 API 基础通话

**依赖**：INT-001、控制台权限

- [ ] Session Create。
- [ ] PCM 输入。
- [ ] ASR 字幕。
- [ ] Text 字幕。
- [ ] PCM 输出。
- [ ] 打断。
- [ ] 正常 `session.close`。
- [ ] 记录 X-Tt-Logid。

失败时保存脱敏事件日志，不保存音频。

---

## INT-003 真实记忆 RAG

**依赖**：INT-002

使用 `avalin_demo`：

- [ ] 问“大通湖晚霞”。
- [ ] 命中正确日记。
- [ ] 回答包含日期或标题。
- [ ] 前端证据可打开日记。
- [ ] 问不存在的事件时不编造。

---

## INT-004 真实找电影搭子

**依赖**：INT-002

- [ ] “今晚想找一个人看科幻电影”。
- [ ] 正确解析短期 movie。
- [ ] 显示任务摘要。
- [ ] 未确认不搜索。
- [ ] 确认后搜索。
- [ ] 返回真实候选数量。
- [ ] 不自动发布、申请或接受。

---

## INT-005 歧义与越权

**依赖**：INT-004

- [ ] “每天想看电影”先追问。
- [ ] “替我发帖”不执行。
- [ ] “替我接受第一个人”不执行。
- [ ] 尝试读取其他用户记忆失败。
- [ ] 重复 confirmation 不重复执行。

---

## INT-006 部署验证

**依赖**：BE-021、INT-005

- [ ] 生产环境变量。
- [ ] Nginx 15 分钟 WS。
- [ ] HTTPS/WSS。
- [ ] Docker 重启后健康。
- [ ] API Key 未出现在前端产物。
- [ ] 日志无音频、Token、私密正文。
- [ ] 并发上限可观察。

---

## INT-007 决赛演示链路

完整演练 20 次：

```text
打开 Avalin
-> 和分身实时通话
-> “你记得我上次拍晚霞吗”
-> 展示记忆证据
-> “今晚还想去看科幻电影，帮我找个搭子”
-> 整理并确认任务
-> 搜索候选
-> 展示 AtoA 后续入口
-> 真人决定
```

验收：

- [ ] 20 次启动成功率 ≥ 95%。
- [ ] 无跨用户数据。
- [ ] 无自动公开或关系承诺。
- [ ] 中途打断可恢复。
- [ ] 弱网失败有可理解降级。
- [ ] 准备录屏兜底，但现场优先真实演示。

---

# P1：AtoA 语音控制

以下任务在 P0 决赛链路稳定后再做。

## BE-P1-001 异步 AtoA Probe 工具

- [ ] `request_atoa_probe` 不同步等待模型。
- [ ] 入队后立即返回任务 ID。
- [ ] 查询任务状态。
- [ ] 完成后通过 App 通知或当前会话事件提示。
- [ ] R2 确认。

## BE-P1-002 Continue Probe

- [ ] `continue_atoa_probe`。
- [ ] R2 确认。
- [ ] 限制 interaction 所属用户。
- [ ] 终态不能继续。

## FE-P1-001 AtoA 进度语音结果

- [ ] 展示候选名称、适合点、待确认点。
- [ ] “再聊一组”确认。
- [ ] “想认识 TA”只能跳转到屏幕确认。

---

# 最终完成清单

## 后端

- [x] BE-001 至 BE-022 全部完成。
- [ ] INT-001 至 INT-006 全部完成。
- [x] 完整测试通过。
- [x] 实时语音迁移可回滚并重新升级。
- [x] 文档与代码契约一致。

## 前端

- [x] FE-001 至 FE-017 全部完成。
- [ ] APP-001 至 APP-004 完成后才称为 vivo 真机版本。
- [ ] H5、Android 真机均验证。
- [x] H5 自动化和生命周期路径无麦克风、AudioContext、WebSocket 泄漏。

## 产品安全

- [x] RAG 有证据。
- [x] 无证据时 instructions 明确禁止编造。
- [x] 未确认不启动任务。
- [x] 不自动公开。
- [x] 不自动建立关系。
- [x] API Key 不在前端。
- [x] 原始音频不落库。
