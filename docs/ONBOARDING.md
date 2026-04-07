# 日迹 App 后端 — 新手入门指南

> **面向：** 所有后端开发组员
>
> **前置知识：** Python 基础语法
>
> **阅读顺序：** 本文档 → COOKBOOK.md（代码模板） → 你的任务书（TASK-X-xxx.md）

---

## 一、后端是什么？

前端（手机 App）是用户看到的界面，后端是「服务器上的程序」，负责：

1. **存数据** — 用户注册信息、日记内容、聊天记录等
2. **处理请求** — 前端发请求（比如「获取我的日记列表」），后端查数据库返回结果
3. **调用 AI** — 情绪分析、日记生成等，后端调用 MiniMax 的 API

前端和后端通过 **HTTP 请求** 通信，数据格式是 **JSON**。

---

## 二、FastAPI 是什么？

FastAPI 是一个 Python Web 框架，用来写后端接口。核心概念就三个：

### 1. 路由（Router）— 接口的地址

```python
@router.get("/diaries")          # 前端访问 GET /api/diaries 时触发这个函数
def list_diaries():
    return {"code": 0, "data": [...]}
```

`@router.get` / `@router.post` / `@router.put` / `@router.delete` 就是 HTTP 方法。

### 2. 请求参数 — 前端传什么

```python
# URL 里的参数
@router.get("/diaries/{diary_id}")      # diary_id 从 URL 中取
def get_diary(diary_id: str):
    ...

# Query 参数（?page=1&page_size=10）
@router.get("/diaries")
def list_diaries(page: int = 1, page_size: int = 10):
    ...

# Body 参数（JSON）
@router.post("/diaries/generate")
def generate_diary(body: GenerateDiaryRequest):   # 从 JSON body 自动解析
    ...
```

### 3. 依赖注入 — 自动获取数据库和当前用户

```python
from app.dependencies import get_current_user, get_db

@router.get("/profile")
def get_profile(
    current_user: User = Depends(get_current_user),  # 自动从 JWT token 获取当前用户
    db: Session = Depends(get_db),                    # 自动获取数据库连接
):
    # current_user 就是当前登录的用户对象
    # db 就是数据库连接，可以用来查询
    ...
```

你不需要自己写认证逻辑，加上 `Depends(get_current_user)` 就行了。

---

## 三、一个请求的完整流程

```
前端（App）                     后端（FastAPI）
  │                               │
  │  GET /api/diaries?page=1      │
  │ ─────────────────────────────→│
  │  Authorization: Bearer xxx    │
  │                               │
  │                    ┌──────────┴──────────┐
  │                    │  1. router.py       │ ← 接收请求，解析参数
  │                    │     ↓               │
  │                    │  2. dependencies.py │ ← 验证 JWT，获取当前用户
  │                    │     ↓               │
  │                    │  3. service.py      │ ← 业务逻辑：查数据库
  │                    │     ↓               │
  │                    │  4. models/*.py     │ ← 数据库表定义
  │                    │     ↓               │
  │                    │  5. schemas.py      │ ← 格式化响应（camelCase）
  │                    └──────────┬──────────┘
  │                               │
  │  {"code":0, "data":{...}}     │
  │ ←─────────────────────────────│
```

### 各层职责

| 文件 | 职责 | 类比 |
|------|------|------|
| **router.py** | 接收请求，调用 service，返回结果 | 前台接待 |
| **service.py** | 业务逻辑：增删改查、调用 AI | 后厨干活 |
| **schemas.py** | 定义请求和响应的数据格式 | 菜单 |
| **models/*.py** | 定义数据库表结构 | 仓库货架 |

---

## 四、项目结构

```
riji-backend/
├── app/                          # 核心代码
│   ├── main.py                   # 应用入口（注册路由、CORS、异常处理）⚠️ 不要改
│   ├── config.py                 # 配置（读 .env）⚠️ 不要改
│   ├── database.py               # 数据库连接 ⚠️ 不要改
│   ├── dependencies.py           # JWT 认证 + get_db ⚠️ 不要改
│   ├── response.py               # 统一响应格式 + 错误码 ⚠️ 不要改
│   ├── serializers.py            # CamelModel 基类 ⚠️ 不要改
│   │
│   ├── models/                   # 数据库模型 ⚠️ 谨慎修改（改了影响所有人）
│   │   ├── user.py               # users + user_settings + user_achievements 表
│   │   ├── user_profile.py       # user_profiles 表
│   │   ├── diary.py              # diaries 表
│   │   ├── material.py           # raw_materials 表
│   │   ├── anniversary.py        # anniversaries 表
│   │   ├── derivative.py         # diary_derivatives 表
│   │   ├── chat.py               # chat_messages 表 + chat_sessions 表（对话段管理）
│   │   ├── social.py             # matches + social_messages 表
│   │   └── study.py              # pomodoros + todos 表（已废弃）
│   │
│   ├── auth/                     # 认证模块 ⚠️ 不要改
│   ├── upload/                   # 文件上传 ⚠️ 不要改
│   ├── ai/                       # AI 功能（TTS、运势、MiniMax 客户端）
│   │   ├── minimax_client.py     # MiniMax API 封装 ⚠️ 不要改（只新增方法）
│   │   ├── router.py
│   │   └── schemas.py
│   │
│   ├── user/                     # 👤 用户模块 → 队友 A
│   ├── diary/                    # 📔 日记模块 → 队友 B
│   ├── material/                 # 📷 素材模块 → 队友 B
│   ├── derivative/               # 🎨 衍生内容 → 队友 C
│   ├── anniversary/              # 📅 纪念日 → 队友 C
│   ├── social/                   # 🤝 社交模块 → 队友 D
│   ├── chat/                     # 💬 对话模块（含对话段管理 + 自动转素材）
│   ├── plaza/                    # 🏫 广场模块 → 队友 E 🆕
│   ├── avatar/                   # 🤖 AI分身模块 → 队友 E 🆕
│   └── study/                    # 📚 学习模块（已废弃）
│
├── tests/                        # 测试
│   ├── conftest.py               # 测试配置（创建测试客户端）
│   ├── test_auth.py
│   ├── test_user.py
│   ├── test_diary.py
│   ├── test_material.py
│   ├── test_anniversary.py
│   ├── test_social.py
│   └── ...
│
├── alembic/                      # 数据库迁移（加字段/加表时用）
├── scripts/
│   └── seed.py                   # 种子数据（测试账号）
├── uploads/                      # 上传文件存储
├── data.db                       # SQLite 数据库文件
├── .env                          # 环境变量配置
├── .env.example                  # .env 模板
├── requirements.txt              # Python 依赖
└── docs/                         # 文档（你正在读的）
```

---

## 五、环境搭建（5 分钟）

### 1. 克隆仓库

```bash
git clone https://github.com/Qyjay/riji-backend.git
cd riji-backend
```

### 2. 创建虚拟环境 + 安装依赖

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

> **什么是虚拟环境？** 简单说就是给这个项目创建一个独立的 Python 环境，安装的库不会影响其他项目。每次打开终端都要先 `source venv/bin/activate`。

### 3. 配置环境变量

```bash
cp .env.example .env
```

打开 `.env`，把 `JWT_SECRET` 改成任意字符串（比如 `my-secret-123`）。其他不用改。

### 4. 初始化数据库 + 测试数据

```bash
# 基础测试数据（3 个用户 + 日记 + 番茄钟 + 待办）
python scripts/seed.py

# 广场+分身模块测试数据（10 个用户 + 15 帖子 + 评论/点赞/记忆/推荐/侧写全模块）
python scripts/seed_plaza_avatar.py
```

会创建测试账号：

**基础账号（密码 `123456`）：**

| 用户名 | 密码 | 学校 |
|--------|------|------|
| kylin | 123456 | 南开大学 |
| xiaolu | 123456 | 天津大学 |
| test | 123456 | 测试大学 |

**广场+分身测试账号（密码 `test123456`）：**

linxiaohan（南开）、zhoucheng（天大）、summer_z（北大）、wangfuai（清华）、liuyang_c（复旦）、chenmo（上交）、yuxin_r（浙大）、leomao（南大）、zhouqian（中大）、hanxiao（武大）

### 5. 启动服务

```bash
uvicorn app.main:app --reload --port 8000
```

`--reload` 表示修改代码后自动重启。

### 6. 测试

打开浏览器访问 http://localhost:8000/docs ，这就是 **Swagger 文档**——可以直接在网页上测试每个接口。

---

## 六、用 Swagger 测试接口

1. 打开 http://localhost:8000/docs
2. 先调 `POST /api/auth/login` 登录，拿到 token
3. 点页面右上角 **Authorize** 按钮，输入 `Bearer <你的token>`
4. 然后就可以测试任何接口了

---

## 七、SQLAlchemy 速查

SQLAlchemy 是 Python 的数据库工具。你不用写 SQL，用 Python 代码操作数据库。

### 查询（SELECT）

```python
# 查一条
user = db.query(User).filter(User.id == user_id).first()

# 查多条
diaries = db.query(Diary).filter(Diary.user_id == user_id).all()

# 条件查询 + 排序 + 分页
items = (
    db.query(Diary)
    .filter(Diary.user_id == user_id)        # WHERE
    .order_by(Diary.created_at.desc())        # ORDER BY
    .offset((page - 1) * page_size)           # 跳过
    .limit(page_size)                         # 取几条
    .all()
)

# 计数
total = db.query(Diary).filter(Diary.user_id == user_id).count()
```

### 新增（INSERT）

```python
from uuid import uuid4
import time

diary = Diary(
    id=str(uuid4()),
    user_id=user_id,
    content="今天天气真好",
    created_at=int(time.time() * 1000),
)
db.add(diary)
db.commit()
db.refresh(diary)   # 刷新，让 diary 对象获取数据库生成的值
```

### 更新（UPDATE）

```python
diary = db.query(Diary).filter(Diary.id == diary_id).first()
diary.content = "修改后的内容"
diary.updated_at = int(time.time() * 1000)
db.commit()
```

### 删除（DELETE）

```python
diary = db.query(Diary).filter(Diary.id == diary_id).first()
db.delete(diary)
db.commit()
```

---

## 八、Pydantic Schema 是什么？

Schema 就是「数据长什么样」的定义。两个用途：

### 1. 请求 Schema — 校验前端传来的数据

```python
from pydantic import BaseModel

class CreateTodoRequest(BaseModel):
    content: str                    # 必填，字符串
    priority: str = "medium"        # 可选，默认 "medium"
```

前端传 `{"content": "写作业"}` → 自动校验并转成 Python 对象。
前端传 `{}` → 自动报错「content 是必填的」。

### 2. 响应 Schema — 格式化返回给前端的数据

```python
from app.serializers import CamelModel

class TodoOut(CamelModel):          # 继承 CamelModel → 自动转 camelCase
    id: str
    content: str
    completed: bool
    priority: str
    created_at: int                 # Python 里写 snake_case
    # 返回给前端时自动变成 createdAt（camelCase）
```

---

## 九、跑测试

```bash
# 跑所有测试
python -m pytest tests/ -v

# 只跑某个模块的测试
python -m pytest tests/test_user.py -v

# 只跑某一个测试函数
python -m pytest tests/test_user.py::test_get_profile -v
```

`-v` 表示显示详细输出。全绿（PASSED）就是通过。

---

## 十、Git 协作规则

### 分支策略

每人从 `main` 创建自己的分支：

```bash
git checkout main
git pull
git checkout -b feat/user           # 队友 A
git checkout -b feat/diary-core     # 队友 B
git checkout -b feat/diary-ai       # 队友 C
git checkout -b feat/social         # 队友 D
git checkout -b feat/plaza-avatar   # 队友 E
```

### 日常工作流

```bash
# 1. 写代码...

# 2. 提交
git add .
git commit -m "feat(user): 实现获取成长数据接口"

# 3. 推送到远程
git push origin feat/user

# 4. 在 GitHub 上创建 Pull Request → main
```

### 铁律

- **只改自己模块的文件**（看你的任务书里「负责的文件」）
- **不要改 ⚠️ 标记的文件**（main.py、config.py、database.py 等）
- **改公共文件前先群里说一声**（models/、response.py 等）
- **每天至少提交一次**，避免最后一天合并冲突

---

## 十一、常见报错 & 解决

| 报错 | 原因 | 解决 |
|------|------|------|
| `ModuleNotFoundError: No module named 'xxx'` | 没有安装依赖 / 没激活虚拟环境 | `source venv/bin/activate && pip install -r requirements.txt` |
| `sqlalchemy.exc.OperationalError: no such table` | 数据库没初始化 | `python scripts/seed.py` |
| `401 Unauthorized` | 没传 token 或 token 过期 | 重新登录拿新 token |
| `422 Unprocessable Entity` | 请求参数格式错误 | 检查 JSON body 字段名和类型 |
| `500 Internal Server Error` | 代码有 bug | 看终端的报错信息（traceback），定位到具体行 |
| `ImportError: cannot import name 'xxx'` | 引用路径写错 | 对照已有模块检查 import 路径 |
| `Address already in use` | 端口 8000 被占用 | 换端口 `--port 8001` 或关掉占用的进程 |

---

## 十二、MiniMax AI Mock 模式

`.env` 中 `MINIMAX_MOCK=true`（默认）：所有 AI 接口返回预设的假数据，不调真实 API，不消耗额度。

开发时始终用 Mock。只有联调测试时才改成 `false`。

---

## 下一步

1. 阅读 [COOKBOOK.md](./COOKBOOK.md) — 学会怎么写代码
2. 阅读你的任务书（TASK-A/B/C/D-xxx.md）— 知道你要做什么
3. 阅读 [API-DOCS.md](./API-DOCS.md) — 查接口规范

有问题群里问，或者直接看已有模块的代码（`material/` 是最好的参考）。

---

*最后更新：2026-03-26*
