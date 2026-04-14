# 任务书 E — 广场 + AI 分身

> **负责人：** 队友 E（或由前辈直接调度）
>
> **模块：** app/plaza/（广场帖子）、app/avatar/（AI 分身）
>
> **前置阅读：** [ONBOARDING.md](./ONBOARDING.md) → [COOKBOOK.md](./COOKBOOK.md) → 本文档
>
> **分支名：** `feat/plaza-avatar`
>
> **前端参考：** `src/services/api/plaza.ts` + `src/services/api/avatar.ts` + `src/services/mock/plaza.ts` + `src/services/mock/avatar.ts`

---

## 当前进度

| 阶段 | 状态 | 备注 |
|------|------|------|
| 数据模型 | ✅ 已完成 | plaza.py（7张表）+ avatar.py 已创建并注册 |
| 种子数据 | ✅ 已完成 | seed_plaza_avatar.py（10用户/15帖/28评论/39点赞/41记忆/20推荐/10侧写） |
| 广场 CRUD | ⬜ 待开始 | 6 个接口 |
| 分身记忆/状态 | ⬜ 待开始 | 6 个接口 |
| 分身推荐+侧写 | ⬜ 待开始 | 4 个接口 |
| 测试 | ⬜ 待开始 | test_plaza + test_avatar |

---

## 模块概述

### 广场（Plaza）

校园社交信息流。用户可以发帖（找搭子/求助/分享/恋爱）、浏览、点赞、评论。支持频道筛选和仅本校可见。

### AI 分身（Avatar）

用户的数字化代理。分身基于用户画像（记忆库）自动浏览广场帖子，匹配感兴趣的内容，与对方分身进行初步对话，推荐给用户。用户可以查看推荐、忽略或发起私聊。

**两个模块紧密关联：** 广场提供内容，分身提供智能匹配。

---

## 你需要新建的文件

| 文件 | 操作 |
|------|------|
| `app/plaza/__init__.py` | **新建** |
| `app/plaza/router.py` | **新建**（6 个路由） |
| `app/plaza/service.py` | **新建**（业务逻辑） |
| `app/plaza/schemas.py` | **新建**（请求/响应 Schema） |
| `app/avatar/__init__.py` | **新建** |
| `app/avatar/router.py` | **新建**（10 个路由） |
| `app/avatar/service.py` | **新建**（业务逻辑） |
| `app/avatar/schemas.py` | **新建**（请求/响应 Schema） |
| `app/models/plaza.py` | **新建**（PlazaPost、PlazaComment、PostLike） |
| `app/models/avatar.py` | **新建**（AvatarMemory、AvatarStatus、AvatarMatch、AvatarProfile） |
| `tests/test_plaza.py` | **新建** |
| `tests/test_avatar.py` | **新建** |

## 需要修改的文件

| 文件 | 操作 |
|------|------|
| `app/main.py` | 注册 plaza_router 和 avatar_router |
| `app/database.py` | `init_db()` 中导入新模型 |
| `app/models/__init__.py` | 导出新模型 |

## 不要碰的文件

- `app/config.py`, `app/dependencies.py`, `app/response.py`, `app/serializers.py`
- `app/auth/*`, `app/upload/*`
- `app/ai/minimax_client.py`（只调用不修改，或新增方法但不改已有方法）
- 其他模块的文件夹

---

## 接口清单

### 广场模块（6 个接口）

#### 1. GET /api/plaza/posts — 帖子列表（分页 + 频道筛选）

**前端调用：** `getPlazaPosts(channel?, page, pageSize)`

**Query 参数：**

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| channel | string | — | buddy / help / share / dating，空则返回全部 |
| page | int | 1 | 页码 |
| page_size | int | 10 | 每页条数 |

**返回格式：** `{ items: PlazaPostOut[], total: number }`

**实现要点：**
- JOIN users 表获取作者信息（authorName / authorAvatar / authorSchool / authorMajor）
- 需要从 users 表额外读取一个「年级」信息作为 authorGrade（可从注册年份推算或新增字段）
- channel 筛选：`PlazaPost.type == channel`，空则不筛选
- school_only=true 的帖子只对同校用户可见（比较 post.user.school == current_user.school）
- 排序：created_at DESC

---

#### 2. GET /api/plaza/posts/{post_id} — 帖子详情

**前端调用：** `getPostDetail(id)`

**返回格式：** PlazaPostOut 对象

---

#### 3. POST /api/plaza/posts — 创建帖子

**前端调用：** `createPost(data)`

**请求 Body：**

```python
class CreatePostRequest(BaseModel):
    type: str                           # buddy / help / share / dating
    content: str                        # 正文
    images: list[str] = []              # 图片 URL 列表
    location: str = ""                  # 位置
    tags: list[str] = []                # 话题标签
    allow_agent_reply: bool = True      # 允许分身回复
    school_only: bool = False           # 仅本校可见
```

**返回格式：** PlazaPostOut 对象

**实现要点：**
- 自动从 current_user 填充作者信息
- likes / comments / agentResponses 初始值 = 0
- isFromAgent = false

---

#### 4. POST /api/plaza/posts/{post_id}/like — 点赞/取消点赞

**前端调用：** `likePost(id)`

**返回格式：** null

**实现要点：**
- 查 post_likes 表：如果已存在 (post_id, user_id) 记录 → 删除（取消点赞）+ likes -1
- 如果不存在 → 创建记录 + likes +1
- Toggle 逻辑

---

#### 5. GET /api/plaza/posts/{post_id}/comments — 评论列表

**前端调用：** `getPostComments(postId)`

**返回格式：** `PlazaCommentOut[]` 裸数组

**实现要点：**
- JOIN users 表获取 authorName / authorAvatar
- 分身评论（is_agent=true）的 authorName 显示为「XXX的分身」
- 排序：created_at ASC（最早的在前）

---

#### 6. POST /api/plaza/posts/{post_id}/comments — 添加评论

**前端调用：** `addComment(postId, content, isAgent)`

**请求 Body：**

```python
class AddCommentRequest(BaseModel):
    content: str                        # 评论内容
    is_agent: bool = False              # 是否分身回复
```

**返回格式：** PlazaCommentOut 对象

**实现要点：**
- 自动填充 authorId / authorName / authorAvatar
- 帖子 comments 字段 +1
- 如果 is_agent=true，authorName 设为「{用户名}的分身」

---

### AI 分身模块（10 个接口）

#### 7. GET /api/avatar/memories — 分身记忆列表

**前端调用：** `getMemories(category?)`

**Query 参数：** `category`（可选筛选）

**返回格式：** `AvatarMemoryOut[]` 裸数组

---

#### 8. POST /api/avatar/memories — 添加记忆

**前端调用：** `addMemory({ category, content })`

**请求 Body：**

```python
class AddMemoryRequest(BaseModel):
    category: str                       # fact/interest/personality/need/habit/relation
    content: str                        # 记忆内容
```

**返回格式：** AvatarMemoryOut 对象

**实现要点：**
- source = "manual"
- confidence = 1.0
- isActive = true，isPinned = false

---

#### 9. PUT /api/avatar/memories/{memory_id} — 更新记忆

**前端调用：** `updateMemory(id, fields)`

**返回格式：** 更新后的 AvatarMemoryOut 对象

---

#### 10. DELETE /api/avatar/memories/{memory_id} — 删除记忆

**前端调用：** `deleteMemory(id)`

**返回格式：** null

---

#### 11. GET /api/avatar/status — 获取分身状态

**前端调用：** `getAvatarStatus()`

**返回格式：** AvatarStatusOut 对象

**实现要点：**
- 每个用户一条 AvatarStatus 记录
- 首次查询时自动创建默认记录

---

#### 12. PUT /api/avatar/status — 更新分身状态

**前端调用：** `updateAvatarStatus(fields)`

**返回格式：** 更新后的 AvatarStatusOut 对象

---

#### 13. GET /api/avatar/matches — 分身推荐列表

**前端调用：** `getAgentMatches()`

**返回格式：** `AvatarMatchOut[]` 裸数组

**实现要点：**
- 查询当前用户的所有 AvatarMatch 记录
- 每条记录需嵌套完整的 PlazaPost 对象（post 字段）
- 默认不返回 status="dismissed" 的记录（或前端过滤）
- 排序：match_score DESC（最相关的在前）

---

#### 14. POST /api/avatar/matches/{match_id}/action — 分身匹配操作

**前端调用：** `dismissMatch(matchId)` 或 `acceptMatch(matchId)`

**请求 Body：**

```python
class MatchActionRequest(BaseModel):
    action: str                         # "dismiss" / "chat"
```

**返回格式：** null

**实现要点：**
- action="dismiss" → status 更新为 "dismissed"
- action="chat" → status 更新为 "chatting"

---

#### 15. GET /api/avatar/profile — 获取分身侧写

**前端调用：** `getAvatarProfile()`

**返回格式：** AvatarProfileOut 对象

**实现要点：**
- 从 avatar_profiles 表读取
- 如果不存在，返回默认空侧写

---

#### 16. POST /api/avatar/profile/regenerate — 重新生成侧写

**前端调用：** `regenerateProfile()`

**返回格式：** AvatarProfileOut 对象

**实现要点：**
- 读取用户所有记忆 + 近期日记/聊天
- 调用 AI（chat_completion）生成人格摘要
- 写入/更新 avatar_profiles 表
- 更新 diaryCount / chatCount / generatedAt

---

## 输出 Schema（必须精确匹配前端 TypeScript）

```python
# app/plaza/schemas.py

from app.serializers import CamelModel
from pydantic import BaseModel
from typing import Optional


class CreatePostRequest(BaseModel):
    type: str
    content: str
    images: list[str] = []
    location: str = ""
    tags: list[str] = []
    allow_agent_reply: bool = True
    school_only: bool = False


class AddCommentRequest(BaseModel):
    content: str
    is_agent: bool = False


class PlazaPostOut(CamelModel):
    id: str
    author_id: str                      # → "authorId"
    author_name: str                    # → "authorName"
    author_avatar: str                  # → "authorAvatar"
    author_school: str                  # → "authorSchool"
    author_major: str                   # → "authorMajor"
    author_grade: str                   # → "authorGrade"
    type: str                           # buddy / help / share / dating
    content: str
    images: list[str]
    location: str
    tags: list[str]
    likes: int
    comments: int
    agent_responses: int                # → "agentResponses"
    created_at: int                     # → "createdAt"
    is_from_agent: bool                 # → "isFromAgent"
    allow_agent_reply: bool             # → "allowAgentReply"
    school_only: bool                   # → "schoolOnly"


class PlazaCommentOut(CamelModel):
    id: str
    post_id: str                        # → "postId"
    author_id: str                      # → "authorId"
    author_name: str                    # → "authorName"
    author_avatar: str                  # → "authorAvatar"
    content: str
    is_agent: bool                      # → "isAgent"
    created_at: int                     # → "createdAt"


# app/avatar/schemas.py

class AddMemoryRequest(BaseModel):
    category: str
    content: str


class UpdateMemoryRequest(BaseModel):
    content: Optional[str] = None
    is_active: Optional[bool] = None
    is_pinned: Optional[bool] = None
    category: Optional[str] = None
    tags: Optional[list[str]] = None


class MatchActionRequest(BaseModel):
    action: str                         # "dismiss" / "chat"


class UpdateStatusRequest(BaseModel):
    is_active: Optional[bool] = None
    enabled_channels: Optional[list[str]] = None
    enabled_actions: Optional[list[str]] = None
    match_range: Optional[dict] = None


class AvatarMemoryOut(CamelModel):
    id: str
    category: str
    content: str
    source: str
    source_ref: Optional[str] = None    # → "sourceRef"
    confidence: float
    created_at: int                     # → "createdAt"
    updated_at: int                     # → "updatedAt"
    is_active: bool                     # → "isActive"
    is_pinned: bool                     # → "isPinned"
    need_type: Optional[str] = None     # → "needType"
    urgency: Optional[str] = None
    expiry: Optional[int] = None
    match_status: Optional[str] = None  # → "matchStatus"
    tags: Optional[list[str]] = None


class AvatarStatusOut(CamelModel):
    is_active: bool                     # → "isActive"
    browsed_count: int                  # → "browsedCount"
    matched_count: int                  # → "matchedCount"
    chatting_count: int                 # → "chattingCount"
    last_active_at: int                 # → "lastActiveAt"
    enabled_channels: list[str]         # → "enabledChannels"
    enabled_actions: list[str]          # → "enabledActions"
    match_range: dict                   # → "matchRange"


class AgentConversationMessageOut(CamelModel):
    from_: str                          # "my_agent" / "their_agent" (alias needed: "from")
    content: str
    timestamp: int


class AvatarMatchOut(CamelModel):
    id: str
    post_id: str                        # → "postId"
    post: PlazaPostOut                  # 嵌套完整帖子
    match_score: int                    # → "matchScore"
    match_reasons: list[str]            # → "matchReasons"
    agent_conversation: list[dict]      # → "agentConversation"
    status: str
    created_at: int                     # → "createdAt"


class AvatarProfileOut(CamelModel):
    summary: str
    diary_count: int                    # → "diaryCount"
    chat_count: int                     # → "chatCount"
    generated_at: int                   # → "generatedAt"
```

**⚠️ 注意：`AgentConversationMessageOut.from_`**

前端字段名是 `from`，但 `from` 是 Python 保留字。需要：
```python
from pydantic import Field
from_: str = Field(alias="from")
```
或者 `agent_conversation` 直接用 `list[dict]` 返回原始 JSON。

---

## 路由注册

```python
# app/main.py 中新增

from app.plaza.router import router as plaza_router
from app.avatar.router import router as avatar_router

app.include_router(plaza_router, prefix="/api")
app.include_router(avatar_router, prefix="/api")
```

```python
# app/plaza/router.py
router = APIRouter(prefix="/plaza", tags=["广场"])

# app/avatar/router.py
router = APIRouter(prefix="/avatar", tags=["AI分身"])
```

---

## 数据模型

详见 [API-DOCS.md](./API-DOCS.md) 的「新增数据模型参考」章节。

需要在 `app/database.py` 的 `init_db()` 中导入新模型：
```python
from app.models import plaza, avatar  # 新增
```

---

## 实施步骤（成员 E 执行计划）

> **编码模式约定**（从 material/ social/ 等已有模块提取）：
>
> | 模式 | 做法 |
> |------|------|
> | 路由层 | `Depends(get_current_user)` + `Depends(get_db)`，返回 `success(...)` |
> | 序列化 | service 返回 dict → router 用 `XxxOut(**dict).model_dump(by_alias=True)` 转 camelCase |
> | JSON 字段 | 数据库存 Text，读取用 `json.loads`，写入用 `json.dumps(ensure_ascii=False)` |
> | 时间戳 | `int(time.time() * 1000)` 毫秒级 |
> | 主键 | `str(uuid4())` |
> | 异常 | `ApiException(NOT_FOUND, "xxx不存在", status_code=404)` |
> | 响应 | 统一 `{"code": 0, "data": ..., "message": "ok"}` |

---

### Step 1：广场模块 schemas + service + router（6 个接口）

**新建 4 个文件：**

| 文件 | 内容 |
|------|------|
| `app/plaza/__init__.py` | 空文件 |
| `app/plaza/schemas.py` | `CreatePostRequest`、`AddCommentRequest`、`PlazaPostOut`、`PlazaCommentOut`（照搬输出 Schema 章节） |
| `app/plaza/service.py` | 6 个业务函数 |
| `app/plaza/router.py` | 6 个路由端点，`APIRouter(prefix="/plaza", tags=["广场"])` |

**service.py 需实现的 6 个函数：**

| # | 函数 | 接口 | 关键逻辑 |
|---|------|------|----------|
| 1 | `list_posts(db, user, channel, page, page_size)` | GET /plaza/posts | JOIN users 取作者信息 (name/avatar/school/major/grade)；channel 筛选；school_only 帖子仅同校可见；分页 offset/limit；排序 created_at DESC |
| 2 | `get_post(db, user, post_id)` | GET /plaza/posts/{id} | JOIN users 取作者信息；school_only 检查；不存在抛 NOT_FOUND |
| 3 | `create_post(db, user, data)` | POST /plaza/posts | 从 current_user 自动填充作者信息；images/tags JSON 编码；likes/comments/agent_responses = 0；is_from_agent = false |
| 4 | `toggle_like(db, user_id, post_id)` | POST /plaza/posts/{id}/like | 查 post_likes 表：存在 → 删除 + likes-1，不存在 → 创建 + likes+1（Toggle 逻辑） |
| 5 | `list_comments(db, post_id)` | GET /plaza/posts/{id}/comments | JOIN users 取 authorName/authorAvatar；分身评论 authorName = "XXX的分身"；排序 created_at ASC |
| 6 | `add_comment(db, user, post_id, data)` | POST /plaza/posts/{id}/comments | 自动填充 authorId/authorName/authorAvatar；帖子 comments+1；is_agent=true 时 authorName = "{用户名}的分身" |

**辅助函数（参考 material/service.py）：**
- `_now_ms()` — 毫秒时间戳
- `_encode(obj)` / `_decode(s, default)` — JSON 编解码
- `_post_to_dict(post, user)` — PlazaPost + User ORM → 响应字典
- `_comment_to_dict(comment, user)` — PlazaComment + User ORM → 响应字典

**router.py 序列化模式（参考 material/router.py）：**
```python
def _serialize_post(d: dict) -> dict:
    return PlazaPostOut(**d).model_dump(by_alias=True)

def _serialize_comment(d: dict) -> dict:
    return PlazaCommentOut(**d).model_dump(by_alias=True)
```

---

### Step 2：分身记忆 + 状态模块（6 个接口）

**在 `app/avatar/` 目录中新建 4 个文件：**

| 文件 | 内容 |
|------|------|
| `app/avatar/__init__.py` | 空文件 |
| `app/avatar/schemas.py` | `AddMemoryRequest`、`UpdateMemoryRequest`、`UpdateStatusRequest`、`MatchActionRequest`、`AvatarMemoryOut`、`AvatarStatusOut`、`AvatarMatchOut`、`AvatarProfileOut`（照搬输出 Schema 章节） |
| `app/avatar/service.py` | 先实现记忆+状态的 6 个函数 |
| `app/avatar/router.py` | 先注册记忆+状态的 6 个端点，`APIRouter(prefix="/avatar", tags=["AI分身"])` |

**service.py 记忆+状态函数：**

| # | 函数 | 接口 | 关键逻辑 |
|---|------|------|----------|
| 7 | `list_memories(db, user_id, category)` | GET /avatar/memories | 按 user_id 查询；可选 category 筛选；tags 字段 json.loads |
| 8 | `add_memory(db, user_id, data)` | POST /avatar/memories | source="manual"；confidence=1.0；is_active=True；is_pinned=False；tags json.dumps |
| 9 | `update_memory(db, user_id, memory_id, data)` | PUT /avatar/memories/{id} | exclude_unset 更新；tags 字段特殊处理 json.dumps；更新 updated_at |
| 10 | `delete_memory(db, user_id, memory_id)` | DELETE /avatar/memories/{id} | 权限校验 user_id；不存在抛 NOT_FOUND |
| 11 | `get_status(db, user_id)` | GET /avatar/status | 每用户一条记录；首次查询自动创建默认记录；enabled_channels/enabled_actions/match_range json.loads |
| 12 | `update_status(db, user_id, data)` | PUT /avatar/status | exclude_unset 更新；JSON 字段需 json.dumps |

**辅助函数：**
- `_memory_to_dict(m)` — AvatarMemory ORM → 响应字典（tags json.loads）
- `_status_to_dict(s)` — AvatarStatus ORM → 响应字典（enabled_channels/enabled_actions/match_range json.loads）

---

### Step 3：分身推荐 + 侧写（4 个接口）

**在已有的 `app/avatar/service.py` 和 `router.py` 中追加：**

| # | 函数 | 接口 | 关键逻辑 |
|---|------|------|----------|
| 13 | `list_matches(db, user_id)` | GET /avatar/matches | JOIN plaza_posts + users 构建嵌套 PlazaPostOut；排除 status="dismissed"；排序 match_score DESC |
| 14 | `match_action(db, user_id, match_id, action)` | POST /avatar/matches/{id}/action | action="dismiss" → status="dismissed"；action="chat" → status="chatting" |
| 15 | `get_profile(db, user_id)` | GET /avatar/profile | 不存在返回默认空侧写 `{summary:"", diary_count:0, chat_count:0, generated_at:0}` |
| 16 | `regenerate_profile(db, user_id)` | POST /avatar/profile/regenerate | 读取用户记忆 + 日记/聊天 → 调用 MiniMax AI chat_completion → 写入/更新 avatar_profiles 表 |

**`regenerate_profile` AI 调用（需支持 Mock）：**
```python
from app.ai.minimax_client import get_minimax_client

client = get_minimax_client()
# MINIMAX_MOCK=true 时返回硬编码摘要
result = await client.chat_completion(prompt, system_prompt)
```

**`list_matches` 嵌套构建关键逻辑：**
- 查询 AvatarMatch → 拿 post_id → 查 PlazaPost → JOIN User
- 用 Step 1 的 `_post_to_dict()` 复用帖子序列化
- match_reasons / agent_conversation 用 json.loads 解码

---

### Step 4：路由注册（修改 main.py）

**修改 `app/main.py`，在路由注册区块末尾添加：**

```python
from app.plaza.router import router as plaza_router
from app.avatar.router import router as avatar_router

app.include_router(plaza_router, prefix="/api")
app.include_router(avatar_router, prefix="/api")
```

**验证：** 启动 `uvicorn app.main:app --reload`，访问 `/docs` 确认 16 个接口全部出现在 Swagger UI 中。

---

### Step 5：测试

**新建 2 个测试文件：**

| 文件 | 测试内容 |
|------|----------|
| `tests/test_plaza.py` | ① 创建帖子 → ② 列表浏览 → ③ 频道筛选 → ④ 帖子详情 → ⑤ 点赞/取消点赞 → ⑥ 添加评论 → ⑦ 评论列表 → ⑧ school_only 逻辑验证 |
| `tests/test_avatar.py` | ① 添加记忆 → ② 记忆列表 → ③ 更新记忆 → ④ 删除记忆 → ⑤ 获取/更新状态 → ⑥ 推荐列表 → ⑦ 忽略/接受匹配 → ⑧ 获取/重新生成侧写 |

**测试基础设施（参考已有 tests/）：**
- `TestClient(app)` + 注册/登录获取 token
- `headers = {"Authorization": f"Bearer {token}"}`
- 断言 `response.json()["code"] == 0`

**运行命令：**
```bash
pytest tests/test_plaza.py tests/test_avatar.py -v
```

---

## 工作重点

### 优先级排序

1. **P0 — 广场帖子 CRUD（4 个接口）** ← Step 1
   - GET /plaza/posts（列表 + 频道筛选）
   - GET /plaza/posts/{id}（详情）
   - POST /plaza/posts（创建）
   - POST /plaza/posts/{id}/like（点赞）
   
2. **P0 — 广场评论（2 个接口）** ← Step 1
   - GET /plaza/posts/{id}/comments
   - POST /plaza/posts/{id}/comments

3. **P1 — 分身记忆 CRUD（4 个接口）** ← Step 2
   - GET/POST/PUT/DELETE /avatar/memories

4. **P1 — 分身状态（2 个接口）** ← Step 2
   - GET/PUT /avatar/status

5. **P2 — 分身推荐 + 操作（2 个接口）** ← Step 3
   - GET /avatar/matches
   - POST /avatar/matches/{id}/action

6. **P2 — 分身侧写（2 个接口）** ← Step 3
   - GET /avatar/profile
   - POST /avatar/profile/regenerate

---

## 与其他模块的依赖

| 依赖方向 | 说明 |
|----------|------|
| **广场 → 用户模块** | 帖子/评论需要 JOIN users 表获取作者信息 |
| **分身 → 用户模块** | 分身侧写需要读 user_profiles 表 |
| **分身 → 日记模块** | 侧写生成需要读 diaries 表 |
| **分身 → 对话模块** | 侧写生成需要读 chat_messages 表 |
| **分身 → AI 客户端** | 侧写生成、帖子匹配需调用 minimax_client |
| **广场 ↔ 分身** | 分身匹配结果引用 PlazaPost，广场帖子触发分身扫描 |

---

## 验收标准

- [x] 数据模型已创建（plaza.py + avatar.py，共 7 张表）
- [x] 数据库已注册（database.py + models/__init__.py）
- [x] 种子数据已创建并验证通过（seed_plaza_avatar.py）
- [ ] 16 个接口在 Swagger 中全部可调通
- [ ] `pytest tests/test_plaza.py tests/test_avatar.py -v` 全部通过
- [ ] 广场完整链路：创建帖子 → 列表浏览 → 频道筛选 → 点赞 → 评论
- [ ] 分身记忆 CRUD 完整链路
- [ ] 分身状态获取/更新
- [ ] 分身推荐列表展示 + 忽略/接受操作
- [ ] 仅本校可见逻辑正确（school_only 帖子只对同校用户可见）
- [ ] 前端 `USE_MOCK=false` 后能正常联调

---

## 预估工作量

| 阶段 | 内容 | 对应步骤 | 预估时间 | 状态 |
|------|------|----------|----------|------|
| 数据模型 | 新建 plaza.py + avatar.py | — | 0.5 天 | ✅ 已完成 |
| 种子数据 | seed_plaza_avatar.py | — | 0.5 天 | ✅ 已完成 |
| 广场 CRUD | 6 个接口 (schemas + service + router) | Step 1 | 1 天 | ⬜ |
| 分身记忆/状态 | 6 个接口 (schemas + service + router) | Step 2 | 1 天 | ⬜ |
| 分身推荐 + 侧写 | 4 个接口 (追加 service + router) | Step 3 | 1 天 | ⬜ |
| 路由注册 | 修改 main.py | Step 4 | 0.1 天 | ⬜ |
| 测试 | test_plaza + test_avatar | Step 5 | 0.5 天 | ⬜ |
| **合计** | | **5 步** | **约 4 天** |

---

*参考：material/ 的 CRUD 结构 | social/ 的 JOIN 查询 | COOKBOOK.md 的代码模板*
