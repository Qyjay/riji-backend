# 2026-04-23 ~ 2026-05-03 真实多用户数据注入说明

这是一套按真实使用链路写入的 11 天多用户数据，用来支持匹配、社交、日记、聊天、统一记忆回灌与数字分身联调。

当前版本已经从 5 个真实用户扩展到 `10` 个真实用户：

- 原始 5 人保持不动
- 新增 5 人的数据量与原始 5 人对齐
- 新增 5 人之间有新的熟人网络
- 新增 5 人和原来的 5 人之间也形成了新的评论、点赞、匹配与私聊关系

## 1. 数据范围

- 时间范围：`2026-04-23` 到 `2026-05-03`
- 用户数：`10`
- 每人每天至少 `2` 次 AI 聊天
- 每人每天 `1` 篇长日记，正文超过 `500` 字
- 每个用户都有持续素材记录、广场互动、匹配关系、私聊与统一记忆回灌
- 每个用户在 11 天内固定有 `5` 条广场内容

当前默认注入结果如下：

- `users: 10`
- `raw_materials: 550`
- `diaries: 110`
- `chat_sessions: 220`
- `chat_messages: 1320`
- `plaza_posts: 50`
- `plaza_comments: 131`
- `post_likes: 182`
- `social_matches: 10`
- `social_messages: 82`
- `anniversaries: 18`
- `memory_facts: 20`

## 2. 10 个测试账号

这 10 个用户都已经有真实账号，重新跑脚本后会统一覆盖为以下登录信息：

| 用户名 | 密码 | 学校 | 专业 | 角色特征 |
| --- | --- | --- | --- | --- |
| `xu_yining` | `123456` | 南开大学 | 软件工程 | 理性克制，秋招与工程成长主线明显 |
| `qiao_meng` | `123456` | 天津大学 | 建筑学 | 外向热情，擅长空间观察与城市内容 |
| `su_wen` | `123456` | 武汉大学 | 临床医学 | 敏感细腻，长期处在高压实习与恢复节奏里 |
| `he_zhuo` | `123456` | 中山大学 | 法学 | 理性克制，擅长规则、结构化表达与判断 |
| `lin_yao` | `123456` | 复旦大学 | 新闻与传播 | 善于表达和观察，内容创作与社交活跃度高 |
| `jiang_nanxi` | `123456` | 清华大学 | 工业设计 | 关注用户路径、材料触感与服务设计 |
| `ran_ke` | `123456` | 西安交通大学 | 机械工程 | 强工程感，重视排障、顺序与调试复盘 |
| `zhou_yue` | `123456` | 北京师范大学 | 汉语言文学 | 擅长对白、人物停顿与文字互看 |
| `ye_qing` | `123456` | 中国农业大学 | 食品科学与工程 | 擅长把食物、照顾和恢复动作写得很真实 |
| `tang_shuo` | `123456` | 中国人民大学 | 社会学 | 擅长访谈、田野、原话与慢一点概括 |

建议匹配同学固定保留这组账号，不要再手动改密码，这样联调时前后端、算法、测试三方口径一致。

## 3. 新增 5 人的定位

新增 5 人补齐了原有 5 人之外的关系类型和兴趣面。

### `jiang_nanxi`

- 关键词：工业设计、服务设计、用户访谈、材料触感、使用路径
- 固定高频互动对象：`xu_yining`、`qiao_meng`
- 适合验证：作品集表达、用户研究、空间停留感、设计如何与工程沟通

### `ran_ke`

- 关键词：机械工程、机器人、故障树、调试日志、工程表达
- 固定高频互动对象：`he_zhuo`、`xu_yining`
- 适合验证：理工方法型匹配、结构化判断、长期排障搭子

### `zhou_yue`

- 关键词：对白、人物观察、广播、戏剧、互看文字
- 固定高频互动对象：`lin_yao`、`tang_shuo`
- 适合验证：内容表达型匹配、文字互看、停顿与人物关系

### `ye_qing`

- 关键词：发酵、早餐、恢复食谱、社区厨房、低门槛照顾
- 固定高频互动对象：`su_wen`、`qiao_meng`
- 适合验证：高压生活里的恢复链路、照顾型关系、长期轻连接

### `tang_shuo`

- 关键词：社会学、田野、访谈提纲、原话整理、解释边界
- 固定高频互动对象：`zhou_yue`、`he_zhuo`
- 适合验证：方法论匹配、慢一点概括、原话与结论的边界

## 4. 注入了哪些源数据

脚本优先写“源行为数据”，再统一回灌记忆，不直接手写 `memory_documents`。

已覆盖的核心表：

- `users`
- `user_settings`
- `user_profiles`
- `avatar_memories`
- `avatar_status`
- `avatar_profiles`
- `avatar_cards`
- `raw_materials`
- `diaries`
- `chat_sessions`
- `chat_messages`
- `plaza_posts`
- `plaza_comments`
- `post_likes`
- `matches`
- `social_messages`
- `anniversaries`
- `memory_facts`

## 5. 统一记忆回灌情况

脚本会在源数据写完之后，自动回灌以下内容进入统一记忆链路：

- `material`
- `diary`
- `chat_session`
- `plaza_post`
- `plaza_comment`
- `social_message`

当前结构化补充数据如下：

- `anniversaries: 18`
- `memory_facts: 20`

所有 `memory_fact` 都会带：

- `evidence_document_id`
- `evidence_chunk_id`

为了避免本地 embedding 限流，脚本运行时会切到 hash fallback：

- `MEMORY_ENABLED = True`
- `MEMORY_VECTOR_ENABLED = False`
- `MEMORY_EMBEDDING_PROVIDER = "hash"`

这样既保留记忆回灌，也能保证本地 SQLite fallback 检索链路可用。

## 6. 图片如何处理

脚本默认直接复用仓库内 `/uploads/**/diary-image/*` 图片，不需要额外手工准备图片。

只有一种情况建议继续补图：

- 如果希望某个用户长期呈现非常稳定的视觉风格，比如总是建筑草图、总是实验室、总是采访现场、总是社区厨房，那可以后续再给该用户补专属图片池

如果只是为了跑真实链路、让日记和广场内容更像真人使用，目前这套图片复用已经足够。

## 7. 扩展后的熟人网络

### 7.1 原有核心关系仍然保留

- `xu_yining <-> he_zhuo`
- `qiao_meng <-> lin_yao`
- `su_wen <-> lin_yao`
- `he_zhuo <-> qiao_meng`

### 7.2 新增 5 人之间的核心关系

- `zhou_yue <-> tang_shuo`
  - 原话、人物、停顿、慢一点概括
- `jiang_nanxi <-> qiao_meng`
  - 停留感、空间路线、材料触感
- `ran_ke <-> he_zhuo`
  - 故障树、结构判断、工程表达
- `ye_qing <-> su_wen`
  - 恢复动作、低门槛照顾、高压节奏

### 7.3 新旧用户之间的新增关系

- `xu_yining <-> jiang_nanxi`
  - 作品集、判断表达、使用路径
- `lin_yao <-> zhou_yue`
  - 对白、写作边界、人物观察
- `tang_shuo <-> lin_yao`
  - 采访入口、原话、解释边界
- `qiao_meng <-> ye_qing`
  - 日常照顾、慢节奏停留、空间感

这意味着匹配算法不应该只给出“兴趣像不像”，还应该能感知：

- 已存在的高频互动对象
- 已发生过的内容共鸣
- 评论、点赞、私聊和匹配之间的连续关系

## 8. 当前 matches 结构

当前共有 `10` 组可验证关系：

- 老 4 组：
  - `xu_yining <-> he_zhuo`
  - `qiao_meng <-> lin_yao`
  - `su_wen <-> lin_yao`
  - `he_zhuo <-> qiao_meng`
- 新增 6 组：
  - `xu_yining <-> jiang_nanxi`
  - `he_zhuo <-> ran_ke`
  - `lin_yao <-> zhou_yue`
  - `su_wen <-> ye_qing`
  - `qiao_meng <-> jiang_nanxi`
  - `tang_shuo <-> zhou_yue`

这些 `matches` 都带有真实的往返私聊，不是空壳关系。

## 9. 如何注入数据

### 9.1 运行前准备

在 `riji-backend` 根目录下执行。

确保本地虚拟环境、依赖、数据库初始化都已经可用。脚本会自动处理旧库里缺失的 `plaza_comments.parent_comment_id` 字段。

### 9.2 注入命令

```bash
python scripts/seed_realistic_may_2026.py
```

脚本行为：

- 会先清理这 10 个用户名对应的旧测试数据
- 再重新写入 11 天完整数据
- 最后统一回灌记忆、补 `anniversaries` 和 `memory_facts`

如果你需要重复联调，直接反复执行这个命令即可。

### 9.3 快速校验

脚本执行结束后，当前预期应接近：

```text
users: 10
raw_materials: 550
diaries: 110
chat_sessions: 220
chat_messages: 1320
plaza_posts: 50
plaza_comments: 131
post_likes: 182
social_matches: 10
social_messages: 82
anniversaries: 18
memory_facts: 20
```

## 10. 如何登录和使用

登录接口：

- `POST /api/auth/login`

请求体示例：

```json
{
  "username": "xu_yining",
  "password": "123456"
}
```

返回值里会有 `token`。之后把它放进请求头：

```text
Authorization: Bearer <token>
```

建议登录后优先检查：

- `GET /api/user/profile`
- `GET /api/avatar/profile`
- `GET /api/avatar/card`
- `GET /api/avatar/memories`
- `GET /api/social/matches`
- `GET /api/avatar/matches`

## 11. 给匹配同学的测试方法

### 11.1 推荐测试顺序

1. 重新注入数据
2. 分别登录 10 个账号，拿到 10 份 token
3. 查看每个账号的 `avatar profile`、`avatar card`、`avatar memories`
4. 查看该账号的 `social matches`
5. 查看该账号的 `avatar matches`
6. 对已存在 `match` 拉消息历史和匹配报告
7. 验证排序结果是否和既有人设、熟人网络、广场互动、私聊历史一致

### 11.2 建议重点验证的接口

- `POST /api/auth/login`
- `GET /api/avatar/matches`
- `POST /api/avatar/matches/{match_id}/action`
- `GET /api/social/matches`
- `GET /api/social/messages/{match_id}`
- `GET /api/social/matches/{match_id}/report`
- `POST /api/social/match-requests`
- `POST /api/social/match-requests/{request_id}/respond`
- `POST /api/social/buddy`
- `POST /api/social/buddy/{request_id}/respond`

### 11.3 预期高相关组合

老组合仍应排得靠前：

- `xu_yining` 与 `he_zhuo`
- `qiao_meng` 与 `lin_yao`
- `su_wen` 与 `lin_yao`
- `he_zhuo` 与 `qiao_meng`

新增组合也应明显靠前：

- `xu_yining` 与 `jiang_nanxi`
- `he_zhuo` 与 `ran_ke`
- `lin_yao` 与 `zhou_yue`
- `su_wen` 与 `ye_qing`
- `qiao_meng` 与 `jiang_nanxi`
- `zhou_yue` 与 `tang_shuo`

### 11.4 算法检查点

匹配同学可以从下面几类信号观察排序是否合理：

- 静态画像信号
  - 学校、专业、兴趣、intent、avatar card 标签
- 行为主题信号
  - 日记高频词、聊天主题、广场帖子内容、评论主题
- 关系信号
  - 固定高频互动对象
  - 已有评论往返关系
  - 已有私聊关系
  - 新旧用户之间的跨圈层互动
- 记忆信号
  - `avatar_memories`
  - `memory_facts`
  - `anniversaries`

### 11.5 一个最小测试闭环

可以先用下面两条链路做最小闭环：

#### 工程/表达链路

1. 用 `xu_yining` 登录
2. 调 `GET /api/avatar/matches`
3. 看 `he_zhuo`、`jiang_nanxi`、`ran_ke` 是否都比较靠前
4. 调 `GET /api/social/matches`
5. 分别拉 `xu_yining <-> he_zhuo` 和 `xu_yining <-> jiang_nanxi` 的消息
6. 对比推荐理由和真实私聊是否一致

#### 内容/观察链路

1. 用 `lin_yao` 登录
2. 调 `GET /api/avatar/matches`
3. 看 `qiao_meng`、`zhou_yue`、`tang_shuo` 是否靠前
4. 调 `GET /api/social/matches`
5. 拉 `lin_yao <-> zhou_yue` 的消息和报告
6. 验证“对白、停顿、人物观察”有没有出现在解释里

## 12. 推荐交付给匹配同学的口径

> 这套种子数据不是随机测试样本，而是 10 个连续活跃 11 天的真实行为模拟。  
> 账号已经建好，用户名固定，密码统一为 `123456`。  
> 数据里同时有用户画像、AI 聊天、长日记、广场内容、评论点赞、已有匹配、私聊、纪念日和结构化记忆事实。  
> 现在除了原来的 5 人关系网络，还多了 5 个新用户，并且这些新用户既彼此形成关系，也和原有 5 人形成了新的跨圈层关系。  
> 请优先验证 `/api/avatar/matches` 和 `/api/social/matches` 的排序与解释是否符合既有互动网络，尤其关注 `xu_yining-he_zhuo`、`xu_yining-jiang_nanxi`、`he_zhuo-ran_ke`、`lin_yao-zhou_yue`、`su_wen-ye_qing`、`zhou_yue-tang_shuo` 这些组合。

## 13. 相关文件

- 种子脚本：`scripts/seed_realistic_may_2026.py`
- 本说明文档：`docs/REALISTIC_USER_DATA_2026_MAY.md`

