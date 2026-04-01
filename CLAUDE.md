# 日迹后端 (backend)

## 项目概述
FastAPI + SQLAlchemy(同步) + SQLite 后端，为日迹 App 提供 API 服务。

## 技术栈
- Python 3.14
- FastAPI 0.115.0
- SQLAlchemy 2.0.35（同步模式）
- SQLite / Alembic 迁移
- bcrypt 4.0.1
- MiniMax AI（5模态 + Mock 模式）

## 项目结构
```
app/
├── main.py           # FastAPI 入口，路由注册
├── config.py         # 配置（MINIMAX_MOCK 等）
├── database.py       # SQLAlchemy 引擎/Session
├── dependencies.py   # FastAPI 依赖注入（认证）
├── response.py       # 统一响应格式 + 错误码
├── auth/             # 注册/登录
├── upload/           # 文件上传（头像/日记图片/语音）
├── user/             # 用户资料 + AI 画像
├── diary/            # 日记管理（v2：AI生成/衍生内容）
├── material/         # 素材管理（CRUD + AI情绪/润色）
├── anniversary/      # 纪念日管理
├── derivative/       # 衍生内容（漫画/小说/分享卡）
├── social/           # 社交匹配 + 搭子
├── plaza/            # 🏫 广场帖子（找搭子/求助/分享/恋爱）
├── avatar/           # 🤖 AI 分身（记忆库/状态/推荐匹配/侧写）
├── chat/             # AI 对话（SSE 流式）
├── study/            # 学习（番茄钟/Todo）
├── ai/               # MiniMax AI 客户端
└── models/           # SQLAlchemy 数据模型
```

## 数据模型
- User / UserSettings / UserAchievement
- Diary（v2：+title/date/status/edit_count/material_ids/emotion_summary）
- RawMaterial（素材：image/voice/text）
- Anniversary（纪念日）
- UserProfile（AI画像）
- DiaryDerivative（衍生内容）
- ChatMessage（AI对话历史）
- Match / SocialMessage（社交）
- Pomodoro / Todo（学习）
- PlazaPost / PlazaComment / PostLike（广场帖子、评论、点赞）
- AvatarMemory / AvatarStatus / AvatarMatch / AvatarProfile（AI 分身记忆、状态、推荐匹配、侧写）

## 规范
- 所有时间戳用毫秒 BigInteger
- UUID 用字符串
- JSON 字段用 Text + json.loads/dumps
- 统一响应：`{"code": 0, "data": {...}, "message": "ok"}`
- 错误码：`ok/success()` 返回 code=0，`ApiException` 抛出业务错误
- Mock 模式：`MINIMAX_MOCK=true` 时不消耗 API

## 开发命令
```bash
# 启动开发服务
uvicorn app.main:app --reload --host 127.0.0.1

# 运行测试
source venv/bin/activate && pytest tests/ -v

# 数据库迁移
alembic revision --autogenerate -m "描述"
alembic upgrade head
```

## 注意事项
- auth/, upload/, config.py, database.py, dependencies.py, response.py 为核心文件，谨慎修改
- 新增字段只增不删
- 所有 AI 方法需要支持 Mock 模式
