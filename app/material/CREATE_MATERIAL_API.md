# 创建素材接口说明（POST /api/materials）

## 1. 接口功能

该接口用于创建一条原始素材记录（文字/图片/语音）。
创建成功后会返回完整素材对象，并在满足条件时触发 AI 情绪提取。

主要职责：
- 接收前端素材内容并写入 `raw_materials` 表。
- 自动生成素材主键 `id`。
- 自动生成素材时间字段 `date`（精确到秒）。
- 对 1 秒内重复点击导致的重复请求做防重。

---

## 2. 请求字段（Body）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| type | string | 是 | 素材类型，创建接口支持 `image` / `voice` / `text` |
| content | string | 否 | 文字内容；图片可放描述；语音可放转写文本 |
| media_url | string | 否 | 媒体地址（图片/语音） |
| thumbnail_url | string | 否 | 缩略图地址（主要用于图片） |
| location | object | 否 | 位置信息（如 `lat/lng/address`） |
| emotion | object | 否 | 情绪信息（未传时会使用默认值） |
| tags | array | 否 | 素材标签数组 |
| date | string | 否 | 可传 `YYYY-MM-DD` 作为日期提示；最终入库会生成到秒 |

情绪默认值：
- `{"label": "平静", "score": 0.5, "emoji": "😐"}`

---

## 3. 关键字段生成规则

### 3.1 主键 id 生成

当前创建逻辑使用「年月日时分秒 + 用户ID」作为主键基础串：
- 基础格式：`YYYYMMDDHHMMSS_userId`
- 示例：`20260403142308_7a10f5f1-2cc8-4ff2-bd72-19a9a4f6c8cb`

如果同一秒出现并发写入导致主键已存在，会自动追加后缀：
- `YYYYMMDDHHMMSS_userId_1`
- `YYYYMMDDHHMMSS_userId_2`

### 3.2 date 生成

`date` 在创建时统一生成到秒，格式为：
- `YYYY-MM-DD HH:MM:SS`

生成策略：
- 若请求传了合法 `YYYY-MM-DD`，使用该日期 + 当前点击时刻的 `HH:MM:SS`。
- 若未传或格式无效，使用当前系统日期 + 当前 `HH:MM:SS`。

---

## 4. 1 秒防重复创建规则

为避免用户短时间连续点击导致重复素材，服务层会检查：
- 仅比较同一用户最近一条素材。
- 如果最近一条与本次请求间隔 `< 1000ms`。
- 且关键负载一致（`type/content/media_url/thumbnail_url/location` 全部相同）。

命中上述条件时：
- 不会新建记录。
- 直接返回上一条素材（实现幂等防重）。

---

## 5. type 字段是否入库，以及影响范围

## 5.1 是否入库

会入库。

`raw_materials` 表中 `type` 是必填字段，创建素材时会写入数据库。

## 5.2 对后端行为的影响

1. 日记生成素材拼接逻辑会按 `type` 分支：
- `text` -> `[文字] ...`
- `image` -> `[图片描述] ...`
- `voice` -> `[语音转文字] ...`
- `chat` -> `[对话记录] ...`

2. `chat` 类型不是由该接口直接创建，而是由对话模块在封闭会话后自动生成素材。

## 5.3 对前端行为的影响（只读说明）

前端会根据 `type` 决定展示样式：
- `image` 展示图片卡片。
- `voice` 展示语音内容。
- `text` 展示文本内容。
- `chat` 在记录页展示对话素材卡片并可展开详情。

---

## 6. 响应字段说明（data）

| 字段 | 说明 |
|---|---|
| id | 素材主键（由后端生成） |
| userId | 用户 ID |
| type | 素材类型 |
| content | 素材文本内容 |
| mediaUrl | 媒体地址 |
| thumbnailUrl | 缩略图地址 |
| location | 位置信息对象 |
| emotion | 情绪对象 |
| tags | 标签数组 |
| date | 创建时间（`YYYY-MM-DD HH:MM:SS`） |
| createdAt | Unix 毫秒时间戳 |
| chatSessionId/startTime/endTime | 仅 `chat` 素材可能有值 |

---

## 7. 兼容性说明

由于 `date` 已升级为到秒格式，按天查询时后端已兼容：
- 当查询参数是 `YYYY-MM-DD` 时，会按该日期前缀匹配（等价当天查询）。
- 当查询参数是完整时间字符串时，执行精确匹配。

---

## 8. 图片上传联动说明

### 8.1 上传接口

图片上传接口：`POST /api/upload/diary-image`

返回字段：
- `url`：原图访问地址
- `thumbnailUrl`：缩略图地址（后端自动生成；生成失败时回退为原图 URL）
- `location`：从 EXIF 解析出的位置信息（`lat/lng/address`，无 EXIF 时为空对象）

### 8.2 与创建素材接口的联动

用户操作链路：
1. 先上传图片，拿到 `url + thumbnailUrl + location`
2. 再调用 `POST /api/materials` 创建 `type=image` 素材

后端兜底逻辑：
- 若创建素材时只传了 `mediaUrl/media_url`，未传 `thumbnailUrl/thumbnail_url` 或 `location`，后端会按 `media_url` 从上传元数据缓存自动回填。
- 这样可以保证「上传图片后创建素材」场景中，缩略图和位置信息默认可带入素材记录。
