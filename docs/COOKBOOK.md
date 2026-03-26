# 日迹 App 后端 — 代码模板 & 规范

> **面向：** 所有后端开发组员
>
> **用法：** 写代码时对照本文档，直接复制模板改。

---

## 一、写一个新接口的完整步骤

假设你要实现「创建待办」接口 `POST /api/study/todos`。

### 第 1 步：在 schemas.py 定义请求和响应

```python
# app/study/schemas.py

from typing import Optional
from pydantic import BaseModel
from app.serializers import CamelModel    # 响应用 CamelModel


# 请求 Schema（用 BaseModel）
class CreateTodoRequest(BaseModel):
    content: str                          # 必填
    priority: Optional[str] = "medium"    # 可选，有默认值


# 响应 Schema（用 CamelModel → 自动 camelCase）
class TodoOut(CamelModel):
    id: str
    content: str
    completed: bool
    priority: str
    created_at: int                       # 返回给前端时自动变成 createdAt
```

### 第 2 步：在 service.py 写业务逻辑

```python
# app/study/service.py

import time
from uuid import uuid4
from sqlalchemy.orm import Session
from app.models.study import Todo
from app.response import ApiException, NOT_FOUND


def create_todo(db: Session, user_id: str, data: dict) -> dict:
    """创建待办"""
    todo = Todo(
        id=str(uuid4()),
        user_id=user_id,
        content=data["content"],
        completed=False,
        priority=data.get("priority", "medium"),
        created_at=int(time.time() * 1000),
    )
    db.add(todo)
    db.commit()
    db.refresh(todo)

    return {
        "id": todo.id,
        "content": todo.content,
        "completed": todo.completed,
        "priority": todo.priority,
        "created_at": todo.created_at,
    }
```

### 第 3 步：在 router.py 注册路由

```python
# app/study/router.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.response import success
from app.study.schemas import CreateTodoRequest, TodoOut
from app.study import service

router = APIRouter(prefix="/study", tags=["学习"])


@router.post("/todos", summary="创建待办")
def create_todo(
    req: CreateTodoRequest,                          # 自动解析 JSON body
    current_user: User = Depends(get_current_user),  # 自动验证 JWT
    db: Session = Depends(get_db),                   # 自动获取数据库
):
    data = req.model_dump()                          # Pydantic 对象 → dict
    result = service.create_todo(db, current_user.id, data)
    out = TodoOut(**result)                           # dict → CamelModel
    return success(out.model_dump(by_alias=True))     # 转 camelCase + 包装响应
```

---

## 二、CRUD 模板（照着改就行）

以 `material/` 模块为参考，这是项目中最完整的实现。

### 创建（Create）

```python
def create_item(db: Session, user_id: str, data: dict) -> dict:
    import time
    from uuid import uuid4

    item = MyModel(
        id=str(uuid4()),
        user_id=user_id,
        name=data["name"],
        created_at=int(time.time() * 1000),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item_to_dict(item)
```

### 查列表（Read List）

```python
def list_items(db: Session, user_id: str, page: int = 1, page_size: int = 10) -> dict:
    query = db.query(MyModel).filter(MyModel.user_id == user_id)
    total = query.count()
    items = (
        query
        .order_by(MyModel.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [item_to_dict(i) for i in items],
        "total": total,
    }
```

### 查单条（Read One）

```python
def get_item(db: Session, user_id: str, item_id: str) -> dict:
    item = db.query(MyModel).filter(
        MyModel.id == item_id,
        MyModel.user_id == user_id,
    ).first()
    if not item:
        raise ApiException(code=NOT_FOUND, message="资源不存在", status_code=404)
    return item_to_dict(item)
```

### 更新（Update）

```python
def update_item(db: Session, user_id: str, item_id: str, data: dict) -> dict:
    import time

    item = db.query(MyModel).filter(
        MyModel.id == item_id,
        MyModel.user_id == user_id,
    ).first()
    if not item:
        raise ApiException(code=NOT_FOUND, message="资源不存在", status_code=404)

    # 只更新传了的字段
    for key, value in data.items():
        if hasattr(item, key) and value is not None:
            setattr(item, key, value)

    item.updated_at = int(time.time() * 1000)
    db.commit()
    db.refresh(item)
    return item_to_dict(item)
```

### 删除（Delete）

```python
def delete_item(db: Session, user_id: str, item_id: str) -> None:
    item = db.query(MyModel).filter(
        MyModel.id == item_id,
        MyModel.user_id == user_id,
    ).first()
    if not item:
        raise ApiException(code=NOT_FOUND, message="资源不存在", status_code=404)
    db.delete(item)
    db.commit()
```

### 模型 → dict 转换函数

每个模块都需要一个，把数据库对象转成 dict：

```python
import json

def _encode(obj) -> str:
    """Python 对象 → JSON 字符串（存数据库用）"""
    return json.dumps(obj, ensure_ascii=False) if obj else ""

def _decode(s: str, default=None):
    """JSON 字符串 → Python 对象（从数据库读用）"""
    if default is None:
        default = []
    try:
        return json.loads(s) if s else default
    except Exception:
        return default

def item_to_dict(item: MyModel) -> dict:
    return {
        "id": item.id,
        "user_id": item.user_id,
        "name": item.name,
        "tags": _decode(item.tags, []),       # JSON 字段要解码
        "created_at": item.created_at,
    }
```

---

## 三、代码规范

### 3.1 响应格式

所有接口必须用 `success()` 包装返回：

```python
from app.response import success

# 返回对象
return success({"id": "xxx", "name": "test"})

# 返回裸数组
return success([item1, item2])

# 返回 null（删除操作）
return success(None)
```

### 3.2 错误处理

抛出 `ApiException`，框架自动转成 JSON 错误响应：

```python
from app.response import ApiException, NOT_FOUND, PARAM_ERROR, BUSINESS_ERROR

# 资源不存在
raise ApiException(code=NOT_FOUND, message="日记不存在", status_code=404)

# 参数错误
raise ApiException(code=PARAM_ERROR, message="日期格式不正确", status_code=400)

# 业务错误
raise ApiException(code=BUSINESS_ERROR, message="修改次数已达上限", status_code=400)
```

常用错误码（定义在 `response.py` 中）：

| 常量 | 值 | 用途 |
|------|------|------|
| NOT_FOUND | 40202 | 资源不存在 |
| PARAM_ERROR | 40102 | 参数错误 |
| PARAM_INVALID | 40101 | 参数无效 |
| BUSINESS_ERROR | 40201 | 业务逻辑错误 |
| AI_SERVICE_ERROR | 50101 | AI 服务调用失败 |

### 3.3 CamelCase 输出

响应 Schema 继承 `CamelModel`（定义在 `serializers.py`），自动把 `snake_case` 转成 `camelCase`：

```python
from app.serializers import CamelModel

class DiaryOut(CamelModel):
    user_id: str        # → 返回给前端时变成 userId
    created_at: int     # → 返回给前端时变成 createdAt
```

使用时：

```python
out = DiaryOut(**some_dict)
return success(out.model_dump(by_alias=True))   # by_alias=True 才会用 camelCase
```

### 3.4 JSON 字段存取

SQLite 没有原生 JSON 类型，我们用 TEXT 存 JSON 字符串：

```python
# 存的时候：Python 对象 → JSON 字符串
item.tags = json.dumps(["校园", "美食"], ensure_ascii=False)
item.emotion = json.dumps({"label": "开心", "score": 0.8}, ensure_ascii=False)

# 读的时候：JSON 字符串 → Python 对象
tags = json.loads(item.tags) if item.tags else []
emotion = json.loads(item.emotion) if item.emotion else {}
```

项目里统一用 `_encode()` 和 `_decode()` 工具函数（参考 `material/service.py`）。

### 3.5 时间戳

统一用 **Unix 毫秒时间戳**：

```python
import time
now = int(time.time() * 1000)   # 当前时间戳（毫秒）
```

### 3.6 UUID

统一用 uuid4 生成 ID：

```python
from uuid import uuid4
new_id = str(uuid4())
```

---

## 四、调用 MiniMax AI

AI 功能封装在 `app/ai/minimax_client.py`，所有模块共用。

### 基本用法

```python
from app.ai.minimax_client import get_minimax_client

client = get_minimax_client()

# 文本对话（非流式，返回完整文本）
reply = await client.chat_completion(
    messages=[{"role": "user", "content": "你好"}],
    system_prompt="你是一个友善的助手",
)

# 情绪提取（返回 dict）
emotion = await client.extract_emotion("今天天气真好，心情不错！")
# → {"label": "开心", "score": 0.88, "emoji": "😊"}

# 文字润色（返回 string）
polished = await client.polish_text("吃了个饭", "文艺")
# → "在某个平凡而特别的午后，吃了个饭..."

# 日记生成（返回 dict）
diary = await client.generate_diary("今天去了图书馆，吃了食堂", weather="晴")
# → {"title": "...", "content": "...", "emotion_summary": {...}}

# 信息提取（返回 dict）
info = await client.extract_info("和小明一起去了食堂，今天是他生日")
# → {"anniversaries": [...], "persons": [...], "preferences": [...]}

# 图片生成（返回 URL string）
url = await client.generate_image("一幅温暖的水彩插画")

# TTS 文字转语音（返回 bytes）
audio = await client.text_to_speech("你好世界", voice_id="female-shaonv")

# 用户画像（返回 dict）
portrait = await client.generate_portrait("日记摘要...", "聊天摘要...")

# 匹配报告（返回 string）
report = await client.generate_match_report(portrait_a, portrait_b)
```

### Mock 模式

`MINIMAX_MOCK=true` 时，所有方法返回预设假数据。你可以通过 `client.mock` 判断：

```python
if client.mock:
    # 返回假数据
else:
    # 调真实 API
```

### 注意：AI 方法是 async 的

调用 AI 的路由函数需要加 `async`：

```python
@router.post("/extract")
async def extract_info(         # ← 注意这里是 async def
    ...
):
    result = await service.extract_info(...)    # ← await
    return success(result)
```

对应的 service 函数也要是 async：

```python
async def extract_info(db, user_id, diary_id):   # ← async def
    client = get_minimax_client()
    result = await client.extract_info(content)    # ← await
    return result
```

---

## 五、扩展指南

### 添加新的数据库字段

1. 在 `app/models/xxx.py` 中给模型类加字段
2. 删掉 `data.db`，重新跑 `python scripts/seed.py`

> 开发阶段直接删库重建最简单。生产环境才用 Alembic 迁移。

### 添加新模块

1. 创建文件夹 `app/newmodule/`
2. 创建 `__init__.py`（空文件）、`router.py`、`schemas.py`、`service.py`
3. 在 `app/main.py` 注册路由：

```python
from app.newmodule.router import router as newmodule_router
app.include_router(newmodule_router, prefix="/api")
```

### 添加新的 AI 能力

在 `minimax_client.py` 的 `MiniMaxClient` 类中添加新方法。记得同时写 mock 分支和真实 API 分支。

---

## 六、最佳参考模块

| 你要做的 | 参考这个模块 | 文件 |
|----------|------------|------|
| CRUD 增删改查 | material/ | material/service.py |
| AI 调用 | diary/ | diary/service.py（generate_diary） |
| 裸数组返回 | anniversary/ | anniversary/router.py |
| 分页列表 | diary/ | diary/service.py（list_diaries） |
| CamelModel 使用 | material/ | material/schemas.py |

遇到不确定怎么写的，先看这些已有代码，照着改就行。

---

*最后更新：2026-03-26*
