# 日迹 App 后端重写开发规范 v2.0

> **本文档定义后端重写的完整开发路径、架构规范和接口实现要求。**
> **核心原则：一切以前端 `API-SPEC.md` 中定义的 52 个接口为准，后端必须严格匹配，不得自行发挥。**
>
> 生成时间：2026-03-25 20:39 CST
> 前端仓库：https://github.com/Qyjay/riji-frontend
> 后端仓库：https://github.com/Qyjay/riji-backend
> 接口规范：`API-SPEC.md`（前端仓库根目录）

---

## 一、上一版后端的问题总结（不再重犯）

| # | 问题 | 根因 | 本次解法 |
|---|------|------|----------|
| 1 | **所有响应字段 snake_case，前端期望 camelCase** | Pydantic 默认输出 snake_case | 全局配置 `alias_generator = to_camel` + `populate_by_name = True` |
| 2 | **列表接口响应格式不统一**（有的该裸数组却包了 `{items, total}`） | 没对照前端代码 | 逐接口核对前端 `request<T>` 的泛型参数 |
| 3 | **22 个接口 return pass（空壳）** | 留给组员写但没人写 | 本次全部实现，不留空壳 |
| 4 | **路径/参数名与前端不匹配** | 没看前端代码 | 从 `API-SPEC.md` 逆向定义路由 |
| 5 | **AI 路由重复冲突**（`/ai/chat` vs `/chat`） | 两种架构方案并存 | 统一按前端调用路径，去掉冗余 |
| 6 | **响应数据结构不匹配**（匹配报告、运势、画像等） | schema 随意定义 | 严格按前端 TypeScript interface 定义 |

---

## 二、技术栈（沿用 + 修正）

| 组件 | 选型 | 版本 | 说明 |
|------|------|------|------|
| 框架 | FastAPI | 0.115+ | 异步支持 |
| 数据库 | SQLite + SQLAlchemy | 2.0+ | 同步 ORM，降低门槛 |
| 迁移 | Alembic | 1.13+ | 数据库版本管理 |
| 认证 | JWT (python-jose) | 3.3+ | Bearer Token |
| 密码 | passlib + bcrypt | 4.0.1 | bcrypt 锁定版本 |
| AI | MiniMax API (httpx) | — | TokenPlan Plus，5 模态 |
| 测试 | pytest + pytest-asyncio | 8.3+ | 每个模块写测试 |
| 序列化 | Pydantic v2 | 2.x | **`alias_generator=to_camel` 全局启用** |

---

## 三、全局架构规范

### 3.1 项目目录结构

```
riji-backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI 入口
│   ├── config.py               # 环境配置（pydantic-settings）
│   ├── database.py             # SQLAlchemy 引擎/会话
│   ├── dependencies.py         # 公共依赖注入（get_db, get_current_user）
│   ├── response.py             # 统一响应格式 + 错误码 + ApiException
│   ├── serializers.py          # 🆕 全局 camelCase 基类 + 序列化工具
│   ├── models/                 # SQLAlchemy 数据模型
│   │   ├── user.py             # User, UserSettings, UserAchievement
│   │   ├── diary.py            # Diary
│   │   ├── material.py         # RawMaterial
│   │   ├── anniversary.py      # Anniversary
│   │   ├── derivative.py       # DiaryDerivative
│   │   ├── chat.py             # ChatMessage
│   │   ├── social.py           # Match, SocialMessage
│   │   ├── study.py            # Pomodoro, Todo
│   │   └── user_profile.py     # UserProfile
│   ├── auth/                   # 认证模块（2 接口）
│   │   ├── router.py
│   │   ├── schemas.py
│   │   └── service.py
│   ├── material/               # 素材模块（8 接口）
│   │   ├── router.py
│   │   ├── schemas.py
│   │   └── service.py
│   ├── diary/                  # 日记模块（10 接口）
│   │   ├── router.py
│   │   ├── schemas.py
│   │   └── service.py
│   ├── ai/                     # AI 模块（4 接口）
│   │   ├── router.py
│   │   ├── schemas.py
│   │   ├── service.py
│   │   └── minimax_client.py   # MiniMax API 封装（沿用）
│   ├── user/                   # 用户模块（8 接口）
│   │   ├── router.py
│   │   ├── schemas.py
│   │   └── service.py
│   ├── social/                 # 社交模块（9 接口）
│   │   ├── router.py
│   │   ├── schemas.py
│   │   └── service.py
│   ├── anniversary/            # 纪念日模块（5 接口）
│   │   ├── router.py
│   │   ├── schemas.py
│   │   └── service.py
│   └── study/                  # 学习模块（6 接口）
│       ├── router.py
│       ├── schemas.py
│       └── service.py
├── tests/
│   ├── conftest.py
│   ├── test_auth.py
│   ├── test_material.py
│   ├── test_diary.py
│   ├── test_ai.py
│   ├── test_user.py
│   ├── test_social.py
│   ├── test_anniversary.py
│   └── test_study.py
├── alembic/
├── scripts/
│   └── seed.py                 # 种子数据
├── requirements.txt
├── alembic.ini
├── .env.example
└── README.md
```

### 3.2 统一响应格式（沿用，已正确）

```python
# response.py — 不变
def success(data=None, message="ok"):
    return {"code": 0, "data": data, "message": message}
```

所有路由返回 `success(data)`，前端 `request.ts` 自动解包 `data` 字段。

### 3.3 🔑 camelCase 序列化（新增核心）

**这是上一版最大的问题。本次必须全局解决。**

```python
# app/serializers.py — 新建
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """
    所有输出 Schema 的基类。
    - JSON 序列化时自动 snake_case → camelCase
    - 反序列化时同时接受 snake_case 和 camelCase
    """
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,      # 允许用原字段名赋值
        from_attributes=True,       # 支持 ORM 对象直接转换
    )
```

**使用方式：**

```python
# 所有输出 Schema 继承 CamelModel
class DiaryOut(CamelModel):
    id: str
    user_id: str          # JSON 输出为 "userId"
    title: str
    created_at: int       # JSON 输出为 "createdAt"
    emotion_summary: dict # JSON 输出为 "emotionSummary"

# 路由中使用
diary = db.query(Diary).first()
return success(DiaryOut.model_validate(diary).model_dump(by_alias=True))
```

**输入 Schema（请求体）保持 BaseModel：**

请求体不需要 camelCase 转换。前端发什么字段名，后端就用什么。例如前端发 `{ style_tags: [...] }`，后端 schema 就定义 `style_tags`。

### 3.4 列表响应规则（逐接口核对）

**规则：看前端 `request<T>` 泛型参数**

- `request<XXX[]>` → 后端返回裸数组：`success([...])`
- `request<{ items: XXX[]; total: number }>` → 后端返回 `success({"items": [...], "total": N})`

| 接口 | 前端泛型 | 后端返回格式 |
|------|---------|-------------|
| `GET /materials?date=` | `RawMaterial[]` | `success([...])` 裸数组 |
| `GET /diaries?page=` | `{ items: Diary[]; total }` | `success({"items": [...], "total": N})` |
| `GET /chat/history` | `{ items: any[]; total }` | `success({"items": [...], "total": N})` |
| `GET /social/matches` | `Match[]` | `success([...])` 裸数组 |
| `GET /social/messages/{id}` | `Message[]` | `success([...])` 裸数组 |
| `GET /anniversaries` | `Anniversary[]` | `success([...])` 裸数组 |
| `GET /derivatives?diary_id=` | `DiaryDerivative[]` | `success([...])` 裸数组 |
| `GET /user/achievements` | `Achievement[]` | `success([...])` 裸数组 |
| `GET /study/pomodoros` | `Pomodoro[]` | `success([...])` 裸数组 |
| `GET /study/todos` | `Todo[]` | `success([...])` 裸数组 |

### 3.5 路由前缀

```python
# main.py — 所有路由统一 /api 前缀
app.include_router(auth_router, prefix="/api")
app.include_router(material_router, prefix="/api")
app.include_router(diary_router, prefix="/api")
app.include_router(ai_router, prefix="/api")         # /api/ai/* 和 /api/chat/*
app.include_router(user_router, prefix="/api")
app.include_router(social_router, prefix="/api")
app.include_router(anniversary_router, prefix="/api")
app.include_router(derivative_router, prefix="/api")
app.include_router(study_router, prefix="/api")
```

### 3.6 JSON 字段存储约定

数据库中存 JSON 的字段（emotion、tags、images、location 等）统一用 `Text` 类型存 JSON 字符串，读取时 `json.loads()`，写入时 `json.dumps(ensure_ascii=False)`。

输出到前端时，必须是解析后的 Python dict/list，不能返回 JSON 字符串。

---

## 四、开发阶段（6 个 Group，严格串行）

### 🔧 Group 0：基础设施重建（预计 15 分钟）

**目标：** 搭建项目骨架，确保能启动、能测试、能连数据库。

**任务清单：**

1. **清理旧代码**
   - 删除所有空壳路由（return pass 的接口）
   - 删除冗余的 `/ai/chat`、`/ai/generate-diary` 等前端不调用的路由
   - 保留：`config.py`、`database.py`、`dependencies.py`、`response.py`、`auth/service.py`、`ai/minimax_client.py`、所有 `models/`

2. **新建 `app/serializers.py`**
   - 实现 `CamelModel` 基类

3. **修复 `database.py`**
   - `init_db()` 中导入所有模型（包括 v2 新增的 material、anniversary、derivative、user_profile）

4. **更新 `requirements.txt`**
   - 确认 `pydantic>=2.0` 支持 `alias_generators`

5. **创建 `scripts/seed.py`**
   - 3 个测试用户（kylin/xiaolu/test，密码 123456）
   - 每个用户若干素材 + 日记 + 成就

6. **验证**
   - `uvicorn app.main:app --reload` 能启动
   - `pytest tests/` 能跑通（至少 conftest 不报错）
   - 访问 `/docs` 能看到 Swagger UI

**产出：** 项目能跑，数据库能建表，空的路由文件准备好。

---

### 📦 Group 1：认证模块（2 接口，预计 10 分钟）

**沿用旧代码，仅修复输出格式。**

| # | 方法 | 路径 | 前端期望响应 `data` |
|---|------|------|-------------------|
| 1 | POST | `/auth/register` | `{ token, user: { id, username, name, school, major, avatar, level } }` |
| 2 | POST | `/auth/login` | 同上 |

**修改点：**
- `AuthResponse` 和 `UserInfo` 继承 `CamelModel`
- 输出时 `model_dump(by_alias=True)`
- **注意：** `UserInfo` 的字段已经全是 camelCase 无下划线，所以实际不影响。但统一继承 `CamelModel` 以防后续加字段。

**测试用例：**
- 注册成功 → 返回 token + 用户信息
- 用户名已存在 → code 非 0
- 登录成功 → 返回 token
- 密码错误 → code 非 0
- 用户名长度校验 → 4-20 字符

---

### 📦 Group 2：素材模块（8 接口，预计 25 分钟）

| # | 方法 | 路径 | 前端期望 `data` 格式 |
|---|------|------|---------------------|
| 3 | POST | `/materials` | `RawMaterial` 对象 (camelCase) |
| 4 | GET | `/materials?date=` | `RawMaterial[]` **裸数组** |
| 5 | GET | `/materials/{id}` | `RawMaterial` 对象 |
| 6 | PUT | `/materials/{id}` | `RawMaterial` 对象 |
| 7 | DELETE | `/materials/{id}` | `null` |
| 8 | POST | `/materials/{id}/emotion` | `{ label, score, emoji }` |
| 9 | POST | `/materials/{id}/polish` | `{ polished: string }` |
| 10 | POST | `/materials/voice` | `{ url, transcription }` |

**输出 Schema：**

```python
class MaterialOut(CamelModel):
    id: str
    user_id: str
    type: str                               # "image" | "voice" | "text"
    content: str
    media_url: str
    thumbnail_url: str
    location: dict                          # {lat?, lng?, address?}
    emotion: dict                           # {label, score, emoji}
    tags: list[str]
    date: str
    created_at: int
```

**注意事项：**
- `GET /materials?date=` → 返回**裸数组**（不是 `{items, total}`）
- `POST /materials/{id}/polish` → 只返回 `{ "polished": "..." }`，不要 `original` 和 `style`
- `POST /materials/voice` → 前端目前传 `{ filePath }`，后端需要实际处理为文件上传或 URL
- `DELETE` → `success(None)`
- JSON 字段（location、emotion、tags）从数据库读取时 `json.loads()`
- 创建素材时自动触发情绪提取（try/except，失败不影响创建）

**测试用例：**
- 创建文字素材 → 返回完整对象（camelCase）
- 按日期查询 → 返回裸数组
- 更新素材 → 只更新传入字段
- 删除素材 → 返回成功
- 情绪提取 → 返回 {label, score, emoji}
- 文字润色（4 种风格）→ 返回 {polished}

---

### 📦 Group 3：日记模块（10 接口，预计 40 分钟）

**最复杂的模块，包含 AI 生成、编辑限制、衍生内容。**

| # | 方法 | 路径 | 前端期望 `data` 格式 |
|---|------|------|---------------------|
| 11 | POST | `/diaries/generate` | `Diary` 对象 (camelCase) |
| 12 | GET | `/diaries?page=&page_size=` | `{ items: Diary[], total }` |
| 13 | GET | `/diaries/{id}` | `Diary` 对象 |
| 14 | PUT | `/diaries/{id}` | `Diary` 对象 |
| 15 | GET | `/diaries/{id}/emotion-trend` | `{ dominant, trend: [{hour, label, score}] }` |
| 16 | POST | `/diaries/{id}/extract` | `{ anniversaries, relations, preferences }` |
| 17 | POST | `/diaries/{id}/derivative` | `DiaryDerivative` 对象 |
| 18 | GET | `/derivatives?diary_id=` | `DiaryDerivative[]` **裸数组** |
| 19 | POST | `/derivatives/{id}/share` | `null` |
| 20 | GET | `/diaries/today-summary?date=` | `TodaySummary` 对象 |

**输出 Schema：**

```python
class DiaryOut(CamelModel):
    id: str
    title: str
    content: str
    date: str                               # "YYYY-MM-DD"
    weather: str
    special_date: str
    emotion_summary: dict                   # {dominant, trend: [{hour, label, score}]}
    material_ids: list[str]
    style: str
    edit_count: int
    max_edits: int
    status: str                             # "draft" | "published"
    created_at: int
    updated_at: int
    # legacy 兼容字段
    emotion: dict                           # {emoji, label, score}
    images: list[str]
    tags: list[str]
    location: str
    has_comic: bool
    has_bgm: bool

class DerivativeOut(CamelModel):
    id: str
    diary_id: str
    type: str                               # "comic" | "novel" | "share_card"
    content: str
    media_url: str
    share_scope: str                        # "private" | "friends" | "public"
    created_at: int

class TodaySummaryOut(CamelModel):
    date: str
    material_count: int
    materials: list[dict]                   # [{id, type, content, createdAt, emotion?}]
    has_diary: bool
    diary_id: str | None
    diary_status: str | None
```

**关键逻辑：**
- **`GET /diaries?page=&page_size=`** — 注意 query param 是 `page_size`（snake_case），不是 `pageSize`
- **`PUT /diaries/{id}`** — 必须检查 `edit_count < max_edits`，超出返回 `ApiException`
- **`POST /diaries/generate`** — 读取当天素材 → 调用 MiniMax → 创建日记记录
- **`POST /diaries/{id}/extract`** — 返回 `{ anniversaries: [{title, date, relatedPerson}], relations: [{name, relation, mentions}], preferences: [{category, item, sentiment}] }` — **注意 relatedPerson 是 camelCase**
- **`GET /derivatives?diary_id=`** — 支持 `diary_id` query 参数筛选，裸数组返回
- **`POST /derivatives/{id}/share`** — 返回 `success(None)`，不需要返回更新后的对象
- **`GET /diaries/today-summary`** — 注意 `materials[].emotion.score` 是 0.0-1.0（跟素材一致）
- **路由注意：** `/diaries/today-summary` 必须在 `/diaries/{id}` **之前**注册，否则 FastAPI 会把 `today-summary` 当成 `{id}`

**测试用例：**
- AI 生成日记（Mock 模式）→ 返回 Diary（所有字段 camelCase）
- 日记列表分页 → `{items, total}`
- 修改日记 → edit_count +1
- 修改超限 → 返回错误
- 生成衍生内容（3 种类型）→ 返回 DerivativeOut
- 衍生列表 + diary_id 筛选 → 裸数组
- 今日概览 → 包含素材列表和日记状态

---

### 📦 Group 4：AI + 用户模块（12 接口，预计 35 分钟）

#### AI 模块（4 接口）

| # | 方法 | 路径 | 前端期望 `data` 格式 |
|---|------|------|---------------------|
| 21 | POST | `/chat` | `string`（纯文本，非 SSE） |
| 22 | GET | `/chat/history?limit=` | `{ items: [{role, content, timestamp}], total }` |
| 23 | POST | `/ai/tts` | `string`（音频文件 URL） |
| 24 | GET | `/ai/fortune` | `{ overall, study, social, health, tip, luckyColor, luckyNumber }` |

**关键决策：**
- **`POST /chat` 返回纯文本，不是 SSE。** 前端目前不支持真正的 SSE（用模拟打字机），所以后端直接返回完整回复。`success("AI 回复文本")`
- **`GET /ai/fortune`** — 运势 schema 必须精确匹配前端 `Fortune` interface：
  ```python
  class FortuneOut(CamelModel):
      overall: int          # 1-5 星
      study: int            # 1-5 星
      social: int           # 1-5 星
      health: int           # 1-5 星
      tip: str              # 今日提示
      lucky_color: str      # 幸运颜色 → JSON 输出 "luckyColor"
      lucky_number: int     # 幸运数字 → JSON 输出 "luckyNumber"
  ```
- **chat router** 不再分 `/ai/chat` 和 `/chat`，只保留 `/chat`（prefix="/chat"）
- **ai router** 只保留 `/ai/tts` 和 `/ai/fortune`（prefix="/ai"）
- 删除旧的 `/ai/chat`、`/ai/generate-diary`、`/ai/comic`、`/ai/share-card`、`/ai/bgm`、`/ai/novel-chapter` — 前端不调用这些

#### 用户模块（8 接口）

| # | 方法 | 路径 | 前端期望 `data` 格式 |
|---|------|------|---------------------|
| 25 | GET | `/user/profile` | `UserProfile` 对象 (camelCase) |
| 26 | POST | `/user/profile` | `UserProfile` 对象 |
| 27 | GET | `/user/agent-portrait` | `string`（图片 URL） |
| 28 | GET | `/user/growth` | `GrowthData` 对象 |
| 29 | GET | `/user/achievements` | `Achievement[]` **裸数组** |
| 30 | GET | `/user/settings` | `Settings` 对象 |
| 31 | POST | `/user/settings` | `Settings` 对象 |
| 32 | GET | `/user/semester-report` | `SemesterReport` 对象 |

**输出 Schema（必须精确匹配前端 TypeScript）：**

```python
class UserProfileOut(CamelModel):
    name: str
    school: str
    major: str
    level: int
    diary_count: int                        # → "diaryCount"
    streak_days: int                        # → "streakDays"
    pomodoro_count: int                     # → "pomodoroCount"
    avatar: str
    style_tags: list[str] | None = None     # → "styleTags"
    custom_style_prompt: str | None = None  # → "customStylePrompt"

class AchievementOut(CamelModel):
    id: str
    title: str
    description: str
    icon: str
    unlocked: bool
    unlocked_at: int | None = None          # → "unlockedAt"

class GrowthDataOut(CamelModel):
    diaries: list[dict]                     # [{date, count}]
    emotions: list[dict]                    # [{label, count}]
    tags: list[dict]                        # [{label, count}]
    pomodoros: list[dict]                   # [{date, count}]
    streak: list[int]

class SettingsOut(CamelModel):
    theme: str                              # "light" | "dark"
    notifications: bool
    auto_bgm: bool                          # → "autoBGM"   ⚠️ 特殊！
    diary_privacy: str                      # → "diaryPrivacy"
    language: str

class SemesterReportOut(CamelModel):
    total_diaries: int                      # → "totalDiaries"
    total_pomodoros: int                    # → "totalPomodoros"
    top_emotions: list[dict]               # → "topEmotions"
    top_tags: list[dict]                   # → "topTags"
    writing_time: int                      # → "writingTime"
    avg_emotion: int                       # → "avgEmotion"
    streak: int
    achievements: int
    highlights: list[str]
```

**⚠️ `autoBGM` 特殊处理：**
前端字段名是 `autoBGM`（B 和 G 和 M 都大写），但 `to_camel("auto_bgm")` 会生成 `autoBgm`。需要手动设置 alias：
```python
auto_bgm: bool = Field(alias="autoBGM", default=False)
```

**`POST /user/profile` 请求体：**
前端发送混合格式：
```python
class UpdateProfileRequest(BaseModel):
    name: str | None = None
    school: str | None = None
    major: str | None = None
    avatar: str | None = None
    style_tags: list[str] | None = None           # snake_case!
    custom_style_prompt: str | None = None        # snake_case!
```

**成就系统实现：**
成就定义硬编码为常量列表（24 个成就，从前端 mock 数据提取），查询 `user_achievements` 表判断是否解锁。

**测试用例：**
- 获取用户资料 → 所有字段 camelCase
- 更新风格标签 → style_tags 写入成功
- 成就列表 → 裸数组，unlocked/unlockedAt 正确
- 设置获取/更新 → autoBGM 字段名正确

---

### 📦 Group 5：社交模块（9 接口，预计 30 分钟）

| # | 方法 | 路径 | 前端期望 `data` 格式 |
|---|------|------|---------------------|
| 33 | GET | `/social/matches` | `Match[]` **裸数组** |
| 34 | POST | `/social/match-requests` | `MatchRequest` 对象 |
| 35 | GET | `/social/messages/{matchId}?limit=&before=` | `Message[]` **裸数组** |
| 36 | GET | `/social/matches/{matchId}/report` | `MatchReport` 对象 |
| 37 | POST | `/social/match-requests/{requestId}/respond` | `null` |
| 38 | POST | `/social/buddy` | `BuddyRequest` 对象 |
| 39 | POST | `/social/buddy/{requestId}/respond` | `null` |
| 40 | GET | `/user/portrait` | `UserPortrait` 对象 |
| 41 | POST | `/user/portrait/refresh` | `UserPortrait` 对象 |

**输出 Schema（精确匹配前端 TypeScript）：**

```python
class MatchOut(CamelModel):
    id: str
    nickname: str               # ⚠️ 需要 JOIN 查 target user 的 name
    avatar: str                 # ⚠️ 需要 JOIN 查 target user 的 avatar
    school: str                 # ⚠️ 需要 JOIN 查 target user 的 school
    common_tags: list[str]      # → "commonTags"
    matched_at: int             # → "matchedAt"（= created_at of match record）

class MatchRequestOut(CamelModel):
    id: str
    from_uid: str               # → "fromUid"
    to_uid: str                 # → "toUid"
    status: str                 # "pending" | "accepted" | "rejected"
    created_at: int             # → "createdAt"

class MessageOut(CamelModel):
    id: str
    match_id: str               # → "matchId"
    from_uid: str               # → "fromUid"
    content: str
    timestamp: int

class MatchReportOut(CamelModel):
    compatibility: int          # 0-100
    analysis: str
    common_points: list[str]    # → "commonPoints"
    differences: list[str]

class BuddyRequestOut(CamelModel):
    id: str
    from_uid: str               # → "fromUid"
    to_uid: str                 # → "toUid"
    reason: str
    status: str
    created_at: int             # → "createdAt"

class UserPortraitOut(CamelModel):
    preferences: list[dict]     # [{category, items: []}]
    personality: list[str]
    relations: list[dict]       # [{name, relation}]
    interests: list[str]
```

**关键注意：**
- **`GET /social/matches`** — 前端期望 `{nickname, avatar, school}` 而不是 `{user_id, target_id}`。后端必须 JOIN users 表查出对方的信息
- **`POST /social/buddy`** — 前端发 `{ target_user_id: "xxx" }`（注意是 `target_user_id`）
- **`POST /social/match-requests/{id}/respond`** — 前端发 `{ accept: true/false }`（布尔值），不是 `{ action: "accept" }`
- **`GET /social/messages/{matchId}?limit=&before=`** — 支持 `limit` 和 `before` query 参数（before 是消息 ID，不是时间戳）
- **`GET /user/portrait`** — 注意路径在 `/user/` 下而不是 `/social/`，但放在 social router 或 user router 都行
- **`UserPortraitOut.preferences`** — 前端期望 `[{category: "美食", items: ["红烧肉", "火锅"]}]` 格式，不是后端旧的 flat dict
- **`UserPortraitOut.personality`** — 前端期望 `string[]` 数组，不是后端旧的单个字符串
- **`UserPortraitOut.relations`** — 前端期望 `[{name, relation}]` 数组，不是后端旧的 dict
- **匹配报告** — 前端期望结构化 `{compatibility, analysis, commonPoints, differences}`，不是纯文本。需要让 MiniMax 输出 JSON

**测试用例：**
- 获取匹配列表 → 裸数组，包含 nickname/avatar/school
- 发送匹配请求 → 返回 MatchRequestOut
- 搭子申请（target_user_id 字段名）→ 返回 BuddyRequestOut
- 响应匹配（accept 布尔值）→ success(None)
- 用户画像结构匹配

---

### 📦 Group 6：纪念日 + 学习模块（11 接口，预计 20 分钟）

#### 纪念日（5 接口）

| # | 方法 | 路径 | 前端期望 `data` 格式 |
|---|------|------|---------------------|
| 42 | GET | `/anniversaries` | `Anniversary[]` **裸数组** |
| 43 | POST | `/anniversaries` | `Anniversary` 对象 |
| 44 | PUT | `/anniversaries/{id}` | `Anniversary` 对象 |
| 45 | DELETE | `/anniversaries/{id}` | `null` |
| 46 | GET | `/anniversaries/today` | `{ today, on_this_day }` |

```python
class AnniversaryOut(CamelModel):
    id: str
    user_id: str                # → "userId"
    title: str
    date: str                   # "MM-DD"
    year: int | None = None
    source: str                 # "manual" | "ai_extracted"
    related_person: str         # → "relatedPerson"
    diary_id: str | None = None # → "diaryId"
    created_at: int             # → "createdAt"
```

**`GET /anniversaries/today` 特殊处理：**
前端代码：
```typescript
const res = await request<{ today: any[]; on_this_day: any[] }>({ url: '/anniversaries/today' })
```
后端必须返回：
```python
success({
    "today": [AnniversaryOut...],    # snake_case key! 前端直接读 res.today
    "on_this_day": [                  # snake_case key!
        {
            "id": "...",
            "title": "...",
            "content": "...",
            "date": "YYYY-MM-DD",
            "emotion": { "label": "...", "score": 88, "emoji": "..." }
        }
    ]
})
```
**⚠️ 注意：这里的外层 key `today` 和 `on_this_day` 保持 snake_case（因为前端直接硬编码读取 `res.today` 和 `res.on_this_day`），但内层对象的字段还是 camelCase。**

#### 学习模块（6 接口，低优先级）

| # | 方法 | 路径 | 前端期望 `data` 格式 |
|---|------|------|---------------------|
| 47 | GET | `/study/pomodoros` | `Pomodoro[]` **裸数组** |
| 48 | POST | `/study/pomodoros` | `Pomodoro` 对象 |
| 49 | POST | `/study/pomodoros/{id}/complete` | `null` |
| 50 | GET | `/study/todos` | `Todo[]` **裸数组** |
| 51 | POST | `/study/todos` | `Todo` 对象 |
| 52 | POST | `/study/todos/{id}/toggle` | `Todo` 对象 |

```python
class PomodoroOut(CamelModel):
    id: str
    task: str
    subject: str
    duration: int
    completed_at: int | None = None     # → "completedAt"
    created_at: int                     # → "createdAt"

class TodoOut(CamelModel):
    id: str
    content: str
    completed: bool
    priority: str                       # "low" | "medium" | "high"
    created_at: int                     # → "createdAt"
```

---

## 五、集成验证（Group 7）

在所有模块实现完成后执行：

1. **启动后端** `uvicorn app.main:app --port 8000`
2. **前端切换到真实模式** `USE_MOCK = false`
3. **逐模块验证：**
   - 注册/登录 → token 存储 → 后续请求带 token
   - 创建素材 → 查看素材列表 → AI 情绪提取
   - 生成日记 → 日记列表 → 编辑日记 → 编辑限制
   - 衍生内容生成 → 列表查看
   - AI 对话 → 聊天历史
   - 用户资料 → 设置 → 成就
   - 社交匹配 → 消息 → 报告
   - 纪念日 CRUD → 今日纪念日

4. **全量测试** `pytest tests/ -v`

---

## 六、可复用代码清单

从旧后端直接复用（无需重写）：

| 文件 | 状态 | 说明 |
|------|------|------|
| `app/config.py` | ✅ 直接用 | 配置正确 |
| `app/database.py` | ⚠️ 小改 | `init_db()` 补全新模型导入 |
| `app/dependencies.py` | ✅ 直接用 | get_current_user 正确 |
| `app/response.py` | ✅ 直接用 | success/error/ApiException 正确 |
| `app/auth/service.py` | ✅ 直接用 | JWT + bcrypt 正确 |
| `app/ai/minimax_client.py` | ✅ 直接用 | 5 模态 + Mock 正确 |
| `app/models/*.py` | ✅ 直接用 | 所有数据模型正确 |
| `.env.example` | ✅ 直接用 | — |

**需要重写的：** 所有 `router.py`、`schemas.py`、`service.py`（每个模块的路由层和业务层）

---

## 七、QA 检查清单（每个接口上线前必须过）

```
□ 路径与 API-SPEC.md 完全一致？
□ HTTP 方法正确（GET/POST/PUT/DELETE）？
□ 需要认证的接口加了 Depends(get_current_user)？
□ query 参数名与前端一致（page_size 不是 pageSize）？
□ 请求体字段名与前端发送的一致？
□ 响应 data 用了 CamelModel + model_dump(by_alias=True)？
□ 列表返回格式正确（裸数组 vs {items, total}）？
□ JSON 字段已 json.loads() 解析，不是返回字符串？
□ autoBGM 等特殊字段用了手动 alias？
□ 有对应的 pytest 测试用例？
```

---

## 八、预估总工时

| Group | 模块 | 接口数 | 预估时间 |
|-------|------|--------|----------|
| 0 | 基础设施 | — | 15 min |
| 1 | 认证 | 2 | 10 min |
| 2 | 素材 | 8 | 25 min |
| 3 | 日记 + 衍生 | 10 | 40 min |
| 4 | AI + 用户 | 12 | 35 min |
| 5 | 社交 | 9 | 30 min |
| 6 | 纪念日 + 学习 | 11 | 20 min |
| 7 | 集成验证 | — | 15 min |
| **合计** | | **52** | **~190 min（≈3小时）** |

---

*本文档由 BB 基于前端 52 个接口逆向编写。每个字段名、每个返回格式、每个枚举值都已与前端代码交叉验证。照着这份写，不会再接不上。*
