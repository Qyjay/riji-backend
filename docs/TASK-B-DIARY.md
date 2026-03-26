# 任务书 B — 日记核心模块

> **负责人：** 队友 B
>
> **模块：** app/diary/（日记 CRUD + 生成）、app/material/（素材 CRUD）
>
> **前置阅读：** [ONBOARDING.md](./ONBOARDING.md) → [COOKBOOK.md](./COOKBOOK.md) → 本文档
>
> **分支名：** `feat/diary-core`

---

## 你负责的文件

| 文件 | 操作 |
|------|------|
| `app/diary/router.py` | 检查 + 修复 |
| `app/diary/service.py` | 检查 + 修复 + 完善 |
| `app/diary/schemas.py` | 检查 + 修复 |
| `app/material/router.py` | 检查 + 修复 |
| `app/material/service.py` | 检查 + 修复 |
| `app/material/schemas.py` | 检查 + 修复 |
| `tests/test_diary.py` | 补充测试 |
| `tests/test_diary_v2.py` | 补充测试 |
| `tests/test_material.py` | 补充测试 |

## 不要碰的文件

- `app/main.py`, `app/config.py`, `app/database.py`, `app/dependencies.py`
- `app/response.py`, `app/serializers.py`
- `app/auth/*`, `app/upload/*`
- `app/ai/minimax_client.py`（AI 客户端，只调用不修改）
- `app/models/*`（改模型前先群里沟通）
- 其他模块的文件夹

---

## 核心概念：素材 → 日记 的关系

```
用户一天的操作流程：
  1. 收集素材（拍照、写文字、录语音）→ 存入 raw_materials 表
  2. 点「生成日记」→ AI 读取当天所有素材，生成日记 → 存入 diaries 表
  3. 用户可以手动修改日记（有次数限制，默认 3 次）
```

素材和日记通过 `date` 字段关联（同一天的素材生成同一天的日记）。日记的 `material_ids` 字段记录了生成时用了哪些素材的 ID。

---

## 接口清单

### 素材模块（8 个接口）

#### POST /api/materials — 创建素材

**当前状态：** ✅ 已实现

service.create_material 创建素材记录。如果未传 emotion 且有文字内容，会自动调用 AI 情绪提取。

**你需要做的：** 测试三种素材类型（text/image/voice）的创建流程。image 类型需要先调 /upload/diary-image 拿到 URL。

---

#### GET /api/materials — 素材列表

**当前状态：** ✅ 已实现

支持按 date 参数筛选（如 `?date=2026-03-26`），返回裸数组。

---

#### GET /api/materials/{material_id} — 素材详情

**当前状态：** ✅ 已实现

---

#### PUT /api/materials/{material_id} — 编辑素材

**当前状态：** ✅ 已实现

service.update_material 只更新传入的字段（exclude_unset）。JSON 字段（location、emotion、tags）需要序列化后存储。

**你需要做的：** 检查 JSON 字段的更新是否正确——从 dict → JSON string 存储、从 JSON string → dict 读取。

---

#### DELETE /api/materials/{material_id} — 删除素材

**当前状态：** ✅ 已实现

---

#### POST /api/materials/{material_id}/emotion — AI 情绪提取

**当前状态：** ✅ 已实现

调用 minimax_client.extract_emotion，结果写回素材的 emotion 字段。

**你需要做的：** 测试 Mock 模式返回的情绪数据格式 `{"label": "开心", "score": 0.88, "emoji": "😊"}`。

---

#### POST /api/materials/{material_id}/polish — AI 文字润色

**当前状态：** ✅ 已实现

支持 4 种风格："文艺" / "幽默" / "简洁" / "温暖"。

**你需要做的：** 返回格式应该是 `{"polished": "润色后的文字"}`。检查 service 里是否正确包装。

---

#### POST /api/materials/voice — 语音上传与转写

**当前状态：** 🟡 Mock 实现

返回硬编码的假 URL 和假转写文本。

**你需要做的：** 暂时保持 Mock。如果后续需要真实转写，可以接入 MiniMax 语音识别 API。

---

### 日记模块（8 个接口）

#### GET /api/diaries/today-summary — 今日概要

**当前状态：** ✅ 已实现

service.get_today_summary 统计当天素材数、是否已生成日记。首页用。

---

#### POST /api/diaries/generate — AI 生成当日日记

**当前状态：** ✅ 已实现

**核心逻辑（伪代码）：**
```
1. 查当天的所有素材 (raw_materials WHERE date == body.date)
2. 把素材文字拼接成一段文本
3. 调用 minimax_client.generate_diary(素材文本, weather)
4. AI 返回 {title, content, emotion_summary}
5. 创建 Diary 记录，status="generated"
6. 如果当天已有日记 → 更新而不是新建
```

**你需要做的：**
- 测试没有素材时的生成（应该提示「请先记录今天的素材」或返回兜底内容）
- 测试重复生成（同一天生成两次），是更新还是报错
- 检查 edit_count 初始值是否为 0，max_edits 默认值是否为 3

---

#### GET /api/diaries — 日记列表

**当前状态：** ✅ 已实现

分页，返回 `{"items": [...], "total": 42}`。同时支持 `page_size` 和 `pageSize` 参数。

---

#### GET /api/diaries/{diary_id} — 日记详情

**当前状态：** ✅ 已实现

---

#### PUT /api/diaries/{diary_id} — 修改日记

**当前状态：** ✅ 已实现

**核心逻辑：**
```
1. 检查 edit_count < max_edits（默认 3 次）
2. 如果超限 → 抛出 PARAM_ERROR "修改次数已达上限"
3. 更新 content，edit_count += 1
```

**你需要做的：** 测试修改次数限制——修改 3 次后第 4 次应该返回错误。

---

#### GET /api/diaries/{diary_id}/emotion-trend — 当日情绪趋势

**当前状态：** ✅ 已实现

service.get_emotion_trend 从日记关联的素材中提取情绪，按时间排列。

**你需要做的：** 测试没有素材时的返回（空趋势）。检查时间格式是否正确。

---

#### POST /api/diaries/{diary_id}/extract — AI 提取信息

**当前状态：** ✅ 已实现

调用 minimax_client.extract_info 从日记内容提取纪念日、人物、偏好。提取结果会自动写入 anniversaries 表和 user_profiles 表。

**你需要做的：** 测试提取结果是否正确写入数据库。这个接口会跨模块写数据（纪念日、用户画像），需要确认不影响其他模块。

---

#### POST /api/diaries/{diary_id}/derivative — 生成衍生内容

**当前状态：** ✅ 已实现

支持 3 种类型：comic（漫画）、novel（小说）、share_card（分享卡）。
- comic：调用 minimax_client.generate_image
- novel/share_card：调用 minimax_client.chat_completion

**你需要做的：** 测试三种类型的生成。检查结果是否正确存入 diary_derivatives 表。

> **注意：** 衍生内容的查询和分享由队友 C 负责（derivative 模块），你只负责「生成」这个接口。

---

## 工作重点

1. **理解素材→日记的完整链路**：创建素材 → 生成日记 → 修改日记
2. **重点测试 AI 接口**：generate、extract、derivative 在 Mock 模式下的行为
3. **检查 JSON 字段的序列化/反序列化**：emotion、tags、location、material_ids、emotion_summary
4. **补充边界测试**：空素材生成日记、超限修改、不存在的 diary_id

## 与其他模块的依赖

| 依赖方向 | 说明 |
|----------|------|
| **你 → AI 客户端** | 调用 minimax_client 的方法（不用改客户端代码） |
| **你 → anniversary 模块** | extract 接口会写入纪念日表（跨模块写入） |
| **衍生模块 → 你** | 队友 C 的 derivative 模块查询你创建的衍生内容 |
| **首页 → 你** | 前端首页会调 today-summary，需要你的接口稳定 |

## 验收标准

- [ ] 16 个接口在 Swagger 中全部可调通
- [ ] `pytest tests/test_diary.py tests/test_diary_v2.py tests/test_material.py -v` 全部通过
- [ ] 素材→日记生成完整链路跑通（创建3条素材 → 生成日记 → 修改日记 → 查看详情）
- [ ] 空数据、边界情况不报 500

## 预估工作量

约 2-3 天。代码大部分已实现，以测试、修复和完善为主。日记生成和信息提取的 AI 链路是重点。

---

*参考：material/service.py 是最好的 CRUD 范本 | AI 调用参考 diary/service.py 的 generate_diary*
