# 日迹 App — RESTful API 接口文档

> **本文档从实际代码提取，记录所有已注册路由的完整信息。**
>
> 最后更新：2026-04-17
>
> Base URL: `http://localhost:8000/api`

---

## 全局约定

### 统一响应格式

所有接口返回 JSON，结构如下：

```json
{
  "code": 0,
  "data": { ... },
  "message": "ok"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| code | number | `0` = 成功，非 0 = 错误（见错误码表） |
| data | any | 业务数据 |
| message | string | 提示信息 |

### 错误码

| 错误码 | 常量名 | 说明 |
|--------|--------|------|
| 40001 | AUTH_USERNAME_EXISTS | 用户名已存在 |
| 40002 | AUTH_INVALID_CREDENTIALS | 用户名或密码错误 |
| 40003 | AUTH_UNAUTHORIZED | 未授权（未登录） |
| 40004 | AUTH_TOKEN_EXPIRED | Token 过期 |
| 40101 | PARAM_INVALID | 参数无效 |
| 40102 | PARAM_ERROR | 参数错误（如超过限制） |
| 40201 | BUSINESS_ERROR | 业务错误 |
| 40202 | NOT_FOUND | 资源不存在 |
| 50001 | SERVER_ERROR | 服务器内部错误 |
| 50101 | AI_SERVICE_ERROR | AI 服务错误 |

### 认证方式

- JWT Bearer Token
- 请求头：`Authorization: Bearer <token>`
- 登录/注册接口无需认证，其余接口均需认证（标注 🔒）

### 分页约定

分页接口使用 query 参数 `page`（默认 1）和 `page_size`（默认 10），返回：

```json
{ "items": [...], "total": 42 }
```

### 时间戳

所有时间字段为 **Unix 毫秒时间戳**（number）。日期字符串格式 `"YYYY-MM-DD"`。

### 字段命名

响应字段默认使用 **camelCase**（如 `userId`、`createdAt`）。请求 body 以各接口 schema 为准：

- 历史业务接口仍以 **snake_case** 为主
- 新聊天链路（如 `/api/chat`、`/api/chat/stream`）已使用 **camelCase** 字段，如 `clientMessageId`、`thumbnailUrl`

> 兼容说明：
> 1. `GET /api/diaries/today-summary` 当前实现返回 snake_case（如 `material_count`、`has_diary`）。
> 2. SSE 事件体中的字段同样使用 camelCase。

---

## 1. 认证模块（Auth）

### POST /api/auth/register — 用户注册

**认证：** 无需

**请求 Body：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| username | string | ✅ | 用户名（4-20 字符） |
| password | string | ✅ | 密码（6-32 字符） |
| name | string | ❌ | 昵称（默认同 username） |
| school | string | ❌ | 学校 |
| major | string | ❌ | 专业 |

**响应 data：**

```json
{
  "token": "eyJhbGciOi...",
  "user": {
    "id": "uuid",
    "username": "kylin",
    "name": "麒麟",
    "school": "南开大学",
    "major": "软件工程",
    "avatar": "",
    "level": 1
  }
}
```

**实现状态：** ✅ 已完成

---

### POST /api/auth/login — 用户登录

**认证：** 无需

**请求 Body：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| username | string | ✅ | 用户名 |
| password | string | ✅ | 密码 |

**响应 data：** 同注册响应

**实现状态：** ✅ 已完成

---
## 2. 用户模块（User）

### GET /api/user/profile — 获取用户资料 🔒

**响应 data：**

```json
{
  "name": "麒麟",
  "school": "南开大学",
  "major": "软件工程",
  "level": 1,
  "diaryCount": 5,
  "streakDays": 3,
  "pomodoroCount": 10,
  "avatar": "/uploads/xxx/avatar/xxx.jpg",
  "styleTags": ["文艺", "温暖"],
  "customStylePrompt": ""
}
```

**实现状态：** ✅ 已完成

---

### POST /api/user/profile — 更新用户资料 🔒

**请求 Body（所有字段可选）：**

| 字段 | 类型 | 说明 |
|------|------|------|
| name | string | 昵称 |
| school | string | 学校 |
| major | string | 专业 |
| avatar | string | 头像 URL |
| style_tags | string[] | 写作风格标签 |
| custom_style_prompt | string | 自定义风格提示词 |

**响应 data：** 同 GET /api/user/profile

**实现状态：** ✅ 已完成

---

### GET /api/user/growth — 获取成长数据 🔒

**响应 data：**

```json
{
  "diaries": [...],
  "emotions": [...],
  "tags": [...],
  "pomodoros": [...],
  "streak": [...]
}
```

**实现状态：** ✅ 已完成

---

### GET /api/user/achievements — 获取成就列表 🔒

**响应 data：** 裸数组

```json
[
  {
    "id": "first_diary",
    "title": "初心",
    "description": "写下第一篇日记",
    "icon": "📝",
    "unlocked": true,
    "unlockedAt": 1711356000000
  }
]
```

**实现状态：** ✅ 已完成

---

### GET /api/user/settings — 获取用户设置 🔒

**响应 data：**

```json
{
  "theme": "light",
  "notifications": true,
  "autoBGM": false,
  "diaryPrivacy": "private",
  "language": "zh-CN",
  "chatMaterialEnabled": true,
  "chatSilenceThreshold": 30,
  "chatMaterialToast": true,
  "chatMinRounds": 3
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| chatMaterialEnabled | bool | 对话自动转素材开关（默认 true） |
| chatSilenceThreshold | int | 静默阈值（分钟，默认 30） |
| chatMaterialToast | bool | toast 提示开关（默认 true） |
| chatMinRounds | int | 最小对话轮数（user 消息数，默认 3） |

**实现状态：** ✅ 已完成

---

### POST /api/user/settings — 更新用户设置 🔒

**请求 Body（所有字段可选）：**

| 字段 | 类型 | 说明 |
|------|------|------|
| theme | string | 主题（"light" / "dark"） |
| notifications | bool | 通知开关 |
| auto_bgm | bool | 自动 BGM |
| diary_privacy | string | 日记隐私（"private" / "friends" / "public"） |
| language | string | 语言 |
| chat_material_enabled | bool | 对话自动转素材开关 |
| chat_silence_threshold | int | 静默阈值（分钟，15~120） |
| chat_material_toast | bool | toast 提示开关 |
| chat_min_rounds | int | 最小轮数（1~20） |

**响应 data：** 同 GET /api/user/settings

**实现状态：** ✅ 已完成

---

### GET /api/user/semester-report — 获取学期报告 🔒

**响应 data：**

```json
{
  "totalDiaries": 42,
  "totalPomodoros": 100,
  "topEmotions": [...],
  "topTags": [...],
  "writingTime": 3600,
  "avgEmotion": 4,
  "streak": 7,
  "achievements": 5,
  "highlights": [...]
}
```

**实现状态：** ✅ 已完成

---

### GET /api/user/portrait — 获取用户 AI 画像 🔒

**响应 data：**

```json
{
  "preferences": [{"category": "food", "items": ["日料"]}],
  "personality": ["开朗", "细腻"],
  "relations": [{"name": "小明", "relation": "室友"}],
  "interests": ["读书", "散步"]
}
```

**实现状态：** ✅ 已完成

---

### POST /api/user/portrait/refresh — 刷新用户画像（AI） 🔒

调用 MiniMax AI 分析日记 + 聊天记录，生成/更新用户画像。

**请求 Body：** 无

**响应 data：** 同 GET /api/user/portrait

**实现状态：** ✅ 已完成（调用 minimax_client.generate_portrait）

---

### GET /api/user/agent-portrait — 获取 AI 画像图 🔒

调用 MiniMax 图片生成 API，根据用户画像生成一张水彩插画。

**请求 Body：** 无

**响应 data：** 图片 URL（string）

**实现状态：** ✅ 已完成（调用 minimax_client.generate_image）

---

## 3. 素材模块（Material）

### POST /api/materials — 创建素材 🔒

**请求 Body：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| type | string | ✅ | "image" / "voice" / "text" / "chat"（自动生成，前端无需手动传） |
| content | string | ❌ | 文字内容 |
| media_url | string[] | ❌ | 媒体文件 URL 数组（先调 /upload 获得，可多图） |
| thumbnail_url | string[] | ❌ | 缩略图 URL 数组（与 media_url 对齐） |
| location | object | ❌ | 位置信息 `{lat, lng, ...}` |
| emotion | object | ❌ | 情绪 `{label, score, emoji}`，空则自动 AI 提取 |
| tags | string[] | ❌ | 标签 |
| date | string | ❌ | 日期 YYYY-MM-DD（默认今天） |

**响应 data（普通类型）：**

```json
{
  "id": "uuid",
  "userId": "uuid",
  "type": "text",
  "content": "今天阳光真好",
  "mediaUrl": [],
  "thumbnailUrl": [],
  "location": {},
  "emotion": {"label": "开心", "score": 0.88, "emoji": "😊"},
  "tags": ["校园"],
  "date": "2026-03-26",
  "createdAt": 1711440000000,
  "chatSessionId": null,
  "startTime": null,
  "endTime": null
}
```

**响应 data（chat 类型，自动生成）：**

```json
{
  "id": "uuid",
  "userId": "uuid",
  "type": "chat",
  "content": "和 AI 聊了骑行路线，探讨了运动习惯...",
  "mediaUrl": [],
  "thumbnailUrl": [],
  "location": {},
  "emotion": {"label": "开心", "score": 0.8, "emoji": "😊"},
  "tags": ["运动", "日常"],
  "date": "2026-03-26",
  "createdAt": 1711440000000,
  "chatSessionId": "session-uuid",
  "startTime": 1711440180000,
  "endTime": 1711440900000
}
```

**实现状态：** ✅ 已完成

**情绪提取补充说明：**

- 当 `emotion` 为空且 `content` 有值时，会自动触发情绪提取并写回。
- 输出标签会归一到固定集合：`开心 / 难过 / 愤怒 / 平静 / 感动 / 焦虑 / 期待 / 无聊`。
- 当模型返回异常或 JSON 不可解析时，后端会基于文本关键词做兜底判断（例如“想哭”优先识别为“难过”），不再一律回退为“平静”。

---

### GET /api/materials — 素材列表 🔒

**Query 参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| date | string | 按日期筛选（YYYY-MM-DD），可选 |

**响应 data：** 裸数组 `[MaterialOut, ...]`

**实现状态：** ✅ 已完成

---

### GET /api/materials/{material_id} — 素材详情 🔒

**响应 data：** MaterialOut 对象

**实现状态：** ✅ 已完成

---

### PUT /api/materials/{material_id} — 编辑素材 🔒

**请求 Body（所有字段可选）：**

| 字段 | 类型 | 说明 |
|------|------|------|
| content | string | 文字内容 |
| media_url | string[] | 媒体 URL 数组 |
| thumbnail_url | string[] | 缩略图数组 |
| location | object | 位置 |
| emotion | object | 情绪 |
| tags | string[] | 标签 |

**响应 data：** 更新后的 MaterialOut

**实现状态：** ✅ 已完成

---

### DELETE /api/materials/{material_id} — 删除素材 🔒

**响应 data：** null

**实现状态：** ✅ 已完成

---

### POST /api/materials/{material_id}/emotion — AI 情绪提取 🔒

对指定素材调用 AI 提取情绪，结果写回数据库。

**请求 Body：** 无

**响应 data：** `{"label": "开心", "score": 0.88, "emoji": "😊"}`

**实现状态：** ✅ 已完成（调用 minimax_client.extract_emotion）

**行为说明：**

- 若模型返回 `悲伤` 等同义标签，会统一规范为 `难过`。
- `score` 支持 0~1 与 0~100 两种输入，服务端会统一归一到 0~1。

---

### POST /api/materials/{material_id}/polish — AI 文字润色 🔒

**请求 Body：**

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| style | string | "文艺" | 风格："文艺" / "幽默" / "简洁" / "温暖" |

**响应 data：** `{"polished": "润色后的文字"}`

**实现状态：** ✅ 已完成（调用 minimax_client.polish_text）

---

### POST /api/materials/voice — 语音上传与转写 🔒

**Content-Type：** multipart/form-data

**请求参数：**

| 字段 | 类型 | 说明 |
|------|------|------|
| file | File | 语音文件（mp3/wav/m4a/ogg，最大 20MB） |

**响应 data：**

```json
{
  "url": "/uploads/xxx/voice/20260414_xxx.m4a",
  "transcription": "这是一段语音记录，原文件名是《morning-note》。"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| url | string | 已上传语音文件 URL |
| transcription | string | 当前返回转写文本，用于前端回填输入框 |

**使用场景：**
- 素材录制页录音转文字
- AI 对话页语音输入转文字

**实现状态：** 🟡 已实现上传链路；当前转写文本为 fallback 文案，尚未接入真实 ASR 服务

---

## 4. 日记模块（Diary）

### GET /api/diaries/today-summary — 今日概要 🔒

**Query 参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| date | string | ✅ | 日期 YYYY-MM-DD |

**响应 data：**

```json
{
  "date": "2026-03-26",
  "material_count": 3,
  "materials": [
    {
      "id": "uuid",
      "type": "text",
      "content": "今天阳光真好",
      "createdAt": 1711440000000,
      "emotion": {"label": "开心", "score": 0.88, "emoji": "😊"}
    }
  ],
  "has_diary": true,
  "diary_id": "uuid",
  "diary_status": "draft"
}
```

**实现状态：** ✅ 已完成

---

### POST /api/diaries/generate — AI 生成当日日记 🔒

**请求 Body：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| date | string | ✅ | 日期 YYYY-MM-DD |
| weather | string | ❌ | 天气（若传入“多云 18℃”会自动规范为“多云”） |
| allow_fallback | bool | ❌ | 无素材时是否允许兜底生成（默认 false） |

**响应 data：** DiaryOut 对象（含 AI 生成的 title、content、emotionSummary、imageUnderstandings）

**实现状态：** ✅ 已完成（调用 minimax_client.generate_diary）

**实现细节补充：**

- 同日期重复调用会更新同一篇日记（upsert），不会重复新建。
- 新建日记 `status` 初始值为 `draft`，`editCount=0`，`maxEdits=3`。
- 每晚 22:00 后，系统后台会自动补生成：当天有素材且尚未生成日记的用户，会自动触发一次生成。
- 当天 `type="chat"` 的素材会参与生成上下文，格式为 `[对话记录] (HH:MM~HH:MM) 摘要内容`。

**图片理解字段说明：**

- `POST /api/diaries/generate` 的请求体不直接接收图片字段。
- 日记生成使用的图片来源于当天素材（`raw_materials.media_url` / `mediaUrl`），即先通过素材接口上传并保存 URL，再在生成流程中读取。
- 当 `VIVO_VISION_ENABLED=true` 时，系统会对当天 image 素材执行视觉理解。
- 图片理解结果会注入到日记生成提示词中的 `[图片描述]` 上下文段落，并同时在响应字段 `imageUnderstandings` 中返回（数组类型，按图片顺序逐条返回，不去重）。
- 该字段会持久化保存到日记记录；后续通过 `GET /api/diaries`、`GET /api/diaries/{diary_id}`、`GET /api/diaries/search` 查询时会返回同一组结果。
- 图片理解失败会自动降级为“仅使用原素材文本继续生成日记”，不阻断主流程。

**图片理解复用调用（给后端开发）：**

- 单图调用：`app.ai.service.understand_image_text(image_url, prompt="", timeout_sec=None) -> str`
- 多图调用：`app.ai.service.understand_images_batch(image_urls, prompt="", timeout_sec=None, max_images=None) -> List[str]`
- 如需带原始 URL 的详细结构，可传：`include_image_url=True`，返回 `List[dict]`
- 多图底层调用优先使用 VIVO `chat/completions` 的单次多图输入格式（`content` 中多个 `image_url` + 一个 `text`）；若返回不可解析，会自动降级为逐图调用，保证可用性。

```python
from app.ai import service as ai_service

# 1) 单图
desc = await ai_service.understand_image_text(
  image_url="https://example.com/a.jpg",
  prompt="请客观描述图片内容",
)

# 2) 多图
items = await ai_service.understand_images_batch(
  image_urls=["https://example.com/a.jpg", "https://example.com/b.jpg"],
  prompt="请分别描述每张图",
)
# items 形如:
# ["...", "..."]
```

**VIVO 视觉理解配置说明（启用方式 + 推荐值）：**

| 环境变量 | 默认值 | 作用 | 推荐值 |
|------|------|------|------|
| VIVO_APP_KEY | 空 | VIVO AppKey | 必填 |
| VIVO_API_BASE | https://api-ai.vivo.com.cn | VIVO 接口地址 | 默认即可 |
| VIVO_VISION_MODEL | Doubao-Seed-2.0-mini | 图片理解模型（可用豆包） | 默认即可 |
| VIVO_VISION_ENABLED | true | 是否开启视觉理解 | true |
| VIVO_VISION_PROMPT | 见配置文件 | 视觉理解提示词模板 | 保持“客观+细节+禁臆测”风格 |
| VIVO_VISION_MAX_IMAGES | 10 | 单次生成最多识别图片数 | 6~10 |
| VIVO_VISION_TIMEOUT_SEC | 50 | 单张图片识别超时秒数 | 30~50 |
| VIVO_VISION_CACHE_TTL_SEC | 21600 | URL 级缓存有效期（秒） | 21600（6小时） |

**启用步骤（环境变量示例）：**

```env
MINIMAX_MOCK=false
LLM_PROVIDER=vivo
VIVO_APP_KEY=your-vivo-app-key
VIVO_API_BASE=https://api-ai.vivo.com.cn
VIVO_VISION_MODEL=Doubao-Seed-2.0-mini
VIVO_VISION_ENABLED=true
VIVO_VISION_MAX_IMAGES=10
VIVO_VISION_TIMEOUT_SEC=50
VIVO_VISION_CACHE_TTL_SEC=21600
```

---

### GET /api/diaries — 日记列表 🔒

**Query 参数：**

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| page | int | 1 | 页码 |
| page_size / pageSize | int | 10 | 每页条数（同时支持两种命名） |

**响应 data：** `{"items": [DiaryOut, ...], "total": 42}`

**实现状态：** ✅ 已完成

---

### GET /api/diaries/{diary_id} — 日记详情 🔒

**响应 data：** DiaryOut 对象

```json
{
  "id": "uuid",
  "userId": "uuid",
  "title": "平凡日子里的小确幸",
  "content": "今天是充实的一天...",
  "date": "2026-03-26",
  "weather": "晴",
  "specialDate": "",
  "emotionSummary": {
    "dominant": "平静",
    "trend": [{"hour": 9, "label": "平静", "score": 70}]
  },
  "materialIds": ["uuid1", "uuid2"],
  "style": "日记式",
  "editCount": 0,
  "maxEdits": 3,
  "status": "draft",
  "createdAt": 1711440000000,
  "updatedAt": 1711440000000,
  "emotion": {"emoji": "😊", "label": "平静", "score": 70},
  "images": [],
  "imageUnderstandings": [],
  "tags": [],
  "location": "",
  "hasComic": false,
  "hasBgm": false
}
```

**实现状态：** ✅ 已完成

---

### PUT /api/diaries/{diary_id} — 修改日记 🔒

检查 `editCount < maxEdits`，超出返回错误。

**请求 Body：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| content | string | ✅ | 修改后的日记内容 |

**响应 data：** 更新后的 DiaryOut

**实现状态：** ✅ 已完成

---

### GET /api/diaries/{diary_id}/emotion-trend — 当日情绪趋势 🔒

从关联素材聚合情绪数据。

**响应 data：**

```json
{
  "dominant": "开心",
  "trend": [
    {"hour": 9, "label": "开心", "score": 85},
    {"hour": 14, "label": "平静", "score": 70}
  ]
}
```

**实现状态：** ✅ 已完成

---

### POST /api/diaries/{diary_id}/extract — AI 提取信息 🔒

从日记内容提取纪念日、人物关系、偏好，写入数据库。

**请求 Body：** 无

**响应 data：**

```json
{
  "anniversaries": [{"title": "和朋友聚餐", "date": "03-25", "relatedPerson": "室友"}],
  "persons": [{"name": "小明", "relation": "室友", "mentions": 1}],
  "relations": [{"name": "小明", "relation": "室友", "mentions": 1}],
  "preferences": ["美食", "散步"]
}
```

**实现状态：** ✅ 已完成（调用 minimax_client.extract_info）

---

### POST /api/diaries/{diary_id}/derivative — 生成衍生内容 🔒

**请求 Body：**

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| type | string | "share_card" | "comic" / "novel" / "share_card" |

**响应 data：** DerivativeOut 对象

```json
{
  "id": "uuid",
  "diaryId": "uuid",
  "type": "share_card",
  "content": "...",
  "mediaUrl": "https://...",
  "shareScope": "private",
  "createdAt": 1711440000000
}
```

**实现状态：** ✅ 已完成（调用 minimax_client.generate_image / chat_completion）

---

### GET /api/diaries/search — 搜索日记 🔒

支持关键词、情绪、标签、天气、日期范围等多维度组合搜索。

**Query 参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| q | string | 否 | 关键词，匹配 title + content + location |
| emotion | string | 否 | 情绪标签，逗号分隔多选，如 emotion=开心,幸福 |
| tag | string | 否 | 标签筛选，逗号分隔多选 |
| weather | string | 否 | 天气筛选，逗号分隔多选 |
| from | string | 否 | 起始日期 YYYY-MM-DD |
| to | string | 否 | 结束日期 YYYY-MM-DD |
| page | int | 否 | 页码，默认 1 |
| page_size | int | 否 | 每页条数，默认 20 |

**响应 data：**

```json
{
  "items": [
    {
      "id": "uuid",
      "userId": "uuid",
      "title": "平凡日子里的小确幸",
      "content": "今天是充实的一天...",
      "date": "2026-03-26",
      "weather": "晴",
      "emotionSummary": {"dominant": "开心", "distribution": {"开心": 0.6}},
      "tags": ["校园", "美食"],
      "location": "南开大学",
      "imageUnderstandings": ["图书馆窗边晚霞，桌上有复习资料"],
      "createdAt": 1711440000000
    }
  ],
  "total": 42,
  "page": 1,
  "page_size": 20
}
```

**搜索逻辑：**

- **多条件组合**：多条件之间 AND 关系（所有条件必须同时满足）
- **同维度多选**：同维度内 OR 关系（emotion=开心,幸福 → 命中任一情绪即可）
- **q 关键词**：在 title/content/location 中模糊匹配（LIKE %q%）
- **emotion**：解析 emotion_summary JSON 字段的 dominant 值进行匹配，支持逗号分隔的多个情绪（IN 查询）
- **tag**：解析 tags JSON 数组，检查是否有交集（任一标签匹配即可）
- **weather**：对查询值先做“去温度”规范化后匹配；支持逗号分隔多值（同维度 OR），并兼容历史数据如 `多云 18℃`（搜索 `多云` 可命中）
- **from/to**：date 字段范围过滤（闭区间 BETWEEN）
- **排序**：结果按 created_at DESC 排序
- **空参数处理**：所有参数为空 = 不筛选（返回全部日记，仅分页）

<<**实现状态：** ✅ 已完成`r`n---

## 5. 衍生内容模块（Derivative）

### GET /api/derivatives — 衍生内容列表 🔒

**Query 参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| diary_id | string | 按日记 ID 筛选（可选） |

**响应 data：** 裸数组 `[DerivativeOut, ...]`

**实现状态：** ✅ 已完成

---

### POST /api/derivatives/{deriv_id}/share — 设置分享范围 🔒

**请求 Body：**

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| scope | string | "private" | "private" / "friends" / "public" |

**响应 data：** null

**实现状态：** ✅ 已完成

---

## 6. 纪念日模块（Anniversary）

### GET /api/anniversaries/today — 今日纪念日 + 那年今日 🔒

**响应 data：**

```json
{
  "today": [AnniversaryOut, ...],
  "on_this_day": [DiaryOut, ...]
}
```

**实现状态：** ✅ 已完成

---

### GET /api/anniversaries — 纪念日列表 🔒

**响应 data：** 裸数组

```json
[
  {
    "id": "uuid",
    "userId": "uuid",
    "title": "生日",
    "date": "03-25",
    "year": 2000,
    "source": "manual",
    "relatedPerson": "妈妈",
    "diaryId": null,
    "createdAt": 1711440000000
  }
]
```

**实现状态：** ✅ 已完成

---

### POST /api/anniversaries — 添加纪念日 🔒

**请求 Body：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| title | string | ✅ | 纪念日名称 |
| date | string | ✅ | 月-日，如 "03-25" |
| year | int | ❌ | 年份 |
| source | string | ❌ | "manual" / "ai_extracted"（默认 manual） |
| related_person | string | ❌ | 相关人物 |
| diary_id | string | ❌ | 关联日记 ID |

**响应 data：** AnniversaryOut

**实现状态：** ✅ 已完成

---

### PUT /api/anniversaries/{ann_id} — 编辑纪念日 🔒

**请求 Body（所有字段可选）：**

| 字段 | 类型 | 说明 |
|------|------|------|
| title | string | 名称 |
| date | string | 月-日 |
| year | int | 年份 |
| related_person | string | 相关人物 |

**响应 data：** 更新后的 AnniversaryOut

**实现状态：** ✅ 已完成

---

### DELETE /api/anniversaries/{ann_id} — 删除纪念日 🔒

**响应 data：** null

**实现状态：** ✅ 已完成

---

## 7. AI 功能模块（AI）

### POST /api/ai/tts — 文字转语音 🔒

**请求 Body：**

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| text | string | — | 要转换的文字 |
| voice | string | "female-shaonv" | 音色 ID |

**响应 data：** 音频文件 URL（string），如 `"/uploads/xxx/tts/xxx.mp3"`

**实现状态：** ✅ 已完成（调用 minimax_client.text_to_speech）

---

### GET /api/ai/fortune — AI 今日运势 🔒

**响应 data：**

```json
{
  "overall": 4,
  "study": 5,
  "social": 3,
  "health": 4,
  "tip": "今天适合专注学习！",
  "luckyColor": "暖橙色",
  "luckyNumber": 7
}
```

**实现状态：** ✅ 已完成（Mock 返回固定数据，真实模式调用 chat_completion）

---

## 8. AI 对话模块（Chat）

### POST /api/chat — AI 对话（非流式） 🔒

发送消息给 AI，返回 AI 回复文本。接口会自动维护 chat session，并在静默超时切段时尝试生成 chat 素材。

**请求 Body：**

```json
{
  "message": "今天有点累，但还是把作业写完了",
  "clientMessageId": "cmsg_20260414_001",
  "attachments": [
    {
      "type": "image",
      "name": "sunset.jpg",
      "url": "/uploads/xxx/diary-image/sunset.jpg",
      "thumbnailUrl": "/uploads/xxx/diary-image/thumb_sunset.jpg",
      "mimeType": "image/jpeg",
      "size": 231231
    }
  ]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| message | string | ✅ | 文本内容（不能为空） |
| clientMessageId | string | ❌ | 前端本地消息 ID（兼容字段） |
| attachments | Attachment[] | ❌ | 附件数组（兼容字段） |

**Attachment 对象：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| type | string | ✅ | `image` / `file` / `voice` |
| name | string | ✅ | 文件名 |
| url | string | ✅ | 上传后的可访问 URL |
| thumbnailUrl | string | ❌ | 图片缩略图 URL |
| mimeType | string | ❌ | MIME 类型 |
| size | number | ❌ | 文件大小，单位字节 |

**响应（无素材生成）：**

```json
{
  "code": 0,
  "data": "辛苦啦，能在疲惫的时候把作业完成，本身就很了不起。",
  "message": "ok"
}
```

**响应（静默切段并生成素材时）：**

```json
{
  "code": 0,
  "data": "辛苦啦，能在疲惫的时候把作业完成，本身就很了不起。",
  "message": "ok",
  "meta": {
    "materialGenerated": true,
    "materialId": "uuid-xxx"
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| data | string | AI 回复文本 |
| meta.materialGenerated | bool | 是否在本次请求前关闭旧 session 并生成了新素材（仅有素材生成时出现） |
| meta.materialId | string | 自动生成素材 ID（仅有素材生成时出现） |

**会话规则：**

1. 仅当前 session 内消息参与 AI 上下文，不再跨 session 混取最近消息。
2. 若距离上一条对话超过 `chatSilenceThreshold`，旧 session 会先关闭，再视配置决定是否转为 chat 素材。
3. 用户消息与 AI 回复都会持久化；失败态由前端自行维护，不入库。
4. 若旧 session 被判定为“与当日已有素材重复”，不会新增 chat 素材，因此本次响应不会携带 `meta`。

**实现状态：** ✅ 已完成

---

### POST /api/chat/stream — AI 对话（SSE 流式） 🔒

流式版本请求体与 `/api/chat` 完全一致，响应为 `text/event-stream`。

**Content-Type：** `application/json`

**Response Content-Type：** `text/event-stream`

**SSE 事件协议：**

| type | 说明 |
|------|------|
| session | 返回当前 `sessionId` |
| ack | 确认用户消息已入库，并返回完整用户消息实体 |
| chunk | AI 文本增量片段 |
| done | AI 回复完成，并返回最终 assistant 消息实体 |
| error | 本次流式生成失败 |

**事件示例：**

```text
data: {"type":"session","sessionId":"sess_123"}

data: {"type":"ack","clientMessageId":"cmsg_20260414_001","message":{"id":"msg_user_1","sessionId":"sess_123","clientMessageId":"cmsg_20260414_001","role":"user","content":"今天有点累，但还是把作业写完了","timestamp":1776150000000,"attachments":[]}}

data: {"type":"chunk","text":"辛苦啦，"}

data: {"type":"chunk","text":"能在疲惫的时候把作业完成，本身就很了不起。"}

data: {"type":"done","message":{"id":"msg_ai_1","sessionId":"sess_123","clientMessageId":null,"role":"assistant","content":"辛苦啦，能在疲惫的时候把作业完成，本身就很了不起。","timestamp":1776150001800,"attachments":[]}}
```

**错误事件示例：**

```text
data: {"type":"error","message":"AI 服务暂时不可用"}
```

**实现状态：** ✅ 已完成（接入 `minimax_client.stream_chat`）

---

### POST /api/chat/close-session — 主动关闭对话段 🔒

用户离开聊天页时，前端主动调用此接口封闭当前 open 的 session。

**请求 Body：** 无

**响应 data：**

```json
{
  "sessionClosed": true,
  "materialGenerated": true,
  "materialId": "uuid-xxx"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| sessionClosed | bool | 是否存在并关闭了 session |
| materialGenerated | bool | 是否生成了 chat 素材 |
| materialId | string \| null | 生成的素材 ID |

> 无 open session → `{"sessionClosed": false, ...}`
> session 轮数不足或 chat_material_enabled=false → `{"sessionClosed": true, "materialGenerated": false, "materialId": null}`

**补充说明：**

- 若当前没有 open session，会返回 `sessionClosed=false`
- 若 session 轮数不足、关闭了 `chatMaterialEnabled` 或摘要阶段无结果，会返回 `materialGenerated=false`
- 若摘要与当日已有素材判重为重复，也会返回 `materialGenerated=false`

**实现状态：** ✅ 已完成

---

### GET /api/chat/session/{session_id}/messages — 获取对话段消息 🔒

前端素材卡片「展开对话」时获取原始对话记录。

**路径参数：** `session_id` — ChatSession 的 ID

**响应 data：**

```json
{
  "session": {
    "id": "uuid",
    "title": "和室友的海河骑行",
    "summary": "下午和小李骑车去了海河边...",
    "startTime": 1711440180000,
    "endTime": 1711440900000,
    "messageCount": 12,
    "mood": "开心",
    "moodEmoji": "😊"
  },
  "messages": [
    {
      "role": "user",
      "content": "今天下午和小李去骑车了",
      "timestamp": 1711440180000
    },
    {
      "role": "assistant",
      "content": "听起来不错！去哪里骑的？",
      "timestamp": 1711440182000
    }
  ]
}
```

**消息字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| role | string | `user` / `assistant` |
| content | string | 消息文本 |
| timestamp | number | Unix 毫秒时间戳 |

**权限：** 仅 session 所属用户可访问。

**实现状态：** ✅ 已完成

---

### GET /api/chat/history — 聊天历史 🔒

**Query 参数：**

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| limit | int | 20 | 获取条数（1-100） |

**响应 data：**

```json
{
  "items": [
    {
      "id": "msg_user_1",
      "sessionId": "sess_123",
      "clientMessageId": "cmsg_001",
      "role": "user",
      "content": "你好",
      "timestamp": 1711440000000,
      "attachments": []
    },
    {
      "id": "msg_ai_1",
      "sessionId": "sess_123",
      "clientMessageId": null,
      "role": "assistant",
      "content": "你好呀！",
      "timestamp": 1711440001000,
      "attachments": []
    }
  ],
  "total": 2
}
```

**补充说明：**

- 当用户还没有历史消息时，接口会返回一条欢迎语消息，前端可直接渲染为空状态首条消息
- `items` 为完整消息实体，字段结构与 `/api/chat` 返回的 `userMessage/assistantMessage` 一致

**实现状态：** ✅ 已完成

---

## 9. 社交模块（Social）

### GET /api/social/matches — 已匹配列表 🔒

**响应 data：** 裸数组

```json
[
  {
    "id": "uuid",
    "nickname": "小鹿",
    "avatar": "/uploads/xxx.jpg",
    "school": "天津大学",
    "commonTags": ["读书", "美食"],
    "matchedAt": 1711440000000
  }
]
```

**实现状态：** ✅ 已完成

---

### POST /api/social/match-requests — 发送匹配请求 🔒

**请求 Body：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| toUid | string | ✅ | 目标用户 ID |

**响应 data：**

```json
{
  "id": "uuid",
  "fromUid": "uuid",
  "toUid": "uuid",
  "status": "pending",
  "createdAt": 1711440000000
}
```

**实现状态：** ✅ 已完成

---

### POST /api/social/match-requests/{request_id}/respond — 响应匹配请求 🔒

**请求 Body：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| accept | bool | ✅ | true=接受, false=拒绝 |

**响应 data：** null

**实现状态：** ✅ 已完成

---

### GET /api/social/messages/{match_id} — 匹配消息列表 🔒

**Query 参数：**

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| limit | int | 50 | 获取条数（1-200） |
| before | string | — | 游标分页：此消息 ID 之前 |

**响应 data：** 裸数组

```json
[
  {
    "id": "uuid",
    "matchId": "uuid",
    "fromUid": "uuid",
    "content": "你好",
    "timestamp": 1711440000000
  }
]
```

**实现状态：** ✅ 已完成

---

### GET /api/social/matches/{match_id}/report — 匹配报告（AI） 🔒

获取/生成 AI 匹配报告。首次调用会生成并缓存。

**响应 data：**

```json
{
  "compatibility": 85,
  "analysis": "你们有很多共同点...",
  "commonPoints": ["都喜欢记录生活", "学习态度积极"],
  "differences": ["作息时间略有差异"]
}
```

**实现状态：** ✅ 已完成（调用 minimax_client.generate_match_report）

---

### POST /api/social/buddy — 申请搭子 🔒

**请求 Body：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| target_user_id | string | ✅ | 目标用户 ID |
| reason | string | ❌ | 申请理由 |

**响应 data：**

```json
{
  "id": "uuid",
  "fromUid": "uuid",
  "toUid": "uuid",
  "reason": "一起去图书馆",
  "status": "pending",
  "createdAt": 1711440000000
}
```

**实现状态：** ✅ 已完成

---

### POST /api/social/buddy/{request_id}/respond — 响应搭子申请 🔒

**请求 Body：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| accept | bool | ✅ | true=同意, false=拒绝 |

**响应 data：** null

**实现状态：** ✅ 已完成

---

## 10. 文件上传模块（Upload）

### POST /api/upload/avatar — 上传头像 🔒

**Content-Type：** multipart/form-data

**请求参数：**

| 字段 | 类型 | 说明 |
|------|------|------|
| file | File | 头像图片（jpeg/png/gif/webp，最大 5MB） |

**响应 data：** `{"avatar": "/uploads/xxx/avatar/xxx.jpg"}`

**实现状态：** ✅ 已完成（自动更新用户 avatar 字段）

---

### POST /api/upload/diary-image — 上传日记图片 🔒

**Content-Type：** multipart/form-data

**请求参数：**

| 字段 | 类型 | 说明 |
|------|------|------|
| file | File | 图片（jpeg/png/gif/webp，最大 10MB） |

**响应 data：** `{"url": "/uploads/xxx/diary-image/xxx.jpg"}`

**实现状态：** ✅ 已完成

---

### POST /api/upload/diary-images — 批量上传日记图片 🔒

**Content-Type：** multipart/form-data

**请求参数：**

| 字段 | 类型 | 说明 |
|------|------|------|
| files | File[] | 图片列表（jpeg/png/gif/webp，单张最大 10MB，单次最多 9 张） |

**响应 data：**

```json
{
  "items": [
    {
      "url": "/uploads/xxx/diary-image/xxx1.jpg",
      "thumbnailUrl": "/uploads/xxx/diary-image/thumb_xxx1.jpg",
      "location": {"lat": 39.12, "lng": 117.20, "address": "39.120000,117.200000"}
    },
    {
      "url": "/uploads/xxx/diary-image/xxx2.jpg",
      "thumbnailUrl": "/uploads/xxx/diary-image/thumb_xxx2.jpg",
      "location": {}
    }
  ]
}
```

**实现状态：** ✅ 已完成

---

### POST /api/upload/voice — 上传语音素材 🔒

**Content-Type：** multipart/form-data

**请求参数：**

| 字段 | 类型 | 说明 |
|------|------|------|
| file | File | 语音（mp3/wav/m4a/ogg，最大 20MB） |

**响应 data：**

```json
{
  "url": "/uploads/xxx/voice/20260414_xxx.m4a"
}
```

**实现状态：** ✅ 已完成

---

### POST /api/upload/chat-file — 上传聊天文件附件 🔒

用于 AI 聊天页发送文件附件。前端应先调用本接口上传文件，再把返回结果组装进 `/api/chat` 或 `/api/chat/stream` 的 `attachments`。

**Content-Type：** multipart/form-data

**请求参数：**

| 字段 | 类型 | 说明 |
|------|------|------|
| file | File | 聊天文件（pdf/doc/docx/ppt/pptx/xls/xlsx/txt/csv，最大 20MB） |

**响应 data：**

```json
{
  "url": "/uploads/xxx/chat-file/notes.pdf",
  "name": "notes.pdf",
  "size": 102400,
  "mimeType": "application/pdf"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| url | string | 上传后的文件 URL |
| name | string | 原始文件名 |
| size | number | 文件大小，单位字节 |
| mimeType | string | MIME 类型 |

**实现状态：** ✅ 已完成

---

## 11. 学习模块（Study）⚠️ 已废弃

> 此模块在 v2 中已废弃，但路由仍注册。后续可移除。

### GET /api/study/pomodoros — 番茄钟列表 🔒

**响应 data：** 裸数组 `[PomodoroOut, ...]`

**实现状态：** ✅ 已完成

---

### POST /api/study/pomodoros — 创建番茄钟 🔒

**请求 Body：**

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| task | string | "新任务" | 任务名称 |
| subject | string | "其他" | 科目 |
| duration | int | 25 | 时长（分钟） |

**实现状态：** ✅ 已完成

---

### POST /api/study/pomodoros/{pomodoro_id}/complete — 完成番茄钟 🔒

**实现状态：** ✅ 已完成

---

### GET /api/study/todos — 待办列表 🔒

**响应 data：** 裸数组 `[TodoOut, ...]`

**实现状态：** ✅ 已完成

---

### POST /api/study/todos — 创建待办 🔒

**请求 Body：**

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| content | string | — | 待办内容 |
| priority | string | "medium" | 优先级 |

**实现状态：** ✅ 已完成

---

### POST /api/study/todos/{todo_id}/toggle — 切换待办完成状态 🔒

**实现状态：** ✅ 已完成

---

## 12. 广场模块（Plaza）🆕

> 广场是校园社交信息流，支持帖子发布、浏览、频道筛选、点赞、评论、评论回复、分身评论草稿/自动发布、分身推荐等功能。

### GET /api/plaza/posts — 帖子列表（分页 + 频道筛选 + 搜索） 🔒

**Query 参数：**

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| channel | string | — | 频道筛选：buddy / help / share / dating，空则返回全部（推荐） |
| q | string | — | 关键词搜索，匹配 content / tags / authorName / location（模糊匹配） |
| page | int | 1 | 页码 |
| page_size | int | 10 | 每页条数 |

**搜索逻辑：**

- `q` 参数与 `channel` 可组合使用（AND 关系）
- 搜索范围：帖子正文（content）、话题标签（tags）、作者昵称（authorName）、位置（location）
- 匹配方式：LIKE %q%（模糊匹配，不区分大小写）
- 空 `q` 参数 = 不筛选（返回全部）

**响应 data：** `{ items: PlazaPost[], total: number }`

```json
{
  "items": [
    {
      "id": "uuid",
      "authorId": "uuid",
      "authorName": "林同学",
      "authorAvatar": "/uploads/xxx.jpg",
      "authorSchool": "南开大学",
      "authorMajor": "计算机科学",
      "authorGrade": "大三",
      "type": "buddy",
      "content": "有人一起周末去打羽毛球吗？",
      "images": ["/uploads/xxx/img1.jpg"],
      "location": "南开大学",
      "tags": ["运动", "羽毛球"],
      "likes": 24,
      "comments": 12,
      "agentResponses": 5,
      "createdAt": 1711440000000,
      "isFromAgent": false,
      "allowAgentReply": true,
      "schoolOnly": false
    }
  ],
  "total": 42
}
```

**实现状态：** ✅ 已实现

---

### GET /api/plaza/posts/{post_id} — 帖子详情 🔒

**响应 data：** PlazaPost 对象

**实现状态：** ✅ 已实现

---

### POST /api/plaza/posts — 创建帖子 🔒

**请求 Body：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| type | string | ✅ | 帖子类型：buddy / help / share / dating |
| content | string | ✅ | 帖子正文 |
| images | string[] | ❌ | 图片 URL 列表（最多 9 张，先调 /upload/diary-image 获取） |
| location | string | ❌ | 位置 |
| tags | string[] | ❌ | 话题标签 |
| allow_agent_reply | bool | ❌ | 是否允许分身代回复评论（默认 true） |
| school_only | bool | ❌ | 是否仅限本校可见（默认 false） |

**响应 data：** PlazaPost 对象

**核心逻辑：**
- 创建帖子记录，自动填充作者信息（从 users 表 JOIN 获取 name、avatar、school、major）
- likes/comments/agentResponses 初始值为 0
- isFromAgent = false（用户手动发帖）
- 写入两份记忆：作者 `avatar_only` 社交表达记忆，以及用于广场匹配的 `plaza_post_index` 共享索引（`school_only=true` 为 `school`，否则为 `public`）
- 触发分身引擎扫描（异步，详见 AI 分身模块）

**实现状态：** ✅ 已实现

---

### POST /api/plaza/posts/{post_id}/like — 点赞帖子 🔒

**请求 Body：** 无

**响应 data：** null

**核心逻辑：**
- 帖子 likes 字段 +1
- 建议维护 post_likes 表防止重复点赞（user_id + post_id 唯一）
- 取消点赞：再次调用同一接口则 likes -1（toggle 逻辑）

**实现状态：** ✅ 已实现

---

### GET /api/plaza/posts/{post_id}/comments — 帖子评论列表 🔒

**响应 data：** 裸数组

```json
[
  {
    "id": "uuid",
    "postId": "uuid",
    "authorId": "uuid",
    "authorName": "孙同学",
    "authorAvatar": "/uploads/xxx.jpg",
    "content": "我也想去！",
    "isAgent": false,
    "parentCommentId": null,
    "parentAuthorName": null,
    "parentContent": null,
    "createdAt": 1711440000000
  },
  {
    "id": "reply-uuid",
    "postId": "uuid",
    "authorId": "agent-owner-uuid",
    "authorName": "林同学的分身",
    "authorAvatar": "/uploads/avatar.jpg",
    "content": "我主人也喜欢羽毛球，可以一起约。",
    "isAgent": true,
    "parentCommentId": "uuid",
    "parentAuthorName": "孙同学",
    "parentContent": "我也想去！",
    "createdAt": 1711440060000
  }
]
```

**字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| isAgent | bool | true 表示该评论由用户 AI 分身生成，authorName 通常显示为「XXX的分身」 |
| parentCommentId | string? | 父评论 ID；为空表示直接评论帖子 |
| parentAuthorName | string? | 父评论作者名称，用于前端展示“回复某人” |
| parentContent | string? | 父评论内容摘要，用于前端展示回复引用 |

**实现状态：** ✅ 已实现

---

### POST /api/plaza/posts/{post_id}/comments — 添加评论或回复评论 🔒

**请求 Body：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| content | string | ✅ | 评论内容 |
| is_agent | bool | ❌ | 是否为分身回复（默认 false） |
| parent_comment_id | string | ❌ | 父评论 ID；为空表示直接评论帖子，存在时表示回复该评论 |

**响应 data：** PlazaComment 对象

**核心逻辑：**
- 创建评论记录，自动填充 authorName/authorAvatar（从 users 表获取）
- 如果 `parent_comment_id` 不为空，会校验父评论属于同一个帖子
- 帖子 comments 字段 +1
- 用户评论与分身评论都会进入广场评论流
- 如果 is_agent=true，评论会以当前用户分身身份展示，并可用于后续分身对话

**实现状态：** ✅ 已实现

---

### GET /api/plaza/comments/inbox — 我的评论与分身评论流 🔒

用于前端“分身评论/评论收件箱”页面，聚合当前用户本人、当前用户分身发出的评论，以及别人回复这些评论的内容。

**响应 data：** 裸数组 `PlazaComment[]`

```json
[
  {
    "id": "uuid",
    "postId": "post-uuid",
    "authorId": "other-user-uuid",
    "authorName": "王同学",
    "authorAvatar": "/uploads/wang.jpg",
    "content": "你们一般几点去？",
    "isAgent": false,
    "parentCommentId": "my-agent-comment-uuid",
    "parentAuthorName": "林同学的分身",
    "parentContent": "我主人也喜欢羽毛球，可以一起约。",
    "createdAt": 1711440120000
  }
]
```

**核心逻辑：**
- 返回当前用户本人评论
- 返回当前用户分身评论
- 返回别人回复当前用户本人或分身评论的评论
- 前端可通过 `isAgent` 区分“用户本人”和“分身”
- 前端可通过 `parentCommentId/parentAuthorName/parentContent` 展示评论线程关系

**实现状态：** ✅ 已实现

---

### POST /api/plaza/posts/{post_id}/agent-comment — 分身评论草稿兼容入口 🔒

旧版本该接口会直接发布分身评论。现在接口会根据分身设置决定行为：默认生成 `AgentAction` 草稿，前端弹出确认卡片；如果用户开启 `auto_approve_comment`，则直接批准并发布评论。

**请求 Body：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| parent_comment_id | string | ❌ | 可选，让分身回复某条评论；为空则评论帖子 |

**响应 data：**

```json
{
  "action": {
    "id": "uuid",
    "actionType": "comment_post",
    "targetType": "plaza_post",
    "targetId": "post-uuid",
    "inputContext": {
      "postId": "post-uuid",
      "postType": "buddy",
      "parent_comment_id": null,
      "memoryCount": 6
    },
    "outputText": "我也想一起去跑步，感觉会很放松。",
    "status": "draft",
    "createdAt": 1711440000000,
    "updatedAt": 1711440000000
  },
  "requiresApproval": true,
  "message": "已生成分身评论草稿，请先确认后再发布。"
}
```

**行为说明：**
- `requiresApproval=true`：前端应立刻弹出确认卡片，展示 `action.outputText`，用户批准后调用 `/api/avatar/actions/{action_id}/approve`
- `requiresApproval=false`：说明用户开启了“分身回无需批准”，后端已经发布该评论
- 传入 `parent_comment_id` 时，批准后的分身评论会成为该评论的回复

**实现状态：** ✅ 已实现

---

## 13. AI 分身模块（Avatar）🆕

> AI 分身是用户的数字化代理，自动浏览广场帖子、匹配感兴趣的内容、生成可审核的公开回复，并在用户允许时自动冲浪评论。
> 分身的行为由用户画像、长期记忆、分身名片、广场帖子索引和用户设置共同驱动。

### GET /api/avatar/memories — 分身记忆列表 🔒

**Query 参数：**

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| category | string | — | 按类型筛选：fact / interest / personality / need / habit / relation |

**响应 data：** 裸数组

```json
[
  {
    "id": "uuid",
    "category": "interest",
    "content": "喜欢骑行，常去海河沿线",
    "source": "diary",
    "sourceRef": "diary-uuid-001",
    "confidence": 0.92,
    "createdAt": 1711440000000,
    "updatedAt": 1711440000000,
    "isActive": true,
    "isPinned": false,
    "needType": null,
    "urgency": null,
    "expiry": null,
    "matchStatus": null,
    "tags": ["骑行", "户外"]
  }
]
```

**字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| category | string | 记忆类型：fact（事实）/ interest（兴趣）/ personality（性格）/ need（需求）/ habit（习惯）/ relation（关系） |
| source | string | 来源：diary（日记提取）/ chat（对话提取）/ manual（手动添加）/ behavior（行为推断） |
| sourceRef | string? | 来源引用 ID（如日记 ID） |
| confidence | number | 置信度 0.0-1.0 |
| isActive | bool | 是否激活（停用的记忆不参与匹配） |
| isPinned | bool | 是否置顶（用户手动标记的重要记忆） |
| needType | string? | need 类型专属：buddy / dating / help / activity |
| urgency | string? | need 类型专属：active（主动找）/ passive（被动等） |
| expiry | number? | need 类型专属：过期时间戳（毫秒） |
| matchStatus | string? | need 类型专属：searching / matched / expired |
| tags | string[]? | 关联标签 |

**实现状态：** ✅ 已实现

---

### POST /api/avatar/memories — 添加记忆 🔒

**请求 Body：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| category | string | ✅ | 记忆类型 |
| content | string | ✅ | 记忆内容 |

**响应 data：** AvatarMemory 对象

**核心逻辑：**
- source 自动设为 "manual"
- confidence 默认 1.0（用户手动添加 = 完全可信）
- isActive = true，isPinned = false

**实现状态：** ✅ 已实现

---

### PUT /api/avatar/memories/{memory_id} — 更新记忆 🔒

**请求 Body（所有字段可选）：**

| 字段 | 类型 | 说明 |
|------|------|------|
| content | string | 记忆内容 |
| isActive | bool | 激活/停用 |
| isPinned | bool | 置顶 |
| category | string | 类型 |
| tags | string[] | 标签 |

**响应 data：** 更新后的 AvatarMemory 对象

**实现状态：** ✅ 已实现

---

### DELETE /api/avatar/memories/{memory_id} — 删除记忆 🔒

**响应 data：** null

**实现状态：** ✅ 已实现

---

### GET /api/avatar/status — 获取分身状态 🔒

**响应 data：**

```json
{
  "isActive": true,
  "browsedCount": 42,
  "matchedCount": 3,
  "chattingCount": 1,
  "lastActiveAt": 1711440000000,
  "enabledChannels": ["buddy", "help", "share", "dating"],
  "enabledActions": ["browse", "match", "comment", "auto_approve_comment", "auto_surf_comment"],
  "matchRange": {
    "school": "南开大学",
    "distanceKm": 10,
    "autoReplyDailyLimit": 5,
    "autoReplyIntervalMinutes": 30,
    "autoReplyMinScore": 55
  }
}
```

**字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| isActive | bool | 分身是否在线冲浪 |
| browsedCount | number | 已浏览帖子数 |
| matchedCount | number | 已匹配帖子数 |
| chattingCount | number | 正在聊天数 |
| lastActiveAt | number | 最后活跃时间 |
| enabledChannels | string[] | 启用的频道 |
| enabledActions | string[] | 启用的动作：browse / match / comment / auto_approve_comment / auto_surf_comment |
| matchRange.school | string | 匹配学校范围 |
| matchRange.distanceKm | number | 匹配距离半径 |
| matchRange.autoReplyDailyLimit | number | 分身自动冲浪每天最多发布/生成的评论数 |
| matchRange.autoReplyIntervalMinutes | number | 分身自动冲浪评论最小间隔，防止 token 消耗过快 |
| matchRange.autoReplyMinScore | number | 自动评论最低兴趣匹配分，低于该分数会跳过 |

**实现状态：** ✅ 已实现

---

### PUT /api/avatar/status — 更新分身状态 🔒

**请求 Body（所有字段可选）：**

| 字段 | 类型 | 说明 |
|------|------|------|
| is_active | bool | 开关分身 |
| enabled_channels | string[] | 启用的频道 |
| enabled_actions | string[] | 启用的动作，可包含 auto_approve_comment / auto_surf_comment |
| match_range | object | 匹配范围与自动冲浪频率配置 |

**请求示例：**

```json
{
  "enabled_actions": ["browse", "match", "comment", "auto_approve_comment", "auto_surf_comment"],
  "match_range": {
    "school": "南开大学",
    "distanceKm": 10,
    "autoReplyDailyLimit": 8,
    "autoReplyIntervalMinutes": 20,
    "autoReplyMinScore": 60
  }
}
```

**响应 data：** 更新后的 AvatarStatus 对象

**实现状态：** ✅ 已实现

---

### GET /api/avatar/matches — 分身推荐列表 🔒

分身会在访问列表时自动浏览可见广场帖子，根据 `avatar_card`、结构化记忆、共享帖子索引和学校可见性生成推荐，并与对方分身名片形成初步对话摘要。

**响应 data：** 裸数组

```json
[
  {
    "id": "uuid",
    "postId": "uuid",
    "post": { "...PlazaPost 完整对象...": true },
    "matchScore": 92,
    "matchReasons": [
      "你们都在南开大学",
      "都在准备雅思（目标7分）",
      "常去同一个图书馆"
    ],
    "agentConversation": [
      {
        "from": "my_agent",
        "content": "我主人也在备考雅思，每天下午泡图书馆",
        "timestamp": 1711440000000
      },
      {
        "from": "their_agent",
        "content": "太好了！可以约图书馆一起学",
        "timestamp": 1711440060000
      }
    ],
    "status": "new",
    "createdAt": 1711440000000
  }
]
```

**字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| postId | string | 匹配的帖子 ID |
| post | PlazaPost | 帖子完整对象（嵌套） |
| matchScore | number | 匹配度 0-100 |
| matchReasons | string[] | 匹配原因列表 |
| agentConversation | array | 分身对话记录 |
| agentConversation[].from | string | "my_agent" / "their_agent" |
| status | string | "new" / "viewed" / "chatting" / "dismissed" |

**实现说明：**
- 自动跳过自己发布的帖子和已 `dismissed` 的帖子。
- `school_only=true` 的帖子只对同校用户参与推荐。
- 推荐理由可以来自同校、帖子内容命中兴趣、双方 avatar_card 共同兴趣、对方 `plaza_post_index` 共享记忆等。

**实现状态：** ✅ 已实现

---

### POST /api/avatar/matches/{match_id}/action — 分身匹配操作 🔒

**请求 Body：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| action | string | ✅ | "dismiss"（忽略）/ "chat"（发起私聊） |

**响应 data：** null

**核心逻辑：**
- action="dismiss" → 将匹配状态更新为 "dismissed"
- action="chat" → 将匹配状态更新为 "chatting"，可选创建私聊会话

**实现状态：** ✅ 已实现

---

### GET /api/avatar/profile — 获取分身侧写 🔒

AI 根据记忆库生成的分身人格摘要。

**响应 data：**

```json
{
  "summary": "你是一个热爱骑行和摄影的南开大学软件工程大三学生，性格开朗但偶尔社恐...",
  "diaryCount": 42,
  "chatCount": 128,
  "generatedAt": 1711440000000
}
```

**实现状态：** ✅ 已实现

---

### POST /api/avatar/profile/regenerate — 重新生成侧写 🔒

**请求 Body：** 无

**响应 data：** AvatarProfile 对象（同 GET）

**核心逻辑：**
- 读取用户所有记忆 + 近期日记/聊天
- 调用 AI（chat_completion）生成人格摘要
- 写入数据库缓存

**实现状态：** ✅ 已实现

---

### GET /api/avatar/card — 获取分身名片 🔒

分身名片是对外社交、agent-to-agent 匹配时可使用的可控摘要。它不会包含日记、私聊、AI 对话等私密原文。

**响应 data：**

```json
{
  "displayName": "小林的分身",
  "publicSummary": "喜欢摄影、骑行，也在寻找低压力的学习搭子。",
  "interestTags": ["摄影", "骑行", "雅思"],
  "socialIntent": ["找学习搭子", "一起运动"],
  "conversationStyle": {
    "tone": "自然、友善、低压力"
  },
  "boundaries": ["不主动透露私密经历"],
  "visibility": "private",
  "updatedAt": 1711440000000
}
```

**实现状态：** ✅ 已实现

---

### POST /api/avatar/card/regenerate — 重新生成分身名片 🔒

基于 `AvatarProfile` 与 `MemoryFact` 重新生成分身名片。

**请求 Body：** 无

**响应 data：** AvatarCard 对象（同 GET）

**实现状态：** ✅ 已实现

---

### GET /api/avatar/actions — 分身行动列表 🔒

查看当前用户分身生成过的草稿、已发布行动和已拒绝行动。

**Query 参数：**

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| status | string | — | 可选：draft / published / rejected |

**响应 data：** 裸数组

```json
[
  {
    "id": "uuid",
    "actionType": "comment_post",
    "targetType": "plaza_post",
    "targetId": "post-uuid",
    "inputContext": {
      "postId": "post-uuid",
      "postType": "share",
      "parent_comment_id": null,
      "auto_surf": false,
      "match_score": 82,
      "memoryCount": 8
    },
    "outputText": "这个路线听起来好舒服，我也想试试。",
    "status": "draft",
    "createdAt": 1711440000000,
    "updatedAt": 1711440000000
  }
]
```

**实现状态：** ✅ 已实现

---

### POST /api/avatar/actions/plaza-comment-draft — 生成广场评论草稿 🔒

生成一条分身评论草稿，但不会直接发布。前端可以展示草稿，让用户批准或拒绝。

**请求 Body：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| post_id | string | ✅ | 要评论的广场帖子 ID |
| parent_comment_id | string | ❌ | 要回复的评论 ID；为空则评论帖子 |

**响应 data：** AgentAction 对象

**核心逻辑：**
- 读取目标广场帖子。
- 如果传入 `parent_comment_id`，读取父评论并让分身针对该评论回复。
- 检索当前用户长期记忆，场景为 `avatar_comment`。
- 结合分身侧写生成 1-3 句话评论草稿。
- 只写入 `agent_actions.status=draft`，不发布评论。

**实现状态：** ✅ 已实现

---

### POST /api/avatar/actions/auto-surf — 触发一次分身自动冲浪评论 🔒

让分身主动浏览广场帖子，根据兴趣匹配度和频率限制决定是否生成或发布评论。该接口适合前端“立即冲浪一次”按钮，也可以后续接入定时任务。

**请求 Body：**

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| limit | int | ❌ | 10 | 本次最多检查的帖子数量 |

**响应 data：**

```json
{
  "actions": [
    {
      "id": "uuid",
      "actionType": "comment_post",
      "targetType": "plaza_post",
      "targetId": "post-uuid",
      "inputContext": {
        "postId": "post-uuid",
        "postType": "share",
        "auto_surf": true,
        "match_score": 78,
        "memoryCount": 6
      },
      "outputText": "这个话题我挺感兴趣的，也想听听大家怎么做。",
      "status": "draft",
      "createdAt": 1711440000000,
      "updatedAt": 1711440000000
    }
  ],
  "publishedCount": 0,
  "draftCount": 1,
  "skippedReason": null
}
```

**核心逻辑：**
- 只有 `isActive=true` 且 `enabledActions` 包含 `comment` 与 `auto_surf_comment` 时才会执行。
- 按 `enabledChannels`、帖子可见性、是否允许分身回复、是否本人帖子等条件筛选帖子。
- 根据分身记忆与帖子内容计算兴趣分，低于 `matchRange.autoReplyMinScore` 会跳过。
- 避免对同一个帖子重复生成评论。
- 使用 `matchRange.autoReplyDailyLimit` 限制每日自动评论数量。
- 使用 `matchRange.autoReplyIntervalMinutes` 限制自动评论间隔，防止 token 消耗过快。
- 如果开启 `auto_approve_comment`，生成后直接发布；否则只生成草稿，等待用户确认。

**实现状态：** ✅ 已实现

---

### POST /api/avatar/actions/{action_id}/approve — 批准分身行动 🔒

批准一条 `draft` 状态的分身行动。当前主要用于发布分身广场评论。

**响应 data：** AgentAction 对象

**核心逻辑：**
- 校验 action 属于当前用户且状态为 draft。
- actionType=comment_post 时，将 `outputText` 写入 `plaza_comments`，并更新帖子 comments / agentResponses 计数。
- 如果 action.inputContext 中存在 `parent_comment_id`，发布为该评论的回复。
- 将 action.status 更新为 published。

**实现状态：** ✅ 已实现

---

### POST /api/avatar/actions/{action_id}/reject — 拒绝分身行动 🔒

拒绝一条 `draft` 状态的分身行动，不会发布任何公开评论。

**响应 data：** AgentAction 对象

**核心逻辑：**
- 校验 action 属于当前用户且状态为 draft。
- 将 action.status 更新为 rejected。

**实现状态：** ✅ 已实现

---
## 14. 统一记忆系统（Memory）🆕

> 统一记忆系统负责把日记、AI 对话、素材、广场发帖/评论、社交私聊等内容沉淀成可检索的长期记忆，并为聊天、分身侧写、分身行动提供上下文。

### POST /api/memory/search — 搜索长期记忆 🔒

**请求 Body：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| query | string | ✅ | 检索文本 |
| scenario | string | ❌ | 场景：chat / profile_generation / avatar_comment 等 |
| top_k | number | ❌ | 返回条数，默认使用配置 `MEMORY_TOP_K` |
| source_types | string[] | ❌ | 限定来源类型 |

**响应 data：** 裸数组。每项包含 `documentId`、`chunkId`、`content`、`sourceType`、`sourceId`、`title`、`score`、`occurredAt`、`visibility`、`metadata`。

**实现状态：** ✅ 已实现（默认 SQLite 关键词检索 fallback；开启 `MEMORY_VECTOR_ENABLED=true` 后可使用 ChromaDB 向量索引，embedding provider 支持 `hash` / `dashscope` / `vivo`）

---

### GET /api/memory/export — 导出当前用户记忆 🔒

导出当前用户的统一记忆数据，包含 documents、facts、profiles、avatarCards、agentActions。用于备份、迁移和隐私透明。

**响应 data：**

```json
{
  "version": 1,
  "documents": [],
  "facts": [],
  "profiles": [],
  "avatarCards": [],
  "agentActions": []
}
```

**实现状态：** ✅ 已实现

---

### DELETE /api/memory/all — 删除当前用户所有记忆 🔒

删除当前用户的统一记忆文档、chunks、结构化事实、统一画像、分身名片和分身行动记录。

**响应 data：** null

**实现状态：** ✅ 已实现

---

### POST /api/memory/agent-context — 生成 agent-to-agent 安全上下文 🔒

只输出对方 `AvatarCard` 与 `public/school/match_card` 级别记忆摘要，不包含 private 日记、AI 对话、社交私聊原文。

**请求 Body：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| ownerUserId | string | ✅ | 要读取公开上下文的用户 ID |
| query | string | ❌ | 检索提示 |
| topK | number | ❌ | 共享记忆条数 |

**实现状态：** ✅ 已实现

---

### GET /api/memory/conflicts — 检测潜在记忆冲突 🔒

按 category + subject + predicate + object 分组，找出内容不同的活跃 facts。该接口只提示冲突，不自动删除。

**实现状态：** ✅ 已实现

---

### POST /api/memory/maintenance/decay — 淡化旧结构化记忆 🔒

对非置顶、非 stable、超过指定天数的活跃 facts 做置信度衰减；低于阈值时自动停用。

**请求 Body：**

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| olderThanDays | number | 180 | 只处理超过该天数的 facts |
| decayFactor | number | 0.92 | 置信度乘数 |
| minConfidence | number | 0.3 | 低于该值后停用 |

**实现状态：** ✅ 已实现

---

### GET /api/memory/documents — 记忆文档列表 🔒

**Query 参数：**

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| source_type | string | — | 按来源筛选 |
| limit | number | 50 | 返回条数 |
| offset | number | 0 | 偏移量 |

**响应 data：** 裸数组。每项包含记忆文档元信息和完整内容。

**实现状态：** ✅ 已实现

---

### GET /api/memory/documents/{document_id} — 记忆文档详情 🔒

**响应 data：** MemoryDocument 对象。

**实现状态：** ✅ 已实现

---

### DELETE /api/memory/documents/{document_id} — 删除记忆文档 🔒

软删除记忆文档，并删除对应 chunks。

**响应 data：** null

**实现状态：** ✅ 已实现

---

### POST /api/memory/documents/{document_id}/extract — 抽取结构化事实 🔒

从指定记忆文档中抽取 `MemoryFact`，用于分身画像、名片和匹配。

**响应 data：** MemoryFact 数组。

**实现状态：** ✅ 已实现

---

### GET /api/memory/facts — 结构化记忆列表 🔒

**Query 参数：**

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| category | string | — | 可选：profile / preference / interest / habit / experience / relationship / boundary / need |
| active_only | bool | true | 是否只返回启用事实 |

**响应 data：** MemoryFact 数组。

**实现状态：** ✅ 已实现

---

### POST /api/memory/facts — 手动创建结构化记忆 🔒

用于前端“我的分身”页面直接写入统一结构化记忆，替代旧的 `/avatar/memories` 主流程。

**请求 Body：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| category | string | 否 | 默认 profile；可选 profile / preference / interest / habit / experience / relationship / boundary / need |
| content | string | 是 | 记忆内容 |
| subject | string | 否 | 默认 user |
| predicate | string | 否 | 默认 has_fact |
| object | string | 否 | 事实对象；默认取 content 前 80 字 |
| confidence | number | 否 | 置信度 0-1，默认 1 |
| stability | string | 否 | stable / recent / temporary，默认 stable |
| isPinned | bool | 否 | 是否置顶，默认 false |

**响应 data：** 新创建的 MemoryFact。

**实现状态：** ✅ 已实现

---

### PUT /api/memory/facts/{fact_id} — 更新结构化记忆 🔒

**请求 Body（所有字段可选）：**

| 字段 | 类型 | 说明 |
|------|------|------|
| content | string | 事实内容 |
| confidence | number | 置信度 0-1 |
| is_active | bool | 是否启用 |
| is_pinned | bool | 是否置顶 |
| category | string | 记忆分类 |

**响应 data：** 更新后的 MemoryFact 对象。

**实现状态：** ✅ 已实现

---

### DELETE /api/memory/facts/{fact_id} — 删除结构化记忆 🔒

删除当前用户的一条结构化记忆。删除后不再参与分身画像、分身名片和匹配推荐。

**响应 data：** null

**实现状态：** ✅ 已实现

---

### POST /api/memory/profile/regenerate — 重新生成记忆画像 🔒

基于结构化事实和近期记忆文档生成 `MemoryProfile`，用于聊天上下文与分身系统。

**响应 data：** MemoryProfile 对象。

**实现状态：** ✅ 已实现

---

### 历史数据补索引脚本

```bash
python scripts/reindex_memories.py
python scripts/reindex_memories.py --user-id <user_id>
python scripts/reindex_memories.py --source diary --source chat_session
python scripts/reindex_memories.py --dry-run
python scripts/reindex_memories.py --rebuild-vector-index
python scripts/reindex_memories.py --progress-every 500 --fail-fast
```

**覆盖来源：** diary、material、chat_session、plaza_post、plaza_comment、social_message。

**说明：**
- `--dry-run` 只统计，不写入。
- `--rebuild-vector-index` 会把已有 `memory_chunks` 重建到可选向量后端。
- `MEMORY_VECTOR_ENABLED=false` 或未安装 ChromaDB 时，向量索引安全 no-op。

### 记忆向量模型配置

记忆系统支持可插拔 embedding provider。当前推荐默认使用 `vivo` provider（与 VIVO 统一鉴权）；离线开发和自动化测试可切回 `hash`；也支持阿里云百炼 / 通义千问 `text-embedding-v4`。

```env
MEMORY_VECTOR_ENABLED=true
MEMORY_EMBEDDING_PROVIDER=vivo   # vivo / dashscope / hash
MEMORY_EMBEDDING_DIMENSIONS=1024
MEMORY_EMBEDDING_BATCH_SIZE=10
MEMORY_EMBEDDING_TIMEOUT_SEC=30

# 使用 VIVO 文本向量
VIVO_APP_KEY=your-vivo-app-key
VIVO_EMBEDDING_BASE_URL=https://api-ai.vivo.com.cn
VIVO_EMBEDDING_MODEL=m3e-base
# 当 VIVO_EMBEDDING_MODEL=bge-base-zh-v1.5 且用于 query 检索时，系统会自动加这段前缀
VIVO_EMBEDDING_QUERY_INSTRUCTION=为这个句子生成表示以用于检索相关文章：

# 或者切换到 DashScope
MEMORY_EMBEDDING_PROVIDER=dashscope
DASHSCOPE_API_KEY=your-dashscope-api-key
DASHSCOPE_EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
DASHSCOPE_EMBEDDING_MODEL=text-embedding-v4
```

**Provider 说明：**

| Provider | 说明 | 适用场景 |
|------|------|------|
| `hash` | 本地 deterministic hash embedding，不调用外部 API，维度固定 64 | 测试、离线开发、无成本回归 |
| `dashscope` | 调用百炼 OpenAI-compatible Embedding 接口，默认 `text-embedding-v4` | 中文语义检索、真实记忆召回 |
| `vivo` | 调用 VIVO `embedding-model-api/predict/batch`，支持 `m3e-base` / `bge-base-zh-v1.5` | 中文语义检索、与 VIVO 能力统一鉴权 |

**通义千问 text-embedding-v4 约束：**

| 项 | 当前配置 |
|------|------|
| 默认地域 | 华北 2（北京） |
| Endpoint | `https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings` |
| 支持维度 | 64、128、256、512、768、1024、1536、2048 |
| 默认维度 | 1024 |
| 单次批量 | 最多 10 条文本 |
| 单条上限 | 8192 tokens |

切换 provider 或维度后，建议重建向量索引：

```bash
python scripts/reindex_memories.py --rebuild-vector-index
```

---

## 新增数据模型参考（广场 + 分身）

以下为广场和分身模块需要新建的数据表，供实现参考：

```python
# app/models/plaza.py

class PlazaPost(Base):
  __tablename__ = "plaza_posts"
  id = Column(String, primary_key=True, default=lambda: str(uuid4()))
  user_id = Column(String, nullable=False)           # 作者 ID
  type = Column(String, nullable=False)               # buddy / help / share / dating
  content = Column(Text, nullable=False)              # 正文
  images = Column(Text, default="[]")                 # JSON: string[]
  location = Column(String, default="")               # 位置
  tags = Column(Text, default="[]")                   # JSON: string[]
  likes = Column(Integer, default=0)                  # 点赞数
  comments = Column(Integer, default=0)               # 评论数
  agent_responses = Column(Integer, default=0)        # 分身响应数
  is_from_agent = Column(Boolean, default=False)      # 是否由分身发布
  allow_agent_reply = Column(Boolean, default=True)   # 是否允许分身回复
  school_only = Column(Boolean, default=False)        # 仅本校可见
  created_at = Column(BigInteger, nullable=False)

class PlazaComment(Base):
  __tablename__ = "plaza_comments"
  id = Column(String, primary_key=True, default=lambda: str(uuid4()))
  post_id = Column(String, nullable=False)            # 帖子 ID
  parent_comment_id = Column(String, nullable=True)    # 父评论 ID；为空表示直接评论帖子
  user_id = Column(String, nullable=False)            # 评论者 ID
  content = Column(Text, nullable=False)              # 评论内容
  is_agent = Column(Boolean, default=False)           # 是否分身评论
  created_at = Column(BigInteger, nullable=False)

class PostLike(Base):
  __tablename__ = "post_likes"
  id = Column(String, primary_key=True, default=lambda: str(uuid4()))
  post_id = Column(String, nullable=False)
  user_id = Column(String, nullable=False)
  created_at = Column(BigInteger, nullable=False)
  # UNIQUE(post_id, user_id)


# app/models/avatar.py

class AvatarMemory(Base):
  __tablename__ = "avatar_memories"
  id = Column(String, primary_key=True, default=lambda: str(uuid4()))
  user_id = Column(String, nullable=False)
  category = Column(String, nullable=False)           # fact/interest/personality/need/habit/relation
  content = Column(Text, nullable=False)
  source = Column(String, default="manual")           # diary/chat/manual/behavior
  source_ref = Column(String, default="")             # 来源引用 ID
  confidence = Column(Float, default=1.0)             # 0.0-1.0
  is_active = Column(Boolean, default=True)
  is_pinned = Column(Boolean, default=False)
  need_type = Column(String, nullable=True)           # buddy/dating/help/activity
  urgency = Column(String, nullable=True)             # active/passive
  expiry = Column(BigInteger, nullable=True)          # 过期时间戳
  match_status = Column(String, nullable=True)        # searching/matched/expired
  tags = Column(Text, default="[]")                   # JSON: string[]
  created_at = Column(BigInteger, nullable=False)
  updated_at = Column(BigInteger, nullable=False)

class AvatarStatus(Base):
  __tablename__ = "avatar_status"
  id = Column(String, primary_key=True, default=lambda: str(uuid4()))
  user_id = Column(String, unique=True, nullable=False)
  is_active = Column(Boolean, default=True)
  browsed_count = Column(Integer, default=0)
  matched_count = Column(Integer, default=0)
  chatting_count = Column(Integer, default=0)
  last_active_at = Column(BigInteger, default=0)
  enabled_channels = Column(Text, default='["buddy","help","share","dating"]')
  enabled_actions = Column(Text, default='["browse","match","comment"]')
  # 可额外包含 auto_approve_comment / auto_surf_comment
  match_range = Column(Text, default='{"school":"","distanceKm":10,"autoReplyDailyLimit":5,"autoReplyIntervalMinutes":30,"autoReplyMinScore":55}')

class AvatarMatch(Base):
  __tablename__ = "avatar_matches"
  id = Column(String, primary_key=True, default=lambda: str(uuid4()))
  user_id = Column(String, nullable=False)            # 被推荐的用户
  post_id = Column(String, nullable=False)            # 匹配的帖子
  match_score = Column(Integer, default=0)            # 0-100
  match_reasons = Column(Text, default="[]")          # JSON: string[]
  agent_conversation = Column(Text, default="[]")     # JSON: AgentConversationMessage[]
  status = Column(String, default="new")              # new/viewed/chatting/dismissed
  created_at = Column(BigInteger, nullable=False)

class AvatarProfile(Base):
  __tablename__ = "avatar_profiles"
  id = Column(String, primary_key=True, default=lambda: str(uuid4()))
  user_id = Column(String, unique=True, nullable=False)
  summary = Column(Text, default="")
  diary_count = Column(Integer, default=0)
  chat_count = Column(Integer, default=0)
  generated_at = Column(BigInteger, default=0)
```

---

## 接口汇总

| # | 方法 | 路径 | 模块 | 状态 |
|---|------|------|------|------|
| 1 | POST | /api/auth/register | 认证 | ✅ |
| 2 | POST | /api/auth/login | 认证 | ✅ |
| 3 | POST | /api/auth/logout | 认证 | ✅ |
| 4 | GET | /api/auth/health | 认证 | ✅ |
| 5 | GET | /api/user/profile | 用户 | ✅ |
| 6 | POST | /api/user/profile | 用户 | ✅ |
| 7 | GET | /api/user/growth | 用户 | ✅ |
| 8 | GET | /api/user/achievements | 用户 | ✅ |
| 9 | GET | /api/user/settings | 用户 | ✅ |
| 10 | POST | /api/user/settings | 用户 | ✅ |
| 11 | GET | /api/user/semester-report | 用户 | ✅ |
| 12 | GET | /api/user/portrait | 用户 | ✅ |
| 13 | POST | /api/user/portrait/refresh | 用户 | ✅ |
| 14 | GET | /api/user/agent-portrait | 用户 | ✅ |
| 15 | POST | /api/materials | 素材 | ✅ |
| 16 | GET | /api/materials | 素材 | ✅ |
| 17 | GET | /api/materials/{material_id} | 素材 | ✅ |
| 18 | PUT | /api/materials/{material_id} | 素材 | ✅ |
| 19 | DELETE | /api/materials/{material_id} | 素材 | ✅ |
| 20 | POST | /api/materials/{material_id}/emotion | 素材 | ✅ |
| 21 | POST | /api/materials/{material_id}/polish | 素材 | ✅ |
| 22 | POST | /api/materials/voice | 素材 | 🟡 |
| 23 | GET | /api/diaries/today-summary | 日记 | ✅ |
| 24 | POST | /api/diaries/generate | 日记 | ✅ |
| 25 | GET | /api/diaries | 日记 | ✅ |
| 26 | GET | /api/diaries/search | 日记 | ✅ |
| 27 | GET | /api/diaries/{diary_id} | 日记 | ✅ |
| 28 | PUT | /api/diaries/{diary_id} | 日记 | ✅ |
| 29 | DELETE | /api/diaries/{diary_id} | 日记 | ✅ |
| 30 | GET | /api/diaries/{diary_id}/emotion-trend | 日记 | ✅ |
| 31 | POST | /api/diaries/{diary_id}/extract | 日记 | ✅ |
| 32 | POST | /api/diaries/{diary_id}/derivative | 日记 | ✅ |
| 33 | GET | /api/derivatives | 衍生 | ✅ |
| 34 | POST | /api/derivatives/{deriv_id}/share | 衍生 | ✅ |
| 35 | GET | /api/anniversaries/today | 纪念日 | ✅ |
| 36 | GET | /api/anniversaries | 纪念日 | ✅ |
| 37 | POST | /api/anniversaries | 纪念日 | ✅ |
| 38 | PUT | /api/anniversaries/{ann_id} | 纪念日 | ✅ |
| 39 | DELETE | /api/anniversaries/{ann_id} | 纪念日 | ✅ |
| 40 | POST | /api/ai/tts | AI | ✅ |
| 41 | GET | /api/ai/fortune | AI | ✅ |
| 42 | POST | /api/chat | 对话 | ✅ |
| 43 | POST | /api/chat/stream | 对话 | ✅ |
| 44 | POST | /api/chat/close-session | 对话 | ✅ |
| 45 | GET | /api/chat/history | 对话 | ✅ |
| 46 | GET | /api/chat/session/{session_id}/messages | 对话 | ✅ |
| 47 | GET | /api/social/matches | 社交 | ✅ |
| 48 | POST | /api/social/match-requests | 社交 | ✅ |
| 49 | POST | /api/social/match-requests/{request_id}/respond | 社交 | ✅ |
| 50 | GET | /api/social/messages/{match_id} | 社交 | ✅ |
| 51 | POST | /api/social/messages/{match_id} | 社交 | ✅ |
| 52 | GET | /api/social/matches/{match_id}/report | 社交 | ✅ |
| 53 | POST | /api/social/buddy | 社交 | ✅ |
| 54 | POST | /api/social/buddy/{request_id}/respond | 社交 | ✅ |
| 55 | POST | /api/upload/avatar | 上传 | ✅ |
| 56 | POST | /api/upload/diary-image | 上传 | ✅ |
| 57 | POST | /api/upload/diary-images | 上传 | ✅ |
| 58 | POST | /api/upload/voice | 上传 | ✅ |
| 59 | POST | /api/upload/chat-file | 上传 | ✅ |
| 60 | GET | /api/study/pomodoros | 学习⚠️ | ✅ |
| 61 | POST | /api/study/pomodoros | 学习⚠️ | ✅ |
| 62 | POST | /api/study/pomodoros/{pomodoro_id}/complete | 学习⚠️ | ✅ |
| 63 | GET | /api/study/todos | 学习⚠️ | ✅ |
| 64 | POST | /api/study/todos | 学习⚠️ | ✅ |
| 65 | POST | /api/study/todos/{todo_id}/toggle | 学习⚠️ | ✅ |
| 66 | GET | /api/plaza/posts | 广场 | ✅ |
| 67 | GET | /api/plaza/posts/{post_id} | 广场 | ✅ |
| 68 | POST | /api/plaza/posts | 广场 | ✅ |
| 69 | POST | /api/plaza/posts/{post_id}/like | 广场 | ✅ |
| 70 | GET | /api/plaza/posts/{post_id}/comments | 广场 | ✅ |
| 71 | POST | /api/plaza/posts/{post_id}/comments | 广场 | ✅ |
| 72 | GET | /api/plaza/comments/inbox | 广场 | ✅ |
| 73 | POST | /api/plaza/posts/{post_id}/agent-comment | 广场 | ✅ |
| 74 | GET | /api/avatar/memories | 分身 | ✅ |
| 75 | POST | /api/avatar/memories | 分身 | ✅ |
| 76 | PUT | /api/avatar/memories/{memory_id} | 分身 | ✅ |
| 77 | DELETE | /api/avatar/memories/{memory_id} | 分身 | ✅ |
| 78 | GET | /api/avatar/status | 分身 | ✅ |
| 79 | PUT | /api/avatar/status | 分身 | ✅ |
| 80 | GET | /api/avatar/matches | 分身 | ✅ |
| 81 | POST | /api/avatar/matches/{match_id}/action | 分身 | ✅ |
| 82 | GET | /api/avatar/profile | 分身 | ✅ |
| 83 | POST | /api/avatar/profile/regenerate | 分身 | ✅ |
| 84 | GET | /api/avatar/card | 分身 | ✅ |
| 85 | POST | /api/avatar/card/regenerate | 分身 | ✅ |
| 86 | GET | /api/avatar/actions | 分身 | ✅ |
| 87 | POST | /api/avatar/actions/plaza-comment-draft | 分身 | ✅ |
| 88 | POST | /api/avatar/actions/auto-surf | 分身 | ✅ |
| 89 | POST | /api/avatar/actions/{action_id}/approve | 分身 | ✅ |
| 90 | POST | /api/avatar/actions/{action_id}/reject | 分身 | ✅ |
| 91 | POST | /api/memory/ingest | 记忆 | ✅ |
| 92 | GET | /api/memory/documents | 记忆 | ✅ |
| 93 | GET | /api/memory/documents/{document_id} | 记忆 | ✅ |
| 94 | POST | /api/memory/search | 记忆 | ✅ |
| 95 | POST | /api/memory/documents/{document_id}/extract | 记忆 | ✅ |
| 96 | GET | /api/memory/facts | 记忆 | ✅ |
| 97 | POST | /api/memory/facts | 记忆 | ✅ |
| 98 | PUT | /api/memory/facts/{fact_id} | 记忆 | ✅ |
| 99 | DELETE | /api/memory/facts/{fact_id} | 记忆 | ✅ |
| 100 | POST | /api/memory/profile/regenerate | 记忆 | ✅ |
**统计：** 本文档当前覆盖 100 个 `/api` 接口条目，其中 99 个 ✅、1 个 🟡、0 个 🔴

---

## 已知问题

1. **语音转写仍为占位实现**：`POST /api/materials/voice` 已完成上传与返回文本，但当前 `transcription` 仍为 fallback 文案，尚未接入真实语音识别服务。
2. **聊天附件暂未深度理解**：图片、文件、语音附件当前只作为结构化上下文参与提示词拼接，未接入 OCR、视觉问答或文件解析能力。
3. **学习模块**：v2 已废弃但路由仍注册，建议后续清理。
4. **自动生成任务部署注意**：22:00 自动补生成依赖后端常驻进程。多实例部署时建议仅保留单实例执行定时任务，避免重复扫描。

---

## MiniMax AI 接口一览

所有 AI 调用封装在 `app/ai/minimax_client.py`，通过 `MINIMAX_MOCK=true/false` 切换 Mock/真实模式。

| 方法 | 用途 | 模型 | 接入的路由 |
|------|------|------|-----------|
| chat_completion | 文本对话 | M2.7-highspeed | /chat, /ai/fortune |
| stream_chat | 流式对话（SSE） | M2.7-highspeed | /chat/stream |
| generate_image | 文生图 | image-01 | /user/agent-portrait, /diaries/{diary_id}/derivative |
| text_to_speech | TTS | speech-2.8-hd | /ai/tts |
| generate_music | 音乐生成 | music-2.5+ | 未接入 |
| extract_emotion | 情绪提取 | chat_completion | /materials/{material_id}/emotion |
| polish_text | 文字润色 | chat_completion | /materials/{material_id}/polish |
| generate_diary | 日记生成 | chat_completion | /diaries/generate |
| extract_info | 信息提取 | chat_completion | /diaries/{diary_id}/extract |
| generate_portrait | 用户画像 | chat_completion | /user/portrait/refresh |
| generate_match_report | 匹配报告 | chat_completion | /social/matches/{match_id}/report |
| detect_duplicate_chat_material | 对话素材判重 | chat_completion | /chat/close-session, /chat（静默切段时自动调用） |
| summarize_chat_session | 对话摘要 | chat_completion | /chat/close-session, /chat（静默切段时自动调用） |
| generate_avatar_profile | 分身侧写生成 | chat_completion | /avatar/profile/regenerate |
| match_post | 帖子匹配打分 / 自动冲浪兴趣判断 | chat_completion | /avatar/matches, /avatar/actions/auto-surf |
| agent_conversation | 分身对话模拟 / 广场评论草稿 | chat_completion | /avatar/matches, /avatar/actions/plaza-comment-draft, /plaza/posts/{post_id}/agent-comment |

---

*本文档从 `app/` 下所有 router.py、schemas.py、service.py 以及前端相关 API 调用提取，最后更新 2026-04-17。*
