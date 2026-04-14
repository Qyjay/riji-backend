# 日迹 App — 后端 API 接口规范 v1.0

> **本文档从前端代码逆向提取，精确到字段名、类型、枚举值。后端实现必须严格遵循此规范，确保前后端零适配对接。**
>
> 生成时间：2026-04-14 18:30 CST
> 前端仓库：https://github.com/Qyjay/riji-frontend

---

## 全局约定

### Base URL

```
http://localhost:8000/api
```

前端 `services/config.ts` 中 `API_BASE_URL = 'http://localhost:8000/api'`，所有请求路径拼接在此之后。

### 统一响应格式

所有 API 响应必须使用以下 JSON 包装格式：

```json
{
  "code": 0,
  "data": { ... },
  "message": "success"
}
```

| 字段      | 类型     | 说明                                |
| --------- | -------- | ----------------------------------- |
| `code`    | `number` | `0` = 成功，非 0 = 业务错误         |
| `data`    | `any`    | 业务数据（具体见各接口定义）         |
| `message` | `string` | 错误时的可读消息                     |

**前端兼容处理：** 如果响应体不含 `code` 字段，前端会直接使用 `res.data` 作为结果（裸响应兼容模式）。但**强烈建议统一使用包装格式**。

### 认证方式

- **JWT Bearer Token**
- 请求头：`Authorization: Bearer <token>`
- 前端在 `request.ts` 中自动注入 token
- 401 响应 → 前端自动清除 token 并跳转登录页

### Content-Type

- 默认：`application/json`
- 文件上传：另行标注

### 分页约定

分页接口统一使用 query 参数：

| 参数        | 类型     | 默认值 | 说明         |
| ----------- | -------- | ------ | ------------ |
| `page`      | `number` | `1`    | 页码（1 起） |
| `page_size` | `number` | `10`   | 每页条数     |

分页响应格式：

```json
{
  "items": [...],
  "total": 42
}
```

> **注意：** 前端代码中将 `items` 映射为 `list`，后端必须返回 `items` 字段。

### 时间戳约定

- 所有 `createdAt`、`updatedAt`、`timestamp`、`completedAt`、`matchedAt`、`unlockedAt` 字段均为 **Unix 毫秒时间戳**（`number`）
- 日期字符串格式：`"YYYY-MM-DD"`（如 `"2026-03-25"`）
- 纪念日月日格式：`"MM-DD"`（如 `"03-25"`）

---

## 1. 认证模块（Auth）

> 认证接口**不走 Mock**，始终调用真实后端。无需 JWT token。

### 1.1 注册

```
POST /auth/register
```

**请求体：**

```typescript
{
  username: string    // 4-20 字符，必填
  password: string    // 6-32 字符，必填
  name?: string       // 昵称，可选
  school?: string     // 学校，可选
  major?: string      // 专业，可选
}
```

**响应 `data`：**

```typescript
{
  token: string       // JWT token
  user: {
    id: string
    username: string
    name: string
    school: string
    major: string
    avatar: string    // 头像 URL
    level: number     // 用户等级
  }
}
```

**错误码：**
- 用户名已存在 → `code` 非 0 + `message` 说明

### 1.2 登录

```
POST /auth/login
```

**请求体：**

```typescript
{
  username: string    // 必填
  password: string    // 必填
}
```

**响应 `data`：** 同注册响应。

**错误码：**
- 用户名/密码错误 → `code` 非 0 + `message` 说明

### 1.3 登出

```
POST /auth/logout
```

**需要认证：** ✅

**请求体：** 无

**响应 `data`：** `null`

**响应 `message`：** `"已成功登出"`

**实现说明：**
- 后端采用 JWT 无状态认证，登出接口仅验证当前 Token 有效性后返回成功
- 前端收到成功响应后需自行清除本地存储的 Token 并跳转登录页
- Token 失效/过期 → 401（由全局认证中间件处理）

### 1.4 健康检查

```
GET /auth/health
```

**需要认证：** ❌

**响应 `data`：**

```typescript
{
  status: "ok"
}
```

**响应 `message`：** `"日迹后端运行中"`

**实现说明：** 前端「测试连接」按钮调用此接口，验证后端服务是否可达。

---

## 2. 素材模块（Material）

> 素材是日记的原始输入——拍照、语音、文字。AI 日记基于当天素材生成。

### 2.1 数据结构：`RawMaterial`

```typescript
interface RawMaterial {
  id: string
  userId: string
  type: 'image' | 'voice' | 'text' | 'chat'  // 素材类型枚举（chat = AI 对话自动生成的素材）
  content: string                       // 文字内容（text 类型）或描述/转写文字（image/voice 类型）或对话摘要（chat 类型）
  mediaUrl: string                      // 媒体文件 URL（image/voice 类型，text/chat 为空字符串）
  thumbnailUrl: string                  // 缩略图 URL（image 类型，其他为空字符串）
  location: {
    lat?: number                        // 纬度，可选
    lng?: number                        // 经度，可选
    address?: string                    // 地址文字，可选
  }
  emotion: {
    label: string                       // 情绪标签（如"开心"、"平静"、"激动"）
    score: number                       // 情绪分数 0.0-1.0
    emoji: string                       // 情绪 emoji（如"😊"、"😌"、"🎉"）
  }
  tags: string[]                        // 标签数组
  date: string                          // 所属日期 "YYYY-MM-DD"
  createdAt: number                     // Unix 毫秒时间戳
  // ========== chat 类型专属字段 ==========
  chatSessionId?: string                // 关联的对话段 ID（仅 chat 类型）
  startTime?: number                    // 对话开始时间 Unix 毫秒（仅 chat 类型）
  endTime?: number                      // 对话结束时间 Unix 毫秒（仅 chat 类型）
}
```

> **`chat` 类型说明：** 当用户离开 AI 对话页面或对话段超时关闭时，后端自动将对话段摘要生成为一条 `type='chat'` 的素材，关联到当天日期。`content` 为 AI 总结的对话内容。

### 2.2 创建素材

```
POST /materials
```

**需要认证：** ✅

**请求体：**

```typescript
{
  type: 'image' | 'voice' | 'text'     // 必填
  content?: string                       // 文字内容
  mediaUrl?: string                      // 媒体文件 URL
  date?: string                          // 日期 "YYYY-MM-DD"，默认今天
}
```

**响应 `data`：** `RawMaterial` 完整对象

**业务逻辑：**
- 新建素材的 `emotion` 可默认为 `{ label: "平静", score: 0.5, emoji: "😐" }`
- `tags` 默认为空数组 `[]`
- `thumbnailUrl` 如有 `mediaUrl` 则生成缩略图 URL

### 2.3 获取指定日期素材列表

```
GET /materials?date={date}
```

**需要认证：** ✅

**Query 参数：**

| 参数   | 类型     | 必填 | 说明                    |
| ------ | -------- | ---- | ----------------------- |
| `date` | `string` | 是   | 日期 `"YYYY-MM-DD"` 格式 |

**响应 `data`：** `RawMaterial[]` 数组

### 2.4 获取素材详情

```
GET /materials/{id}
```

**需要认证：** ✅

**响应 `data`：** `RawMaterial` 对象

### 2.5 更新素材

```
PUT /materials/{id}
```

**需要认证：** ✅

**请求体：** `Partial<RawMaterial>` — 只传需要更新的字段

```typescript
{
  content?: string
  mediaUrl?: string
  thumbnailUrl?: string
  location?: { lat?: number; lng?: number; address?: string }
  emotion?: { label: string; score: number; emoji: string }
  tags?: string[]
}
```

**响应 `data`：** 更新后的完整 `RawMaterial` 对象

### 2.6 删除素材

```
DELETE /materials/{id}
```

**需要认证：** ✅

**响应 `data`：** `null` 或空对象

### 2.7 AI 情绪提取

```
POST /materials/{id}/emotion
```

**需要认证：** ✅

**请求体：** 无（根据素材 id 自动读取内容）

**响应 `data`：**

```typescript
{
  label: string     // 情绪标签，如"开心"、"幸福"、"平静"、"激动"、"感动"
  score: number     // 情绪分数 0.0-1.0
  emoji: string     // 对应 emoji，如"😊"、"🥰"、"😌"、"🎉"、"🥹"
}
```

**业务逻辑：** 调用 MiniMax API 分析素材文本内容，提取情绪。

### 2.8 AI 文字润色

```
POST /materials/{id}/polish
```

**需要认证：** ✅

**请求体：**

```typescript
{
  style: string     // 润色风格，枚举值："文艺" | "幽默" | "简洁" | "温暖"
}
```

**响应 `data`：**

```typescript
{
  polished: string  // 润色后的文字
}
```

**业务逻辑：** 读取素材的 `content`，结合指定风格调用 MiniMax API 润色。

### 2.9 语音上传与转写

```
POST /materials/voice
```

**需要认证：** ✅

**请求体：**

```typescript
{
  filePath: string  // 语音文件路径（UniApp 本地路径）
}
```

> **实现说明：** 前端目前传 `filePath`，实际后端可能需要改为文件上传（`multipart/form-data`）。当前前端代码未使用 `uni.uploadFile`，后续可能调整。

**响应 `data`：**

```typescript
{
  url: string           // 上传后的语音文件 URL
  transcription: string // 语音转文字结果
}
```

### 2.10 上传日记图片

```
POST /upload/diary-image
```

**需要认证：** ✅

**Content-Type：** `multipart/form-data`

**请求体：**

| 字段   | 类型   | 说明                     |
| ------ | ------ | ------------------------ |
| `file` | `File` | 图片文件（JPEG/PNG 等） |

**响应 `data`：**

```typescript
{
  url: string            // 上传后的图片 URL
  thumbnailUrl: string   // 缩略图 URL
  location: any          // EXIF 中提取的地理位置信息（无则 null）
}
```

**实现说明：** 前端在 H5 平台使用 `uni.uploadFile`，字段名为 `file`。后端需接收 multipart 请求，存储图片并生成缩略图。

### 2.11 上传聊天文件

```
POST /upload/chat-file
```

**需要认证：** ✅

**Content-Type：** `multipart/form-data`

**请求体：**

| 字段   | 类型   | 说明                                   |
| ------ | ------ | -------------------------------------- |
| `file` | `File` | 附件文件（图片、PDF、文档等） |

**响应 `data`：**

```typescript
{
  url: string            // 上传后的文件 URL
  name: string           // 文件名
  size: number           // 文件大小（字节）
  mimeType: string       // MIME 类型
}
```

**实现说明：** 前端在 H5 平台使用 `fetch` + `FormData`，在 App 平台使用 `uni.uploadFile`。字段名均为 `file`。上传成功后前端将返回的信息作为 `ChatAttachment` 附加到聊天消息中。

---

## 3. 日记模块（Diary）

### 3.1 数据结构：`Diary`

```typescript
interface Diary {
  id: string
  title: string                    // 日记标题
  content: string                  // 日记正文（Markdown 或纯文本）
  date: string                     // 日期 "YYYY-MM-DD"
  weather: string                  // 天气，如 "☀️ 晴"、"🌧️ 阴"
  specialDate: string              // 特殊日期标记，如 "和小红认识满一年"，无则空字符串
  emotionSummary: {
    dominant: string               // 主导情绪，如 "开心"、"焦虑"
    trend: Array<{
      hour: number                 // 小时 (0-23)
      label: string                // 情绪标签
      score: number                // 情绪分数 (0-100)
    }>
  }
  materialIds: string[]            // 关联的素材 ID 数组
  style: string                    // 日记风格，如 "治愈系"、"日记式"、"故事型"、"活力型"
  editCount: number                // 已编辑次数
  maxEdits: number                 // 最大允许编辑次数（建议默认 3）
  status: 'draft' | 'published'   // 日记状态枚举
  createdAt: number                // Unix 毫秒时间戳
  updatedAt: number                // Unix 毫秒时间戳
  // ========== Legacy 兼容字段 ==========
  emotion: {
    emoji: string                  // 主情绪 emoji
    label: string                  // 主情绪标签
    score: number                  // 主情绪分数 (0-100)
  }
  images: string[]                 // 图片 URL 数组（从关联素材中提取）
  tags: string[]                   // 标签数组
  location: string                 // 地点文字
  hasComic: boolean                // 是否已生成漫画
  hasBGM: boolean                  // 是否已生成 BGM
}
```

> **重要：** `emotionSummary.trend[].score` 和 `emotion.score` 的值域不同！
> - `emotionSummary.trend[].score`：0-100 整数
> - `emotion.score`：0-100 整数（非 0-1）

### 3.2 数据结构：`DiaryDerivative`

```typescript
interface DiaryDerivative {
  id: string
  diaryId: string                              // 关联日记 ID
  type: 'comic' | 'novel' | 'share_card'      // 衍生内容类型枚举
  content: string                              // 文字内容（novel/share_card），漫画为空字符串
  mediaUrl: string                             // 媒体 URL（comic/share_card 的图片），novel 为空字符串
  shareScope: 'private' | 'friends' | 'public' // 分享范围枚举
  createdAt: number                            // Unix 毫秒时间戳
}
```

### 3.3 AI 生成日记

```
POST /diaries/generate
```

**需要认证：** ✅

**请求体：**

```typescript
{
  date: string          // 日期 "YYYY-MM-DD"，必填
  weather?: string      // 天气信息，可选
}
```

**响应 `data`：** 完整的 `Diary` 对象

**业务逻辑：**
1. 读取指定日期的所有素材（`materials`）
2. 结合天气、特殊日期（纪念日）、用户风格偏好
3. 调用 MiniMax API 生成日记
4. 新生成的日记 `status` 为 `'draft'`，`editCount` 为 `0`，`maxEdits` 为 `3`

### 3.4 获取日记列表

```
GET /diaries?page={page}&page_size={page_size}
```

**需要认证：** ✅

**Query 参数：**

| 参数        | 类型     | 默认值 | 说明     |
| ----------- | -------- | ------ | -------- |
| `page`      | `number` | `1`    | 页码     |
| `page_size` | `number` | `10`   | 每页条数 |

**响应 `data`：**

```typescript
{
  items: Diary[]    // ⚠️ 必须叫 items，前端会映射为 list
  total: number     // 总数
}
```

### 3.5 获取日记详情

```
GET /diaries/{id}
```

**需要认证：** ✅

**响应 `data`：** `Diary` 对象

### 3.6 更新日记内容

```
PUT /diaries/{id}
```

**需要认证：** ✅

**请求体：**

```typescript
{
  content: string   // 新的日记正文
}
```

**响应 `data`：** 更新后的 `Diary` 对象

**业务逻辑：**
- 检查 `editCount < maxEdits`，否则拒绝修改并返回错误
- 更新 `content`、`editCount += 1`、`updatedAt`

### 3.7 删除日记

```
DELETE /diaries/{id}
```

**需要认证：** ✅

**路径参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `id` | `string` | 日记 ID |

**响应 `data`**： `null`

**业务逻辑：**
- 验证日记归属（只能删除自己的日记）
- 日记不存在时返回 404

### 3.8 获取情绪趋势

```
GET /diaries/{id}/emotion-trend
```

**需要认证：** ✅

**响应 `data`：**

```typescript
{
  dominant: string
  trend: Array<{
    hour: number      // 0-23
    label: string     // 情绪标签
    score: number     // 0-100
  }>
}
```

### 3.9 AI 信息提取

```
POST /diaries/{id}/extract
```

**需要认证：** ✅

**请求体：** 无

**响应 `data`：**

```typescript
{
  anniversaries: Array<{
    title: string           // 纪念日标题
    date: string            // "MM-DD" 格式
    relatedPerson: string   // 相关人物
  }>
  relations: Array<{
    name: string            // 人名
    relation: string        // 关系，如 "朋友"、"家人"、"室友"
    mentions: number        // 提及次数
  }>
  preferences: Array<{
    category: string        // 偏好类别，如 "美食"、"学习"
    item: string            // 具体偏好项
    sentiment: string       // 情感倾向："positive" | "negative" | "neutral"
  }>
}
```

### 3.10 生成衍生内容

```
POST /diaries/{id}/derivative
```

**需要认证：** ✅

**请求体：**

```typescript
{
  type: 'comic' | 'novel' | 'share_card'   // 必填
}
```

**响应 `data`：** `DiaryDerivative` 对象

**业务逻辑：**
- `comic`：调用 MiniMax 图片生成 API，返回 `mediaUrl`，`content` 为空
- `novel`：调用 MiniMax 文本生成 API，返回 `content`，`mediaUrl` 为空
- `share_card`：生成分享文案 + 卡片图片，两者都有值

### 3.11 获取衍生内容列表

```
GET /derivatives?diary_id={diaryId}
```

**需要认证：** ✅

**Query 参数：**

| 参数       | 类型     | 必填 | 说明                       |
| ---------- | -------- | ---- | -------------------------- |
| `diary_id` | `string` | 否   | 按日记 ID 筛选，不传则返回全部 |

**响应 `data`：** `DiaryDerivative[]` 数组

### 3.12 设置衍生内容分享范围

```
POST /derivatives/{id}/share
```

**需要认证：** ✅

**请求体：**

```typescript
{
  scope: 'private' | 'friends' | 'public'   // 必填
}
```

**响应 `data`：** `null` 或空对象

### 3.13 获取今日概览

```
GET /diaries/today-summary?date={date}
```

**需要认证：** ✅

**Query 参数：**

| 参数   | 类型     | 必填 | 说明              |
| ------ | -------- | ---- | ----------------- |
| `date` | `string` | 是   | `"YYYY-MM-DD"` 格式 |

**响应 `data`：**

```typescript
{
  date: string
  material_count: number          // 当天素材总数
  materials: Array<{
    id: string
    type: string                  // "image" | "voice" | "text"
    content: string
    createdAt: number             // Unix 毫秒时间戳
    emotion?: {
      label: string
      emoji: string
      score: number               // 0.0-1.0
    }
  }>
  has_diary: boolean              // 今天是否已生成日记
  diary_id: string | null         // 日记 ID，无则 null
  diary_status: string | null     // "draft" | "published"，无则 null
}
```

> **注意：** 此接口中 `materials[].emotion.score` 范围是 **0.0-1.0**（不同于 Diary 里的 0-100）

### 3.14 搜索日记

```
POST /diaries/search
```

**需要认证：** ✅

**请求体：**

```typescript
{
  keyword?: string                    // 关键词（匹配标题/正文）
  dateRange?: [string, string]        // 日期范围 ["YYYY-MM-DD", "YYYY-MM-DD"]
  emotions?: string[]                 // 情绪标签筛选，如 ["开心", "焦虑"]
  tags?: string[]                     // 标签筛选
  weathers?: string[]                 // 天气筛选
}
```

> 所有字段均可选。多条件之间为 AND 关系。

**响应 `data`：** `Diary[]` — 符合条件的日记数组

**实现说明：**
- `keyword` 对 `title` 和 `content` 做模糊搜索
- `dateRange` 为闭区间 `[start, end]`
- `emotions` 匹配 `emotion.label` 字段
- `tags` 匹配 `tags` 数组（包含任一即匹配）
- `weathers` 匹配 `weather` 字段
- 结果按 `createdAt` 降序排列

---

## 4. AI 对话模块（Chat）

> AI 对话支持三种模式：非流式 POST、SSE 流式 POST、WebSocket 流式。
> 对话基于「对话段（Session）」管理：一段连续对话自动归入同一 session，静默超时后自动关闭旧 session 并生成对话素材。

### 4.1 数据结构

#### `ChatMessage`

```typescript
interface ChatMessage {
  id: string
  sessionId: string | null        // 所属对话段 ID
  clientMessageId: string | null  // 前端消息 ID（用于去重/确认）
  role: 'user' | 'assistant'
  content: string
  timestamp: number               // Unix 毫秒时间戳
  attachments: ChatAttachment[]
}

interface ChatAttachment {
  type: string                    // 附件类型
  name: string                    // 文件名
  url: string                     // 文件 URL
  mimeType?: string
  size?: number
  thumbnailUrl?: string
}
```

#### `ChatSession`

```typescript
interface ChatSession {
  id: string
  title: string                   // 对话段标题（AI 生成）
  summary: string                 // 对话段摘要（AI 生成）
  startTime: number               // 开始时间戳
  endTime: number | null          // 结束时间戳
  messageCount: number
  mood: string                    // 情绪标签
  moodEmoji: string               // 情绪 emoji
}
```

### 4.2 AI 对话（非流式）

```
POST /chat
```

**需要认证：** ✅

**请求体：**

```typescript
{
  message: string                              // 用户消息
  clientMessageId?: string                     // 前端消息 ID（可选，用于去重）
  attachments?: ChatAttachment[]               // 附件列表，默认 []
}
```

> `message` 与 `attachments` 至少需要一项。

**响应 `data`：**

```typescript
{
  sessionId: string                            // 当前对话段 ID
  userMessage: ChatMessage                     // 已保存的用户消息
  assistantMessage: ChatMessage                // AI 回复消息
  materialGenerated: boolean                   // 是否因旧 session 关闭而生成了素材
  materialId: string | null                    // 生成的素材 ID
}
```

### 4.3 AI 对话（SSE 流式）

```
POST /chat/stream
```

**需要认证：** ✅

**请求体：** 同 4.2

**响应：** `Content-Type: text/event-stream`

SSE 事件流按顺序推送以下事件：

| 事件类型 | 说明 | 数据格式 |
|----------|------|----------|
| `session` | 当前对话段 ID | `{ type: "session", sessionId: string }` |
| `ack` | 用户消息已保存确认 | `{ type: "ack", clientMessageId: string, message: ChatMessage }` |
| `chunk` | AI 回复文本片段（多次） | `{ type: "chunk", text: string }` |
| `done` | 流式回复完成 | `{ type: "done", message: ChatMessage }` |
| `error` | 发生错误 | `{ type: "error", message: string }` |

**前端使用 XHR/fetch 接收 SSE 流，逐步拼接 `chunk` 实现打字机效果。**

### 4.4 获取聊天历史

```
GET /chat/history?limit={limit}
```

**需要认证：** ✅

**Query 参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `limit` | number | 20 | 获取条数（1-100） |

**响应 `data`：**

```typescript
{
  items: ChatMessage[]
  total: number
}
```

**实现说明：**
- 如果用户没有任何聊天记录，返回一条 AI 欢迎消息
- 按时间倒序返回最近的消息

### 4.5 主动关闭当前对话段

```
POST /chat/close-session
```

**需要认证：** ✅

**请求体：** 无

**响应 `data`：**

```typescript
{
  sessionClosed: boolean                       // 是否有 session 被关闭
  materialGenerated: boolean                   // 是否生成了对话素材
  materialId: string | null                    // 生成的素材 ID
}
```

**实现说明：** 关闭当前 open 状态的对话段。如果用户设置了自动生成素材，会调用 AI 总结对话内容并生成一条 chat 类型的素材。

### 4.6 获取对话段消息

```
GET /chat/session/{sessionId}/messages
```

**需要认证：** ✅

**响应 `data`：**

```typescript
{
  session: ChatSession                         // 对话段信息
  messages: ChatMessage[]                      // 该段内的所有消息
}
```

### 4.7 WebSocket 流式对话

```
WebSocket /ws/chat?token={jwt_token}
```

> 通过 query 参数传递 JWT token 进行认证（WebSocket 无法使用 Authorization header）。

**消息协议：**

**客户端 → 服务端（JSON）：**

```typescript
{ message: string }
```

**服务端 → 客户端（JSON 事件流）：**

| 类型 | 数据 |
|------|------|
| `chunk` | `{ type: "chunk", text: string }` |
| `done` | `{ type: "done" }` |
| `error` | `{ type: "error", message: string }` |

**连接超时：** 30 秒内未发送消息则断开。

### 4.8 文字转语音（TTS）

```
POST /ai/tts
```

**需要认证：** ✅

**请求体：**

```typescript
{
  text: string        // 待转语音的文字，必填
  voice?: string      // 音色标识，可选
}
```

**响应 `data`：** `string` — 生成的音频文件 URL

### 4.9 AI 运势生成

```
GET /ai/fortune
```

**需要认证：** ✅

**响应 `data`：**

```typescript
{
  overall: number       // 综合运势 1-5（星级）
  study: number         // 学业运势 1-5
  social: number        // 社交运势 1-5
  health: number        // 健康运势 1-5
  tip: string           // 今日提示文案
  luckyColor: string    // 幸运颜色，如 "暖橙色"
  luckyNumber: number   // 幸运数字
}
```

---

## 5. 用户模块（User）

### 5.1 数据结构：`UserProfile`

```typescript
interface UserProfile {
  name: string
  school: string
  major: string
  level: number                     // 用户等级
  diaryCount: number                // 日记总数
  streakDays: number                // 连续写日记天数
  pomodoroCount: number             // 番茄钟总数
  avatar: string                    // 头像 URL
  styleTags?: string[]              // 写作风格标签，如 ["文艺", "治愈"]
  customStylePrompt?: string        // 自定义风格 prompt
}
```

### 5.2 获取用户资料

```
GET /user/profile
```

**需要认证：** ✅

**响应 `data`：** `UserProfile` 对象

### 5.3 更新用户资料

```
POST /user/profile
```

**需要认证：** ✅

**请求体：** `Partial<UserProfile>` — 只传需要更新的字段

```typescript
{
  name?: string
  school?: string
  major?: string
  avatar?: string
  style_tags?: string[]             // ⚠️ 注意：风格标签用 snake_case
  custom_style_prompt?: string      // ⚠️ 注意：自定义 prompt 用 snake_case
}
```

> **注意：** `style_tags` 和 `custom_style_prompt` 在请求体中用 **snake_case**（见前端 `updateStyleTags` 和 `updateCustomStylePrompt` 实现），但响应中的 `UserProfile` 用 **camelCase**（`styleTags`、`customStylePrompt`）。后端需同时支持两种命名或做映射。

**响应 `data`：** 更新后的 `UserProfile` 对象

### 5.4 获取 AI 画像图

```
GET /user/agent-portrait
```

**需要认证：** ✅

**响应 `data`：** `string` — AI 生成的用户画像图片 URL

### 5.5 获取成长数据

```
GET /user/growth
```

**需要认证：** ✅

**响应 `data`：**

```typescript
{
  diaries: Array<{
    date: string      // "YYYY-MM-DD"
    count: number     // 当天日记数
  }>
  emotions: Array<{
    label: string     // 情绪标签
    count: number     // 出现次数
  }>
  tags: Array<{
    label: string     // 标签名
    count: number     // 出现次数
  }>
  pomodoros: Array<{
    date: string      // "YYYY-MM-DD"
    count: number     // 当天番茄钟数
  }>
  streak: number[]    // 连续天数数组（每个元素代表连续记录的第 N 天）
}
```

### 5.6 获取成就列表

```
GET /user/achievements
```

**需要认证：** ✅

**响应 `data`：** `Achievement[]`

```typescript
interface Achievement {
  id: string
  title: string           // 成就名称
  description: string     // 成就描述
  icon: string            // emoji 图标
  unlocked: boolean       // 是否已解锁
  unlockedAt?: number     // 解锁时间（Unix 毫秒），未解锁时无此字段
}
```

### 5.7 获取设置

```
GET /user/settings
```

**需要认证：** ✅

**响应 `data`：**

```typescript
{
  theme: 'light' | 'dark'                     // 主题枚举
  notifications: boolean                       // 是否开启通知
  autoBGM: boolean                             // 是否自动生成 BGM
  diaryPrivacy: 'private' | 'friends' | 'public'  // 日记默认隐私
  language: string                             // 语言代码，如 "zh-CN"
}
```

### 5.8 更新设置

```
POST /user/settings
```

**需要认证：** ✅

**请求体：** `Partial<Settings>` — 只传需要更新的字段

**响应 `data`：** 更新后的完整 `Settings` 对象

### 5.9 获取学期报告

```
GET /user/semester-report
```

**需要认证：** ✅

**响应 `data`：**

```typescript
{
  totalDiaries: number          // 总日记数
  totalPomodoros: number        // 总番茄钟数
  topEmotions: Array<{
    label: string
    count: number
  }>
  topTags: Array<{
    label: string
    count: number
  }>
  writingTime: number           // 累计写作时长（小时）
  avgEmotion: number            // 平均情绪分 (0-100)
  streak: number                // 最长连续天数
  achievements: number          // 已解锁成就数
  highlights: string[]          // 亮点文案数组
}
```

---

## 6. 社交模块（Social）

> 社交匹配分为「长期匹配」和「短期搭子」两种类型，匹配通过后可互发消息。支持 AI 生成匹配报告。

### 6.1 数据结构

#### `Match`（已匹配用户）

```typescript
interface Match {
  id: string
  nickname: string              // 对方昵称
  avatar: string                // 对方头像 URL
  school: string                // 对方学校
  commonTags: string[]          // 共同标签
  matchedAt: number             // Unix 毫秒时间戳
}
```

#### `MatchRequest`（匹配请求）

```typescript
interface MatchRequest {
  id: string
  fromUid: string               // 发起方用户 ID
  toUid: string                 // 目标方用户 ID
  status: 'pending' | 'accepted' | 'rejected'
  createdAt: number
}
```

#### `Message`（社交消息）

```typescript
interface Message {
  id: string
  matchId: string               // 关联的匹配 ID
  fromUid: string               // 发送者 ID
  content: string               // 消息内容
  timestamp: number             // Unix 毫秒时间戳
}
```

#### `MatchReport`（AI 匹配报告）

```typescript
interface MatchReport {
  compatibility: number         // 匹配度 0-100
  analysis: string              // 分析文案
  commonPoints: string[]        // 共同点
  differences: string[]         // 差异点
}
```

#### `BuddyRequest`（搭子申请）

```typescript
interface BuddyRequest {
  id: string
  fromUid: string
  toUid: string
  reason: string                // 申请理由
  status: 'pending' | 'accepted' | 'rejected'
  createdAt: number
}
```

#### `UserPortrait`（用户画像）

```typescript
interface UserPortrait {
  preferences: Array<{
    category: string            // 偏好类别
    items: string[]             // 具体偏好项
  }>
  personality: string[]         // 性格标签数组
  relations: Array<{
    name: string
    relation: string            // 关系描述
  }>
  interests: string[]           // 兴趣列表
}
```

### 6.2 获取已匹配列表

```
GET /social/matches
```

**需要认证：** ✅

**响应 `data`：** `Match[]`

**实现说明：**
- 返回 `status="accepted"` 的所有匹配（含长期匹配和搭子）
- 包含对方用户的昵称、头像、学校信息（后端 JOIN 查询）
- 按 `matchedAt` 降序排列

### 6.3 发送匹配请求

```
POST /social/match-requests
```

**需要认证：** ✅

**请求体：**

```typescript
{
  toUid: string               // 目标用户 ID，必填
}
```

**响应 `data`：** `MatchRequest` 对象

**错误码：**
- `toUid` 为空 → `code` 非 0 + `message: "toUid 不能为空"`
- 目标用户不存在 → 404 + `message: "用户不存在"`
- 已存在匹配请求 → `code` 非 0 + `message: "已存在匹配请求"`

**实现说明：** 创建类型为 `long_term` 的匹配请求，初始状态为 `pending`。

### 6.4 获取匹配消息

```
GET /social/messages/{matchId}?limit={limit}&before={before}
```

**需要认证：** ✅

**路径参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `matchId` | string | 匹配 ID |

**Query 参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `limit` | number | 50 | 获取条数（1-200） |
| `before` | string | 无 | 游标分页：返回此消息 ID 之前的消息 |

**响应 `data`：** `Message[]`

**实现说明：**
- 验证当前用户属于该匹配关系
- 按 `timestamp` 升序返回（最旧到最新）
- 匹配不存在或不属于当前用户 → 404

### 6.5 发送消息

```
POST /social/messages/{matchId}
```

**需要认证：** ✅

**路径参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `matchId` | string | 匹配 ID |

**请求体：**

```typescript
{
  content: string             // 消息内容，必填（不能为空）
}
```

**响应 `data`：** `Message` 对象

**错误码：**
- 匹配未通过 → `code` 非 0 + `message: "匹配未通过，暂时不能发送消息"`
- 消息内容为空 → `code` 非 0 + `message: "消息内容不能为空"`
- 匹配不存在 → 404

**实现说明：** 仅当匹配状态为 `accepted` 时才允许发送消息。

### 6.6 获取匹配报告

```
GET /social/matches/{matchId}/report
```

**需要认证：** ✅

**响应 `data`：** `MatchReport` 对象

**实现说明：**
- 如果已有缓存的报告（`match_report` 字段非空），直接返回
- 否则调用 MiniMax AI 根据双方用户画像生成报告，并缓存到数据库
- Mock 模式下返回预设的示例报告

### 6.7 响应匹配请求

```
POST /social/match-requests/{requestId}/respond
```

**需要认证：** ✅

**路径参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `requestId` | string | 匹配请求 ID |

**请求体：**

```typescript
{
  accept: boolean             // true=接受, false=拒绝
}
```

**响应 `data`：** `null`

**错误码：**
- 请求不存在或不是发给当前用户的 → 404 + `message: "匹配请求不存在"`

**实现说明：** 只有 `target_id` 等于当前用户的请求才能响应。接受后匹配状态变为 `accepted`，拒绝变为 `rejected`。

### 6.8 申请搭子

```
POST /social/buddy
```

**需要认证：** ✅

**请求体：**

```typescript
{
  target_user_id: string      // ⚠️ snake_case，目标用户 ID，必填
  reason?: string             // 申请理由，默认空字符串
}
```

**响应 `data`：** `BuddyRequest` 对象

**错误码：**
- 目标用户不存在 → 404 + `message: "用户不存在"`

**实现说明：** 创建类型为 `buddy` 的匹配请求。`reason` 字段存储在 `match_report` 列中。

### 6.9 响应搭子申请

```
POST /social/buddy/{requestId}/respond
```

**需要认证：** ✅

**路径参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `requestId` | string | 搭子申请 ID |

**请求体：**

```typescript
{
  accept: boolean             // true=接受, false=拒绝
}
```

**响应 `data`：** `null`

**错误码：**
- 申请不存在或不是发给当前用户的搭子类型 → 404 + `message: "搭子申请不存在"`

### 6.10 获取用户画像

```
GET /user/portrait
```

**需要认证：** ✅

**响应 `data`：** `UserPortrait` 对象

> **注意路径：** 虽属社交模块逻辑，但路径为 `/user/portrait`（非 `/social/portrait`）。

### 6.11 刷新用户画像

```
POST /user/portrait/refresh
```

**需要认证：** ✅

**请求体：** 无

**响应 `data`：** `UserPortrait` 对象（重新生成的画像）

**实现说明：** 综合用户的日记数据、聊天记录等，调用 MiniMax AI 重新生成用户画像。Mock 模式下返回预设的示例画像。

---

## 7. 纪念日模块（Anniversary）

### 7.1 数据结构：`Anniversary`

```typescript
interface Anniversary {
  id: string
  userId: string
  title: string                    // 纪念日标题
  date: string                     // "MM-DD" 格式（月-日）
  year?: number                    // 起始年份，可选
  source: 'manual' | 'ai_extracted'  // 来源枚举
  relatedPerson: string            // 相关人物，无则空字符串
  diaryId?: string                 // 关联日记 ID，可选
  createdAt: number                // Unix 毫秒时间戳
}
```

### 7.2 获取纪念日列表

```
GET /anniversaries
```

**需要认证：** ✅

**响应 `data`：** `Anniversary[]`

### 7.3 创建纪念日

```
POST /anniversaries
```

**需要认证：** ✅

**请求体：** `Partial<Anniversary>`

```typescript
{
  title?: string
  date?: string             // "MM-DD"
  year?: number
  source?: 'manual' | 'ai_extracted'
  relatedPerson?: string
  diaryId?: string
}
```

**响应 `data`：** 完整的 `Anniversary` 对象

### 7.4 更新纪念日

```
PUT /anniversaries/{id}
```

**需要认证：** ✅

**请求体：** `Partial<Anniversary>` — 只传需要更新的字段

**响应 `data`：** 更新后的完整 `Anniversary` 对象

### 7.5 删除纪念日

```
DELETE /anniversaries/{id}
```

**需要认证：** ✅

**响应 `data`：** `null` 或空对象

### 7.6 获取今日纪念日 + 那年今日

```
GET /anniversaries/today
```

**需要认证：** ✅

**响应 `data`：**

```typescript
{
  today: Anniversary[]              // 今天匹配的纪念日
  on_this_day: Array<{              // "那年今日"的日记
    id: string
    title: string
    content: string
    date: string                    // "YYYY-MM-DD"
    emotion: {
      label: string
      score: number                 // 0-100
      emoji: string
    }
  }>
}
```

> **前端映射：**
> - `today` → `anniversaries`
> - `on_this_day` → `thisDateInHistory`（前端额外包装了 `yearsAgo` 字段，后端可选择在此包含）

---

## 8. 学习模块（Study）

> **优先级低：** 前辈已确认砍掉学习模块（番茄钟/待办），但前端代码仍保留。后端可延后实现。

### 8.1 数据结构

```typescript
interface Pomodoro {
  id: string
  task: string              // 任务名称
  subject: string           // 学科
  duration: number          // 时长（分钟）
  completedAt?: number      // 完成时间，未完成则无此字段
  createdAt: number         // Unix 毫秒时间戳
}

interface Todo {
  id: string
  content: string           // 待办内容
  completed: boolean        // 是否完成
  priority: 'low' | 'medium' | 'high'  // 优先级枚举
  createdAt: number         // Unix 毫秒时间戳
}
```

### 8.2 获取番茄钟列表

```
GET /study/pomodoros
```

**需要认证：** ✅

**响应 `data`：** `Pomodoro[]`

### 8.3 创建番茄钟

```
POST /study/pomodoros
```

**需要认证：** ✅

**请求体：** `Partial<Pomodoro>`

```typescript
{
  task?: string       // 默认 "新任务"
  subject?: string    // 默认 "其他"
  duration?: number   // 默认 25
}
```

**响应 `data`：** `Pomodoro` 对象

### 8.4 完成番茄钟

```
POST /study/pomodoros/{id}/complete
```

**需要认证：** ✅

**请求体：** 无

**响应 `data`：** `null` 或空对象

**业务逻辑：** 设置 `completedAt = Date.now()`

### 8.5 获取待办列表

```
GET /study/todos
```

**需要认证：** ✅

**响应 `data`：** `Todo[]`

### 8.6 创建待办

```
POST /study/todos
```

**需要认证：** ✅

**请求体：** `Partial<Todo>`

```typescript
{
  content?: string
  priority?: 'low' | 'medium' | 'high'   // 默认 "medium"
}
```

**响应 `data`：** `Todo` 对象

### 8.7 切换待办完成状态

```
POST /study/todos/{id}/toggle
```

**需要认证：** ✅

**请求体：** 无

**响应 `data`：** 更新后的 `Todo` 对象

---

## 9. 广场模块（Plaza）

> 校园广场：帖子信息流、评论、AI 分身自动评论、分身推荐。

### 9.1 数据结构

#### `PlazaPost`

```typescript
interface PlazaPost {
  id: string
  authorId: string
  authorName: string
  authorAvatar: string
  authorSchool: string
  authorMajor: string
  authorGrade: string
  type: 'buddy' | 'help' | 'share' | 'dating'
  content: string
  images: string[]
  location: string
  tags: string[]
  likes: number
  comments: number
  agentResponses: number
  createdAt: number
  isFromAgent: boolean
  allowAgentReply: boolean
  schoolOnly: boolean
}
```

#### `PlazaComment`

```typescript
interface PlazaComment {
  id: string
  postId: string
  authorId: string
  authorName: string
  authorAvatar: string
  content: string
  isAgent: boolean
  createdAt: number
}
```

#### `AgentMatch`

```typescript
interface AgentMatch {
  id: string
  postId: string
  post: PlazaPost
  matchScore: number
  matchReasons: string[]
  agentConversation: AgentConversationMessage[]
  status: 'new' | 'viewed' | 'chatting' | 'dismissed'
  createdAt: number
}

interface AgentConversationMessage {
  from: 'my_agent' | 'their_agent'
  content: string
  timestamp: number
}
```

### 9.2 获取帖子列表

```
GET /plaza/posts?channel=&q=&page=&page_size=
```

**需要认证：** ✅

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| channel | string | 否 | 频道筛选：`buddy`/`help`/`share`/`dating` |
| q | string | 否 | 关键词搜索（匹配帖子内容和标签） |
| page | number | 否 | 页码，默认 1 |
| page_size | number | 否 | 每页数量，默认 10 |

**响应 `data`：**

```typescript
{ items: PlazaPost[], total: number }
```

**实现说明：**
- `school_only=true` 的帖子只对同校用户可见
- 排序：`createdAt` 降序

### 9.3 获取帖子详情

```
GET /plaza/posts/{id}
```

**需要认证：** ✅

**响应 `data`：** `PlazaPost` 对象

### 9.4 创建帖子

```
POST /plaza/posts
```

**需要认证：** ✅

**请求体：**

```typescript
{
  type: 'buddy' | 'help' | 'share' | 'dating'
  content: string
  images?: string[]
  location?: string
  tags?: string[]
  allowAgentReply?: boolean    // 默认 true
  schoolOnly?: boolean         // 默认 false
}
```

**响应 `data`：** 创建的 `PlazaPost` 对象

### 9.5 点赞帖子

```
POST /plaza/posts/{id}/like
```

**需要认证：** ✅

**请求体：** 无

**响应 `data`：** `null`

**实现说明：** Toggle 逻辑——已赞则取消，未赞则点赞。

### 9.6 获取评论列表

```
GET /plaza/posts/{postId}/comments
```

**需要认证：** ✅

**响应 `data`：** `PlazaComment[]`

### 9.7 发送评论

```
POST /plaza/posts/{postId}/comments
```

**需要认证：** ✅

**请求体：**

```typescript
{
  content: string
  isAgent?: boolean   // 默认 false
}
```

**响应 `data`：** 创建的 `PlazaComment` 对象

### 9.8 AI 分身自动评论

```
POST /plaza/posts/{postId}/agent-comment
```

> 后端根据当前用户的 AI 分身画像 + 帖子内容，自动生成评论并发布。
> 前端无需传入评论内容，由 AI 生成。

**需要认证：** ✅

**请求体：** 无

**响应 `data`：**

```typescript
{
  comment: PlazaComment
}
```

**错误码：**
- 帖子不存在 → `code` 非 0 + `message: "帖子不存在"`
- 帖子不允许分身回复 → `code` 非 0 + `message: "该帖子不允许分身回复"`
- 用户未配置分身画像 → `code` 非 0 + `message: "请先设置分身画像"`

### 9.9 获取分身推荐匹配

```
GET /avatar/matches
```

**需要认证：** ✅

**响应 `data`：** `AgentMatch[]`

**实现说明：**
- 排除 `status="dismissed"` 的记录
- 按 `matchScore` 降序

### 9.10 处理分身推荐（接受/忽略）

```
POST /avatar/matches/{matchId}/action
```

**需要认证：** ✅

**请求体：**

```typescript
{
  action: 'chat' | 'dismiss'
}
```

**响应 `data`：** `null`

---

## 附录 A：接口速查表

| # | 方法 | 路径 | 模块 | 说明 |
|---|------|------|------|------|
| 1 | POST | `/auth/register` | Auth | 注册 |
| 2 | POST | `/auth/login` | Auth | 登录 |
| 3 | POST | `/auth/logout` | Auth | 登出 |
| 4 | GET | `/auth/health` | Auth | 健康检查 |
| 5 | POST | `/materials` | Material | 创建素材 |
| 6 | GET | `/materials?date=` | Material | 获取指定日期素材 |
| 7 | GET | `/materials/{id}` | Material | 素材详情 |
| 8 | PUT | `/materials/{id}` | Material | 更新素材 |
| 9 | DELETE | `/materials/{id}` | Material | 删除素材 |
| 10 | POST | `/materials/{id}/emotion` | Material | AI 情绪提取 |
| 11 | POST | `/materials/{id}/polish` | Material | AI 文字润色 |
| 12 | POST | `/materials/voice` | Material | 语音上传+转写 |
| 13 | POST | `/upload/diary-image` | Upload | 上传日记图片 |
| 14 | POST | `/upload/chat-file` | Upload | 上传聊天文件 |
| 15 | POST | `/diaries/generate` | Diary | AI 生成日记 |
| 16 | GET | `/diaries?page=&page_size=` | Diary | 日记列表 |
| 17 | GET | `/diaries/{id}` | Diary | 日记详情 |
| 18 | PUT | `/diaries/{id}` | Diary | 更新日记 |
| 19 | DELETE | `/diaries/{id}` | Diary | 删除日记 |
| 20 | GET | `/diaries/{id}/emotion-trend` | Diary | 情绪趋势 |
| 21 | POST | `/diaries/{id}/extract` | Diary | AI 信息提取 |
| 22 | POST | `/diaries/{id}/derivative` | Diary | 生成衍生内容 |
| 23 | GET | `/derivatives?diary_id=` | Diary | 衍生内容列表 |
| 24 | POST | `/derivatives/{id}/share` | Diary | 设置分享范围 |
| 25 | GET | `/diaries/today-summary?date=` | Diary | 今日概览 |
| 26 | POST | `/diaries/search` | Diary | 搜索日记 |
| 27 | POST | `/chat` | Chat | AI 对话（非流式） |
| 28 | POST | `/chat/stream` | Chat | AI 对话（SSE 流式） |
| 29 | GET | `/chat/history?limit=` | Chat | 聊天历史 |
| 30 | POST | `/chat/close-session` | Chat | 关闭当前对话段 |
| 31 | GET | `/chat/session/{sessionId}/messages` | Chat | 获取对话段消息 |
| 32 | WS | `/ws/chat?token=` | Chat | WebSocket 流式对话 |
| 33 | POST | `/ai/tts` | AI | 文字转语音 |
| 34 | GET | `/ai/fortune` | AI | 运势生成 |
| 35 | GET | `/user/profile` | User | 获取用户资料 |
| 36 | POST | `/user/profile` | User | 更新用户资料 |
| 37 | GET | `/user/agent-portrait` | User | AI 画像图 |
| 38 | GET | `/user/growth` | User | 成长数据 |
| 39 | GET | `/user/achievements` | User | 成就列表 |
| 40 | GET | `/user/settings` | User | 获取设置 |
| 41 | POST | `/user/settings` | User | 更新设置 |
| 42 | GET | `/user/semester-report` | User | 学期报告 |
| 43 | GET | `/social/matches` | Social | 已匹配列表 |
| 44 | POST | `/social/match-requests` | Social | 发送匹配请求 |
| 45 | GET | `/social/messages/{matchId}?limit=&before=` | Social | 获取匹配消息 |
| 46 | POST | `/social/messages/{matchId}` | Social | 发送消息 |
| 47 | GET | `/social/matches/{matchId}/report` | Social | AI 匹配报告 |
| 48 | POST | `/social/match-requests/{requestId}/respond` | Social | 响应匹配请求 |
| 49 | POST | `/social/buddy` | Social | 申请搭子 |
| 50 | POST | `/social/buddy/{requestId}/respond` | Social | 响应搭子申请 |
| 51 | GET | `/user/portrait` | Social | 用户画像 |
| 52 | POST | `/user/portrait/refresh` | Social | 刷新画像 |
| 53 | GET | `/anniversaries` | Anniversary | 纪念日列表 |
| 54 | POST | `/anniversaries` | Anniversary | 创建纪念日 |
| 55 | PUT | `/anniversaries/{id}` | Anniversary | 更新纪念日 |
| 56 | DELETE | `/anniversaries/{id}` | Anniversary | 删除纪念日 |
| 57 | GET | `/anniversaries/today` | Anniversary | 今日纪念日 |
| 58 | GET | `/study/pomodoros` | Study | 番茄钟列表 |
| 59 | POST | `/study/pomodoros` | Study | 创建番茄钟 |
| 60 | POST | `/study/pomodoros/{id}/complete` | Study | 完成番茄钟 |
| 61 | GET | `/study/todos` | Study | 待办列表 |
| 62 | POST | `/study/todos` | Study | 创建待办 |
| 63 | POST | `/study/todos/{id}/toggle` | Study | 切换待办状态 |
| 64 | GET | `/plaza/posts?channel=&q=&page=&page_size=` | Plaza | 帖子列表 |
| 65 | GET | `/plaza/posts/{id}` | Plaza | 帖子详情 |
| 66 | POST | `/plaza/posts` | Plaza | 创建帖子 |
| 67 | POST | `/plaza/posts/{id}/like` | Plaza | 点赞帖子 |
| 68 | GET | `/plaza/posts/{postId}/comments` | Plaza | 评论列表 |
| 69 | POST | `/plaza/posts/{postId}/comments` | Plaza | 发送评论 |
| 70 | POST | `/plaza/posts/{postId}/agent-comment` | Plaza | AI 分身自动评论 |
| 71 | GET | `/avatar/matches` | Plaza | 分身推荐匹配 |
| 72 | POST | `/avatar/matches/{matchId}/action` | Plaza | 处理分身推荐 |

**共计 72 个接口**（Auth 4 + Material 8 + Upload 2 + Diary 12 + Chat 6 + AI 2 + User 8 + Social 10 + Anniversary 5 + Study 6 + Plaza 9）

---

## 附录 B：字段命名约定

### 请求体（前端 → 后端）

前端代码中**混用** camelCase 和 snake_case。以下是**实际发送的字段名**：

| 接口 | 字段 | 实际命名 |
|------|------|----------|
| `POST /user/profile` | 风格标签 | `style_tags` (snake_case) |
| `POST /user/profile` | 自定义 prompt | `custom_style_prompt` (snake_case) |
| `POST /social/buddy` | 目标用户 ID | `target_user_id` (snake_case) |
| `POST /diaries/generate` | 日期 | `date` |
| `POST /diaries/generate` | 天气 | `weather` |
| 其他所有 | — | camelCase |

### 响应体（后端 → 前端）

前端 TypeScript interface 使用 **camelCase**（如 `userId`、`createdAt`、`mediaUrl`）。后端响应必须匹配。

**例外 — 分页响应：**
- 后端返回 `items`（不是 `list`）
- 后端返回 `total`

**例外 — 今日纪念日：**
- 后端返回 `today` 和 `on_this_day`（snake_case）

### 建议

后端统一使用 **snake_case** 存储和内部处理，在 API 层做序列化转换：
- 响应序列化时 snake_case → camelCase（除了已标注的例外）
- 或者全部使用 camelCase 输出，前端已按此预期

---

## 附录 C：枚举值完整列表

| 枚举 | 值 | 使用位置 |
|------|----|----------|
| 素材类型 | `'image'` \| `'voice'` \| `'text'` \| `'chat'` | `RawMaterial.type` |
| 日记状态 | `'draft'` \| `'published'` | `Diary.status` |
| 衍生类型 | `'comic'` \| `'novel'` \| `'share_card'` | `DiaryDerivative.type` |
| 分享范围 | `'private'` \| `'friends'` \| `'public'` | `DiaryDerivative.shareScope`, `Settings.diaryPrivacy` |
| 润色风格 | `'文艺'` \| `'幽默'` \| `'简洁'` \| `'温暖'` | `POST /materials/{id}/polish` |
| 纪念日来源 | `'manual'` \| `'ai_extracted'` | `Anniversary.source` |
| 消息角色 | `'user'` \| `'assistant'` | `ChatMessage.role` |
| 匹配状态 | `'pending'` \| `'accepted'` \| `'rejected'` | `MatchRequest.status`, `BuddyRequest.status` |
| 匹配类型 | `'long_term'` \| `'buddy'` | `Match.matchType` |
| 对话段状态 | `'open'` \| `'closed'` | `ChatSession.status` |
| SSE 事件类型 | `'session'` \| `'ack'` \| `'chunk'` \| `'done'` \| `'error'` | `POST /chat/stream` |
| 广场帖子类型 | `'buddy'` \| `'help'` \| `'share'` \| `'dating'` | `PlazaPost.type` |
| 分身推荐状态 | `'new'` \| `'viewed'` \| `'chatting'` \| `'dismissed'` | `AgentMatch.status` |
| 分身推荐操作 | `'chat'` \| `'dismiss'` | `POST /avatar/matches/{matchId}/action` |
| 主题 | `'light'` \| `'dark'` | `Settings.theme` |
| 待办优先级 | `'low'` \| `'medium'` \| `'high'` | `Todo.priority` |

---

## 附录 D：前端未调用但需要关注的接口

以下功能的前端页面存在但**目前使用硬编码 Mock 数据**（不经过 services 层），后端仍需实现以便后续对接：

| 页面 | 当前状态 | 需要的接口 |
|------|----------|------------|
| `social/match.vue` | 硬编码推荐数据 | `GET /social/recommendations`（推荐列表） |
| `growth/index.vue` | 硬编码成长数据 | 已有 `GET /user/growth` |
| `growth/achievements.vue` | 硬编码成就数据 | 已有 `GET /user/achievements` |
| `novel/index.vue` | 硬编码小说章节 | 待定义：`GET /novels`、`GET /novels/{id}/chapters` |
| `profile/agent-portrait.vue` | 硬编码画像数据 | 已有 `GET /user/portrait` + `GET /user/agent-portrait` |
| `profile/semester-report.vue` | 占位页面 | 已有 `GET /user/semester-report` |
| `discover/index.vue` | 静态展示 | 无需接口 |
| `social/index.vue` | 占位页面 | 后续定义 |
| `study/index.vue` | 占位页面 | 低优先级 |

---

## 附录 E：前端请求封装逻辑（request.ts 摘要）

```
1. 读取 uni.getStorageSync('token')
2. 拼接 header: { Authorization: 'Bearer <token>', Content-Type: 'application/json' }
3. URL = API_BASE_URL + options.url
4. HTTP 401 → 清除 token + currentUser → reLaunch('/pages/login/index')
5. HTTP 非 2xx → reject Error
6. 响应体有 code 字段 → code===0 取 data，否则 reject(message)
7. 响应体无 code 字段 → 直接返回 res.data（裸响应兼容）
```

---

*本文档由 BB 从前端源码逆向生成。前端每个 `request()` 调用、每个 TypeScript interface、每个 Mock 返回值都已交叉验证。照着这份写后端，不会接不上。*
