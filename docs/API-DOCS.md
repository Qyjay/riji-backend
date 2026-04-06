# 日迹 App — RESTful API 接口文档

> **本文档从实际代码提取，记录所有已注册路由的完整信息。**
>
> 最后更新：2026-04-06
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

响应字段使用 **camelCase**（如 `userId`、`createdAt`），请求 body 使用 **snake_case**。

> 兼容说明：`GET /api/diaries/today-summary` 当前实现返回 snake_case（如 `material_count`、`has_diary`）。

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
| media_url | string | ❌ | 媒体文件 URL（先调 /upload 获得） |
| thumbnail_url | string | ❌ | 缩略图 URL |
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
  "mediaUrl": "",
  "thumbnailUrl": "",
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
  "mediaUrl": "",
  "thumbnailUrl": "",
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
| media_url | string | 媒体 URL |
| thumbnail_url | string | 缩略图 |
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
| file | File | 语音文件（mp3/wav/m4a，最大 20MB） |

**响应 data：** `{"url": "/uploads/voice/xxx.mp3", "transcription": "转写文字"}`

**使用场景：**
- 素材录制页录音转文字
- AI 对话页语音输入转文字

**实现状态：** 🟡 返回 Mock 数据，未实现真实语音转写（需对接 ASR API）

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
| weather | string | ❌ | 天气 |

**响应 data：** DiaryOut 对象（含 AI 生成的 title、content、emotionSummary）

**实现状态：** ✅ 已完成（调用 minimax_client.generate_diary）

**实现细节补充：**

- 当前实现每次调用都会新建 Diary 记录，不会覆盖同日期已有日记（与 TASK-B 文档里的“同日更新”伪代码不同）。
- 新建日记 `status` 初始值为 `draft`，`editCount=0`，`maxEdits=3`。

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
- **weather**：weather 字段 IN 匹配，支持逗号分隔的多个天气
- **from/to**：date 字段范围过滤（闭区间 BETWEEN）
- **排序**：结果按 created_at DESC 排序
- **空参数处理**：所有参数为空 = 不筛选（返回全部日记，仅分页）

**实现状态：** 🔴 待实现

---

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

### POST /api/chat — AI 对话 🔒

发送消息给 AI，返回纯文本回复（非 SSE 流式）。自动保存对话历史，并集成对话段（session）管理。

每次发消息时，后端会：
1. 检查是否有 open 的 ChatSession
2. 若超过静默阈值（用户设置），关闭旧 session 并生成 chat 素材
3. 将消息绑定到当前 session

**请求 Body：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| message | string | ✅ | 用户消息 |

**响应 data：** AI 回复文本（string）

**响应示例（触发素材生成时附带 meta）：**

```json
{
  "code": 0,
  "data": "AI 回复文本",
  "message": "ok",
  "meta": {
    "materialGenerated": true,
    "materialId": "uuid-xxx"
  }
}
```

> `meta` 字段仅在触发了旧 session 封闭并生成素材时附带，否则不出现。

**实现状态：** ✅ 已完成（调用 minimax_client.chat_completion，取最近 20 条历史作为上下文，集成 session 管理）

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
    {"role": "user", "content": "今天下午和小李去骑车了", "timestamp": 1711440180000},
    {"role": "assistant", "content": "听起来不错！去哪里骑的？", "timestamp": 1711440182000}
  ]
}
```

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
    {"role": "user", "content": "你好", "timestamp": 1711440000000},
    {"role": "assistant", "content": "你好呀！", "timestamp": 1711440001000}
  ],
  "total": 2
}
```

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

### POST /api/upload/voice — 上传语音素材 🔒

**Content-Type：** multipart/form-data

**请求参数：**

| 字段 | 类型 | 说明 |
|------|------|------|
| file | File | 语音（mp3/wav/m4a/ogg，最大 20MB） |

**响应 data：** `{"url": "/uploads/xxx/voice/xxx.mp3"}`

**实现状态：** 🟡 文件保存可用，但 upload/service.py 的 MIME 校验只支持图片类型，语音上传会被拦截

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

> 广场是校园社交信息流，支持帖子发布、浏览、频道筛选、点赞、评论、分身代回复等功能。

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

**实现状态：** 🔴 待实现

---

### GET /api/plaza/posts/{post_id} — 帖子详情 🔒

**响应 data：** PlazaPost 对象

**实现状态：** 🔴 待实现

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
- 触发分身引擎扫描（异步，详见 AI 分身模块）

**实现状态：** 🔴 待实现

---

### POST /api/plaza/posts/{post_id}/like — 点赞帖子 🔒

**请求 Body：** 无

**响应 data：** null

**核心逻辑：**
- 帖子 likes 字段 +1
- 建议维护 post_likes 表防止重复点赞（user_id + post_id 唯一）
- 取消点赞：再次调用同一接口则 likes -1（toggle 逻辑）

**实现状态：** 🔴 待实现

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
    "createdAt": 1711440000000
  }
]
```

**说明：** isAgent=true 表示该评论由用户的 AI 分身自动生成。分身评论的 authorName 显示为「XXX的分身」。

**实现状态：** 🔴 待实现

---

### POST /api/plaza/posts/{post_id}/comments — 添加评论 🔒

**请求 Body：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| content | string | ✅ | 评论内容 |
| is_agent | bool | ❌ | 是否为分身回复（默认 false） |

**响应 data：** PlazaComment 对象

**核心逻辑：**
- 创建评论记录，自动填充 authorName/authorAvatar（从 users 表获取）
- 帖子 comments 字段 +1
- 如果 is_agent=true，调用 AI 生成分身风格回复（可选：直接使用用户传入的 content）

**实现状态：** 🔴 待实现

---

## 13. AI 分身模块（Avatar）🆕

> AI 分身是用户的数字化代理，自动浏览广场帖子、匹配感兴趣的内容、代用户发起对话。
> 分身的行为由用户画像（记忆库）驱动。

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

**实现状态：** 🔴 待实现

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

**实现状态：** 🔴 待实现

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

**实现状态：** 🔴 待实现

---

### DELETE /api/avatar/memories/{memory_id} — 删除记忆 🔒

**响应 data：** null

**实现状态：** 🔴 待实现

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
  "enabledActions": ["browse", "match", "comment"],
  "matchRange": {
    "school": "南开大学",
    "distanceKm": 10
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
| enabledActions | string[] | 启用的动作：browse / match / comment |
| matchRange | object | 匹配范围：本校名称 + 距离半径 |

**实现状态：** 🔴 待实现

---

### PUT /api/avatar/status — 更新分身状态 🔒

**请求 Body（所有字段可选）：**

| 字段 | 类型 | 说明 |
|------|------|------|
| is_active | bool | 开关分身 |
| enabled_channels | string[] | 启用的频道 |
| enabled_actions | string[] | 启用的动作 |
| match_range | object | 匹配范围 |

**响应 data：** 更新后的 AvatarStatus 对象

**实现状态：** 🔴 待实现

---

### GET /api/avatar/matches — 分身推荐列表 🔒

分身自动浏览广场帖子后，根据用户画像匹配感兴趣的帖子，并与对方分身进行初步对话。

**响应 data：** 裸数组

```json
[
  {
    "id": "uuid",
    "postId": "uuid",
    "post": { "...PlazaPost 完整对象..." },
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

**实现状态：** 🔴 待实现

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

**实现状态：** 🔴 待实现

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

**实现状态：** 🔴 待实现

---

### POST /api/avatar/profile/regenerate — 重新生成侧写 🔒

**请求 Body：** 无

**响应 data：** AvatarProfile 对象（同 GET）

**核心逻辑：**
- 读取用户所有记忆 + 近期日记/聊天
- 调用 AI（chat_completion）生成人格摘要
- 写入数据库缓存

**实现状态：** 🔴 待实现

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
  match_range = Column(Text, default='{"school":"","distanceKm":10}')

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
| 3 | GET | /api/user/profile | 用户 | ✅ |
| 4 | POST | /api/user/profile | 用户 | ✅ |
| 5 | GET | /api/user/growth | 用户 | ✅ |
| 6 | GET | /api/user/achievements | 用户 | ✅ |
| 7 | GET | /api/user/settings | 用户 | ✅ |
| 8 | POST | /api/user/settings | 用户 | ✅ |
| 9 | GET | /api/user/semester-report | 用户 | ✅ |
| 10 | GET | /api/user/portrait | 用户 | ✅ |
| 11 | POST | /api/user/portrait/refresh | 用户 | ✅ |
| 12 | GET | /api/user/agent-portrait | 用户 | ✅ |
| 13 | POST | /api/materials | 素材 | ✅ |
| 14 | GET | /api/materials | 素材 | ✅ |
| 15 | GET | /api/materials/{material_id} | 素材 | ✅ |
| 16 | PUT | /api/materials/{material_id} | 素材 | ✅ |
| 17 | DELETE | /api/materials/{material_id} | 素材 | ✅ |
| 18 | POST | /api/materials/{material_id}/emotion | 素材 | ✅ |
| 19 | POST | /api/materials/{material_id}/polish | 素材 | ✅ |
| 20 | POST | /api/materials/voice | 素材 | 🟡 |
| 21 | GET | /api/diaries/today-summary | 日记 | ✅ |
| 22 | POST | /api/diaries/generate | 日记 | ✅ |
| 23 | GET | /api/diaries | 日记 | ✅ |
| 24 | GET | /api/diaries/{diary_id} | 日记 | ✅ |
| 25 | PUT | /api/diaries/{diary_id} | 日记 | ✅ |
| 26 | GET | /api/diaries/{diary_id}/emotion-trend | 日记 | ✅ |
| 27 | POST | /api/diaries/{diary_id}/extract | 日记 | ✅ |
| 28 | POST | /api/diaries/{diary_id}/derivative | 日记 | ✅ |
| 29 | GET | /api/derivatives | 衍生 | ✅ |
| 30 | POST | /api/derivatives/{deriv_id}/share | 衍生 | ✅ |
| 31 | GET | /api/anniversaries/today | 纪念日 | ✅ |
| 32 | GET | /api/anniversaries | 纪念日 | ✅ |
| 33 | POST | /api/anniversaries | 纪念日 | ✅ |
| 34 | PUT | /api/anniversaries/{ann_id} | 纪念日 | ✅ |
| 35 | DELETE | /api/anniversaries/{ann_id} | 纪念日 | ✅ |
| 36 | POST | /api/ai/tts | AI | ✅ |
| 37 | GET | /api/ai/fortune | AI | ✅ |
| 38 | POST | /api/chat | 对话 | ✅ |
| 39 | GET | /api/chat/history | 对话 | ✅ |
| 40 | GET | /api/social/matches | 社交 | ✅ |
| 41 | POST | /api/social/match-requests | 社交 | ✅ |
| 42 | POST | /api/social/match-requests/{request_id}/respond | 社交 | ✅ |
| 43 | GET | /api/social/messages/{match_id} | 社交 | ✅ |
| 44 | GET | /api/social/matches/{match_id}/report | 社交 | ✅ |
| 45 | POST | /api/social/buddy | 社交 | ✅ |
| 46 | POST | /api/social/buddy/{request_id}/respond | 社交 | ✅ |
| 47 | POST | /api/upload/avatar | 上传 | ✅ |
| 48 | POST | /api/upload/diary-image | 上传 | ✅ |
| 49 | POST | /api/upload/voice | 上传 | 🟡 |
| 50 | GET | /api/study/pomodoros | 学习⚠️ | ✅ |
| 51 | POST | /api/study/pomodoros | 学习⚠️ | ✅ |
| 52 | POST | /api/study/pomodoros/{pomodoro_id}/complete | 学习⚠️ | ✅ |
| 53 | GET | /api/study/todos | 学习⚠️ | ✅ |
| 54 | POST | /api/study/todos | 学习⚠️ | ✅ |
| 55 | POST | /api/study/todos/{todo_id}/toggle | 学习⚠️ | ✅ |

**统计：** 74 个路由，55 个 ✅，2 个 🟡，17 个 🔴（含 16 个广场 + 分身新增 + 1 个搜索）

---

## 已知问题

1. **语音上传 MIME 校验**：`upload/service.py` 的 `ALLOWED_IMAGE_TYPES` 只包含图片类型，`POST /api/upload/voice` 会因 MIME 校验失败而 400。需要新增语音 MIME 类型支持。
2. **语音转写**：`POST /api/materials/voice` 返回硬编码 Mock 数据，未接入真实语音转文字服务。
3. **学习模块**：v2 已废弃但路由仍注册，建议后续清理。
4. **同日重复生成策略**：`POST /api/diaries/generate` 在当前实现中会重复新建日记；若要符合 TASK-B 伪代码的“同日更新”，需补充 upsert 逻辑。
5. **社交消息发送接口缺失**：TASK-D 提及 `POST /api/social/messages/{match_id}`（发送消息），当前后端未注册该接口，`social_messages` 仅有读取逻辑。

---

## MiniMax AI 接口一览

所有 AI 调用封装在 `app/ai/minimax_client.py`，通过 `MINIMAX_MOCK=true/false` 切换 Mock/真实模式。

| 方法 | 用途 | 模型 | 接入的路由 |
|------|------|------|-----------|
| chat_completion | 文本对话 | M2.7-highspeed | /chat, /ai/fortune |
| stream_chat | 流式对话（SSE） | M2.7-highspeed | 未接入 |
| generate_image | 文生图 | image-01 | /user/agent-portrait, /diaries/{diary_id}/derivative |
| text_to_speech | TTS | speech-2.8-hd | /ai/tts |
| generate_music | 音乐生成 | music-2.5+ | 未接入 |
| extract_emotion | 情绪提取 | chat_completion | /materials/{material_id}/emotion |
| polish_text | 文字润色 | chat_completion | /materials/{material_id}/polish |
| generate_diary | 日记生成 | chat_completion | /diaries/generate |
| extract_info | 信息提取 | chat_completion | /diaries/{diary_id}/extract |
| generate_portrait | 用户画像 | chat_completion | /user/portrait/refresh |
| generate_match_report | 匹配报告 | chat_completion | /social/matches/{match_id}/report |
| generate_match_report | 匹配报告 | chat_completion | /social/matches/{id}/report |
| summarize_chat_session | 对话摘要 | chat_completion | /chat（session 封闭时自动调用）|
| *generate_avatar_profile* | *分身侧写生成* | *chat_completion* | */avatar/profile/regenerate* 🆕 待新增 |
| *match_post* | *帖子匹配打分* | *chat_completion* | */avatar/matches* 🆕 待新增 |
| *agent_conversation* | *分身对话模拟* | *chat_completion* | */avatar/matches* 🆕 待新增 |

---

*本文档从 `app/` 下所有 router.py、schemas.py、service.py 以及前端 `services/api/plaza.ts`、`services/api/avatar.ts` 提取，最后更新 2026-04-02。*
