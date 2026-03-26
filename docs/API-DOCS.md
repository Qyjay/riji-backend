# 日迹 App — RESTful API 接口文档

> **本文档从实际代码提取，记录所有已注册路由的完整信息。**
>
> 最后更新：2026-03-26
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
  "language": "zh-CN"
}
```

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
| type | string | ✅ | "image" / "voice" / "text" |
| content | string | ❌ | 文字内容 |
| media_url | string | ❌ | 媒体文件 URL（先调 /upload 获得） |
| thumbnail_url | string | ❌ | 缩略图 URL |
| location | object | ❌ | 位置信息 `{lat, lng, ...}` |
| emotion | object | ❌ | 情绪 `{label, score, emoji}`，空则自动 AI 提取 |
| tags | string[] | ❌ | 标签 |
| date | string | ❌ | 日期 YYYY-MM-DD（默认今天） |

**响应 data：**

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
  "createdAt": 1711440000000
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

**请求 Body：** dict（任意）

**响应 data：** `{"url": "/uploads/voice/xxx.mp3", "transcription": "转写文字"}`

**实现状态：** 🟡 返回 Mock 数据，未实现真实语音转写

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
  "materialCount": 3,
  "materials": [...],
  "hasDiary": true,
  "diaryId": "uuid",
  "diaryStatus": "generated"
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
  "emotionSummary": {"dominant": "平静", "distribution": {"开心": 0.4}},
  "materialIds": ["uuid1", "uuid2"],
  "style": "",
  "editCount": 0,
  "maxEdits": 3,
  "status": "generated",
  "createdAt": 1711440000000,
  "updatedAt": 1711440000000,
  "emotion": {},
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
  "trend": [
    {"time": "09:00", "emotion": "开心", "score": 0.85},
    {"time": "14:00", "emotion": "平静", "score": 0.7}
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
  "anniversaries": [{"title": "和朋友聚餐", "date": "03-25", "related_person": "室友"}],
  "persons": [{"name": "小明", "relation": "室友"}],
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
| source | string | ❌ | "manual" / "ai"（默认 manual） |
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

发送消息给 AI，返回纯文本回复（非 SSE 流式）。自动保存对话历史。

**请求 Body：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| message | string | ✅ | 用户消息 |

**响应 data：** AI 回复文本（string）

**实现状态：** ✅ 已完成（调用 minimax_client.chat_completion，取最近 20 条历史作为上下文）

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
| 15 | GET | /api/materials/{id} | 素材 | ✅ |
| 16 | PUT | /api/materials/{id} | 素材 | ✅ |
| 17 | DELETE | /api/materials/{id} | 素材 | ✅ |
| 18 | POST | /api/materials/{id}/emotion | 素材 | ✅ |
| 19 | POST | /api/materials/{id}/polish | 素材 | ✅ |
| 20 | POST | /api/materials/voice | 素材 | 🟡 |
| 21 | GET | /api/diaries/today-summary | 日记 | ✅ |
| 22 | POST | /api/diaries/generate | 日记 | ✅ |
| 23 | GET | /api/diaries | 日记 | ✅ |
| 24 | GET | /api/diaries/{id} | 日记 | ✅ |
| 25 | PUT | /api/diaries/{id} | 日记 | ✅ |
| 26 | GET | /api/diaries/{id}/emotion-trend | 日记 | ✅ |
| 27 | POST | /api/diaries/{id}/extract | 日记 | ✅ |
| 28 | POST | /api/diaries/{id}/derivative | 日记 | ✅ |
| 29 | GET | /api/derivatives | 衍生 | ✅ |
| 30 | POST | /api/derivatives/{id}/share | 衍生 | ✅ |
| 31 | GET | /api/anniversaries/today | 纪念日 | ✅ |
| 32 | GET | /api/anniversaries | 纪念日 | ✅ |
| 33 | POST | /api/anniversaries | 纪念日 | ✅ |
| 34 | PUT | /api/anniversaries/{id} | 纪念日 | ✅ |
| 35 | DELETE | /api/anniversaries/{id} | 纪念日 | ✅ |
| 36 | POST | /api/ai/tts | AI | ✅ |
| 37 | GET | /api/ai/fortune | AI | ✅ |
| 38 | POST | /api/chat | 对话 | ✅ |
| 39 | GET | /api/chat/history | 对话 | ✅ |
| 40 | GET | /api/social/matches | 社交 | ✅ |
| 41 | POST | /api/social/match-requests | 社交 | ✅ |
| 42 | POST | /api/social/match-requests/{id}/respond | 社交 | ✅ |
| 43 | GET | /api/social/messages/{match_id} | 社交 | ✅ |
| 44 | GET | /api/social/matches/{id}/report | 社交 | ✅ |
| 45 | POST | /api/social/buddy | 社交 | ✅ |
| 46 | POST | /api/social/buddy/{id}/respond | 社交 | ✅ |
| 47 | POST | /api/upload/avatar | 上传 | ✅ |
| 48 | POST | /api/upload/diary-image | 上传 | ✅ |
| 49 | POST | /api/upload/voice | 上传 | 🟡 |
| 50 | GET | /api/study/pomodoros | 学习⚠️ | ✅ |
| 51 | POST | /api/study/pomodoros | 学习⚠️ | ✅ |
| 52 | POST | /api/study/pomodoros/{id}/complete | 学习⚠️ | ✅ |
| 53 | GET | /api/study/todos | 学习⚠️ | ✅ |
| 54 | POST | /api/study/todos | 学习⚠️ | ✅ |
| 55 | POST | /api/study/todos/{id}/toggle | 学习⚠️ | ✅ |

**统计：** 55 个路由，53 个 ✅，2 个 🟡，0 个 🔴

---

## 已知问题

1. **语音上传 MIME 校验**：`upload/service.py` 的 `ALLOWED_IMAGE_TYPES` 只包含图片类型，`POST /api/upload/voice` 会因 MIME 校验失败而 400。需要新增语音 MIME 类型支持。
2. **语音转写**：`POST /api/materials/voice` 返回硬编码 Mock 数据，未接入真实语音转文字服务。
3. **学习模块**：v2 已废弃但路由仍注册，建议后续清理。

---

## MiniMax AI 接口一览

所有 AI 调用封装在 `app/ai/minimax_client.py`，通过 `MINIMAX_MOCK=true/false` 切换 Mock/真实模式。

| 方法 | 用途 | 模型 | 接入的路由 |
|------|------|------|-----------|
| chat_completion | 文本对话 | M2.7-highspeed | /chat, /ai/fortune |
| stream_chat | 流式对话（SSE） | M2.7-highspeed | 未接入 |
| generate_image | 文生图 | image-01 | /user/agent-portrait, /diaries/{id}/derivative |
| text_to_speech | TTS | speech-2.8-hd | /ai/tts |
| generate_music | 音乐生成 | music-2.5+ | 未接入 |
| extract_emotion | 情绪提取 | chat_completion | /materials/{id}/emotion |
| polish_text | 文字润色 | chat_completion | /materials/{id}/polish |
| generate_diary | 日记生成 | chat_completion | /diaries/generate |
| extract_info | 信息提取 | chat_completion | /diaries/{id}/extract |
| generate_portrait | 用户画像 | chat_completion | /user/portrait/refresh |
| generate_match_report | 匹配报告 | chat_completion | /social/matches/{id}/report |

---

*本文档从 `app/` 下所有 router.py、schemas.py、service.py 实际代码提取，最后更新 2026-03-26。*
