# 任务书 C — 日记 AI + 衍生内容 + 纪念日

> **负责人：** 队友 C
>
> **模块：** app/ai/（AI 功能）、app/derivative/（衍生内容）、app/anniversary/（纪念日）
>
> **前置阅读：** [ONBOARDING.md](./ONBOARDING.md) → [COOKBOOK.md](./COOKBOOK.md) → 本文档
>
> **分支名：** `feat/diary-ai`

---

## 你负责的文件

| 文件 | 操作 |
|------|------|
| `app/ai/router.py` | 检查 + 完善 |
| `app/ai/service.py` | **需要写**（目前为空） |
| `app/ai/schemas.py` | 检查 + 完善 |
| `app/derivative/router.py` | 检查（已实现） |
| `app/derivative/service.py` | **需要新建** |
| `app/derivative/schemas.py` | **需要新建** |
| `app/anniversary/router.py` | 检查（已实现） |
| `app/anniversary/service.py` | 检查（已实现） |
| `app/anniversary/schemas.py` | 检查（已实现） |
| `tests/test_ai.py` | 补充测试 |
| `tests/test_anniversary.py` | 补充测试 |

## 不要碰的文件

- 公共文件（main.py、config.py 等）
- `app/ai/minimax_client.py`（AI 客户端封装，**只调用不修改**）
- `app/diary/*`（队友 B 负责）
- `app/models/*`（改前沟通）
- 其他模块

---

## 接口清单

### AI 功能模块（2 个已注册接口 + ai/service.py 需要写）

#### POST /api/ai/tts — 文字转语音

**当前状态：** ✅ 已实现（在 router.py 中直接写了逻辑）

调用 minimax_client.text_to_speech，保存音频文件到 uploads 目录，返回 URL。

**你需要做的：** 核对 Mock 模式下的返回。当前 Mock 返回一个最小 MP3 字节，前端能播放但无声。

---

#### GET /api/ai/fortune — AI 今日运势

**当前状态：** ✅ 已实现（在 router.py 中直接写了逻辑）

Mock 模式返回固定运势数据，真实模式调用 chat_completion 让 AI 生成 JSON。

**你需要做的：** 核对返回字段：overall/study/social/health（1-5）、tip、luckyColor、luckyNumber。

---

#### ai/service.py — 需要你写

当前 `ai/service.py` 是空文件（只有一行注释）。目前 TTS 和 Fortune 的逻辑直接写在了 router.py 里。

**建议改造：**
1. 把 router.py 中 TTS 和 Fortune 的业务逻辑抽取到 service.py
2. router.py 只负责接收请求和返回响应

这不是必须的，但能让代码更清晰。如果时间紧可以跳过。

---

### 衍生内容模块（2 个接口）

#### GET /api/derivatives — 衍生内容列表

**当前状态：** ✅ 已实现（直接在 router.py 里写了查询逻辑）

查询当前用户的所有衍生内容，支持按 diary_id 筛选，返回裸数组。

**你需要做的：** 测试筛选功能。核对 DerivativeOut 的字段是否正确。

---

#### POST /api/derivatives/{deriv_id}/share — 设置分享范围

**当前状态：** ✅ 已实现（直接在 router.py 里写了）

设置衍生内容的 share_scope："private" / "friends" / "public"。

**你需要做的：** 核对权限检查——只有衍生内容所属日记的作者才能设置分享范围。

---

#### 需要新建的文件

当前 derivative 模块没有 service.py 和 schemas.py。router.py 里直接用了 diary/schemas.py 的 DerivativeOut。

**如果需要扩展**（比如加新接口），建议：

1. 新建 `app/derivative/schemas.py`：

```python
# app/derivative/schemas.py
from pydantic import BaseModel

class ShareRequest(BaseModel):
    scope: str = "private"
```

2. 新建 `app/derivative/service.py`，把 router.py 中的查询逻辑抽出来。

目前两个接口逻辑简单，直接写在 router 也没问题。

---

### 纪念日模块（5 个接口）

#### GET /api/anniversaries/today — 今日纪念日 + 那年今日

**当前状态：** ✅ 已实现

service.get_today_anniversaries 逻辑：
```
1. 查 anniversaries 表中 date 匹配今天月日的记录
2. 查 diaries 表中 date 匹配往年今天的记录（"那年今日"）
3. 返回 {today: [...], on_this_day: [...]}
```

**你需要做的：** 测试日期匹配逻辑。纪念日的 date 格式是 "MM-DD"（如 "03-25"），注意月和日要补零。

---

#### GET /api/anniversaries — 纪念日列表

**当前状态：** ✅ 已实现，返回裸数组。

---

#### POST /api/anniversaries — 添加纪念日

**当前状态：** ✅ 已实现

**你需要做的：** 测试 source 字段。手动添加的 source="manual"，AI 提取的 source="ai"。

---

#### PUT /api/anniversaries/{ann_id} — 编辑纪念日

**当前状态：** ✅ 已实现

---

#### DELETE /api/anniversaries/{ann_id} — 删除纪念日

**当前状态：** ✅ 已实现

---

## MiniMax AI 客户端速查

你需要了解但**不用修改**的 `app/ai/minimax_client.py`，已封装的方法：

| 方法 | 输入 | 输出 | 你的接口用到？ |
|------|------|------|--------------|
| `chat_completion(messages, system_prompt)` | 消息列表 | string | fortune 用到 |
| `text_to_speech(text, voice_id)` | 文字 + 音色 | bytes | tts 用到 |
| `generate_image(prompt, aspect_ratio)` | 提示词 | URL string | — |
| `generate_music(prompt, lyrics)` | 提示词 | URL string | 未接入 |
| `extract_emotion(text)` | 文字 | dict | — |
| `polish_text(text, style)` | 文字 + 风格 | string | — |
| `generate_diary(materials, weather)` | 素材 + 天气 | dict | — |
| `extract_info(content)` | 日记内容 | dict | — |
| `generate_portrait(diary, chat)` | 摘要 | dict | — |
| `generate_match_report(a, b)` | 两个画像 | string | — |

使用方法参考 [COOKBOOK.md](./COOKBOOK.md) 的「调用 MiniMax AI」章节。

---

## 工作重点

1. **核对已有接口**：AI 和纪念日模块代码基本写好了，以测试为主
2. **衍生内容模块**：代码在 router 里直接写了，考虑是否需要抽出 service 层
3. **补充测试**：特别是纪念日的日期匹配、AI 的 Mock 返回格式
4. **理解 AI 调用链路**：router → service → minimax_client → MiniMax API

## 与其他模块的依赖

| 依赖方向 | 说明 |
|----------|------|
| **diary 模块 → 你** | 队友 B 的 extract 接口会往你的 anniversaries 表写数据 |
| **diary 模块 → derivative** | 队友 B 的 derivative 接口会往 diary_derivatives 表写数据，你的 GET /derivatives 查询它 |
| **你 → AI 客户端** | 调用 minimax_client 的方法 |

## 验收标准

- [ ] 9 个接口在 Swagger 中全部可调通
- [ ] `pytest tests/test_ai.py tests/test_anniversary.py -v` 全部通过
- [ ] TTS Mock 模式返回有效 URL
- [ ] 纪念日 CRUD 完整（创建 → 列表 → 编辑 → 删除）
- [ ] 今日纪念日 + 那年今日逻辑正确

## 预估工作量

约 1-2 天。代码基本已实现，以测试和完善为主。如果要重构 service 层需要额外 0.5 天。

---

*参考：anniversary/service.py 是完整的 CRUD 范本 | AI 调用参考 COOKBOOK.md*
