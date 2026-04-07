# 日迹 App — 后端 API 接口规范 v1.0

> **本文档从前端代码逆向提取，精确到字段名、类型、枚举值。后端实现必须严格遵循此规范，确保前后端零适配对接。**
>
> 生成时间：2026-03-25 18:30 CST
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

---

## 2. 素材模块（Material）

> 素材是日记的原始输入——拍照、语音、文字。AI 日记基于当天素材生成。

### 2.1 数据结构：`RawMaterial`

```typescript
interface RawMaterial {
  id: string
  userId: string
  type: 'image' | 'voice' | 'text'    // 素材类型枚举
  content: string                       // 文字内容（text 类型）或描述/转写文字（image/voice 类型）
  mediaUrl: string                      // 媒体文件 URL（image/voice 类型，text 为空字符串）
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
}
```

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

### 3.7 获取情绪趋势

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

### 3.8 AI 信息提取

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

### 3.9 生成衍生内容

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

### 3.10 获取衍生内容列表

```
GET /derivatives?diary_id={diaryId}
```

**需要认证：** ✅

**Query 参数：**

| 参数       | 类型     | 必填 | 说明                       |
| ---------- | -------- | ---- | -------------------------- |
| `diary_id` | `string` | 否   | 按日记 ID 筛选，不传则返回全部 |

**响应 `data`：** `DiaryDerivative[]` 数组

### 3.11 设置衍生内容分享范围

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

### 3.12 获取今日概览

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

---

## 4. AI 模块

### 4.1 AI 对话

```
POST /chat
```

**需要认证：** ✅

**请求体：**

```typescript
{
  message: string   // 用户消息，必填
}
```

**响应 `data`：** `string` — AI 回复的纯文本

> **SSE 流式说明：** 前端 `chat/index.vue` 中目前是**模拟打字机效果**（逐字显示），并未使用真正的 SSE/EventSource。当前实现是一次性拿到完整回复后用 `setInterval` 逐字渲染。
>
> **建议后端同时支持：**
> 1. 当前模式：`POST /chat` 返回完整文本
> 2. 后续升级：`POST /chat/stream` 返回 SSE 流（`text/event-stream`）

### 4.2 获取聊天历史

```
GET /chat/history?limit={limit}
```

**需要认证：** ✅

**Query 参数：**

| 参数    | 类型     | 默认值 | 说明       |
| ------- | -------- | ------ | ---------- |
| `limit` | `number` | `20`   | 获取条数   |

**响应 `data`：**

```typescript
{
  items: Array<{
    role: 'user' | 'assistant'    // 消息角色枚举
    content: string               // 消息内容
    timestamp: number             // Unix 毫秒时间戳
  }>
  total: number
}
```

> **前端映射：** `items` → `list`

### 4.3 文字转语音（TTS）

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

### 4.4 AI 运势生成

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

### 6.1 数据结构

```typescript
// 已匹配用户
interface Match {
  id: string
  nickname: string
  avatar: string              // 头像 URL
  school: string
  commonTags: string[]        // 共同标签
  matchedAt: number           // Unix 毫秒时间戳
}

// 匹配请求
interface MatchRequest {
  id: string
  fromUid: string
  toUid: string
  status: 'pending' | 'accepted' | 'rejected'  // 状态枚举
  createdAt: number
}

// 聊天消息
interface Message {
  id: string
  matchId: string             // 关联的匹配 ID
  fromUid: string             // 发送者 ID
  content: string
  timestamp: number           // Unix 毫秒时间戳
}

// 匹配推荐
interface MatchRecommendation {
  id: string
  userId: string
  nickname: string
  avatar: string
  school: string
  commonInterests: string[]   // 共同兴趣
  compatibility: number       // 匹配度 0-100
}

// 匹配报告
interface MatchReport {
  compatibility: number       // 匹配度 0-100
  analysis: string            // 分析文案
  commonPoints: string[]      // 共同点
  differences: string[]       // 差异点
}

// 搭子申请
interface BuddyRequest {
  id: string
  fromUid: string
  toUid: string
  reason: string              // 申请理由
  status: 'pending' | 'accepted' | 'rejected'
  createdAt: number
}

// 用户画像
interface UserPortrait {
  preferences: Array<{
    category: string          // 偏好类别
    items: string[]           // 具体偏好项
  }>
  personality: string[]       // 性格标签数组
  relations: Array<{
    name: string
    relation: string          // 关系描述
  }>
  interests: string[]         // 兴趣列表
}
```

### 6.2 获取已匹配列表

```
GET /social/matches
```

**需要认证：** ✅

**响应 `data`：** `Match[]`

### 6.3 发送匹配请求

```
POST /social/match-requests
```

**需要认证：** ✅

**请求体：** `Partial<MatchRequest>`

```typescript
{
  toUid?: string    // 目标用户 ID
  // fromUid 由后端从 token 中获取
}
```

**响应 `data`：** `MatchRequest` 完整对象

### 6.4 获取匹配消息

```
GET /social/messages/{matchId}?limit={limit}&before={before}
```

**需要认证：** ✅

**Query 参数：**

| 参数     | 类型     | 默认值 | 说明                         |
| -------- | -------- | ------ | ---------------------------- |
| `limit`  | `number` | `50`   | 获取条数                     |
| `before` | `string` | 无     | 游标分页：返回此 ID 之前的消息 |

**响应 `data`：** `Message[]`

### 6.5 获取匹配报告

```
GET /social/matches/{matchId}/report
```

**需要认证：** ✅

**响应 `data`：** `MatchReport` 对象

### 6.6 响应匹配请求

```
POST /social/match-requests/{requestId}/respond
```

**需要认证：** ✅

**请求体：**

```typescript
{
  accept: boolean   // true=接受, false=拒绝
}
```

**响应 `data`：** `null` 或空对象

### 6.7 申请搭子

```
POST /social/buddy
```

**需要认证：** ✅

**请求体：**

```typescript
{
  target_user_id: string    // ⚠️ snake_case，目标用户 ID
  // reason 字段在前端 applyBuddy 函数签名中有，但未传给后端
}
```

> **注意：** 前端 `applyBuddy(targetId, reason)` 中 `reason` 参数存在于函数签名但**未包含在请求体中**。后端可选择支持 `reason` 字段。

**响应 `data`：** `BuddyRequest` 对象

### 6.8 响应搭子申请

```
POST /social/buddy/{requestId}/respond
```

**需要认证：** ✅

**请求体：**

```typescript
{
  accept: boolean   // true=接受, false=拒绝
}
```

**响应 `data`：** `null` 或空对象

### 6.9 获取用户画像

```
GET /user/portrait
```

**需要认证：** ✅

**响应 `data`：** `UserPortrait` 对象

> **注意路径：** 虽然在社交模块的 API 文件中定义，但路径是 `/user/portrait` 而非 `/social/portrait`。

### 6.10 刷新用户画像

```
POST /user/portrait/refresh
```

**需要认证：** ✅

**请求体：** 无

**响应 `data`：** `UserPortrait` 对象（重新生成的画像）

**业务逻辑：** 综合用户的日记数据、聊天记录等，调用 MiniMax API 重新生成用户画像。

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

## 附录 A：接口速查表

| # | 方法 | 路径 | 模块 | 说明 |
|---|------|------|------|------|
| 1 | POST | `/auth/register` | Auth | 注册 |
| 2 | POST | `/auth/login` | Auth | 登录 |
| 3 | POST | `/materials` | Material | 创建素材 |
| 4 | GET | `/materials?date=` | Material | 获取指定日期素材 |
| 5 | GET | `/materials/{id}` | Material | 素材详情 |
| 6 | PUT | `/materials/{id}` | Material | 更新素材 |
| 7 | DELETE | `/materials/{id}` | Material | 删除素材 |
| 8 | POST | `/materials/{id}/emotion` | Material | AI 情绪提取 |
| 9 | POST | `/materials/{id}/polish` | Material | AI 文字润色 |
| 10 | POST | `/materials/voice` | Material | 语音上传+转写 |
| 11 | POST | `/diaries/generate` | Diary | AI 生成日记 |
| 12 | GET | `/diaries?page=&page_size=` | Diary | 日记列表 |
| 13 | GET | `/diaries/{id}` | Diary | 日记详情 |
| 14 | PUT | `/diaries/{id}` | Diary | 更新日记 |
| 15 | GET | `/diaries/{id}/emotion-trend` | Diary | 情绪趋势 |
| 16 | POST | `/diaries/{id}/extract` | Diary | AI 信息提取 |
| 17 | POST | `/diaries/{id}/derivative` | Diary | 生成衍生内容 |
| 18 | GET | `/derivatives?diary_id=` | Diary | 衍生内容列表 |
| 19 | POST | `/derivatives/{id}/share` | Diary | 设置分享范围 |
| 20 | GET | `/diaries/today-summary?date=` | Diary | 今日概览 |
| 21 | POST | `/chat` | AI | AI 对话 |
| 22 | GET | `/chat/history?limit=` | AI | 聊天历史 |
| 23 | POST | `/ai/tts` | AI | 文字转语音 |
| 24 | GET | `/ai/fortune` | AI | 运势生成 |
| 25 | GET | `/user/profile` | User | 获取用户资料 |
| 26 | POST | `/user/profile` | User | 更新用户资料 |
| 27 | GET | `/user/agent-portrait` | User | AI 画像图 |
| 28 | GET | `/user/growth` | User | 成长数据 |
| 29 | GET | `/user/achievements` | User | 成就列表 |
| 30 | GET | `/user/settings` | User | 获取设置 |
| 31 | POST | `/user/settings` | User | 更新设置 |
| 32 | GET | `/user/semester-report` | User | 学期报告 |
| 33 | GET | `/social/matches` | Social | 已匹配列表 |
| 34 | POST | `/social/match-requests` | Social | 发送匹配请求 |
| 35 | GET | `/social/messages/{matchId}?limit=&before=` | Social | 匹配消息 |
| 36 | GET | `/social/matches/{matchId}/report` | Social | 匹配报告 |
| 37 | POST | `/social/match-requests/{requestId}/respond` | Social | 响应匹配请求 |
| 38 | POST | `/social/buddy` | Social | 申请搭子 |
| 39 | POST | `/social/buddy/{requestId}/respond` | Social | 响应搭子申请 |
| 40 | GET | `/user/portrait` | Social | 用户画像 |
| 41 | POST | `/user/portrait/refresh` | Social | 刷新画像 |
| 42 | GET | `/anniversaries` | Anniversary | 纪念日列表 |
| 43 | POST | `/anniversaries` | Anniversary | 创建纪念日 |
| 44 | PUT | `/anniversaries/{id}` | Anniversary | 更新纪念日 |
| 45 | DELETE | `/anniversaries/{id}` | Anniversary | 删除纪念日 |
| 46 | GET | `/anniversaries/today` | Anniversary | 今日纪念日 |
| 47 | GET | `/study/pomodoros` | Study | 番茄钟列表 |
| 48 | POST | `/study/pomodoros` | Study | 创建番茄钟 |
| 49 | POST | `/study/pomodoros/{id}/complete` | Study | 完成番茄钟 |
| 50 | GET | `/study/todos` | Study | 待办列表 |
| 51 | POST | `/study/todos` | Study | 创建待办 |
| 52 | POST | `/study/todos/{id}/toggle` | Study | 切换待办状态 |

**共计 52 个接口**（Auth 2 + Material 8 + Diary 10 + AI 4 + User 8 + Social 9 + Anniversary 5 + Study 6）

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
| 素材类型 | `'image'` \| `'voice'` \| `'text'` | `RawMaterial.type` |
| 日记状态 | `'draft'` \| `'published'` | `Diary.status` |
| 衍生类型 | `'comic'` \| `'novel'` \| `'share_card'` | `DiaryDerivative.type` |
| 分享范围 | `'private'` \| `'friends'` \| `'public'` | `DiaryDerivative.shareScope`, `Settings.diaryPrivacy` |
| 润色风格 | `'文艺'` \| `'幽默'` \| `'简洁'` \| `'温暖'` | `POST /materials/{id}/polish` |
| 纪念日来源 | `'manual'` \| `'ai_extracted'` | `Anniversary.source` |
| 消息角色 | `'user'` \| `'assistant'` | `ChatMessage.role` |
| 匹配状态 | `'pending'` \| `'accepted'` \| `'rejected'` | `MatchRequest.status`, `BuddyRequest.status` |
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
