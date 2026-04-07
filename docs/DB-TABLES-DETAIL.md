# data.db 表结构与功能映射

> 数据来源：`riji-backend/data.db`
>
> 说明：本文档展示每张表内字段含义与功能读写路径。

---

## 1. 全表概览

- 表总数：**22**

| 表名 | 模块分组 | 主要用途 |
|------|----------|----------|
| alembic_version | 数据库元数据 | Alembic 迁移版本记录表，标记数据库 schema 版本。 |
| anniversaries | 素材-日记主链路（TASK-B 核心） | 纪念日表，支持手工添加与 AI 提取写入。 |
| avatar_matches | Avatar 相关（当前代码未注册路由） | Avatar 匹配表（当前后端代码未直接读写）。 |
| avatar_memories | Avatar 相关（当前代码未注册路由） | Avatar 记忆表（当前后端代码未直接读写）。 |
| avatar_profiles | Avatar 相关（当前代码未注册路由） | Avatar 画像表（当前后端代码未直接读写）。 |
| avatar_status | Avatar 相关（当前代码未注册路由） | Avatar 状态表（当前后端代码未直接读写）。 |
| chat_messages | 聊天与社交 | AI 对话消息表。 |
| chat_sessions | 聊天与社交（当前代码未注册路由） | 聊天会话表（当前后端代码未直接读写）。 |
| diaries | 素材-日记链路 | 日记主表，保存日记正文、情绪汇总与编辑状态。 |
| diary_derivatives | 素材-日记链路 | 日记衍生内容表，保存漫画/小说/分享卡等。 |
| matches | 聊天与社交 | 社交匹配关系表。 |
| plaza_comments | 聊天与社交（当前代码未注册路由） | 广场评论表（当前后端代码未直接读写）。 |
| plaza_posts | 聊天与社交（当前代码未注册路由） | 广场帖子表（当前后端代码未直接读写）。 |
| pomodoros | 学习模块 | 番茄钟记录表。 |
| post_likes | 聊天与社交（当前代码未注册路由） | 帖子点赞关系表（当前后端代码未直接读写）。 |
| raw_materials | 素材-日记主链路（TASK-B 核心） | 素材表，记录文字/图片/语音素材。 |
| social_messages | 聊天与社交 | 社交私信消息表。 |
| todos | 学习模块 | 待办事项表。 |
| user_achievements | 用户与画像 | 用户成就解锁记录表。 |
| user_profiles | 用户与画像 | AI 画像表，保存偏好、关系图谱、兴趣与写作风格。 |
| user_settings | 用户与画像 | 用户设置表（每个用户一条）。 |
| users | 用户与画像 | 用户主表，保存账号信息、基础资料与成长字段。 |

---

## 2. 写入/读出判定口径

- 写入功能：直接 `INSERT`/`UPDATE`/`DELETE` 的路由或服务逻辑。
- 读出功能：直接查询该表的路由或服务逻辑。
- “当前代码未发现”表示在 `app/` 目录现有实现中未检索到直接访问。

### 2.1 TASK-C / TASK-D 表读写落地结论

| 任务 | 功能点 | 涉及表 | 当前实现结论 |
|------|--------|--------|--------------|
| TASK-C | AI：`/api/ai/tts`、`/api/ai/fortune` | 无（文件系统/AI 调用） | ✅ 已完成；不涉及 data.db 读写 |
| TASK-C | 衍生内容：`GET /api/derivatives`、`POST /api/derivatives/{deriv_id}/share` | `diary_derivatives`、`diaries` | ✅ 已完成；`diary_derivatives` 读写、`diaries` 用于归属校验读取 |
| TASK-C | 纪念日：`/api/anniversaries*` + `today` | `anniversaries`、`diaries` | ✅ 已完成；`anniversaries` 完整 CRUD，`diaries` 读取“那年今日” |
| TASK-D | AI 对话：`POST /api/chat`、`GET /api/chat/history` | `chat_messages` | ✅ 已完成；对话消息已实现读写 |
| TASK-D | 社交匹配：`/api/social/matches*`、`/api/social/buddy*` | `matches`、`users`、`user_profiles` | ✅ 已完成；`matches` 读写，`users`/`user_profiles` 用于展示与报告计算 |
| TASK-D | 社交消息：`GET /api/social/messages/{match_id}` | `social_messages` | ⚠️ 部分完成；当前仅读取，任务书提及的发送接口未实现 |

- 与 TASK-D 的主要差异：`POST /api/social/messages/{match_id}`（发送消息）尚未注册，因此 `social_messages` 当前没有业务写入入口。

---

## 3. 各表详细说明

### 3.1 alembic_version

- 模块分组：数据库元数据
- 主要用途：Alembic 迁移版本记录表，标记数据库 schema 版本。

| 维度 | 说明 |
|------|------|
| 写入功能 | Alembic 迁移命令写入（`alembic upgrade`） |
| 读出功能 | Alembic 迁移命令读取（`alembic current/history`） |

| 字段名 | 类型 | 非空 | 主键 | 字段说明 |
|--------|------|------|------|----------|
| version_num | VARCHAR(32) | 是 | 是 | Alembic 当前迁移版本号 |

### 3.2 anniversaries

- 模块分组：素材-日记主链路
- 主要用途：纪念日表，支持手工添加与 AI 提取写入。

| 维度 | 说明 |
|------|------|
| 写入功能 | `POST /api/anniversaries` 手工创建纪念日（`app/anniversary/service.py#create_anniversary`）<br>`PUT /api/anniversaries/{ann_id}` 更新纪念日（`app/anniversary/service.py#update_anniversary`）<br>`DELETE /api/anniversaries/{ann_id}` 删除纪念日（`app/anniversary/service.py#delete_anniversary`）<br>`POST /api/diaries/{diary_id}/extract` AI 提取后写入纪念日（`app/diary/service.py#extract_diary_info`） |
| 读出功能 | `GET /api/anniversaries` 列表读取（`app/anniversary/service.py#list_anniversaries`）<br>`GET /api/anniversaries/today` 按月日读取今日纪念日（`app/anniversary/service.py#get_today_anniversaries`） |

| 字段名 | 类型 | 非空 | 主键 | 字段说明 |
|--------|------|------|------|----------|
| id | VARCHAR | 是 | 是 | 主键 ID（通常为 UUID 字符串） |
| user_id | VARCHAR | 是 | 否 | 所属用户 ID（关联 users.id） |
| title | VARCHAR | 是 | 否 | 纪念日名称 |
| date | VARCHAR | 是 | 否 | 月日（MM-DD） |
| year | INTEGER | 否 | 否 | 年份（可选） |
| source | VARCHAR | 否 | 否 | 来源（manual/ai_extracted） |
| related_person | VARCHAR | 否 | 否 | 相关人物 |
| diary_id | VARCHAR | 否 | 否 | 关联日记 ID（可选） |
| created_at | BIGINT | 是 | 否 | 创建时间（Unix 毫秒时间戳） |

### 3.3 avatar_matches

- 模块分组：Avatar 相关（当前代码未注册路由）
- 主要用途：Avatar 匹配表（当前后端代码未直接读写）。

| 维度 | 说明 |
|------|------|
| 写入功能 | 当前代码未发现直接写入路径 |
| 读出功能 | 当前代码未发现直接读取路径 |

| 字段名 | 类型 | 非空 | 主键 | 字段说明 |
|--------|------|------|------|----------|
| id | VARCHAR | 是 | 是 | 主键 ID（通常为 UUID 字符串） |
| user_id | VARCHAR | 是 | 否 | 所属用户 ID（关联 users.id） |
| post_id | VARCHAR | 是 | 否 | 关联帖子 ID |
| match_score | INTEGER | 否 | 否 | 匹配分数 |
| match_reasons | TEXT | 否 | 否 | 匹配理由（JSON/文本） |
| agent_conversation | TEXT | 否 | 否 | 代理会话内容（JSON/文本） |
| status | VARCHAR | 否 | 否 | 匹配状态 |
| created_at | BIGINT | 是 | 否 | 创建时间（Unix 毫秒时间戳） |

### 3.4 avatar_memories

- 模块分组：Avatar 相关（当前代码未注册路由）
- 主要用途：Avatar 记忆表（当前后端代码未直接读写）。

| 维度 | 说明 |
|------|------|
| 写入功能 | 当前代码未发现直接写入路径 |
| 读出功能 | 当前代码未发现直接读取路径 |

| 字段名 | 类型 | 非空 | 主键 | 字段说明 |
|--------|------|------|------|----------|
| id | VARCHAR | 是 | 是 | 主键 ID（通常为 UUID 字符串） |
| user_id | VARCHAR | 是 | 否 | 所属用户 ID（关联 users.id） |
| category | VARCHAR | 是 | 否 | 记忆分类 |
| content | TEXT | 是 | 否 | 记忆内容 |
| source | VARCHAR | 否 | 否 | 来源模块 |
| source_ref | VARCHAR | 否 | 否 | 来源引用 ID |
| confidence | FLOAT | 否 | 否 | 置信度 |
| is_active | BOOLEAN | 否 | 否 | 是否生效 |
| is_pinned | BOOLEAN | 否 | 否 | 是否置顶 |
| need_type | VARCHAR | 否 | 否 | 需求类型 |
| urgency | VARCHAR | 否 | 否 | 紧急程度 |
| expiry | BIGINT | 否 | 否 | 过期时间（Unix 毫秒） |
| match_status | VARCHAR | 否 | 否 | 匹配状态 |
| tags | TEXT | 否 | 否 | 标签（JSON） |
| created_at | BIGINT | 是 | 否 | 创建时间（Unix 毫秒时间戳） |
| updated_at | BIGINT | 是 | 否 | 更新时间（Unix 毫秒时间戳） |

### 3.5 avatar_profiles

- 模块分组：Avatar 相关（当前代码未注册路由）
- 主要用途：Avatar 画像表（当前后端代码未直接读写）。

| 维度 | 说明 |
|------|------|
| 写入功能 | 当前代码未发现直接写入路径 |
| 读出功能 | 当前代码未发现直接读取路径 |

| 字段名 | 类型 | 非空 | 主键 | 字段说明 |
|--------|------|------|------|----------|
| id | VARCHAR | 是 | 是 | 主键 ID（通常为 UUID 字符串） |
| user_id | VARCHAR | 是 | 否 | 所属用户 ID（关联 users.id） |
| summary | TEXT | 否 | 否 | Avatar 画像摘要 |
| diary_count | INTEGER | 否 | 否 | 采样日记数 |
| chat_count | INTEGER | 否 | 否 | 采样聊天数 |
| generated_at | BIGINT | 否 | 否 | 生成时间（Unix 毫秒） |

### 3.6 avatar_status

- 模块分组：Avatar 相关（当前代码未注册路由）
- 主要用途：Avatar 状态表（当前后端代码未直接读写）。

| 维度 | 说明 |
|------|------|
| 写入功能 | 当前代码未发现直接写入路径 |
| 读出功能 | 当前代码未发现直接读取路径 |

| 字段名 | 类型 | 非空 | 主键 | 字段说明 |
|--------|------|------|------|----------|
| id | VARCHAR | 是 | 是 | 主键 ID（通常为 UUID 字符串） |
| user_id | VARCHAR | 是 | 否 | 所属用户 ID（关联 users.id） |
| is_active | BOOLEAN | 否 | 否 | 是否激活 Avatar |
| browsed_count | INTEGER | 否 | 否 | 浏览数量 |
| matched_count | INTEGER | 否 | 否 | 匹配数量 |
| chatting_count | INTEGER | 否 | 否 | 聊天数量 |
| last_active_at | BIGINT | 否 | 否 | 最后活跃时间（Unix 毫秒） |
| enabled_channels | TEXT | 否 | 否 | 启用渠道（JSON） |
| enabled_actions | TEXT | 否 | 否 | 启用动作（JSON） |
| match_range | TEXT | 否 | 否 | 匹配范围配置（JSON） |

### 3.7 chat_messages

- 模块分组：聊天与社交
- 主要用途：AI 对话消息表。

| 维度 | 说明 |
|------|------|
| 写入功能 | `POST /api/chat` 写入用户消息与 AI 回复（`app/chat/router.py#ai_chat`） |
| 读出功能 | `POST /api/chat` 读取最近消息构建上下文（`app/chat/router.py#ai_chat`）<br>`GET /api/chat/history` 读取聊天历史（`app/chat/router.py#get_chat_history`）<br>`POST /api/user/portrait/refresh` 抽样用户消息用于画像（`app/user/router.py#refresh_portrait`） |

| 字段名 | 类型 | 非空 | 主键 | 字段说明 |
|--------|------|------|------|----------|
| id | VARCHAR | 是 | 是 | 主键 ID（通常为 UUID 字符串） |
| user_id | VARCHAR | 是 | 否 | 所属用户 ID（关联 users.id） |
| role | VARCHAR | 是 | 否 | 消息角色（user/assistant） |
| content | TEXT | 是 | 否 | 消息内容 |
| timestamp | BIGINT | 是 | 否 | 消息时间（Unix 毫秒） |

### 3.8 chat_sessions

- 模块分组：聊天与社交（当前代码未注册路由）
- 主要用途：聊天会话表（当前后端代码未直接读写）。

| 维度 | 说明 |
|------|------|
| 写入功能 | 当前代码未发现直接写入路径 |
| 读出功能 | 当前代码未发现直接读取路径 |

| 字段名 | 类型 | 非空 | 主键 | 字段说明 |
|--------|------|------|------|----------|
| id | VARCHAR | 是 | 是 | 主键 ID（通常为 UUID 字符串） |
| user_id | VARCHAR | 是 | 否 | 所属用户 ID（关联 users.id） |
| status | VARCHAR | 否 | 否 | 会话状态 |
| start_time | BIGINT | 是 | 否 | 会话开始时间（Unix 毫秒） |
| end_time | BIGINT | 否 | 否 | 会话结束时间（Unix 毫秒） |
| message_count | INTEGER | 否 | 否 | 消息数量 |
| title | VARCHAR | 否 | 否 | 会话标题 |
| summary | TEXT | 否 | 否 | 会话摘要 |
| mood | VARCHAR | 否 | 否 | 情绪标签 |
| mood_emoji | VARCHAR | 否 | 否 | 情绪表情 |
| topic_tags | TEXT | 否 | 否 | 话题标签（JSON） |
| material_id | VARCHAR | 否 | 否 | 关联素材 ID |
| date | VARCHAR | 是 | 否 | 会话日期 |
| created_at | BIGINT | 是 | 否 | 创建时间（Unix 毫秒时间戳） |

### 3.9 diaries

- 模块分组：素材-日记链路
- 主要用途：日记主表，保存日记正文、情绪汇总与编辑状态。

| 维度 | 说明 |
|------|------|
| 写入功能 | `POST /api/diaries/generate` 新建日记（`app/diary/service.py#generate_diary`）<br>`PUT /api/diaries/{diary_id}` 更新日记内容与编辑次数（`app/diary/service.py#update_diary`） |
| 读出功能 | `GET /api/diaries` 列表读取（`app/diary/service.py#list_diaries`）<br>`GET /api/diaries/{diary_id}` 详情读取（`app/diary/service.py#get_diary`）<br>`GET /api/diaries/today-summary` 判断当日是否已有日记（`app/diary/service.py#get_today_summary`）<br>`GET /api/anniversaries/today` 查询“那年今日”日记（`app/anniversary/service.py#get_today_anniversaries`）<br>`POST /api/user/portrait/refresh` 抽样最近日记构建画像（`app/user/router.py#refresh_portrait`） |

| 字段名 | 类型 | 非空 | 主键 | 字段说明 |
|--------|------|------|------|----------|
| id | VARCHAR | 是 | 是 | 主键 ID（通常为 UUID 字符串） |
| user_id | VARCHAR | 是 | 否 | 所属用户 ID（关联 users.id） |
| content | TEXT | 是 | 否 | 日记正文 |
| images | TEXT | 否 | 否 | 配图 URL 列表（JSON） |
| emotion | TEXT | 否 | 否 | 兼容情绪字段（JSON） |
| tags | TEXT | 否 | 否 | 标签列表（JSON） |
| location | VARCHAR | 否 | 否 | 地点文本 |
| weather | VARCHAR | 否 | 否 | 天气 |
| style | VARCHAR | 否 | 否 | 日记风格 |
| has_comic | BOOLEAN | 否 | 否 | 是否已生成漫画 |
| has_bgm | BOOLEAN | 否 | 否 | 是否已生成背景音乐 |
| comic_url | VARCHAR | 否 | 否 | 漫画 URL |
| bgm_url | VARCHAR | 否 | 否 | 背景音乐 URL |
| created_at | BIGINT | 是 | 否 | 创建时间（Unix 毫秒时间戳） |
| updated_at | BIGINT | 是 | 否 | 更新时间（Unix 毫秒时间戳） |
| title | VARCHAR | 否 | 否 | 日记标题 |
| special_date | VARCHAR | 否 | 否 | 特殊日期标注 |
| emotion_summary | TEXT | 否 | 否 | 情绪汇总（JSON） |
| material_ids | TEXT | 否 | 否 | 关联素材 ID 列表（JSON） |
| edit_count | INTEGER | 否 | 否 | 已编辑次数 |
| max_edits | INTEGER | 否 | 否 | 最大可编辑次数 |
| status | VARCHAR | 否 | 否 | 日记状态（draft/published） |
| date | VARCHAR | 否 | 否 | 日记所属日期（YYYY-MM-DD） |

### 3.10 diary_derivatives

- 模块分组：素材-日记链路
- 主要用途：日记衍生内容表，保存漫画/小说/分享卡等。

| 维度 | 说明 |
|------|------|
| 写入功能 | `POST /api/diaries/{diary_id}/derivative` 新建衍生内容（`app/diary/service.py#generate_derivative`）<br>`POST /api/derivatives/{deriv_id}/share` 更新 `share_scope`（`app/derivative/router.py#set_share_scope`） |
| 读出功能 | `GET /api/derivatives` 按用户日记集合读取衍生内容（`app/derivative/router.py#list_derivatives`）<br>`POST /api/derivatives/{deriv_id}/share` 查询后校验归属并更新（`app/derivative/router.py#set_share_scope`） |

| 字段名 | 类型 | 非空 | 主键 | 字段说明 |
|--------|------|------|------|----------|
| id | VARCHAR | 是 | 是 | 主键 ID（通常为 UUID 字符串） |
| diary_id | VARCHAR | 是 | 否 | 来源日记 ID |
| type | VARCHAR | 是 | 否 | 衍生类型（comic/novel/share_card） |
| content | TEXT | 否 | 否 | 衍生文本内容 |
| media_url | VARCHAR | 否 | 否 | 衍生媒体 URL |
| share_scope | VARCHAR | 否 | 否 | 分享范围（private/friends/public） |
| created_at | BIGINT | 是 | 否 | 创建时间（Unix 毫秒时间戳） |

### 3.11 matches

- 模块分组：聊天与社交
- 主要用途：社交匹配关系表。

| 维度 | 说明 |
|------|------|
| 写入功能 | `POST /api/social/match-requests` 创建匹配请求（`app/social/router.py#create_match_request`）<br>`POST /api/social/match-requests/{request_id}/respond` 更新匹配状态（`app/social/router.py#respond_match_request`）<br>`POST /api/social/buddy` 创建搭子申请（`app/social/router.py#apply_buddy`）<br>`POST /api/social/buddy/{request_id}/respond` 更新搭子申请状态（`app/social/router.py#respond_buddy`）<br>`GET /api/social/matches/{match_id}/report` 首次生成并缓存 `match_report`（`app/social/router.py#get_match_report`） |
| 读出功能 | `GET /api/social/matches` 读取已接受匹配列表（`app/social/router.py#list_matches`）<br>`GET /api/social/messages/{match_id}` 读取匹配记录做权限校验（`app/social/router.py#get_messages`）<br>`GET /api/social/matches/{match_id}/report` 读取匹配关系并返回报告（`app/social/router.py#get_match_report`） |

| 字段名 | 类型 | 非空 | 主键 | 字段说明 |
|--------|------|------|------|----------|
| id | VARCHAR | 是 | 是 | 主键 ID（通常为 UUID 字符串） |
| user_id | VARCHAR | 是 | 否 | 所属用户 ID（关联 users.id） |
| target_id | VARCHAR | 是 | 否 | 匹配目标用户 ID |
| common_tags | TEXT | 否 | 否 | 共同标签（JSON） |
| status | VARCHAR | 否 | 否 | 匹配状态（pending/accepted/rejected） |
| created_at | BIGINT | 是 | 否 | 创建时间（Unix 毫秒时间戳） |
| match_type | VARCHAR | 否 | 否 | 匹配类型（long_term/buddy） |
| match_report | TEXT | 否 | 否 | 匹配报告文本或 JSON 字符串 |
| user_portrait_snapshot | TEXT | 否 | 否 | 画像快照（JSON） |

### 3.12 plaza_comments

- 模块分组：聊天与社交（当前代码未注册路由）
- 主要用途：广场评论表（当前后端代码未直接读写）。

| 维度 | 说明 |
|------|------|
| 写入功能 | 当前代码未发现直接写入路径 |
| 读出功能 | 当前代码未发现直接读取路径 |

| 字段名 | 类型 | 非空 | 主键 | 字段说明 |
|--------|------|------|------|----------|
| id | VARCHAR | 是 | 是 | 主键 ID（通常为 UUID 字符串） |
| post_id | VARCHAR | 是 | 否 | 所属帖子 ID |
| user_id | VARCHAR | 是 | 否 | 所属用户 ID（关联 users.id） |
| content | TEXT | 是 | 否 | 评论内容 |
| is_agent | BOOLEAN | 否 | 否 | 是否 AI 评论 |
| created_at | BIGINT | 是 | 否 | 创建时间（Unix 毫秒时间戳） |

### 3.13 plaza_posts

- 模块分组：聊天与社交（当前代码未注册路由）
- 主要用途：广场帖子表（当前后端代码未直接读写）。

| 维度 | 说明 |
|------|------|
| 写入功能 | 当前代码未发现直接写入路径 |
| 读出功能 | 当前代码未发现直接读取路径 |

| 字段名 | 类型 | 非空 | 主键 | 字段说明 |
|--------|------|------|------|----------|
| id | VARCHAR | 是 | 是 | 主键 ID（通常为 UUID 字符串） |
| user_id | VARCHAR | 是 | 否 | 所属用户 ID（关联 users.id） |
| type | VARCHAR | 是 | 否 | 帖子类型 |
| content | TEXT | 是 | 否 | 帖子正文 |
| images | TEXT | 否 | 否 | 图片列表（JSON） |
| location | VARCHAR | 否 | 否 | 地点文本 |
| tags | TEXT | 否 | 否 | 标签列表（JSON） |
| likes | INTEGER | 否 | 否 | 点赞数缓存 |
| comments | INTEGER | 否 | 否 | 评论数缓存 |
| agent_responses | INTEGER | 否 | 否 | AI 回复数缓存 |
| is_from_agent | BOOLEAN | 否 | 否 | 是否 AI 生成帖子 |
| allow_agent_reply | BOOLEAN | 否 | 否 | 是否允许 AI 回复 |
| school_only | BOOLEAN | 否 | 否 | 是否校内可见 |
| created_at | BIGINT | 是 | 否 | 创建时间（Unix 毫秒时间戳） |

### 3.14 pomodoros

- 模块分组：学习模块
- 主要用途：番茄钟记录表。

| 维度 | 说明 |
|------|------|
| 写入功能 | `POST /api/study/pomodoros` 创建番茄钟（`app/study/router.py#create_pomodoro`）<br>`POST /api/study/pomodoros/{pomodoro_id}/complete` 更新完成时间（`app/study/router.py#complete_pomodoro`） |
| 读出功能 | `GET /api/study/pomodoros` 读取番茄钟列表（`app/study/router.py#list_pomodoros`）<br>`GET /api/user/growth` 读取已完成番茄钟做统计（`app/user/service.py#get_growth_data`）<br>`GET /api/user/semester-report` 读取已完成番茄钟做学期报告统计（`app/user/service.py#get_semester_report`） |

| 字段名 | 类型 | 非空 | 主键 | 字段说明 |
|--------|------|------|------|----------|
| id | VARCHAR | 是 | 是 | 主键 ID（通常为 UUID 字符串） |
| user_id | VARCHAR | 是 | 否 | 所属用户 ID（关联 users.id） |
| task | VARCHAR | 是 | 否 | 任务名称 |
| subject | VARCHAR | 否 | 否 | 学科分类 |
| duration | INTEGER | 否 | 否 | 时长（分钟） |
| completed_at | BIGINT | 否 | 否 | 完成时间（Unix 毫秒，空表示未完成） |
| created_at | BIGINT | 是 | 否 | 创建时间（Unix 毫秒时间戳） |

### 3.15 post_likes

- 模块分组：聊天与社交（当前代码未注册路由）
- 主要用途：帖子点赞关系表（当前后端代码未直接读写）。

| 维度 | 说明 |
|------|------|
| 写入功能 | 当前代码未发现直接写入路径 |
| 读出功能 | 当前代码未发现直接读取路径 |

| 字段名 | 类型 | 非空 | 主键 | 字段说明 |
|--------|------|------|------|----------|
| id | VARCHAR | 是 | 是 | 主键 ID（通常为 UUID 字符串） |
| post_id | VARCHAR | 是 | 否 | 帖子 ID |
| user_id | VARCHAR | 是 | 否 | 点赞用户 ID |
| created_at | BIGINT | 是 | 否 | 创建时间（Unix 毫秒时间戳） |

### 3.16 raw_materials

- 模块分组：素材-日记链路
- 主要用途：素材表，记录文字/图片/语音素材。

| 维度 | 说明 |
|------|------|
| 写入功能 | `POST /api/materials` 创建素材（`app/material/service.py#create_material`）<br>`PUT /api/materials/{material_id}` 更新素材内容/标签/情绪（`app/material/service.py#update_material`）<br>`DELETE /api/materials/{material_id}` 删除素材（`app/material/service.py#delete_material`）<br>`POST /api/materials/{material_id}/emotion` 更新情绪提取结果（`app/material/service.py#extract_emotion`） |
| 读出功能 | `GET /api/materials` 列表查询（`app/material/service.py#list_materials`）<br>`GET /api/materials/{material_id}` 单条查询（`app/material/service.py#get_material`）<br>`POST /api/diaries/generate` 读取当日素材生成日记（`app/diary/service.py#generate_diary`）<br>`GET /api/diaries/today-summary` 读取当日素材概览（`app/diary/service.py#get_today_summary`）<br>`GET /api/diaries/{diary_id}/emotion-trend` 根据 `material_ids` 聚合情绪（`app/diary/service.py#get_emotion_trend`） |

| 字段名 | 类型 | 非空 | 主键 | 字段说明 |
|--------|------|------|------|----------|
| id | VARCHAR | 是 | 是 | 主键 ID（通常为 UUID 字符串） |
| user_id | VARCHAR | 是 | 否 | 所属用户 ID（关联 users.id） |
| type | VARCHAR | 是 | 否 | 素材类型（text/image/voice） |
| content | TEXT | 否 | 否 | 文字内容或语音转写文本 |
| media_url | VARCHAR | 否 | 否 | 素材媒体 URL |
| thumbnail_url | VARCHAR | 否 | 否 | 缩略图 URL |
| location | TEXT | 否 | 否 | 位置信息（JSON） |
| emotion | TEXT | 否 | 否 | 情绪信息（JSON） |
| tags | TEXT | 否 | 否 | 标签列表（JSON） |
| date | VARCHAR | 是 | 否 | 素材所属日期（YYYY-MM-DD） |
| created_at | BIGINT | 是 | 否 | 创建时间（Unix 毫秒时间戳） |
| chat_session_id | VARCHAR | 否 | 否 | 关联聊天会话 ID（预留） |
| start_time | BIGINT | 否 | 否 | 语音开始时间（预留） |
| end_time | BIGINT | 否 | 否 | 语音结束时间（预留） |

### 3.17 social_messages

- 模块分组：聊天与社交
- 主要用途：社交私信消息表。

| 维度 | 说明 |
|------|------|
| 写入功能 | 当前代码未发现直接写入接口（暂无发送消息接口） |
| 读出功能 | `GET /api/social/messages/{match_id}` 读取消息列表（`app/social/router.py#get_messages`） |

| 字段名 | 类型 | 非空 | 主键 | 字段说明 |
|--------|------|------|------|----------|
| id | VARCHAR | 是 | 是 | 主键 ID（通常为 UUID 字符串） |
| match_id | VARCHAR | 是 | 否 | 所属匹配 ID |
| from_uid | VARCHAR | 是 | 否 | 发送者用户 ID |
| content | TEXT | 是 | 否 | 消息内容 |
| timestamp | BIGINT | 是 | 否 | 发送时间（Unix 毫秒） |

### 3.18 todos

- 模块分组：学习模块
- 主要用途：待办事项表。

| 维度 | 说明 |
|------|------|
| 写入功能 | `POST /api/study/todos` 创建待办（`app/study/router.py#create_todo`）<br>`POST /api/study/todos/{todo_id}/toggle` 切换完成状态（`app/study/router.py#toggle_todo`） |
| 读出功能 | `GET /api/study/todos` 读取待办列表（`app/study/router.py#list_todos`）<br>`POST /api/study/todos/{todo_id}/toggle` 查询后切换状态并返回（`app/study/router.py#toggle_todo`） |

| 字段名 | 类型 | 非空 | 主键 | 字段说明 |
|--------|------|------|------|----------|
| id | VARCHAR | 是 | 是 | 主键 ID（通常为 UUID 字符串） |
| user_id | VARCHAR | 是 | 否 | 所属用户 ID（关联 users.id） |
| content | VARCHAR | 是 | 否 | 待办内容 |
| completed | BOOLEAN | 否 | 否 | 是否完成 |
| priority | VARCHAR | 否 | 否 | 优先级（low/medium/high） |
| created_at | BIGINT | 是 | 否 | 创建时间（Unix 毫秒时间戳） |

### 3.19 user_achievements

- 模块分组：用户与画像
- 主要用途：用户成就解锁记录表。

| 维度 | 说明 |
|------|------|
| 写入功能 | 当前代码未发现直接写入路径（可能由脚本或后续功能写入） |
| 读出功能 | `GET /api/user/achievements` 读取解锁状态（`app/user/service.py#get_achievements`）<br>`GET /api/user/semester-report` 统计已解锁数量（`app/user/service.py#get_semester_report`） |

| 字段名 | 类型 | 非空 | 主键 | 字段说明 |
|--------|------|------|------|----------|
| id | VARCHAR | 是 | 是 | 主键 ID（通常为 UUID 字符串） |
| user_id | VARCHAR | 是 | 否 | 所属用户 ID（关联 users.id） |
| achievement_id | VARCHAR | 是 | 否 | 成就编码 |
| unlocked_at | BIGINT | 是 | 否 | 解锁时间（Unix 毫秒） |

### 3.20 user_profiles

- 模块分组：用户与画像
- 主要用途：AI 画像表，保存偏好、关系图谱、兴趣与写作风格。

| 维度 | 说明 |
|------|------|
| 写入功能 | `POST /api/diaries/{diary_id}/extract` 创建/更新关系与兴趣（`app/diary/service.py#extract_diary_info`）<br>`POST /api/user/portrait/refresh` 刷新整份画像（`app/user/router.py#refresh_portrait`） |
| 读出功能 | `GET /api/user/portrait` 读取画像（`app/user/router.py#get_portrait`）<br>`GET /api/user/agent-portrait` 读取性格用于生成提示词（`app/user/router.py#get_agent_portrait`）<br>`GET /api/social/matches/{match_id}/report` 读取双方画像计算匹配报告（`app/social/router.py#get_match_report`） |

| 字段名 | 类型 | 非空 | 主键 | 字段说明 |
|--------|------|------|------|----------|
| id | VARCHAR | 是 | 是 | 主键 ID（通常为 UUID 字符串） |
| user_id | VARCHAR | 是 | 否 | 所属用户 ID（关联 users.id） |
| preferences | TEXT | 否 | 否 | 偏好（JSON） |
| personality | TEXT | 否 | 否 | 性格描述 |
| writing_style | TEXT | 否 | 否 | 写作风格描述 |
| relations | TEXT | 否 | 否 | 人物关系图谱（JSON） |
| interests | TEXT | 否 | 否 | 兴趣列表（JSON） |
| updated_at | BIGINT | 是 | 否 | 更新时间（Unix 毫秒时间戳） |

### 3.21 user_settings

- 模块分组：用户与画像
- 主要用途：用户设置表（每个用户一条）。

| 维度 | 说明 |
|------|------|
| 写入功能 | `POST /api/auth/register` 创建默认设置（`app/auth/router.py#register`）<br>`POST /api/user/settings` 创建/更新设置（`app/user/service.py#update_settings`） |
| 读出功能 | `GET /api/user/settings` 读取设置（`app/user/service.py#get_settings`）<br>`POST /api/user/settings` 更新后回读（`app/user/service.py#update_settings`） |

| 字段名 | 类型 | 非空 | 主键 | 字段说明 |
|--------|------|------|------|----------|
| id | VARCHAR | 是 | 是 | 主键 ID（通常为 UUID 字符串） |
| user_id | VARCHAR | 是 | 否 | 所属用户 ID（关联 users.id） |
| theme | VARCHAR | 否 | 否 | 主题（light/dark 等） |
| notifications | BOOLEAN | 否 | 否 | 是否开启通知 |
| auto_bgm | BOOLEAN | 否 | 否 | 是否自动背景音乐 |
| diary_privacy | VARCHAR | 否 | 否 | 日记隐私级别 |
| language | VARCHAR | 否 | 否 | 语言设置 |

### 3.22 users

- 模块分组：用户与画像
- 主要用途：用户主表，保存账号信息、基础资料与成长字段。

| 维度 | 说明 |
|------|------|
| 写入功能 | `POST /api/auth/register` 新建用户（`app/auth/router.py#register`）<br>`POST /api/user/profile` 更新昵称/学校/专业/头像/风格（`app/user/service.py#update_user_profile`）<br>`POST /api/study/pomodoros/{pomodoro_id}/complete` 增加 `pomodoro_count`（`app/study/router.py#complete_pomodoro`）<br>`POST /api/diaries/generate` 增加 `diary_count`（`app/diary/service.py#generate_diary`） |
| 读出功能 | `POST /api/auth/login` 按用户名读取（`app/auth/router.py#login`）<br>鉴权依赖 `get_current_user` 按 `user_id` 读取（`app/dependencies.py#get_current_user`）<br>`GET /api/user/profile` 读取资料（`app/user/service.py#get_user_profile`）<br>`GET /api/social/*` 读取对方用户信息用于展示（`app/social/service.py#match_to_out`） |

| 字段名 | 类型 | 非空 | 主键 | 字段说明 |
|--------|------|------|------|----------|
| id | VARCHAR | 是 | 是 | 主键 ID（通常为 UUID 字符串） |
| username | VARCHAR | 是 | 否 | 登录用户名（唯一） |
| password | VARCHAR | 是 | 否 | 密码哈希（bcrypt） |
| name | VARCHAR | 否 | 否 | 昵称 |
| school | VARCHAR | 否 | 否 | 学校 |
| major | VARCHAR | 否 | 否 | 专业 |
| grade | VARCHAR | 否 | 否 | 年级 |
| avatar | VARCHAR | 否 | 否 | 头像 URL |
| signature | VARCHAR | 否 | 否 | 个性签名 |
| level | INTEGER | 否 | 否 | 等级 |
| xp | INTEGER | 否 | 否 | 经验值 |
| diary_count | INTEGER | 否 | 否 | 日记累计数 |
| streak_days | INTEGER | 否 | 否 | 连续打卡天数 |
| pomodoro_count | INTEGER | 否 | 否 | 完成番茄钟数量 |
| created_at | BIGINT | 是 | 否 | 创建时间（Unix 毫秒时间戳） |
| updated_at | BIGINT | 是 | 否 | 更新时间（Unix 毫秒时间戳） |
| openclaw_agent_id | VARCHAR | 否 | 否 | 外部 AI 代理 ID |
| style_tags | TEXT | 否 | 否 | 写作风格标签（JSON） |
| custom_style_prompt | TEXT | 否 | 否 | 自定义写作 Prompt |
