# TASK-F：对话自动转素材

> **负责人：** Claude Code (Backend)
> **依赖：** 无（独立任务）
> **优先级：** P0
> **预计工时：** 40 分钟
> **创建时间：** 2026-04-02

---

## 一、需求概述

用户与 AI 伙伴聊天时，对话内容按照静默阈值自动切分为「对话段」，每段对话自动生成一条 `type="chat"` 的素材，与照片/文字素材平级汇入素材时间线，最终统一参与每日日记生成。

**核心流程：**
```
用户聊天 → 静默超过阈值 → 后端自动封闭对话段
→ AI 生成标题/摘要/情绪/标签 → 创建 chat 类型素材
→ 素材进入时间线 → 参与日记汇总
```

---

## 二、数据模型变更

### 2.1 新增表：`chat_sessions`

在 `app/models/chat.py` 中新增 `ChatSession` 模型：

```python
class ChatSession(Base):
    """对话段 — 一段连续对话的封装"""
    __tablename__ = "chat_sessions"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    status = Column(String, default="open")           # "open" | "closed"
    start_time = Column(BigInteger, nullable=False)    # 第一条消息时间戳（ms）
    end_time = Column(BigInteger, nullable=True)       # 最后一条消息时间戳（ms）
    message_count = Column(Integer, default=0)         # 消息条数（user+assistant 各算一条）
    title = Column(String, default="")                 # AI 生成标题
    summary = Column(Text, default="")                 # AI 生成摘要
    mood = Column(String, default="")                  # 情绪标签
    mood_emoji = Column(String, default="")            # 情绪 emoji
    topic_tags = Column(Text, default="[]")            # JSON: 话题标签
    material_id = Column(String, nullable=True)        # 关联素材 ID
    date = Column(String, nullable=False)              # 归属日期 YYYY-MM-DD
    created_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index("ix_chat_sessions_user_date", "user_id", "date"),
        Index("ix_chat_sessions_user_status", "user_id", "status"),
    )
```

### 2.2 修改表：`chat_messages`

在 `ChatMessage` 模型中新增字段：

```python
session_id = Column(String, nullable=True)  # 关联 chat_sessions.id
```

### 2.3 修改表：`raw_materials`

在 `RawMaterial` 模型中新增字段：

```python
chat_session_id = Column(String, nullable=True)  # 仅 chat 类型使用
start_time = Column(BigInteger, nullable=True)    # 对话开始时间
end_time = Column(BigInteger, nullable=True)      # 对话结束时间
```

`type` 字段扩展支持 `"chat"` 值（无需改模型，仅在业务逻辑中使用）。

### 2.4 修改表：`user_settings`

在 `UserSettings` 模型中新增字段：

```python
chat_material_enabled = Column(Boolean, default=True)     # 对话自动转素材开关
chat_silence_threshold = Column(Integer, default=30)       # 静默阈值（分钟）
chat_material_toast = Column(Boolean, default=True)        # toast 提示开关
chat_min_rounds = Column(Integer, default=3)               # 最小轮数（user 消息数）
```

### 2.5 数据库迁移

修改模型后，删除 `data.db` 重建：

```bash
python scripts/seed.py
python scripts/seed_plaza_avatar.py
```

---

## 三、接口变更清单

### 3.1 修改 `POST /api/chat` — 集成 session 管理

**文件：** `app/chat/router.py`

**改动逻辑：**

在每次用户发消息时：

1. 查询该用户是否有 `status="open"` 的 ChatSession
2. **有 open session：**
   - 获取该 session 最后一条消息的时间戳
   - 如果 `(当前时间 - 最后消息时间) > 用户的 chat_silence_threshold * 60 * 1000`：
     - 封闭旧 session → 调用 `close_and_materialize()` 生成素材
     - 新建一个 session
   - 如果未超过阈值 → 复用当前 session
3. **无 open session：** 新建 session
4. 将 user_msg 和 ai_msg 的 `session_id` 设为当前 session.id
5. 更新 session 的 `message_count`（+2，user+assistant）和 `end_time`

**响应 data 新增字段：** 无变化（仍然返回 AI 回复文本）

但在返回前，如果因静默超时触发了旧 session 封闭并生成了素材，需要在响应中附带通知信息：

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

> **注意：** `meta` 字段仅在有素材生成时附带。需要修改 `success()` 的返回方式，或者单独在 router 层构造响应。建议在 router 层直接构造，不改动全局 `success()`：

```python
result = {"code": 0, "data": reply, "message": "ok"}
if material_generated:
    result["meta"] = {"materialGenerated": True, "materialId": material_id}
return result
```

### 3.2 新增 `POST /api/chat/close-session` 🔒

**文件：** `app/chat/router.py`

**功能：** 用户离开聊天页时，前端主动调用此接口封闭当前 open 的 session。

**请求 Body：** 无

**响应 data：**

```json
{
  "sessionClosed": true,
  "materialGenerated": true,
  "materialId": "uuid-xxx"
}
```

- 如果没有 open session → `{"sessionClosed": false, "materialGenerated": false, "materialId": null}`
- 如果 open session 的消息轮数不够 → `{"sessionClosed": true, "materialGenerated": false, "materialId": null}`
- 如果用户关闭了 chat_material_enabled → `{"sessionClosed": true, "materialGenerated": false, "materialId": null}`

**CamelCase 响应 Schema：**

```python
class CloseSessionOut(CamelModel):
    session_closed: bool
    material_generated: bool
    material_id: Optional[str] = None
```

### 3.3 新增 `GET /api/chat/session/{session_id}/messages` 🔒

**文件：** `app/chat/router.py`

**功能：** 前端素材卡片「展开对话」时获取原始对话记录。

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

**Schema：**

```python
class ChatSessionOut(CamelModel):
    id: str
    title: str
    summary: str
    start_time: int
    end_time: Optional[int] = None
    message_count: int
    mood: str
    mood_emoji: str

class ChatMessageOut(CamelModel):
    role: str
    content: str
    timestamp: int

class SessionMessagesOut(CamelModel):
    session: ChatSessionOut
    messages: List[ChatMessageOut]
```

**权限校验：** 确认 session 属于 current_user。

### 3.4 修改 `GET /api/user/settings` 和 `POST /api/user/settings`

**文件：** `app/user/router.py` + `app/user/schemas.py` + `app/user/service.py`

**新增返回字段（GET）：**

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

**新增请求字段（POST）：**

| 字段 | 类型 | 说明 |
|------|------|------|
| chat_material_enabled | bool | 对话自动转素材开关 |
| chat_silence_threshold | int | 静默阈值（分钟，15~120） |
| chat_material_toast | bool | toast 提示开关 |
| chat_min_rounds | int | 最小轮数（1~20） |

### 3.5 修改 `GET /api/materials` — 支持 chat 类型

**文件：** `app/material/service.py` + `app/material/schemas.py`

确保 `material_to_dict()` 函数输出新增字段：

```python
def material_to_dict(m: RawMaterial) -> dict:
    result = {
        "id": m.id,
        "user_id": m.user_id,
        "type": m.type,
        "content": m.content,
        "media_url": m.media_url or "",
        "thumbnail_url": m.thumbnail_url or "",
        "location": _decode(m.location, {}),
        "emotion": _decode(m.emotion, {}),
        "tags": _decode(m.tags, []),
        "date": m.date,
        "created_at": m.created_at,
        # 新增 chat 专属字段
        "chat_session_id": m.chat_session_id or None,
        "start_time": m.start_time or None,
        "end_time": m.end_time or None,
    }
    return result
```

**更新 `MaterialOut` Schema：**

```python
class MaterialOut(CamelModel):
    id: str
    user_id: str
    type: str
    content: str
    media_url: str
    thumbnail_url: str
    location: dict
    emotion: dict
    tags: list
    date: str
    created_at: int
    # 新增
    chat_session_id: Optional[str] = None
    start_time: Optional[int] = None
    end_time: Optional[int] = None
```

### 3.6 修改 `POST /api/diaries/generate` — 纳入 chat 素材

**文件：** `app/diary/service.py`

在 `generate_diary()` 函数的 `parts` 构建循环中新增：

```python
elif m.type == "chat" and m.content:
    time_range = ""
    if m.start_time and m.end_time:
        from datetime import datetime
        s = datetime.fromtimestamp(m.start_time / 1000).strftime("%H:%M")
        e = datetime.fromtimestamp(m.end_time / 1000).strftime("%H:%M")
        time_range = f"({s}~{e}) "
    parts.append(f"[对话记录] {time_range}{m.content}")
```

### 3.7 新增 AI 方法：`summarize_chat_session`

**文件：** `app/ai/minimax_client.py`

在 `MiniMaxClient` 类中新增方法：

```python
async def summarize_chat_session(self, messages: list) -> dict:
    """将一段对话概括为素材标题 + 摘要 + 情绪 + 标签"""
    if self.mock:
        return {
            "title": "和 AI 的一段对话",
            "summary": "用户和 AI 聊了一段有趣的对话，讨论了日常生活中的各种话题。",
            "mood": "平静",
            "mood_emoji": "😌",
            "tags": ["日常", "对话"]
        }
    
    conversation = "\n".join([
        f"{'用户' if m['role']=='user' else 'AI'}: {m['content']}"
        for m in messages
    ])
    
    system_prompt = """你是一个对话分析助手。请分析以下对话内容，提取结构化信息。
必须返回严格的 JSON 格式，不要包含任何其他文字：
{
  "title": "简短标题（10字以内，概括对话主题）",
  "summary": "2~3句话的摘要，描述对话的主要内容",
  "mood": "情绪标签（开心/难过/平静/吐槽/焦虑/兴奋/感动/无聊/困惑/释然）",
  "mood_emoji": "对应的emoji（一个）",
  "tags": ["话题标签1", "话题标签2"]
}"""
    
    user_prompt = f"对话内容：\n{conversation}"
    
    result_text = await self.chat_completion(
        [{"role": "user", "content": user_prompt}],
        system_prompt=system_prompt
    )
    
    import json
    try:
        return json.loads(result_text)
    except json.JSONDecodeError:
        return {
            "title": "对话记录",
            "summary": conversation[:200],
            "mood": "平静",
            "mood_emoji": "😐",
            "tags": ["对话"]
        }
```

---

## 四、核心服务函数

### 4.1 `close_and_materialize()` — 封闭对话段并生成素材

**文件：** `app/chat/service.py`（新建）

```python
import json
import time
from uuid import uuid4
from typing import Optional

from sqlalchemy.orm import Session

from app.models.chat import ChatMessage, ChatSession
from app.models.material import RawMaterial
from app.models.user import UserSettings


def _now_ms() -> int:
    return int(time.time() * 1000)

def _uuid() -> str:
    return str(uuid4())


async def close_and_materialize(
    db: Session,
    session: ChatSession,
    settings: UserSettings,
) -> Optional[RawMaterial]:
    """封闭对话段并生成素材。返回生成的素材，或 None（不满足条件）。"""
    
    # 1. 封闭 session
    session.status = "closed"
    session.end_time = session.end_time or _now_ms()
    
    # 2. 检查是否开启
    if not getattr(settings, 'chat_material_enabled', True):
        db.commit()
        return None
    
    # 3. 检查最小轮数（chat_min_rounds 指 user 消息数，message_count 是总数）
    min_rounds = getattr(settings, 'chat_min_rounds', 3)
    user_msg_count = session.message_count // 2  # user+assistant 各算一条
    if user_msg_count < min_rounds:
        db.commit()
        return None
    
    # 4. 获取该 session 的所有消息
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.timestamp)
        .all()
    )
    
    if not messages:
        db.commit()
        return None
    
    msg_list = [{"role": m.role, "content": m.content} for m in messages]
    
    # 5. 调用 AI 生成摘要
    from app.ai.minimax_client import get_minimax_client
    client = get_minimax_client()
    result = await client.summarize_chat_session(msg_list)
    
    # 6. 回填 session
    session.title = result.get("title", "对话记录")
    session.summary = result.get("summary", "")
    session.mood = result.get("mood", "平静")
    session.mood_emoji = result.get("mood_emoji", "😐")
    session.topic_tags = json.dumps(result.get("tags", []), ensure_ascii=False)
    
    # 7. 创建素材
    material = RawMaterial(
        id=_uuid(),
        user_id=session.user_id,
        type="chat",
        content=result.get("summary", ""),
        chat_session_id=session.id,
        start_time=session.start_time,
        end_time=session.end_time,
        emotion=json.dumps({
            "label": result.get("mood", "平静"),
            "score": 0.8,
            "emoji": result.get("mood_emoji", "😐"),
        }, ensure_ascii=False),
        tags=json.dumps(result.get("tags", []), ensure_ascii=False),
        date=session.date,
        created_at=session.start_time,
    )
    db.add(material)
    
    # 8. 回填 session.material_id
    session.material_id = material.id
    db.commit()
    
    return material


def get_or_create_session(
    db: Session,
    user_id: str,
    now_ms: int,
    silence_threshold_min: int = 30,
) -> tuple:
    """
    获取或创建当前 open 的 session。
    返回 (session, old_session_to_close_or_None)
    """
    from datetime import datetime
    
    open_session = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == user_id, ChatSession.status == "open")
        .first()
    )
    
    if open_session:
        # 检查是否超过静默阈值
        last_time = open_session.end_time or open_session.start_time
        silence_ms = silence_threshold_min * 60 * 1000
        
        if (now_ms - last_time) > silence_ms:
            # 超时，需要封闭旧 session 并创建新的
            old_session = open_session
            today = datetime.fromtimestamp(now_ms / 1000).strftime("%Y-%m-%d")
            new_session = ChatSession(
                id=_uuid(),
                user_id=user_id,
                status="open",
                start_time=now_ms,
                end_time=now_ms,
                message_count=0,
                date=today,
                created_at=now_ms,
            )
            db.add(new_session)
            db.flush()
            return new_session, old_session
        else:
            # 未超时，复用
            return open_session, None
    else:
        # 无 open session，新建
        today = datetime.fromtimestamp(now_ms / 1000).strftime("%Y-%m-%d")
        new_session = ChatSession(
            id=_uuid(),
            user_id=user_id,
            status="open",
            start_time=now_ms,
            end_time=now_ms,
            message_count=0,
            date=today,
            created_at=now_ms,
        )
        db.add(new_session)
        db.flush()
        return new_session, None
```

---

## 五、需要修改的文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `app/models/chat.py` | 修改 | 新增 ChatSession 模型 + ChatMessage 加 session_id |
| `app/models/material.py` | 修改 | 新增 chat_session_id / start_time / end_time |
| `app/models/user.py` | 修改 | UserSettings 新增 4 个 chat 相关字段 |
| `app/chat/router.py` | 修改 | 集成 session 管理 + 新增 2 个接口 |
| `app/chat/service.py` | 新建 | close_and_materialize + get_or_create_session |
| `app/chat/schemas.py` | 新建 | CloseSessionOut, ChatSessionOut 等 |
| `app/user/schemas.py` | 修改 | SettingsOut + UpdateSettingsRequest 新增字段 |
| `app/user/service.py` | 修改 | get_settings / update_settings 处理新字段 |
| `app/material/service.py` | 修改 | material_to_dict 输出新字段 |
| `app/material/schemas.py` | 修改 | MaterialOut 新增可选字段 |
| `app/diary/service.py` | 修改 | generate_diary 纳入 chat 素材 |
| `app/ai/minimax_client.py` | 修改 | 新增 summarize_chat_session 方法 |
| `scripts/seed.py` | 修改 | 重建数据库时包含新表 |

---

## 六、测试要求

修改完成后，运行测试确认不破坏已有功能：

```bash
source venv/bin/activate && pytest tests/ -v
```

如果现有测试因数据库 schema 变更而失败，需要同步更新 `tests/conftest.py` 中的数据库初始化逻辑。

新增接口需要手动验证（Swagger 或 curl）。

---

## 七、文档更新（必须）

完成代码后，必须更新以下文档：

### 7.1 `docs/API-DOCS.md`

1. 在 §8 AI 对话模块中：
   - 更新 `POST /api/chat` 的说明（新增 session 管理逻辑 + meta 字段）
   - 新增 `POST /api/chat/close-session` 接口文档
   - 新增 `GET /api/chat/session/{session_id}/messages` 接口文档

2. 在 §2 用户模块中：
   - 更新 `GET /api/user/settings` 和 `POST /api/user/settings` 的字段列表

3. 在 §3 素材模块中：
   - 更新 `POST /api/materials` 的 type 说明（新增 "chat"）
   - 更新 `GET /api/materials` 的响应字段（新增 chatSessionId / startTime / endTime）

4. 在 §4 日记模块中：
   - 更新 `POST /api/diaries/generate` 说明（现在包含 chat 类型素材）

5. 更新接口汇总表（新增 2 个接口，总数变为 74）

6. 更新 MiniMax AI 接口一览（新增 summarize_chat_session）

### 7.2 `docs/ONBOARDING.md`

1. 在 §四 项目结构中：
   - `app/chat/` 注释更新为 `💬 对话模块（含对话段管理 + 自动转素材）`
   - models 下新增 `chat.py` 说明 ChatSession

2. 在 §十一（常见报错）后，可选新增一条关于 session 的说明

### 7.3 `docs/COOKBOOK.md`

- 在 §四 调用 MiniMax AI 的示例列表中新增 `summarize_chat_session` 示例

### 7.4 `CLAUDE.md`（项目根目录）

- 数据模型列表新增 ChatSession
- 接口总数更新

### 7.5 `README.md`（如果有相关描述需要更新）

---

## 八、接口契约（前后端对齐用）

以下是前端会调用的精确接口格式，**不能改变**：

### POST /api/chat（已有，修改响应）

```
Request:  { "message": "string" }
Response: { "code": 0, "data": "AI回复文本", "message": "ok", "meta": {"materialGenerated": bool, "materialId": "string|null"} }
```

`meta` 仅在触发了旧 session 封闭时附带。无触发时不含 `meta` 字段。

### POST /api/chat/close-session（新增）

```
Request:  无 body
Response: { "code": 0, "data": {"sessionClosed": bool, "materialGenerated": bool, "materialId": "string|null"}, "message": "ok" }
```

### GET /api/chat/session/{session_id}/messages（新增）

```
Response: {
  "code": 0,
  "data": {
    "session": {
      "id": "string",
      "title": "string",
      "summary": "string",
      "startTime": number,
      "endTime": number|null,
      "messageCount": number,
      "mood": "string",
      "moodEmoji": "string"
    },
    "messages": [
      {"role": "user|assistant", "content": "string", "timestamp": number}
    ]
  },
  "message": "ok"
}
```

### GET /api/user/settings（修改，新增字段）

```
Response data 新增:
  "chatMaterialEnabled": bool,
  "chatSilenceThreshold": number,
  "chatMaterialToast": bool,
  "chatMinRounds": number
```

### POST /api/user/settings（修改，新增字段）

```
Request body 新增可选字段:
  "chat_material_enabled": bool,
  "chat_silence_threshold": number,
  "chat_material_toast": bool,
  "chat_min_rounds": number
```

### GET /api/materials（修改，chat 类型素材新增字段）

```
当 type="chat" 时，响应多出:
  "chatSessionId": "string",
  "startTime": number,
  "endTime": number
```

---

## 九、注意事项

1. **不要修改** `app/main.py`、`app/config.py`、`app/database.py`、`app/dependencies.py`、`app/response.py`
2. `minimax_client.py` 只**新增**方法，不修改已有方法
3. 所有新字段使用 `default` 值，确保向后兼容
4. JSON 字段存取统一使用 `json.dumps(ensure_ascii=False)` 和 `json.loads`
5. 时间戳统一用毫秒 BigInteger
6. 先删除 data.db 再跑 seed.py 重建数据库
7. 完成后 `git add -A && git commit -m "feat(chat): 对话自动转素材 — session管理 + AI摘要 + 素材生成" && git push`

---

*创建时间：2026-04-02 | 作者：BB*
