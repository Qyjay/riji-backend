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
- 当 `emotion` 为空且 `content` 有值时，后端会自动触发情绪提取并写回

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

**补充规则：**
- 标签统一规范到：`开心 / 难过 / 愤怒 / 平静 / 感动 / 焦虑 / 期待 / 无聊`
- 模型返回 `悲伤` 等同义标签时会归一为 `难过`
- 模型异常或返回不可解析时，后端会使用文本关键词兜底（如“想哭”优先识别为“难过”）

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
  imageUnderstandings: string[]    // 图片视觉理解结果（按图片顺序逐条返回）
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
  weather?: string      // 天气信息，可选；若包含温度（如"多云 18℃"）后端会规范为"多云"
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
GET /diaries/search?q=&emotion=&tag=&weather=&from=&to=&page=&page_size=
```

**需要认证：** ✅

**Query 参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `q` | `string` | 否 | 关键词，匹配 `title/content/location` |
| `emotion` | `string` | 否 | 情绪筛选，逗号分隔多值（如 `开心,幸福`） |
| `tag` | `string` | 否 | 标签筛选，逗号分隔多值 |
| `weather` | `string` | 否 | 天气筛选，逗号分隔多值 |
| `from` | `string` | 否 | 起始日期 `YYYY-MM-DD` |
| `to` | `string` | 否 | 结束日期 `YYYY-MM-DD` |
| `page` | `number` | 否 | 页码，默认 `1` |
| `page_size` | `number` | 否 | 每页条数，默认 `20` |

**响应 `data`：**

```typescript
{
  items: Diary[]
  total: number
  page: number
  page_size: number
}
```

**实现说明：**
- `q` 对 `title/content/location` 做模糊搜索
- `from/to` 为闭区间日期过滤
- `emotion` 匹配 `emotionSummary.dominant`，支持逗号分隔多值（同维度 OR）
- `tag` 匹配 `tags` 数组（命中任一标签即可）
- `weather` 查询值会先做“去温度”规范化，再匹配 `weather` 字段；兼容历史值如 `多云 18℃`（搜索 `多云` 可命中）
- 多条件组合为 AND 关系
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
  title: string                   // 对话段标题（AI 生成，关闭前为空）
  summary: string                 // 对话段摘要（AI 生成，关闭前为空）
  startTime: number               // 开始时间戳（ms）
  endTime: number | null          // 最后一条消息时间戳（ms）
  messageCount: number            // 消息条数
  mood: string                    // 情绪标签（AI 生成，关闭前为空）
  moodEmoji: string               // 情绪 emoji
  status: 'open' | 'closed'      // open=进行中，closed=已关闭（已物化）
  date: string                    // 归属日期 YYYY-MM-DD
  topicTags: string[]             // 话题标签（AI 生成）
  materialId: string | null       // 关联的 chat 素材 ID（closed 后才有）
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
  sessionId?: string                           // 指定发往的对话段 ID（可选）
}
```

> `message` 与 `attachments` 至少需要一项。
> `sessionId` 不传时自动使用当前 open 对话段（超过静默阈值则新建）；传入时直接使用该对话段（若已关闭则自动重新打开）。

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

### 4.5 获取对话段列表

```
GET /chat/sessions
```

**需要认证：** ✅

**Query 参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `page` | number | 1 | 页码（从 1 开始） |
| `pageSize` | number | 20 | 每页条数（1-100） |

**响应 `data`：**

```typescript
{
  items: ChatSession[]                         // 对话段列表，按开始时间倒序
  total: number                               // 总条数
  page: number                                // 当前页
  pageSize: number                            // 每页条数
}
```

**实现说明：**
- 返回该用户所有对话段（包括 open 和 closed 状态），按 `startTime` 倒序排列
- 每个 `ChatSession` 包含 `status`、`topicTags`、`materialId` 等完整字段
- 前端可用此接口渲染历史聊天列表页，点击某条进入 4.7 查看完整消息

### 4.6 新建对话段

```
POST /chat/sessions
```

**需要认证：** ✅

**请求体：** 无

**响应 `data`：**

```typescript
{
  session: ChatSession                         // 新建的对话段信息
  oldSessionClosed: boolean                    // 是否关闭了旧的 open 对话段
  materialGenerated: boolean                   // 是否为旧段生成了素材
  materialId: string | null                    // 生成的素材 ID
}
```

**实现说明：** 强制新建一个 open 对话段。若当前存在 open 的对话段，会先关闭并尝试物化（同 close-session 逻辑）。前端"新建对话"按钮调用此接口。

### 4.7 主动关闭当前对话段

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

### 4.8 获取对话段消息

```
GET /chat/session/{sessionId}/messages
```

**需要认证：** ✅

**响应 `data`：**

```typescript
{
  session: ChatSession                         // 对话段信息（含完整字段）
  messages: ChatMessage[]                      // 该段内的所有消息，按时间升序
}
```

**实现说明：** 用于历史聊天详情页，展示某个对话段内的完整消息列表。

### 4.9 WebSocket 流式对话

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

### 4.10 文字转语音（TTS）

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

### 4.11 AI 运势生成

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
  status: 'pending' | 'accepted' | 'rejected'   // 本条匹配当前状态（默认列表多为 accepted；见 §6.2 Query）
  matchType: 'long_term' | 'buddy'              // 长期匹配或短期搭子
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
GET /social/matches?include_pending=
```

**需要认证：** ✅

**Query 参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `include_pending` | boolean | `false` | 为 `true` 时返回 `status` 为 `accepted` 与 `pending` 的匹配（便于核对 AtoA `decide=connect`（§11.7.1.5）或 `POST /social/buddy` 产生的待处理搭子）；为 `false` 时行为与历史一致，仅 `accepted` |

**响应 `data`：** `Match[]`（每项含 `status`、`matchType`，见 §6.1 `Match`）

**实现说明：**
- 默认（`include_pending` 缺省或 `false`）：仅返回 `status="accepted"` 的匹配（含长期匹配与搭子），用于「已通过、可发消息」列表。
- `include_pending=true`：额外包含 `pending`，用于接收方查看待响应的搭子申请或联调核对；不含 `rejected`。
- 包含对方用户的昵称、头像、学校信息（后端 JOIN 查询）
- 按 `matchedAt`（即 `created_at`）降序排列

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
- 如果存在 `AvatarCard`，会把双方分身名片放入匹配上下文；AI 不可用时返回 fail-open 默认报告
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
| `requestId` | string | **`social.Match` 表主键**，即搭子记录在库里的 `id`。来源示例：`POST /social/buddy` 响应中的 `id`，或 **`POST /avatar/atoa/{interactionId}/decide`**（§11.7.1.5，`decision=connect`）响应中的 **`socialMatchId`**。**不得**使用分身互动 `id` 或用户 `id`。 |

**请求体：**

```typescript
{
  accept: boolean             // true=接受, false=拒绝
}
```

**响应 `data`：** `null`

**实现说明：** 仅 **`Match.target_id` 等于当前用户** 的待处理搭子可申请可响应（接收方操作）。发起方（`user_id`）调用本接口会返回业务错误提示，不应由发起方「自批」申请。

**Phase 8C 联动：** 若该 `social.Match` 由 **`POST /avatar/atoa/{interactionId}/decide`**（`connect`）创建，且发起方探针记录上 **`triggeredMatchId` 与本条 `Match.id` 一致**，接收方 `accept` / `reject` 后，服务端会将对应 **`GET /avatar/probe-log`** 条目的 **`outcome`** 同步为 **`connect_confirmed`** / **`connect_rejected`**。

**错误码与典型 `message`（`ApiException`）：**
- 记录不存在或 `id` 误用 → **404**，`message` 含引导：须使用 AtoA `decide=connect` 或 `POST /social/buddy` 返回的 **社交匹配 id**
- 当前用户为该搭子记录的 **发起方**（`user_id`）→ **400**，`message` 含「请让对方（接收方）登录后调用」
- 当前用户非该记录的参与方 → **404**，`message` 含「不是该申请的接收方」
- 该搭子 **`status` 已不是 `pending`**（已处理）→ **400**，`message`：`该搭子申请已处理，无需再次响应`

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

### 9.8 AI 分身评论草稿兼容入口

```
POST /plaza/posts/{postId}/agent-comment
```

> 旧版本该接口会直接发布分身评论。现在它只生成评论草稿，不会直接公开发布。
> 前端应展示草稿，并通过 `/avatar/actions/{actionId}/approve` 批准后再发布。

**需要认证：** ✅

**请求体：** 无

**响应 `data`：**

```typescript
{
  action: AgentAction
  requiresApproval: true
  message: string
}
```

**错误码：**
- 帖子不存在 → `code` 非 0 + `message: "帖子不存在"`
- 帖子不允许分身回复 → `code` 非 0 + `message: "该帖子不允许分身回复"`
- 用户未配置分身画像 → `code` 非 0 + `message: "请先设置分身画像"`

## 10. 记忆系统模块（Memory）

统一记忆系统将日记、AI 对话、素材、广场帖子/评论、社交私聊沉淀为长期记忆，并为聊天、分身侧写和 agent-to-agent 行动提供上下文。

### 10.1 搜索长期记忆

```
POST /memory/search
```

**需要认证：** ✅

**请求体：**

```typescript
{
  query: string
  scenario?: 'chat' | 'profile_generation' | 'avatar_comment' | string
  top_k?: number
  source_types?: string[]
}
```

**响应 `data`：** `MemorySearchItem[]`

**说明：** 当前实现为 SQLite 关键词 fallback，向量索引入口保留在 `app/memory/indexer.py`。

### 10.1.1 导出与删除全部记忆

```
GET /memory/export
DELETE /memory/all
```

**需要认证：** ✅

**说明：** 导出包含 documents、facts、profiles、avatarCards、agentActions；删除会清空当前用户的统一记忆数据。

### 10.1.2 Agent-to-agent 安全上下文

```
POST /memory/agent-context
```

**请求体：**

```typescript
{
  ownerUserId: string
  query?: string
  topK?: number
}
```

**说明：** 只返回对方 `AvatarCard` 和 public/school/match_card 级别记忆摘要，不返回 private 原文。

### 10.1.3 记忆维护

```
GET /memory/conflicts
POST /memory/maintenance/decay
```

**说明：** `conflicts` 只提示潜在冲突；`decay` 对旧的低稳定性 facts 做置信度淡化。

### 10.2 记忆文档列表

```
GET /memory/documents?source_type=&limit=50&offset=0
```

**需要认证：** ✅

**响应 `data`：** `MemoryDocument[]`

### 10.3 记忆文档详情

```
GET /memory/documents/{documentId}
```

**需要认证：** ✅

**响应 `data`：** `MemoryDocument`

### 10.4 删除记忆文档

```
DELETE /memory/documents/{documentId}
```

**需要认证：** ✅

**响应 `data`：** `null`

**说明：** 软删除 document，并删除关联 chunks。

### 10.5 抽取结构化记忆

```
POST /memory/documents/{documentId}/extract
```

**需要认证：** ✅

**响应 `data`：** `MemoryFact[]`

**说明：** 从记忆原文中抽取兴趣、习惯、经历、关系、边界、需求等结构化事实。

### 10.6 结构化记忆列表

```
GET /memory/facts?category=&active_only=true
```

**需要认证：** ✅

**响应 `data`：** `MemoryFact[]`

### 10.7 更新结构化记忆

```
PUT /memory/facts/{factId}
```

**需要认证：** ✅

**请求体：**

```typescript
{
  content?: string
  confidence?: number
  is_active?: boolean
  is_pinned?: boolean
}
```

**响应 `data`：** `MemoryFact`

### 10.8 重新生成记忆画像

```
POST /memory/profile/regenerate
```

**需要认证：** ✅

**响应 `data`：** `MemoryProfile`

### 10.9 历史数据补索引

```bash
python scripts/reindex_memories.py
python scripts/reindex_memories.py --user-id <user_id>
python scripts/reindex_memories.py --source diary --source chat_session
python scripts/reindex_memories.py --dry-run
python scripts/reindex_memories.py --rebuild-vector-index
python scripts/reindex_memories.py --progress-every 500 --fail-fast
```

**覆盖来源：** diary、material、chat_session、plaza_post、plaza_comment、social_message。

**说明：** `--rebuild-vector-index` 会重建已有 `memory_chunks` 的可选向量索引；未开启 `MEMORY_VECTOR_ENABLED` 或未安装 ChromaDB 时安全 no-op。

---

## 11. AI 分身模块（Avatar）

> 分身（Avatar）是用户在日迹里的 AI 代理。它记录用户兴趣和需求（记忆库），  
> 在广场自动为用户寻找搭子（推荐匹配），并按个性化计划定时冲浪广场内容。

### 11.1 分身记忆库

#### 11.1.1 获取记忆列表

```
GET /avatar/memories?category=
```

**需要认证：** ✅

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `category` | string | 否 | 筛选类别：`fact`/`interest`/`personality`/`need`/`habit`/`relation` |

**响应 `data`：** `AvatarMemory[]`

```typescript
interface AvatarMemory {
  id: string
  category: string
  content: string
  source: string              // "manual" | "diary" | "chat" | "behavior"
  sourceRef?: string
  confidence: number          // 0.0–1.0
  isActive: boolean
  isPinned: boolean
  needType?: string           // need 类型专属：buddy/dating/help/activity
  urgency?: string            // need 专属：active/passive
  expiry?: number             // 毫秒时间戳
  matchStatus?: string        // need 专属：searching/matched/expired
  tags: string[]
  createdAt: number
  updatedAt: number
}
```

#### 11.1.2 添加记忆

```
POST /avatar/memories
```

**需要认证：** ✅

**请求体：**

```typescript
{
  category: string    // fact/interest/personality/need/habit/relation
  content: string
}
```

**响应 `data`：** `AvatarMemory`

#### 11.1.3 更新记忆

```
PUT /avatar/memories/{memoryId}
```

**需要认证：** ✅

**请求体（所有字段可选）：**

```typescript
{
  content?: string
  isActive?: boolean
  isPinned?: boolean
  category?: string
  tags?: string[]
}
```

**响应 `data`：** `AvatarMemory`

#### 11.1.4 删除记忆

```
DELETE /avatar/memories/{memoryId}
```

**需要认证：** ✅

**响应 `data`：** `null`

---

### 11.2 分身状态与个性化冲浪配置

#### 11.2.1 获取分身状态

```
GET /avatar/status
```

**需要认证：** ✅

**响应 `data`：** `AvatarStatus`

```typescript
interface AvatarStatus {
  isActive: boolean               // 分身是否在线冲浪
  browsedCount: number            // 累计浏览帖子数
  matchedCount: number            // 累计推荐匹配数
  chattingCount: number           // 当前正在聊天数
  lastActiveAt: number            // 上次活跃时间戳（毫秒）
  enabledChannels: string[]       // 开启的频道：buddy/help/share/dating
  enabledActions: string[]        // 开启的动作：browse/match/comment
  matchRange: {
    school: string
    distanceKm: number
    autoReplyDailyLimit: number
    autoReplyIntervalMinutes: number
    autoReplyMinScore: number
  }

  // ── 个性化冲浪配置（Phase 1 新增）──────────────────────────
  surfFrequency: string           // "adaptive"|"low"|"medium"|"high"|"custom"
  surfWindow: {                   // 允许冲浪的时间段
    start: string                 // "09:00"
    end: string                   // "23:00"
    timezone: string              // "Asia/Shanghai"
  }
  quietMode: boolean              // 暂停分身（用户可随时开启）
  autoMatchEnabled: boolean       // 是否自动生成推荐匹配
  autoCommentEnabled: boolean     // 是否自动生成评论草稿
  autoPublishEnabled: boolean     // 是否自动发布（默认 false，高风险）
  nextSurfAt: number              // 下次冲浪时间戳（毫秒）
  lastSurfAt: number              // 上次冲浪时间戳（毫秒）
  dailySurfCount: number          // 今日已冲浪次数
  dailyActionCount: number        // 今日已执行行动数

  personalizedSurfPlan: {
    mode: "cold_start" | "personalized"
    confidence: number            // 0.0–0.95，数据越多越高
    preferredHours: number[]      // 你最活跃的小时（0-23）
    surfSlots: Array<{
      hour: number
      minute: number
      reason: string              // 人类可读的原因说明
    }>
    quietHours: number[]          // 安静时段（不冲浪）
    dailyLimit: number            // 每日冲浪上限
    minIntervalMinutes: number    // 两次冲浪最短间隔
    sampleSize: number            // 用于生成计划的数据点数
    feedbackHours: Record<string, number>   // 各时段的反馈得分（Phase 2）
    banditArms: Record<string, {            // UCB Bandit 臂状态（Phase 3）
      pulls: number
      totalReward: number
      meanReward: number
    }>
    totalPulls: number            // 历史总冲浪次数
    updatedAt: number
  }
}
```

#### 11.2.2 更新分身状态

```
PUT /avatar/status
```

**需要认证：** ✅

**请求体（所有字段可选）：**

```typescript
{
  isActive?: boolean
  enabledChannels?: string[]
  enabledActions?: string[]
  matchRange?: object
  surfFrequency?: "adaptive" | "low" | "medium" | "high" | "custom"
  surfWindow?: { start: string, end: string, timezone: string }
  quietMode?: boolean
  autoMatchEnabled?: boolean
  autoCommentEnabled?: boolean
  autoPublishEnabled?: boolean    // 开启前需先开启 autoCommentEnabled
}
```

**响应 `data`：** `AvatarStatus`

**实现说明：**
- `surfFrequency = "adaptive"` 时，后端立即重新计算 `personalizedSurfPlan` 和 `nextSurfAt`
- 开启 `autoPublishEnabled` 之前必须先开启 `autoCommentEnabled`，否则返回参数错误

---

### 11.3 使用习惯采集（个性化冲浪 Phase 1）

```
POST /avatar/usage-events
```

**需要认证：** ✅

**说明：** 前端在 App 生命周期关键节点调用，后端按 `weekday × hour` 聚合存储，用于生成个性化冲浪计划。不存储原始事件序列，只累加统计量（保护隐私）。

**请求体：**

```typescript
{
  event_type: "app_open" | "app_resume" | "app_close" | "active_ping" | "page_view"
  timestamp?: number    // 毫秒时间戳，不传则用服务端当前时间
  active_ms?: number    // 本次活跃时长（毫秒），用于 active_ping / app_close
  page?: string         // 当前页面：plaza / diary / chat / avatar / study
}
```

**事件发送时机：**

| 事件 | 何时发送 |
|------|---------|
| `app_open` | 用户从桌面冷启动 App |
| `app_resume` | App 从后台切回前台 |
| `app_close` | App 切到后台或关闭（附带本次活跃时长） |
| `active_ping` | 用户持续活跃时每 60 秒发一次心跳 |
| `page_view` | 切换到主要页面时 |

**响应 `data`：**

```typescript
{
  recorded: true
  personalizedSurfPlan: PersonalizedSurfPlan   // 更新后的最新计划
  nextSurfAt: number                            // 下次冲浪时间
  recordedAt: number                            // 服务端处理时间
}
```

**响应示例：**

```json
{
  "code": 0,
  "data": {
    "recorded": true,
    "nextSurfAt": 1746273045000,
    "recordedAt": 1746269410000,
    "personalizedSurfPlan": {
      "mode": "personalized",
      "confidence": 0.82,
      "preferredHours": [15, 20, 21, 22],
      "surfSlots": [
        { "hour": 14, "minute": 45, "reason": "你通常在 15:00 后使用 App，提前为你预热推荐" },
        { "hour": 19, "minute": 45, "reason": "你通常在 20:00 后使用 App，且历史上这个时段你更愿意接受推荐" }
      ],
      "dailyLimit": 5,
      "minIntervalMinutes": 120,
      "sampleSize": 42
    }
  }
}
```

---

### 11.4 冲浪执行日志

```
GET /avatar/surf-logs?limit=20
```

**需要认证：** ✅

**查询参数：**

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `limit` | number | 20 | 最多返回条数，上限 100 |

**响应 `data`：**

```typescript
{
  items: AvatarSurfLog[]
  total: number
}

interface AvatarSurfLog {
  id: string
  trigger: "scheduler" | "manual" | "post_publish" | "profile_update"
  status: "success" | "skipped" | "failed" | "running"
  scannedPosts: number
  scannedUsers: number
  generatedMatches: number
  generatedActions: number
  skippedReason: string     // 跳过时的原因，如"安静模式"/"已达今日上限"
  errorMessage: string
  startedAt: number
  finishedAt?: number
  // Phase 8A（AtoA 搭子模式冲浪统计）
  scannedAtoaPairs: number       // 本次进入 AtoA 探针的候选对数（与 Top-10 会话内实际生成条数一致）
  upgradedToMutual: number       // 本次升级为双向达标的对数
  surfReport: string             // 自然语言汇报摘要（可为空）
  top10SessionId?: string         // 本次创建的 avatar_atoa_sessions.id，无则缺省或空串
}
```

---

### 11.5 分身侧写

#### 11.5.1 获取侧写

```
GET /avatar/profile
```

**需要认证：** ✅

**响应 `data`：**

```typescript
{
  summary: string       // AI 生成的人格摘要（150-300字）
  diaryCount: number    // 基于多少篇日记生成
  chatCount: number     // 基于多少条对话生成
  generatedAt: number   // 生成时间戳
}
```

#### 11.5.2 重新生成侧写

```
POST /avatar/profile/regenerate
```

**需要认证：** ✅

**响应 `data`：** 同 11.5.1

**说明：** 调用 AI，读取记忆库 + 日记 + 聊天历史重新生成摘要。支持 Mock 模式（`MINIMAX_MOCK=true`）。

---

### 11.6 分身名片

#### 11.6.1 获取名片

```
GET /avatar/card
```

**需要认证：** ✅

**响应 `data`：**

```typescript
{
  displayName: string       // 展示名称
  publicSummary: string     // 可公开的简介摘要
  interestTags: string[]    // 兴趣标签
  socialIntent: string[]    // 社交意图
  conversationStyle: {
    tone: string
  }
  boundaries: string[]      // 社交边界
  visibility: "private" | "school" | "match_card" | "public"
  updatedAt: number
}
```

#### 11.6.2 重新生成名片

```
POST /avatar/card/regenerate
```

**需要认证：** ✅

**响应 `data`：** 同 11.6.1

---

### 11.7 分身 AtoA 匹配（Phase 8）

> Phase 8A：`run_avatar_surf_for_user`（外部 `scripts/run_avatar_scheduler.py` 等）内建 **AtoA Top-10 探针**：写入 `avatar_atoa_sessions` / `avatar_atoa_interactions`，对话由大模型生成；监察接口见 **§11.7.1**。双向达标记录同时落在 `AvatarMatch`（`matchType="atoa"`），列表见 **§11.7.1.3**。
> Phase 8B / 8C：用户对单条探针「继续聊」或「打断 / 结交」，见 **§11.7.1.4**、**§11.7.1.5**；结交产生的待处理搭子与 **§6.2**、**§6.9** 一致。

#### 11.7.1 Phase 8 AtoA 搭子模式（探针日志 / 会话 / 继续聊 / 决策）

> 典型触发：外部调度执行 `run_avatar_surf_for_user`（如 `python scripts/run_avatar_scheduler.py --user <username>`），需分身开启且 `auto_match_enabled=true`，且全库满足 AtoA 冷启动人数门槛。对话由 **`LLM_PROVIDER`** 配置的大模型生成；`MINIMAX_MOCK=true` 时为模板对话（联调真实蓝心时请关闭 Mock）。

##### 11.7.1.1 分身探针日志（我发起的 AtoA）

```
GET /avatar/probe-log?limit=20&offset=0&outcome=&session_id=
```

**需要认证：** ✅

**范围与去重（实现约定，前端对齐）：**

- **默认（不传 `session_id`）**：只返回 **当前用户最近一次成功分身冲浪**（`AvatarSurfLog`，`status=success`，按 `started_at` 最新）所关联的 **`top10_session_id`**（即 `AvatarSurfLog.top10_session_id` → `avatar_atoa_sessions.id`）下的探针记录。
  - 若最近一次成功冲浪 **未产生 AtoA**（`top10_session_id` 为空），**`data` 为空数组 `[]`**。
- **`session_id` 有值**：仅在该次 **`avatar_atoa_sessions.id`** 下筛选（用于查看历史某轮会话），规则下同。
- **同一 `session_id`、同一对方用户 `userBId`**：若存在多条互动（多次冲浪重复探针），**只保留 `created_at` 最新的一条**（按对方用户去重后再分页）。
- **`outcome`**：在去重前的查询条件上筛选；**`limit` / `offset`**：在 **去重后的列表** 上分页。

**Query 参数：**

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `limit` | number | 20 | 1–100；作用于去重后的列表 |
| `offset` | number | 0 | 分页偏移；作用于去重后的列表 |
| `outcome` | string | 无 | 可选，精确筛选：`pending_user_decision` / `blocked` / `connected` / `connect_confirmed` / `connect_rejected` / `mutual` / `one_sided` / `incompatible` 等 |
| `session_id` | string | 无 | 可选；不传则限定为「最近一次成功冲浪」关联的会话 |

**响应 `data`：** `ProbeLogItem[]`（**裸数组**，与项目内其它 `GET /avatar/*` 列表一致）

```typescript
interface AtoaConversationTurn {
  role: "avatar_a" | "avatar_b"   // avatar_a = 发起方（当前用户）分身，avatar_b = 候选用户分身
  content: string
}

interface ProbeLogItem {
  id: string
  sessionId?: string
  userBId: string
  userBName: string
  userBAvatar: string
  interactionType: string         // 如 card_exchange
  outcome: string                 // 见附录 C「AtoA 探针 outcome」
  readableOutcome: string         // 中文可读说明
  scoreA: number
  scoreB: number
  sharedTopics: string[]
  reasonsA: string[]
  conversation: AtoaConversationTurn[]
  riskFlags: string[]
  interactionPhase: number        // 轮组序号，「继续聊」后递增
  userDecision?: string           // continue | block | connect
  isMutual: boolean
  triggeredMatchId?: string       // connect 成功后为 social.Match.id（与 §6.9 的 requestId 一致）
  createdAt: number
  updatedAt: number
}
```

##### 11.7.1.2 AtoA 候选池会话（Top-10 进度）

```
GET /avatar/atoa/sessions?limit=5&offset=0
```

**需要认证：** ✅

**范围（实现约定，前端对齐）：**

- 只返回 **最近一次成功分身冲浪**（同上，`AvatarSurfLog` `status=success` 按 `started_at` 最新）所关联的 **`top10_session_id`** 对应的那一条 **`AvatarAtoaSession`**。
- **`data` 长度为 0 或 1**：无成功冲浪、或最近一次冲浪未关联 AtoA 会话、或会话不存在时，为 **`[]`**。
- **`pendingCount` / `decidedCount`**：在该 `session_id` 下，先按 **`userBId`（对方用户）只保留最新一条互动**，再统计 outcome（与 §11.7.1.1 去重口径一致）。
- **`candidateCount`**：`candidate_ids`（粗筛候选用户 ID 列表）长度。
- **`limit` / `offset`**：保留兼容；当前实现下 **`offset > 0` 时返回 `[]`**（仅一页，至多一条会话摘要）。

**响应 `data`：** `AtoaSessionSummary[]`（裸数组）

```typescript
interface AtoaSessionSummary {
  id: string
  status: "active" | "completed" | "superseded"
  candidateCount: number          // 粗筛写入会话时的候选人数（candidate_ids 长度）
  excludedCount: number           // excluded_ids 长度（已打断等排除的候选）
  pendingCount: number            // 去重后的对方用户中，outcome 仍为 pending_user_decision 的人数
  decidedCount: number          // 去重后的对方用户中，已非 pending 的人数合计
  surfLogId?: string             // 关联的 AvatarSurfLog.id（若有）
  createdAt: number
  updatedAt: number
}
```

##### 11.7.1.3 AtoA 双向达标推荐列表

```
GET /avatar/mutual-matches?limit=20&offset=0
```

**需要认证：** ✅

**响应 `data`：** `MutualAtoaMatch[]`（裸数组，`AvatarMatch` 中 `matchType="atoa"` 且 `isMutual=true`）

```typescript
interface MutualAtoaMatch {
  id: string
  targetUserId: string
  targetUserName: string
  targetUserAvatar: string
  targetUserSchool: string
  targetCardInterests: string[]
  targetCardIntent: string[]
  myScore: number
  theirScore: number
  myReasons: string[]
  theirReasons: string[]
  intentType: string
  suggestedOpening: string
  status: string                  // new / viewed / chatting / dismissed
  peerMatchId?: string
  createdAt: number
}
```

##### 11.7.1.4 继续 AtoA 对话（Phase 8B）

```
POST /avatar/atoa/{interactionId}/continue
```

**需要认证：** ✅

**路径参数：** `interactionId` — **§11.7.1.1** 返回的 `ProbeLogItem.id`（且须为当前用户作为发起方 `user_a` 的记录）。

**请求体：** 无

**响应 `data`：**

```typescript
{
  id: string
  userBId: string
  userBName: string
  outcome: string               // 一般为 pending_user_decision
  interactionPhase: number
  newTurns: AtoaConversationTurn[]   // 本次新增 ≤3 轮（每轮 avatar_a + avatar_b 各一条）
  conversation: AtoaConversationTurn[]  // 合并后的全量对话
  updatedAt: number
}
```

**错误：** 非发起方 → **403**；`outcome` 已为 `blocked` / `connected` 等终态 → **400**（不允许继续聊）。

##### 11.7.1.5 AtoA 最终决策（Phase 8C）

```
POST /avatar/atoa/{interactionId}/decide
```

**需要认证：** ✅

**请求体：**

```typescript
{
  decision: "block" | "connect"
  openingMessage?: string   // connect 时可选；不传则用关联 AvatarMatch 的 suggestedOpening 等兜底
}
```

**响应 `data`：**

```typescript
{
  outcome: "blocked" | "connected"
  socialMatchId?: string      // connect 成功时非空，即 social.Match.id，用于 §6.2 / §6.9
}
```

**实现说明：**
- **`block`**：`AtoaInteraction.outcome=blocked`；关联 `AvatarMatch`（`atoa`）置 `dismissed`；对方不可见。
- **`connect`**：创建或复用 `social.Match`（`buddy`，`pending`），`AtoaInteraction.outcome=connected`，`isVisibleToB=true`；返回 **`socialMatchId`** 供接收方调 **§6.9**。

---

### 11.8 分身行动草稿与审批

#### 11.8.1 分身行动列表

```
GET /avatar/actions?status=draft
```

**需要认证：** ✅

**查询参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `status` | string | 筛选：`draft` / `published` / `rejected` |

**响应 `data`：** `AgentAction[]`

```typescript
interface AgentAction {
  id: string
  actionType: string      // "comment_post"
  targetType: string      // "plaza_post"
  targetId: string
  inputContext: object
  outputText: string      // 草稿内容
  status: "draft" | "published" | "rejected"
  createdAt: number
  updatedAt: number
}
```

#### 11.8.2 生成广场评论草稿

```
POST /avatar/actions/plaza-comment-draft
```

**需要认证：** ✅

**请求体：**

```typescript
{
  post_id: string
  parent_comment_id?: string   // 回复某条评论时传入
}
```

**响应 `data`：** `AgentAction`

**说明：** 只生成草稿，不直接发布。草稿读取分身侧写与长期记忆，提示词要求不得泄露私密原文。

#### 11.8.3 触发一次分身自动冲浪

```
POST /avatar/actions/auto-surf
```

**需要认证：** ✅

**请求体：**

```typescript
{
  limit?: number    // 本次最多生成几条草稿，默认 1，最大 5
}
```

**响应 `data`：**

```typescript
{
  actions: AgentAction[]
  publishedCount: number
  draftCount: number
  skippedReason: string    // 跳过时的原因
}
```

#### 11.8.4 批准分身行动

```
POST /avatar/actions/{actionId}/approve
```

**需要认证：** ✅

**响应 `data`：** `AgentAction`

**说明：** 当前支持批准 `comment_post`，会发布一条 `isAgent=true` 的广场评论。批准后触发 UCB Bandit 正向反馈（+4）。

#### 11.8.5 拒绝分身行动

```
POST /avatar/actions/{actionId}/reject
```

**需要认证：** ✅

**响应 `data`：** `AgentAction`

**说明：** 拒绝后触发 UCB Bandit 负向反馈（-2），帮助分身学习你不喜欢的时段/内容。

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
| 26 | GET | `/diaries/search` | Diary | 搜索日记 |
| 27 | POST | `/chat` | Chat | AI 对话（非流式） |
| 28 | POST | `/chat/stream` | Chat | AI 对话（SSE 流式） |
| 29 | GET | `/chat/history?limit=` | Chat | 聊天历史（近期消息扁平列表） |
| 30 | GET | `/chat/sessions` | Chat | 对话段列表（分页） |
| 31 | POST | `/chat/sessions` | Chat | 新建对话段 |
| 32 | POST | `/chat/close-session` | Chat | 关闭当前对话段 |
| 33 | GET | `/chat/session/{sessionId}/messages` | Chat | 获取对话段消息 |
| 34 | WS | `/ws/chat?token=` | Chat | WebSocket 流式对话 |
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
| 43 | GET | `/social/matches?include_pending=` | Social | 已匹配列表（可选含 pending 搭子） |
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
| 71 | GET | `/avatar/memories?category=` | Avatar | 分身记忆列表 |
| 72 | POST | `/avatar/memories` | Avatar | 添加记忆 |
| 73 | PUT | `/avatar/memories/{memoryId}` | Avatar | 更新记忆 |
| 74 | DELETE | `/avatar/memories/{memoryId}` | Avatar | 删除记忆 |
| 75 | GET | `/avatar/status` | Avatar | 获取分身状态（含个性化冲浪计划） |
| 76 | PUT | `/avatar/status` | Avatar | 更新分身状态 |
| 77 | POST | `/avatar/usage-events` | Avatar | 上报 App 使用事件（个性化冲浪学习） |
| 78 | GET | `/avatar/surf-logs?limit=` | Avatar | 分身冲浪执行日志 |
| 79 | GET | `/avatar/profile` | Avatar | 获取分身侧写 |
| 80 | POST | `/avatar/profile/regenerate` | Avatar | 重新生成分身侧写 |
| 81 | GET | `/avatar/card` | Avatar | 获取分身名片 |
| 82 | POST | `/avatar/card/regenerate` | Avatar | 重新生成分身名片 |
| 83 | GET | `/avatar/actions?status=` | Avatar | 分身行动列表 |
| 84 | POST | `/avatar/actions/plaza-comment-draft` | Avatar | 生成广场评论草稿 |
| 85 | POST | `/avatar/actions/auto-surf` | Avatar | 触发一次分身自动冲浪 |
| 86 | POST | `/avatar/actions/{actionId}/approve` | Avatar | 批准分身行动 |
| 87 | POST | `/avatar/actions/{actionId}/reject` | Avatar | 拒绝分身行动 |
| 88 | GET | `/avatar/probe-log?limit=&offset=&outcome=&session_id=` | Avatar | Phase 8A：默认仅最近一次成功冲浪对应会话的探针；按对方用户去重；可传 `session_id` 查历史会话 |
| 89 | GET | `/avatar/atoa/sessions?limit=&offset=` | Avatar | Phase 8A：仅最近一次成功冲浪对应的 Top-10 会话摘要（0～1 条）；pending/decided 按对方用户去重统计 |
| 90 | GET | `/avatar/mutual-matches?limit=&offset=` | Avatar | Phase 8A：AtoA 双向达标推荐列表 |
| 91 | POST | `/avatar/atoa/{interactionId}/continue` | Avatar | Phase 8B：继续 AtoA 分身对话 |
| 92 | POST | `/avatar/atoa/{interactionId}/decide` | Avatar | Phase 8C：打断或结交（结交返回 socialMatchId） |

**共计 92 个接口**（Auth 4 + Material 8 + Upload 2 + Diary 12 + Chat 6 + AI 2 + User 8 + Social 10 + Anniversary 5 + Study 6 + Plaza 9 + **Avatar 22**）

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
| 分身推荐状态 | `'new'` \| `'viewed'` \| `'chatting'` \| `'dismissed'` | `AgentMatch.status`（`chatting` 由 AtoA 互动写入；`dismissed` 由 Phase 8C `decision=block` 写入） |
| 分身推荐匹配来源 | `'post'` \| `'user'` \| `'atoa'` | `AvatarMatch.matchType` |
| AtoA 探针 outcome | `'pending_user_decision'` \| `'blocked'` \| `'connected'` \| `'connect_confirmed'` \| `'connect_rejected'` \| `'mutual'` \| `'one_sided'` \| `'incompatible'` \| … | `GET /avatar/probe-log` 每条 `outcome`；终态以前三者为 Phase 8C 主路径 |
| 分身推荐意图类型 | `'buddy'` \| `'help'` \| `'share'` \| `'dating'` | `AvatarMatch.intentType` |
| 冲浪频率模式 | `'adaptive'` \| `'low'` \| `'medium'` \| `'high'` \| `'custom'` | `AvatarStatus.surfFrequency` |
| 使用事件类型 | `'app_open'` \| `'app_resume'` \| `'app_close'` \| `'active_ping'` \| `'page_view'` | `POST /avatar/usage-events` |
| 冲浪计划模式 | `'cold_start'` \| `'personalized'` | `personalizedSurfPlan.mode` |
| 冲浪日志状态 | `'running'` \| `'success'` \| `'skipped'` \| `'failed'` | `AvatarSurfLog.status` |
| 冲浪触发来源 | `'scheduler'` \| `'manual'` \| `'post_publish'` \| `'profile_update'` | `AvatarSurfLog.trigger` |
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
