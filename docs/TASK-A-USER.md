# 任务书 A — 用户模块

> **负责人：** 队友 A
>
> **模块：** app/user/
>
> **前置阅读：** [ONBOARDING.md](./ONBOARDING.md) → [COOKBOOK.md](./COOKBOOK.md) → 本文档
>
> **分支名：** `feat/user`

---

## 你负责的文件

| 文件 | 操作 |
|------|------|
| `app/user/router.py` | 检查 + 修复 |
| `app/user/service.py` | 检查 + 修复 |
| `app/user/schemas.py` | 检查 + 修复 |
| `tests/test_user.py` | 补充测试 |

## 不要碰的文件

- `app/main.py`, `app/config.py`, `app/database.py`, `app/dependencies.py`
- `app/response.py`, `app/serializers.py`
- `app/auth/*`（认证模块，已完成）
- `app/models/*`（改模型前先群里沟通）
- 其他模块的文件夹

---

## 接口清单

你负责 10 个接口，全部在 `app/user/router.py` 中已注册。

### 1. GET /api/user/profile — 获取用户资料

**当前状态：** ✅ 已实现

service.get_user_profile 从 users 表读取用户信息，返回 name、school、major、level、diaryCount 等字段。

**你需要做的：** 核对返回字段是否与 [API-DOCS.md](./API-DOCS.md) 一致。特别检查 styleTags 和 customStylePrompt 是否正确返回。

---

### 2. POST /api/user/profile — 更新用户资料

**当前状态：** ✅ 已实现

service.update_user_profile 支持更新 name、school、major、avatar、style_tags、custom_style_prompt。

**你需要做的：** 测试 style_tags（数组）和 custom_style_prompt（字符串）是否正确存取。这两个字段在数据库中是 TEXT（JSON 序列化），需要用 `_encode/_decode`。

---

### 3. GET /api/user/growth — 获取成长数据

**当前状态：** ✅ 已实现

service.get_growth_data 从 diaries、pomodoros 表聚合数据，返回 diaries（最近7天日记数）、emotions（情绪分布）、tags（热门标签）、pomodoros（番茄钟统计）、streak（连续天数）。

**你需要做的：** 核对逻辑是否正确。特别是情绪分布 emotions 和标签统计 tags 的聚合逻辑——它们从日记的 JSON 字段中提取，可能有边界情况（空日记、没有 emotion 字段的日记）。

---

### 4. GET /api/user/achievements — 获取成就列表

**当前状态：** ✅ 已实现

service.get_achievements 有一个预定义的成就列表（first_diary、streak_3 等），对照 user_achievements 表标注是否已解锁。

**你需要做的：** 核对成就定义是否合理，考虑是否需要新增成就类型。

---

### 5. GET /api/user/settings — 获取用户设置

**当前状态：** ✅ 已实现

**注意：** SettingsOut 中 `auto_bgm` 的别名是 `autoBGM`（全大写 BGM），不是 `autoBgm`。这是特殊处理，已在 schemas.py 中配置。

---

### 6. POST /api/user/settings — 更新用户设置

**当前状态：** ✅ 已实现

---

### 7. GET /api/user/semester-report — 获取学期报告

**当前状态：** ✅ 已实现

service.get_semester_report 聚合用户所有数据生成学期报告。

**你需要做的：** 核对统计逻辑。highlights 字段的生成逻辑可能需要完善——当前可能是空数组或固定值。

---

### 8. GET /api/user/portrait — 获取用户 AI 画像

**当前状态：** ✅ 已实现

从 user_profiles 表读取，格式转换逻辑较复杂（preferences dict→list、personality 逗号分割→list 等）。

**你需要做的：** 测试当 user_profiles 为空时的返回（应返回空数组/空列表）。

---

### 9. POST /api/user/portrait/refresh — 刷新用户画像（AI）

**当前状态：** ✅ 已实现

调用 minimax_client.generate_portrait，需要 `async def`。逻辑：取最近 10 篇日记 + 最近 20 条聊天 → AI 分析 → 写入 user_profiles 表。

**你需要做的：** 测试 Mock 模式下的返回格式。确保写入的数据能被 GET /portrait 正确读取。

---

### 10. GET /api/user/agent-portrait — 获取 AI 画像图

**当前状态：** ✅ 已实现

调用 minimax_client.generate_image 生成水彩插画 URL。

**你需要做的：** Mock 模式下返回一个占位图 URL，确认前端能正常显示。

---

## 工作重点

你的模块代码完成度较高，主要工作是：

1. **通读所有 service 代码**，理解每个函数的逻辑
2. **用 Swagger 逐个测试**，确认返回格式正确
3. **补充边界情况处理**：空数据、JSON 字段解码异常等
4. **补充测试用例**：在 `tests/test_user.py` 中为每个接口写测试
5. **确保 camelCase 输出**：所有 `_` 字段都要正确转换

## 验收标准

- [ ] 10 个接口在 Swagger 中全部可调通
- [ ] `pytest tests/test_user.py -v` 全部通过
- [ ] Mock 模式下 AI 相关接口（portrait/refresh、agent-portrait）返回合理数据
- [ ] 空用户（新注册、没有日记和成就）的返回不报 500

## 预估工作量

约 1-2 天。代码基本已写好，以测试和修复为主。

---

*参考模块：material/ 的 CRUD 结构 | 参考文档：[API-DOCS.md](./API-DOCS.md)*
