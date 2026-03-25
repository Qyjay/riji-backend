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
├── chat/             # AI 对话（SSE 流式，三层降级）
├── study/            # 学习（番茄钟/Todo）
├── ai/               # MiniMax AI 客户端 + AI 功能路由（fortune/comic/share-card/bgm/tts/novel-chapter）
├── openclaw/         # OpenClaw Gateway 客户端（带记忆对话）
│   ├── client.py     # OpenClawClient + get_openclaw_client()
│   └── prompt_builder.py  # build_chat_system_prompt()
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

## 规范
- 所有时间戳用毫秒 BigInteger
- UUID 用字符串
- JSON 字段用 Text + json.loads/dumps
- 统一响应：`{"code": 0, "data": {...}, "message": "ok"}`
- 错误码：`ok/success()` 返回 code=0，`ApiException` 抛出业务错误
- Mock 模式：`MINIMAX_MOCK=true` 时不消耗 API

## AI 功能路由（app/ai/router.py）
- `GET /ai/fortune`：根据最近 3 篇日记情绪趋势生成今日运势
- `POST /ai/comic`：日记内容 → AI 场景提取 → 漫画图片生成（3:4）
- `POST /ai/share-card`：查日记 → 并行生成金句 + 卡片背景图
- `POST /ai/bgm`：情绪关键词 → 映射音乐风格 → generate_music()
- `POST /ai/tts`：文字转语音 → 保存 uploads/tts/*.mp3 → 返回 URL
- `POST /ai/novel-chapter`：日记改编为指定风格小说章节

## OpenClaw Gateway（带记忆 AI 对话）
- 配置：`OPENCLAW_ENABLED=true` + `OPENCLAW_GATEWAY_TOKEN` + `OPENCLAW_GATEWAY_URL`（默认 http://127.0.0.1:18789）
- 三层降级：OpenClaw → 直连 MiniMax → Mock
- `OPENCLAW_ENABLED` 默认 `False`，Mock 模式下不调 OpenClaw
- `user` 字段设为 `riji-{user_id}` 实现 per-user session 隔离

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
