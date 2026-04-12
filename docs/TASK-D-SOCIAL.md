# 任务书 D — 社交 + AI 对话

> **负责人：** 队友 D
>
> **模块：** app/social/（社交匹配）、app/chat/（AI 对话）
>
> **前置阅读：** [ONBOARDING.md](./ONBOARDING.md) → [COOKBOOK.md](./COOKBOOK.md) → 本文档
>
> **分支名：** `feat/social`

---

## 你负责的文件

| 文件 | 操作 |
|------|------|
| `app/social/router.py` | 已完成（路由已薄化，调用 `service.py`） |
| `app/social/service.py` | 已完成（已承载主要社交业务逻辑） |
| `app/social/schemas.py` | 已完成（含 `SendMessageBody` 等 schema） |
| `app/chat/router.py` | 已完成（路由已薄化，调用 `service.py`） |
| `app/chat/service.py` | 已完成（AI 对话/历史逻辑已抽离） |
| `app/chat/schemas.py` | 已完成（统一 chat schema 定义） |
| `tests/test_social.py` | 已完成（补齐社交链路与异常场景测试） |
| `tests/test_ai.py` | 已验证（覆盖 AI 对话与历史能力） |

## 不要碰的文件

- 公共文件（main.py、config.py 等）
- `app/ai/minimax_client.py`（只调用不修改）
- `app/models/*`（改前沟通）
- 其他模块

---

## 接口清单

### 社交模块（8 个接口）

#### GET /api/social/matches — 已匹配列表

**当前状态：** ✅ 已实现（路由调用 `service.match_to_out()` 等服务层逻辑）

查询 status="accepted" 的匹配记录，JOIN 用户表获取对方昵称、头像、学校。返回裸数组。

**你需要做的：** 测试返回格式。service.match_to_out 负责格式转换，检查当对方用户不存在时是否会报错。

---

#### POST /api/social/match-requests — 发送匹配请求

**当前状态：** ✅ 已实现（路由调用 `service.create_match_request()`）

**核心逻辑：**
```
1. 检查 toUid 不为空
2. 检查目标用户存在
3. 检查不存在重复的匹配请求
4. 创建 Match 记录，status="pending"，match_type="long_term"
```

**你需要做的：** 测试重复请求拦截。测试向不存在用户发送请求。

---

#### POST /api/social/match-requests/{request_id}/respond — 响应匹配请求

**当前状态：** ✅ 已实现

只有 target_id（被申请方）才能响应。accept=true → status="accepted"，accept=false → status="rejected"。

---

#### GET /api/social/messages/{match_id} — 匹配消息列表

**当前状态：** ✅ 已实现（路由调用 `service.get_messages()`）

支持游标分页（before 参数），返回裸数组。

**当前说明：** 发送消息接口已补齐，消息列表接口保留游标分页能力。

---

#### GET /api/social/matches/{match_id}/report — 匹配报告（AI）

**当前状态：** ✅ 已实现（路由调用 `service.get_match_report()`，首次生成后缓存）

调用 minimax_client.generate_match_report 生成报告，缓存到 Match.match_report 字段。

**你需要做的：** 测试 Mock 模式返回。检查当用户没有 portrait 时的兜底逻辑。

---

#### POST /api/social/buddy — 申请搭子

**当前状态：** ✅ 已实现

创建 match_type="buddy" 的匹配记录。

---

#### POST /api/social/buddy/{request_id}/respond — 响应搭子申请

**当前状态：** ✅ 已实现

---

### 已新增接口

#### POST /api/social/messages/{match_id} — 发送消息

该接口已在仓库中完成，当前行为如下：

**请求 Body：**
```json
{
  "content": "你好！"
}
```

**当前逻辑：**
```python
@router.post("/messages/{match_id}", summary="发送消息")
def send_message(match_id, body, current_user, db):
    # 1. 检查匹配存在且 status="accepted"
    # 2. 检查当前用户是匹配双方之一
    # 3. 创建 SocialMessage 记录
    # 4. 返回消息对象
```

**参考 models：**
```python
# app/models/social.py 中的 SocialMessage
class SocialMessage(Base):
    id = Column(String, primary_key=True)
    match_id = Column(String, nullable=False)
    from_uid = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    timestamp = Column(BigInteger, nullable=False)
```

---

### AI 对话模块（2 个接口）

#### POST /api/chat — AI 对话

**当前状态：** ✅ 已实现（路由调用 `service.send_message()`）

**当前实现逻辑：**
```
1. 保存用户消息到 chat_messages 表（role="user"）
2. 取最近 20 条历史消息
3. 调用 minimax_client.chat_completion（非流式）
4. 保存 AI 回复到 chat_messages 表（role="assistant"）
5. 返回 AI 回复文本
```

**你需要做的：**

当前返回的是纯文本（非流式）。前端用模拟打字机效果渲染。如果后续需要真正的流式（SSE），需要改造为：

```python
from fastapi.responses import StreamingResponse

@router.post("/stream", summary="AI 对话（流式 SSE）")
async def ai_chat_stream(body, current_user, db):
    client = get_minimax_client()

    async def generate():
        async for chunk in client.stream_chat(messages, system_prompt):
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

minimax_client 已经有 `stream_chat` 方法了，只是没有被任何路由接入。

> **目前先不改**，除非前辈说要做 SSE。

---

#### GET /api/chat/history — 聊天历史

**当前状态：** ✅ 已实现

返回 `{"items": [...], "total": N}`。

---

#### chat/service.py — 已完成

当前 `chat/service.py` 已完成抽离，chat 逻辑不再直接堆在 router.py 里。

**当前包含：**

```python
# app/chat/service.py

async def send_message(db, user_id, message):
    """保存用户消息 + 调 AI + 保存回复 + 返回回复文本"""
    ...

def get_history(db, user_id, limit=20):
    """获取聊天历史"""
    ...
```

---

### social/service.py — 已完成补充

当前已不再只有 2 个工具函数，而是承载了主要社交业务逻辑：

```python
def get_other_user_id(match, current_user_id) -> str
def match_to_out(match, current_user_id, db) -> dict
def list_matches(db, user_id) -> list[dict]
def create_match_request(db, user_id, target_id) -> Match
def get_messages(db, user_id, match_id, limit, before) -> list[SocialMessage]
def send_message(db, user_id, match_id, content) -> SocialMessage
async def get_match_report(db, user_id, match_id) -> dict
def respond_match_request(db, user_id, request_id, accept) -> None
def apply_buddy(db, user_id, target_id, reason) -> Match
def respond_buddy(db, user_id, request_id, accept) -> None
```

大量业务逻辑直接写在 router.py 里。**建议逐步抽取到 service.py**：

1. `list_matches(db, user_id)` — 查询已匹配列表
2. `create_match_request(db, user_id, target_id)` — 创建匹配请求
3. `respond_match_request(db, user_id, request_id, accept)` — 响应请求
4. `get_messages(db, user_id, match_id, limit, before)` — 获取消息
5. `send_message(db, user_id, match_id, content)` — **新增：发送消息**
6. `get_match_report(db, user_id, match_id)` — 获取匹配报告
7. `apply_buddy(db, user_id, target_id, reason)` — 申请搭子

当前仓库状态已按建议完成重构，router 主要负责参数解析与响应包装，service 负责业务逻辑。按优先级总结如下：

- **已完成：** 新增发送消息接口
- **已完成：** 把 router 逻辑抽到 service
- **已完成：** chat service 层抽取

---

## 工作重点

1. **新增发送消息接口**（最重要，没这个接口社交功能不完整）
2. **测试社交完整链路**：发送匹配请求 → 对方接受 → 发送消息 → 查看消息 → 查看匹配报告
3. **测试 AI 对话**：发送消息 → 收到回复 → 查看历史
4. **重构 service 层**（如果时间允许）

## 开发步骤（成员 D）

- [x] 第一步：补齐 `POST /api/social/messages/{match_id}` 发送消息接口
  - 已完成 `SendMessageBody` 请求体定义
  - 已完成 `social/service.py` 中 `send_message(db, user_id, match_id, content)` 业务逻辑
  - 已完成 `social/router.py` 路由接入，当前支持：
    - 校验匹配存在
    - 校验当前用户属于该匹配
    - 校验匹配状态为 `accepted`
    - 校验消息内容非空
    - 创建并返回 `SocialMessage`
  - 已完成发送消息接口基础用例验证（`test_send_message_after_match_accepted`）
- [x] 第二步：补充 `tests/test_social.py`
  - 覆盖发送消息成功场景
  - 覆盖未接受匹配禁止发送消息
  - 覆盖非匹配双方禁止发消息
  - 覆盖重复匹配请求和不存在用户场景
- [x] 第三步：补齐社交完整链路自测
  - 发送匹配请求
  - 接受请求
  - 发送消息
  - 获取消息列表
  - 获取匹配报告
- [x] 第四步：整理 `chat/service.py` 与 `chat/schemas.py`
  - 抽离 AI 对话逻辑
  - 统一 schema 定义
- [x] 第五步：按时间决定是否继续重构 `social/service.py`
  - 将更多业务逻辑从 `router.py` 抽离到 `service.py`

## 与其他模块的依赖

| 依赖方向 | 说明 |
|----------|------|
| **你 → 用户模块** | 匹配列表需要 JOIN users 表获取对方信息 |
| **你 → AI 客户端** | 对话和匹配报告调用 minimax_client |
| **你 → user_profiles** | 匹配报告需要读用户画像（队友 A 负责） |

## 验收标准

- [x] 9+ 个接口在 Swagger 中全部可调通（含新增的发送消息）
- [x] `pytest tests/test_social.py -v` 全部通过
- [x] 社交完整链路：匹配 → 接受 → 发消息 → 查消息
- [x] AI 对话能跑通（Mock 模式）
- [x] 搭子申请完整链路：申请 → 接受/拒绝

## 预估工作量

约 2-3 天。
- 发送消息接口：0.5 天
- 测试所有接口：1 天
- service 层重构：1 天（可选）

---

*参考：社交 router 的代码风格参考自身，CRUD 参考 material/service.py | AI 对话参考 COOKBOOK.md*
