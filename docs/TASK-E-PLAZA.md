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

## 工作重点

### 优先级排序

1. **P0 — 广场帖子 CRUD（4 个接口）**
   - GET /plaza/posts（列表 + 频道筛选）
   - GET /plaza/posts/{id}（详情）
   - POST /plaza/posts（创建）
   - POST /plaza/posts/{id}/like（点赞）
   
2. **P0 — 广场评论（2 个接口）**
   - GET /plaza/posts/{id}/comments
   - POST /plaza/posts/{id}/comments

3. **P1 — 分身记忆 CRUD（4 个接口）**
   - GET/POST/PUT/DELETE /avatar/memories

4. **P1 — 分身状态（2 个接口）**
   - GET/PUT /avatar/status

5. **P2 — 分身推荐 + 操作（2 个接口）**
   - GET /avatar/matches
   - POST /avatar/matches/{id}/action

6. **P2 — 分身侧写（2 个接口）**
   - GET /avatar/profile
   - POST /avatar/profile/regenerate

### 实现建议

- **Phase 1（Mock 先行）：** 先用硬编码 Mock 数据跑通所有接口，确保前端能联调
- **Phase 2（数据库）：** 建表 + CRUD 实现，真实存取数据
- **Phase 3（AI 接入）：** 分身侧写生成、帖子匹配打分接入 MiniMax AI

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

| 阶段 | 内容 | 预估时间 |
|------|------|----------|
| 数据模型 | 新建 plaza.py + avatar.py | 0.5 天 |
| 广场 CRUD | 6 个接口 | 1 天 |
| 分身记忆/状态 | 6 个接口 | 1 天 |
| 分身推荐 + 侧写 | 4 个接口 | 1 天 |
| 测试 | test_plaza + test_avatar | 0.5 天 |
| **合计** | | **约 4 天** |

---

*参考：material/ 的 CRUD 结构 | social/ 的 JOIN 查询 | COOKBOOK.md 的代码模板*
