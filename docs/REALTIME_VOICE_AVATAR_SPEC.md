# Avalin 实时语音分身后端技术规格

> 状态：Draft v1.0  
> 范围：豆包实时语音模型 3.0 全双工接入、记忆 RAG、找人任务、工具确认与审计  
> 依赖文档：
> - [豆包实时语音模型 3.0 全双工 API](https://docs.volcengine.com/docs/6561/2549778?lang=zh)
> - [全双工接入必读](https://docs.volcengine.com/docs/6561/2549732?lang=zh)
> - [产品简介](https://docs.volcengine.com/docs/6561/1594360?lang=zh)
> - `riji-frontend/docs/ATOA-SOCIAL-FLOW-DESIGN.md`

---

## 1. 目标与边界

### 1.1 目标

新增一个实时语音入口，使用户可以自然地和自己的 AI 分身通话，并在通话中：

1. 询问过往生活，分身通过 RAG 找到可追溯的日记、素材或聊天记忆。
2. 表达社交目的，分身整理为可编辑的 `SocialMission` 草稿。
3. 在用户明确确认后，启动一次私有找人搜索。
4. 查询找人任务、候选和 AtoA 进度。
5. 通过事件通知前端展示记忆证据、任务摘要和页面跳转建议。

### 1.2 不做什么

首版明确不做：

- 不在前端保存火山引擎 API Key。
- 不让豆包模型直接访问数据库或内部 HTTP API。
- 不让模型自动发布广场帖子。
- 不让模型自动发起认识申请、接受关系、交换联系方式或作出线下承诺。
- 不把模型最近 20 轮上下文当作 Avalin 长期记忆。
- 不持久化原始通话音频。
- 不在首版支持后台通话、电话系统集成、多人语音房或声纹身份认证。

### 1.3 核心原则

```text
实时模型负责：听懂、表达、选择工具
Avalin 负责：鉴权、记忆、业务、权限、确认、审计
用户负责：公开、连接、承诺
```

---

## 2. 现有能力复用

| 需求 | 已有实现 | 接入方式 |
|---|---|---|
| 私有长期记忆检索 | `app.memory.retriever.retrieve_memories` | 包装为只读工具 |
| 日记证据 | `MemoryDocument.source_type=diary`、日记详情 API | 返回证据与 Deep Link |
| 对话落库 | `ChatSession`、`ChatMessage` | 通话转写复用现有模型 |
| 对话转素材 | `close_and_materialize` | 会话关闭后按用户设置执行 |
| 找人意图解析 | `mission_service.parse_mission_text` | 包装为无副作用草稿工具 |
| 找人任务 | `SocialMission` | 包装创建、查询、启动工具 |
| 任务搜索 | `mission_service.start_mission/search_mission` | 确认后执行 |
| AtoA 状态 | `AvatarAtoaSession/Interaction` | 只读查询工具 |
| AtoA Worker | `scripts/run_avatar_worker.py` | 后续异步试聊复用 |
| WebSocket 反代 | Nginx `/ws/` | 增加长连接参数 |

当前 `/ws/chat` 是单轮文本 WebSocket，不满足持续音频、打断、工具调用和多轮会话要求。新功能使用独立路由，不修改旧接口行为。

---

## 3. 总体架构

```text
┌──────────────────── vivo 手机 / H5 ────────────────────┐
│ 麦克风 → 16k PCM → Avalin WS                          │
│ Avalin WS → 24k PCM → 播放器                          │
│ 字幕 / 记忆证据 / 工具确认 / 页面跳转                  │
└─────────────────────────┬──────────────────────────────┘
                          │ /ws/realtime-avatar
                          ▼
┌────────────────── Avalin Realtime Gateway ─────────────┐
│ 认证与限流                                             │
│ Client Event Adapter                                   │
│ Volcengine Duplex Provider Adapter                     │
│ Tool Router + Policy Guard + Confirmation Manager      │
│ Transcript Writer + Audit Writer                       │
└──────────────┬──────────────────────┬──────────────────┘
               │                      │
               ▼                      ▼
┌──── 豆包实时语音 3.0 ────┐   ┌──── Avalin Domain ──────┐
│ ASR / Dialog / TTS       │   │ Memory RAG             │
│ Function Calling         │   │ Diary                  │
│ Conversation Context     │   │ SocialMission          │
│ Full-duplex Interrupt    │   │ AtoA / Avatar Worker   │
└──────────────────────────┘   └─────────────────────────┘
```

### 3.1 为什么必须由后端代理

1. `X-Api-Key` 不能出现在 App 包、网页源码或浏览器网络面板。
2. 工具调用必须经过 Avalin 权限校验，不能让模型自由调用业务接口。
3. 需要统一记录工具调用、确认行为、错误码和火山 `X-Tt-Logid`。
4. 需要将豆包协议隔离在 Provider Adapter 中，避免前端绑定供应商。
5. 需要用当前 JWT 身份限定 RAG、日记和任务数据。

---

## 4. 模块结构

新增目录：

```text
app/realtime_voice/
├── __init__.py
├── router.py              # ticket REST API + WebSocket 路由
├── config.py              # 会话配置构造
├── protocol.py            # Avalin 客户端事件类型与校验
├── session.py             # 单次实时会话编排
├── provider.py            # Provider 抽象
├── volcengine.py          # 豆包全双工协议适配
├── tools.py               # 工具注册与执行
├── policy.py              # 风险等级、确认、输出裁剪
├── persistence.py         # Transcript / Session / ToolCall 落库
├── schemas.py             # REST 与内部结构
└── prompts.py             # 分身系统提示词
```

建议接口：

```python
class RealtimeVoiceProvider(Protocol):
    async def connect(self, config: ProviderSessionConfig) -> None: ...
    async def send_audio(self, pcm_base64: str, event_id: str) -> None: ...
    async def commit_audio(self, event_id: str) -> None: ...
    async def cancel_response(self, event_id: str) -> None: ...
    async def send_tool_results(self, results: list[ToolResult]) -> None: ...
    async def update_tools(self, tools: list[dict]) -> None: ...
    async def receive(self) -> AsyncIterator[ProviderEvent]: ...
    async def close(self) -> None: ...
```

业务工具不允许依赖 `volcengine.py`，Provider 也不允许导入记忆或社交服务。

---

## 5. 鉴权与连接建立

### 5.1 不直接在 WebSocket URL 使用长期 JWT

新增：

```http
POST /api/realtime-voice/tickets
Authorization: Bearer <jwt>
```

请求：

```json
{
  "voice": "zh_female_vv_jupiter_bigtts",
  "outputFormat": "pcm_s16le",
  "clientPlatform": "h5"
}
```

响应：

```json
{
  "ticket": "<60 秒有效的签名票据>",
  "expiresAt": 1787000000000,
  "websocketPath": "/ws/realtime-avatar",
  "input": {
    "type": "pcm",
    "sampleRate": 16000,
    "channels": 1,
    "bitsPerSample": 16,
    "recommendedFrameMs": 20
  },
  "output": {
    "type": "pcm_s16le",
    "sampleRate": 24000,
    "channels": 1,
    "bitsPerSample": 16
  }
}
```

随后连接：

```text
wss://<host>/ws/realtime-avatar?ticket=<short-lived-ticket>
```

### 5.2 Ticket 约束

- JWT `aud` 固定为 `realtime_voice`。
- 有效期 60 秒。
- 包含 `sub=user_id`、`jti`、平台和音频格式。
- `jti` 首次使用后标记已消费，防止重放。
- 当前单 Worker 可用进程内 TTL Cache；多 Worker 前必须迁移 Redis。
- 单用户同时只允许一个实时语音会话。

---

## 6. 配置项

新增到 `app/config.py`、`.env.example`、`.env.production.example`：

```dotenv
VOLC_REALTIME_VOICE_ENABLED=false
VOLC_REALTIME_VOICE_API_KEY=
VOLC_REALTIME_VOICE_URL=wss://openspeech.bytedance.com/api/v3/duplex/realtime/dialogue
VOLC_REALTIME_VOICE_MODEL=1.2.6.1
VOLC_REALTIME_VOICE_DEFAULT_VOICE=zh_female_vv_jupiter_bigtts

REALTIME_VOICE_MAX_GLOBAL_SESSIONS=5
REALTIME_VOICE_MAX_SESSION_SEC=1200
REALTIME_VOICE_IDLE_CLOSE_SEC=540
REALTIME_VOICE_TOOL_TIMEOUT_SEC=8
REALTIME_VOICE_CONFIRM_TTL_SEC=120
REALTIME_VOICE_TICKET_TTL_SEC=60
REALTIME_VOICE_STORE_TRANSCRIPT=true
REALTIME_VOICE_STORE_AUDIO=false
REALTIME_VOICE_MAX_TOOL_RESULT_CHARS=4000
```

约束：

- 关闭 Feature Flag 时 ticket 接口返回明确的 `503`。
- 启动时不得打印 API Key。
- 生产环境不允许 `REALTIME_VOICE_STORE_AUDIO=true`。
- 官方默认 StartSession QPM 为 60、TPM 为 10 万；应用侧还需设置更低的并发上限。

---

## 7. 音频协议

### 7.1 输入

- PCM、单声道、16000 Hz、int16、小端序。
- 推荐每包 20 ms，即 640 字节原始 PCM。
- 客户端转 Base64 后作为 JSON 文本事件发送。
- 首版不接受 MP3/M4A 文件上传式输入。
- `speech_opus` 作为 P1，避免首版同时处理两套编码。

### 7.2 输出

- 首版要求豆包返回 PCM、单声道、24000 Hz、int16、小端序。
- 后端不解码音频，只校验事件和转发 Base64。
- 客户端使用播放缓冲队列，不能每个 chunk 创建一个独立播放器。

### 7.3 不持久化音频

后端只保存：

- ASR 完成文本。
- 模型回复完成文本。
- 工具调用与结果摘要。
- 用量、时延和错误元数据。

不保存：

- 原始麦克风 PCM。
- 模型返回 PCM。
- Base64 音频事件。

---

## 8. Avalin 客户端 WebSocket 协议

不要把豆包事件原样暴露给前端。使用供应商无关的 Avalin 事件。

### 8.1 客户端上行事件

#### `session.start`

```json
{
  "type": "session.start",
  "eventId": "evt-client-1",
  "voice": "zh_female_vv_jupiter_bigtts",
  "resumeSessionId": null
}
```

#### `audio.append`

```json
{
  "type": "audio.append",
  "eventId": "evt-audio-1",
  "audio": "<base64 pcm>"
}
```

#### `audio.commit`

用户主动结束一段话时发送。VAD 正常时可不依赖该事件，但按键说话模式必须发送。

```json
{"type":"audio.commit","eventId":"evt-commit-1"}
```

#### `response.cancel`

```json
{"type":"response.cancel","eventId":"evt-cancel-1"}
```

#### `confirmation.resolve`

```json
{
  "type": "confirmation.resolve",
  "eventId": "evt-confirm-1",
  "confirmationId": "confirm-uuid",
  "decision": "approve"
}
```

`decision` 仅允许 `approve` 或 `reject`。

#### `session.close`

```json
{"type":"session.close","eventId":"evt-close-1"}
```

### 8.2 服务端下行事件

统一字段：

```json
{
  "type": "event.type",
  "eventId": "server-event-id",
  "sessionId": "avalin-session-id",
  "timestamp": 1787000000000
}
```

事件列表：

| 事件 | 关键字段 | 用途 |
|---|---|---|
| `session.ready` | `providerSessionId` | 可以开始发送音频 |
| `session.state` | `state` | listening/thinking/speaking 等 |
| `asr.started` |  | 用户开始说话，可立即停止本地播报 |
| `asr.delta` | `text` | 实时字幕 |
| `asr.done` | `text`, `itemId` | 用户完整一句话 |
| `assistant.text.delta` | `text` | 回复字幕 |
| `assistant.text.done` | `text`, `itemId` | 完整回复 |
| `assistant.audio.started` | `ttsType` | 准备播放 |
| `assistant.audio.delta` | `audio`, `sequence` | 24k PCM |
| `assistant.audio.done` | `statusCode` | 一轮播报结束 |
| `tool.started` | `toolCallId`, `name` | 显示执行状态 |
| `tool.result` | `name`, `display` | 展示证据或任务结果 |
| `confirmation.required` | `confirmation` | 用户确认面板 |
| `navigation.suggested` | `path`, `label` | 前端决定是否跳转 |
| `response.done` | `usage`, `latency` | 一轮结束 |
| `response.canceled` |  | 打断成功 |
| `session.reconnecting` | `attempt` | 5xx 恢复 |
| `session.closed` | `reason`, `summary` | 正常结束 |
| `error` | `code`, `message`, `recoverable` | 错误 |

### 8.3 会话状态机

```text
idle
  -> connecting
  -> ready
  -> listening
  -> thinking
  -> speaking
  -> listening

speaking -> interrupted -> listening
thinking/speaking -> tool_running -> thinking/speaking
tool_running -> awaiting_confirmation -> tool_running
any_active -> reconnecting -> ready
any_active -> closing -> closed
any_active -> error
```

后端必须校验状态。例如在 `closed` 状态收到 `audio.append` 时返回不可恢复错误，而不是静默丢弃。

---

## 9. 豆包 Provider 映射

### 9.1 Session Create

上游固定：

```json
{
  "type": "session.create",
  "session": {
    "type": "realtime",
    "model": "1.2.6.1",
    "instructions": "<Avalin prompt>",
    "audio": {
      "input": {"format": {"type": "pcm", "rate": 16000}},
      "output": {
        "format": {"type": "pcm_s16le", "rate": 24000},
        "voice": "<configured voice>",
        "speed": 0,
        "loudness": 0
      }
    },
    "tools": ["<tool schemas>"]
  },
  "extension": {
    "asr": {},
    "tts": {},
    "dialog": {}
  }
}
```

### 9.2 下行映射

| 豆包事件 | Avalin 事件 |
|---|---|
| `session.created` | `session.ready` |
| `conversation.item.input_audio_transcription.started` | `asr.started` |
| `...transcription.delta` | `asr.delta` |
| `...transcription.completed` | `asr.done` |
| `response.output_text.delta` | `assistant.text.delta` |
| `response.output_text.done` | `assistant.text.done` |
| `response.output_audio.started` | `assistant.audio.started` |
| `response.output_audio.delta` | `assistant.audio.delta` |
| `response.output_audio.done` | `assistant.audio.done` |
| `response.function_call_arguments.done` | Tool Router |
| `response.done` | `response.done` |
| `response.canceled` | `response.canceled` |
| `error` | `error` |

### 9.3 Function Call 回传

每个豆包 `call_id` 必须原样回传：

```json
{
  "type": "conversation.item.create",
  "items": [
    {
      "call_id": "<provider call id>",
      "role": "tool",
      "content": [
        {
          "type": "input_text",
          "text": "{\"ok\":true,\"data\":{...}}"
        }
      ]
    }
  ]
}
```

一次事件可能包含多个 Function Call。后端需：

1. 分别校验每个调用。
2. 只并行执行只读工具，最大并发 3。
3. 聚合所有结果后一次回传。
4. 任何结果都必须带原 `call_id`。

---

## 10. 分身系统提示词

核心约束：

```text
你是 Avalin 中由用户长期记忆逐渐形成的 AI 分身。

1. 你可以自然交谈，但涉及用户过去经历时，必须先调用记忆工具。
2. 没有检索到证据时，明确说“我没有找到对应记录”，不得补写。
3. 记忆工具返回的 title/date/snippet 是证据；回答时简洁引用日期或标题。
4. 用户表达找人目的时，先整理草稿。缺少时间、地点、活动或关系目的时，最多追问 3 个关键问题。
5. “每天想看电影”等表达有歧义时必须确认频率与具体时间。
6. 搜索公开信息、发布帖子、申请认识、接受关系是不同权限。
7. 你不能替用户发布、申请、接受关系、交换联系方式、支付或承诺见面。
8. 工具返回失败时如实说明，不得声称已经完成。
9. 回复要适合语音：短句、自然停顿、先结论后细节，默认不超过 100 个汉字。
10. 当用户开始说话时立即停止当前播报。
```

提示词中不注入所有长期记忆。长期记忆只能按需通过 Tool 获取，避免 12K 上下文被静态画像占满。

---

## 11. Tool Router

### 11.1 风险等级

| 级别 | 含义 | 执行策略 |
|---|---|---|
| R0 | 只读 | 自动执行 |
| R1 | 私有、可撤销草稿 | 自动执行，前端可见 |
| R2 | 私有业务动作或 Agent 行动 | 必须明确确认 |
| R3 | 公开、关系、支付、线下承诺 | 不向实时模型暴露，只返回页面入口 |

### 11.2 P0 工具

#### `search_personal_memory`，R0

参数：

```json
{
  "query": "大通湖 晚霞",
  "sourceTypes": ["diary", "material"],
  "topK": 4
}
```

执行：

```python
retrieve_memories(
    db,
    user_id=current_user.id,
    query=query,
    scenario="chat",
    top_k=min(top_k, 6),
    source_types=validated_source_types,
)
```

返回：

```json
{
  "items": [
    {
      "documentId": "...",
      "sourceType": "diary",
      "sourceId": "<diary id>",
      "title": "同一片晚霞",
      "snippet": "傍晚在湖边拍到...",
      "occurredAt": 1786800000000,
      "score": 0.91,
      "deepLink": "/pages/diary/detail?id=<diary id>"
    }
  ]
}
```

规则：

- 最多 6 条。
- 单条 snippet 最多 240 字。
- 不返回完整私密日记。
- 只允许当前用户数据。
- Tool Result 给模型；`display` 事件给前端展示证据。

#### `get_memory_document`，R0

只允许获取上一次 `search_personal_memory` 返回过的 `documentId`，防止模型枚举任意 ID。

返回标题、日期、最多 800 字内容和 Deep Link。

#### `draft_social_mission`，R0

参数：

```json
{"text":"今天晚上想找一个人看科幻电影"}
```

复用 `mission_service.parse_mission_text()`，不写数据库。

返回：

- `draft`
- `inferredFields`
- `questions`
- 前端可展示的 `summary`

如果 `questions` 非空，模型必须先追问，不能直接创建任务。

#### `create_social_mission_draft`，R1

只有 `draft_social_mission` 已在当前会话生成合法草稿时可调用。

复用 `mission_service.create_mission()`，状态固定 `draft`，权限强制：

```json
{
  "autoPublish": false,
  "autoConnect": false
}
```

#### `start_social_mission`，R2

参数：

```json
{
  "missionId": "...",
  "confirmationToken": "..."
}
```

执行 `mission_service.start_mission()`。

确认要求：

- Token 由后端在任务摘要展示后生成。
- 不允许在创建草稿的同一用户话轮中使用。
- 120 秒过期。
- 绑定 `user_id + mission_id + draft_hash + action`。
- 执行后立即失效。

#### `list_social_missions`，R0

返回最多 10 条任务，字段限制为：

- id
- title
- mode
- status
- candidateCount
- pendingCount
- updatedAt
- deepLink

#### `get_social_mission_progress`，R0

返回任务摘要、候选数量、待决定数量、最多 3 个候选摘要和页面 Deep Link。

#### `open_app_page`，R0

不直接控制客户端，只返回 `navigation.suggested`。

允许路由白名单：

- `/pages/index/index`
- `/pages/chat/index`
- `/pages/social/index`
- `/pages/social/find`
- `/pages/social/mission-detail`
- `/pages/diary/detail`
- `/pages/profile/avatar-memory`

路由参数必须由后端根据已授权资源生成，模型不能传任意 URL。

### 11.3 P1 工具

- `create_private_memory_note`，R1
- `pause_social_mission`，R2
- `resume_social_mission`，R2
- `request_atoa_probe`，R2，必须异步入队
- `continue_atoa_probe`，R2
- `get_atoa_probe_summary`，R0

### 11.4 明确禁止暴露的工具

- `publish_mission_post`
- `connect_candidate`
- `accept_match`
- `reject_match`
- `send_social_message`
- `share_contact`
- 任意支付、定位精确地址或外部系统写操作

模型可以建议用户打开对应页面，但不能执行。

---

## 12. 确认机制

### 12.1 确认对象

```json
{
  "id": "confirm-uuid",
  "action": "start_social_mission",
  "riskLevel": "R2",
  "title": "开始寻找今晚的电影搭子？",
  "summary": [
    "活动：看科幻电影",
    "时间：今晚",
    "地点：南开大学附近 5 km",
    "范围：公开帖子与授权名片"
  ],
  "expiresAt": 1787000120000,
  "approveLabel": "确认开始",
  "rejectLabel": "再改一下"
}
```

### 12.2 两种确认路径

1. 屏幕点击：客户端发送 `confirmation.resolve`。
2. 下一语音话轮明确确认：模型携带后端签发的 `confirmationToken` 调用工具。

安全约束：

- “嗯”“可以吧”“随便”等弱肯定不视为确认。
- 不允许在工具草稿生成的同一话轮执行 R2。
- 过期、重复、摘要已变化的确认全部拒绝。
- 确认拒绝后保留草稿，但不搜索。

---

## 13. 数据模型

### 13.1 `realtime_voice_sessions`

| 字段 | 类型 | 说明 |
|---|---|---|
| id | String PK | Avalin 会话 ID |
| user_id | FK users | 所属用户 |
| chat_session_id | FK chat_sessions nullable | 对应文本对话段 |
| provider | String | `volcengine_duplex` |
| provider_session_id | String | 豆包 session.id |
| status | String | connecting/active/closed/error |
| client_platform | String | h5/app-android |
| input_format | String | pcm_16k_s16le |
| output_format | String | pcm_24k_s16le |
| voice | String | 音色 |
| started_at | BigInteger | 开始时间 |
| ended_at | BigInteger nullable | 结束时间 |
| last_active_at | BigInteger | 最近音频或事件时间 |
| close_reason | String | user/idle/network/error/max_duration |
| provider_log_id | String | X-Tt-Logid |
| usage_json | Text | token/音频用量 |
| error_code | String | 最后错误码 |
| created_at | BigInteger | 创建时间 |
| updated_at | BigInteger | 更新时间 |

索引：

- `(user_id, created_at)`
- `(status, last_active_at)`
- `provider_session_id`

### 13.2 `realtime_tool_calls`

| 字段 | 类型 | 说明 |
|---|---|---|
| id | String PK | 内部工具调用 ID |
| voice_session_id | FK | 实时会话 |
| user_id | FK | 用户 |
| provider_call_id | String | 豆包 call_id |
| tool_name | String | 工具名 |
| arguments_json | Text | 校验后参数 |
| risk_level | String | R0-R3 |
| status | String | received/awaiting_confirmation/running/succeeded/failed/rejected/expired |
| result_json | Text | 裁剪后的结果 |
| confirmation_id | String nullable | 确认 ID |
| idempotency_key | String | 幂等键 |
| error_message | Text | 错误 |
| created_at/updated_at/finished_at | BigInteger | 生命周期 |

唯一约束：

```text
(voice_session_id, provider_call_id)
```

### 13.3 Transcript

复用：

- `ChatSession`
- `ChatMessage`

规则：

- `asr.done` 保存为 `role=user`。
- `assistant.text.done` 保存为 `role=assistant`。
- delta 不落库。
- 相同 provider item ID 必须幂等。
- 会话正常或异常关闭后，按当前用户设置调用 `close_and_materialize`。

---

## 14. 并发与异步设计

单次连接包含三个协程：

```text
client_reader       客户端 -> 上游
provider_reader     上游 -> 客户端 / Tool Router
session_watchdog    超时 / 心跳 / 关闭
```

Python 3.9 使用 `asyncio.create_task` + `asyncio.wait`，不使用 `TaskGroup`。

数据库约束：

- 不跨协程共享同一个 SQLAlchemy Session。
- 每个 Tool Call 从 `SessionLocal()` 获取独立会话。
- Tool 完成后立即 close。
- 只读工具最多并行 3 个。
- 写工具串行执行。

背压：

- 客户端输入队列最多缓存 100 个 20 ms 帧，即约 2 秒。
- 超过阈值先发送 `client.slow_down`，持续增长则关闭连接。
- 输出音频不在后端长期排队；客户端必须及时消费。

---

## 15. 重连与关闭

### 15.1 5xx

- 最多自动重连 2 次。
- 退避：1 秒、2 秒。
- 使用上一次 `provider_session_id` 尝试接续。
- 不重放已提交音频。
- 前端收到 `session.reconnecting`。

### 15.2 4xx

鉴权、参数、音色错误不自动重试，返回不可恢复错误。

### 15.3 空闲与最长时长

- 官方超过 10 分钟无交互会释放连接。
- Avalin 在 9 分钟空闲时主动优雅关闭。
- 首版单次通话最长 20 分钟。
- 前端进入后台超过 30 秒关闭会话。

### 15.4 优雅关闭

必须：

1. 向豆包发送 `session.close`。
2. 等待 `session.closed`，最多 3 秒。
3. 再关闭上游 WebSocket。
4. 完成 transcript 与 usage 落库。
5. 向客户端发送 `session.closed`。

---

## 16. 可观测性

### 16.1 日志字段

- `voice_session_id`
- `user_id_hash`
- `provider_session_id`
- `event_id`
- `provider_call_id`
- `tool_name`
- `tool_status`
- `provider_log_id`
- `latency_ms`
- `error_code`

禁止记录：

- API Key
- JWT / ticket
- 原始 Base64 音频
- 完整私密日记
- 完整 Tool arguments 中的敏感字段

### 16.2 指标

- 活跃实时会话数
- Session Create 成功率和 P50/P95
- 首个 ASR delta 时延
- 用户停说到首个回复音频时延
- 打断确认时延
- Tool Call 成功率与 P95
- RAG 命中率、无结果率
- Mission 草稿确认率
- 5xx 重连率
- 非正常关闭率

### 16.3 产品目标值

以下是 Avalin 工程目标，不是上游 SLA：

- Session Ready P95 < 2.5 秒。
- 正常网络下停说到首音频 P95 < 2.0 秒。
- `search_personal_memory` P95 < 1.2 秒。
- `draft_social_mission` P95 < 500 ms。
- 客户端打断到停止播放 < 300 ms。
- 工具越权执行次数为 0。

---

## 17. 安全与隐私

1. RAG 固定 `user_id=current_user.id`，模型不可传 user ID。
2. `sourceTypes` 使用白名单。
3. `documentId` 必须来自本会话最近一次 RAG 结果。
4. Tool 参数使用 Pydantic 严格 Schema，拒绝未知字段。
5. Tool Result 长度上限 4000 字符。
6. 页面路径使用后端白名单，不允许外链。
7. R2 使用一次性确认 Token。
8. R3 工具不注册到豆包 Session。
9. 不存原始音频。
10. 通话转素材遵循用户现有 `chat_material_enabled` 设置。
11. 对外 AtoA 仍只能读取 `AvatarCard` 和任务授权摘要，不能读取本次通话原文。

---

## 18. Nginx 与部署

`/ws/` 调整：

```nginx
location /ws/ {
    proxy_pass http://$backend_upstream;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_buffering off;
    proxy_read_timeout 900s;
    proxy_send_timeout 900s;
}
```

部署约束：

- 首版继续使用单个 Uvicorn Worker。
- 最大实时通话并发默认 5。
- AtoA Worker 与实时语音连接互相独立。
- 生产前确认服务器到 `openspeech.bytedance.com:443` 的 WSS 连通性。
- Health API 增加配置就绪状态，不主动创建上游会话。

建议：

```http
GET /api/realtime-voice/health
```

返回 Feature Flag、配置状态、当前会话数和并发上限，不返回 Key。

---

## 19. 测试策略

### 19.1 单元测试

- Ticket 签发、过期和重放。
- 客户端事件 Schema 校验。
- 豆包事件到 Avalin 事件映射。
- Function Call 多调用聚合与 `call_id` 配对。
- Tool 风险等级和白名单。
- RAG 结果裁剪与 Deep Link。
- Mission 歧义问题和确认 Token。
- Tool 幂等。
- 日志脱敏。

### 19.2 Provider Fake

实现 `FakeRealtimeVoiceProvider`，可脚本化输出：

- 正常 ASR/Text/Audio。
- Function Call。
- 多个并行 Function Call。
- 用户打断。
- 5xx 后恢复。
- 4xx 鉴权失败。
- 上游超时。
- 非正常关闭。

自动化测试不得依赖真实火山 API。

### 19.3 集成测试

使用 FastAPI `TestClient.websocket_connect`：

1. 获取 ticket。
2. 建立 WS。
3. 发送 `session.start`。
4. 发送模拟 PCM。
5. 收到字幕和音频事件。
6. 触发记忆工具并验证只返回当前用户数据。
7. 触发找人草稿。
8. 验证未确认不能启动。
9. 确认后创建并启动任务。
10. 关闭会话并验证 ChatMessage 落库。

### 19.4 真实 API 冒烟

仅手动运行，使用独立脚本：

```text
scripts/realtime_voice_smoke.py
```

脚本不进入常规 CI，不打印 Key，不保存音频。

---

## 20. 验收场景

### 20.1 记忆场景

用户说：

> 你还记得我上次在大通湖拍晚霞吗？

验收：

- 模型调用 `search_personal_memory`。
- 不命中时明确说没有找到。
- 命中时回答包含日期或日记标题。
- 前端收到至少一条证据卡片。
- 点击证据可打开正确日记。
- 不返回其他用户数据。

### 20.2 找电影搭子

用户说：

> 今天晚上想找一个人看科幻电影。

验收：

- 模型先调用 `draft_social_mission`。
- 生成短期 `movie` 草稿。
- 屏幕展示时间、地点、人数和权限摘要。
- 未确认时数据库没有 searching 任务。
- 用户确认后创建任务并开始搜索。
- 模型只汇报真实候选数。
- 不自动发布帖子，不自动申请认识。

### 20.3 歧义场景

用户说：

> 我每天想去看电影，帮我找搭子。

验收：

- 分身询问是“今天”“固定周期”还是“最近经常”。
- 在时间和频率确认前不启动任务。

### 20.4 打断

- AI 播报时用户开口。
- 客户端立即停止本地播放。
- 后端向上游发送 `response.cancel`。
- 收到 `response.canceled`。
- 用户新一句话被正常识别。

### 20.5 权限

用户说：

> 直接帮我发帖并替我接受第一个人。

验收：

- 模型不能调用对应工具。
- 分身解释必须由本人确认。
- 可以建议打开任务或广场页面。

---

## 21. 实施分期

### P0：实时通话骨架

- Ticket。
- WebSocket Gateway。
- 豆包 Provider。
- PCM 收发。
- 字幕、音频、打断。
- transcript 落库。
- Fake Provider 测试。

### P1：记忆 RAG

- `search_personal_memory`。
- `get_memory_document`。
- 证据事件。
- Deep Link。
- 记忆越权测试。

### P2：语音找人

- `draft_social_mission`。
- `create_social_mission_draft`。
- `start_social_mission`。
- 确认 Token。
- 任务进度查询。

### P3：AtoA 与稳定性

- 异步 `request_atoa_probe`。
- AtoA 摘要。
- 重连、指标、并发保护。
- vivo Android 原生音频验证。

---

## 22. Definition of Done

- 所有新增配置均有 example 和启动校验。
- 前端永远拿不到火山 API Key。
- 实时模型不能执行任何 R3 行为。
- RAG 有来源证据且无跨用户泄漏。
- Mission 未确认不能进入 searching。
- 打断和优雅关闭可验证。
- Fake Provider 覆盖成功、工具、重连、错误路径。
- 单元测试、集成测试和现有测试全部通过。
- Nginx 支持 15 分钟 WebSocket。
- 文档中的事件、Schema 和实际代码一致。
