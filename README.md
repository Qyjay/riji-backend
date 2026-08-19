# 日迹 App — 后端 API

大学生 AI 生活伙伴 App 后端服务。FastAPI + SQLite + SQLAlchemy。

## 快速开始（3 分钟）

```bash
# 1. 克隆仓库 & 进入后端目录
cd backend

# 2. 创建虚拟环境 & 安装依赖
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 JWT_SECRET（随便写一串字符串即可）

# 4. 初始化数据库 & 灌入测试数据
python scripts/seed.py

# 5. 启动服务
uvicorn app.main:app --reload --port 8000 --log-level info
uvicorn app.main:app --reload --host 127.0.0.1 --log-level info #指定日志
# 6. 打开浏览器测试
# Swagger 文档：http://localhost:8000/docs
```

## 测试账号

| 用户名 | 密码 | 学校 |
|--------|------|------|
| kylin | 123456 | 南开大学 |
| xiaolu | 123456 | 天津大学 |
| test | 123456 | 测试大学 |

### 广场+分身模块测试账号

运行 `python scripts/seed_plaza_avatar.py` 创建以下账号（统一密码 `test123456`）：

| 用户名 | 姓名 | 学校 |
|--------|------|------|
| linxiaohan | 林晓涵 | 南开大学 |
| zhoucheng | 周澄 | 天津大学 |
| summer_z | 张诗涵 | 北京大学 |
| wangfuai | 王FU艾 | 清华大学 |
| liuyang_c | 刘洋 | 复旦大学 |
| chenmo | 陈墨 | 上海交通大学 |
| yuxin_r | 于欣怡 | 浙江大学 |
| leomao | 李茂 | 南京大学 |
| zhouqian | 周谦 | 中山大学 |
| hanxiao | 韩笑 | 武汉大学 |

该脚本还会创建 15 条广场帖子、28 条评论、39 条点赞、41 条分身记忆、10 条分身状态、20 条推荐匹配、10 条分身侧写。

## 项目结构

```
backend/
├── app/
│   ├── main.py           # 入口：路由注册 + CORS + 异常处理
│   ├── config.py          # 配置（读 .env）
│   ├── database.py        # 数据库连接
│   ├── dependencies.py    # get_current_user / get_db
│   ├── response.py        # 统一响应格式 + 错误码
│   │
│   ├── models/            # ⚠️ 数据模型（不要改）
│   ├── auth/              # ⚠️ 认证模块（不要改）
│   ├── upload/            # ⚠️ 文件上传（不要改）
│   │
│   ├── ai/                # AI 功能 → 组员 C + D
│   │   ├── minimax_client.py  # MiniMax SDK（直接调用）
│   │   ├── router.py      # 路由（填 TODO）
│   │   ├── service.py     # 业务逻辑
│   │   └── schemas.py     # 请求/响应模型
│   │
│   ├── user/              # 用户模块 → 组员 A
│   ├── diary/             # 日记模块 → 组员 B + C
│   ├── study/             # 学习模块 → 组员 A
│   ├── social/            # 社交模块 → 组员 D
│   ├── plaza/             # 🏫 广场模块 → 组员 E
│   └── avatar/            # 🤖 AI分身模块 → 组员 E
│
├── tests/                 # 测试
├── scripts/
│   ├── seed.py                   # 种子数据（基础测试账号）
│   └── seed_plaza_avatar.py      # 广场+分身种子数据（10用户/15帖/全模块）
├── requirements.txt
└── .env.example
```

## 组员开发指南

### 你只需要改自己的目录

每个模块目录下有 3 个文件：
- `router.py` — 路由（接口定义，里面有 TODO 注释告诉你要做什么）
- `service.py` — 业务逻辑
- `schemas.py` — 请求/响应 Pydantic 模型（已预定义，可按需扩展）

### 开发流程

1. 打开你负责的 `router.py`
2. 找到 TODO 注释，照着写
3. 保存 → 服务自动热更新（`--reload`）
4. 打开 `http://localhost:8000/docs` 测试

### 统一响应格式

所有接口必须返回统一格式：

```json
{
  "code": 0,
  "data": { ... },
  "message": "ok"
}
```

使用 `response.py` 提供的工具函数：

```python
from app.response import success, ApiException, NOT_FOUND

# 成功
return success(data={"name": "kylin"}, message="获取成功")

# 错误
raise ApiException(code=NOT_FOUND, message="日记不存在", status_code=404)
```

### 认证

需要登录的接口加 `Depends(get_current_user)`：

```python
from app.dependencies import get_current_user, get_db

@router.get("/profile")
def get_profile(
    current_user = Depends(get_current_user),  # 自动从 JWT 获取用户
    db = Depends(get_db),                       # 数据库 session
):
    # current_user 就是 User 对象
    return success(data={"name": current_user.name})
```

### 调用 AI（5 个模态，一个 Key）

```python
from app.ai.minimax_client import get_minimax_client

client = get_minimax_client()

# 1. 非流式对话（M2.7）
text = await client.chat_completion(
    messages=[{"role": "user", "content": "你好"}],
    system_prompt="你是一个友好的 AI 助手"
)

# 2. 流式对话 SSE（M2.7）
async for chunk in client.stream_chat(messages, system_prompt):
    yield f"data: {chunk}\n\n"

# 3. 文生图（image-01）
url = await client.generate_image("一只可爱的猫咪", aspect_ratio="1:1")

# 4. TTS（speech-2.8-hd）
audio_bytes = await client.text_to_speech("你好世界", voice_id="male-qn-qingse")

# 5. 音乐生成（music-2.5+）
music_url = await client.generate_music(
    prompt="流行音乐, 开心, 校园生活",
    lyrics="[verse]\n阳光洒在操场上\n青春的风轻轻吹",
)
# 纯音乐（无人声）
bgm_url = await client.generate_music(
    prompt="轻柔钢琴曲, 温暖, 日记背景",
    is_instrumental=True,
)
```

## 运行测试

```bash
python -m pytest tests/ -v
```

## 豆包实时语音分身

实时语音由后端代理连接豆包全双工模型，前端不会接触火山 API Key。

本地配置：

```bash
VOLC_REALTIME_VOICE_ENABLED=true
VOLC_REALTIME_VOICE_API_KEY=<server-only-key>
REALTIME_VOICE_PROVIDER=volcengine_duplex
REALTIME_VOICE_MAX_GLOBAL_SESSIONS=5
REALTIME_VOICE_MAX_INPUT_FRAMES=100
REALTIME_VOICE_MAX_RECONNECTS=2
```

启动后验证：

```bash
curl http://127.0.0.1:8000/api/realtime-voice/health
```

`enabled` 和 `configured` 均为 `true` 后，已登录客户端可先请求
`POST /api/realtime-voice/tickets`，再连接 `/ws/realtime-avatar`。

部署约束：

- H5 麦克风只允许 `localhost` 或 HTTPS，生产必须提供 HTTPS/WSS。
- 当前 Ticket 防重放、全局并发和单用户会话限制是进程内实现，后端固定使用一个 Uvicorn Worker。
- 扩展到多个后端 Worker 前，必须把 Ticket 和会话注册表迁移到 Redis。
- Nginx `/ws/` 必须关闭代理缓冲，并将读写超时设置为 900 秒。
- 后端容器需要能访问 `openspeech.bytedance.com:443`。
- 原始 PCM、Ticket、JWT、API Key 和完整私密记忆不会写入日志。

## 数据库迁移

```bash
# 生成新的迁移
alembic revision --autogenerate -m "描述"

# 执行迁移
alembic upgrade head
```

## ⚠️ 注意事项

1. **不要修改** `models/`、`auth/`、`upload/`、`main.py`、`dependencies.py`、`response.py`
2. **只修改你自己负责的模块目录**
3. JSON 字段（images/emotion/tags）存储为 Text，读取时用 `json.loads()`，写入时用 `json.dumps()`
4. 所有时间戳用**毫秒**（`int(time.time() * 1000)`）
5. Git 分支：在自己的 feature branch 上开发，完成后发 PR
