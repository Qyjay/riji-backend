"""为 kylin 用户生成 avatar 和 plaza 测试数据"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import random
import time
from uuid import uuid4
from app.database import SessionLocal
from sqlalchemy import text

# kylin 用户ID
KYLIN_USER_ID = "9e765c4a-cbd8-4d46-9a9b-b39876dcfd13"

# 其他用户ID（用于模拟他人行为）
OTHER_USER_IDS = [
    "a1b2c3d4-e5f6-4a5b-8c9d-e0f1a2b3c4d5",
    "b2c3d4e5-f6a7-4b8c-9d0e-f1a2b3c4d5e6",
    "c3d4e5f6-a7b8-4c9d-0e1f-a2b3c4d5e6f7",
    "d4e5f6a7-b8c9-4d0e-1f2a-b3c4d5e6f7a8",
    "e5f6a7b8-c9d0-4e1f-2a3b-c4d5e6f7a8b9",
    "f6a7b8c9-d0e1-4f2a-3b4c-d5e6f7a8b9c0",
    "a7b8c9d0-e1f2-4a3b-4c5d-e6f7a8b9c0d1",
    "b8c9d0e1-f2a3-4b4c-5d6e-f7a8b9c0d1e2",
]

db = SessionLocal()
now = int(time.time() * 1000)

def ts(days_ago=0, hours_ago=0):
    """生成时间戳"""
    return now - days_ago * 86400000 - hours_ago * 3600000

# ============== Avatar 数据 ==============

# 1. avatar_status - 分身状态（每用户一条）
avatar_statuses = [
    {
        "id": str(uuid4()),
        "user_id": KYLIN_USER_ID,
        "is_active": True,
        "browsed_count": random.randint(50, 200),
        "matched_count": random.randint(10, 50),
        "chatting_count": random.randint(2, 15),
        "last_active_at": ts(hours_ago=random.randint(0, 48)),
        "enabled_channels": json.dumps(["buddy", "help", "share", "dating"]),
        "enabled_actions": json.dumps(["browse", "match", "comment"]),
        "match_range": json.dumps({"school": "南开大学", "distanceKm": 15}),
    }
]
for uid in OTHER_USER_IDS[:3]:
    avatar_statuses.append({
        "id": str(uuid4()),
        "user_id": uid,
        "is_active": True,
        "browsed_count": random.randint(20, 100),
        "matched_count": random.randint(5, 30),
        "chatting_count": random.randint(1, 10),
        "last_active_at": ts(hours_ago=random.randint(0, 72)),
        "enabled_channels": json.dumps(["buddy", "help", "share"]),
        "enabled_actions": json.dumps(["browse", "match"]),
        "match_range": json.dumps({"school": "天津大学", "distanceKm": 10}),
    })

# 2. avatar_memories - 分身记忆库（多条）
memory_categories = ["preference", "personality", "habit", "emotion", "social", "study", "life"]
memory_data = [
    {"category": "preference", "content": "喜欢在晚上写日记，认为夜晚是反思的最佳时间", "tags": ["夜间", "日记", "习惯"]},
    {"category": "preference", "content": "偏好使用蓝色调，认为蓝色代表沉稳和理性", "tags": ["颜色", "蓝色", "审美"]},
    {"category": "personality", "content": "内向型人格，社交场合中倾向于倾听而非发言", "tags": ["内向", "倾听者"]},
    {"category": "personality", "content": "追求完美主义，对日记的排版和内容都有较高要求", "tags": ["完美主义", "日记"]},
    {"category": "habit", "content": "每周日晚上会进行一周总结，规划下一周的目标", "tags": ["周总结", "计划"]},
    {"category": "habit", "content": "习惯在日记中使用emoji来表达情绪", "tags": ["emoji", "表达"]},
    {"category": "emotion", "content": "最近面临期末考试压力，表现出焦虑情绪", "tags": ["考试", "焦虑", "压力"]},
    {"category": "emotion", "content": "对未来的职业规划感到迷茫，不确定是否要考研", "tags": ["职业规划", "迷茫", "考研"]},
    {"category": "emotion", "content": "与室友关系有些紧张，希望能改善相处模式", "tags": ["室友", "人际关系"]},
    {"category": "social", "content": "渴望找到志同道合的学习伙伴，特别是编程方向的", "tags": ["学习伙伴", "编程", "南开大学"]},
    {"category": "social", "content": "对搭子文化感兴趣，想尝试找到一起学习的伙伴", "tags": ["搭子", "学习"]},
    {"category": "study", "content": "正在学习数据结构与算法，准备秋招面试", "tags": ["数据结构", "算法", "秋招"]},
    {"category": "study", "content": "参加了学校的软件工程比赛，需要团队协作", "tags": ["比赛", "团队协作"]},
    {"category": "life", "content": "最近开始健身，每周去三次健身房", "tags": ["健身", "健康"]},
    {"category": "life", "content": "喜欢摄影，会用手机记录校园风景", "tags": ["摄影", "校园"]},
    {"category": "personality", "content": "喜欢阅读科幻小说，特别喜欢刘慈欣的作品", "tags": ["阅读", "科幻", "刘慈欣"]},
    {"category": "preference", "content": "咖啡爱好者，每天需要一杯咖啡才能清醒", "tags": ["咖啡", "提神"]},
    {"category": "emotion", "content": "对即将到来的暑假有期待，计划学习新技能", "tags": ["暑假", "计划"]},
    {"category": "social", "content": "在班级里担任学习委员，需要帮助同学解答问题", "tags": ["学习委员", "班级"]},
    {"category": "habit", "content": "习惯用碎片时间背单词，每天通勤时学习", "tags": ["单词", "通勤"]},
]

avatar_memories = []
for i, mem in enumerate(memory_data):
    avatar_memories.append({
        "id": str(uuid4()),
        "user_id": KYLIN_USER_ID,
        "category": mem["category"],
        "content": mem["content"],
        "source": random.choice(["diary", "chat", "manual", "behavior"]),
        "source_ref": f"ref_{i}",
        "confidence": round(random.uniform(0.7, 1.0), 2),
        "is_active": True,
        "is_pinned": i < 5,
        "need_type": random.choice([None, "study", "social", "emotion"]),
        "urgency": random.choice([None, "high", "medium", "low"]),
        "expiry": None if random.random() > 0.3 else ts(days_ago=-30),
        "match_status": random.choice([None, "matched", "pending", "rejected"]),
        "tags": json.dumps(mem["tags"]),
        "created_at": ts(days_ago=random.randint(1, 30)),
        "updated_at": ts(days_ago=random.randint(0, 5)),
    })

# 3. avatar_profiles - 分身侧写（每用户一条）
avatar_profiles = [{
    "id": str(uuid4()),
    "user_id": KYLIN_USER_ID,
    "summary": "南开大学软件工程大三学生，内向但善于思考，追求完美主义。对编程有强烈兴趣，正在为秋招做准备。喜欢在夜间反思和写日记，用emoji表达情绪。面临考试压力和职业规划迷茫，希望能找到学习伙伴。最近开始健身，培养新爱好。担任班级学习委员，有一定责任感。",
    "diary_count": 17,
    "chat_count": 73,
    "generated_at": ts(hours_ago=24),
}]

# 4. avatar_matches - 推荐匹配
avatar_matches_data = [
    {"score": 85, "reasons": ["同为软件工程专业", "都在准备秋招", "都有健身习惯"], "status": "pending"},
    {"score": 78, "reasons": ["南开大学校友", "喜欢摄影", "内向型人格"], "status": "new"},
    {"score": 72, "reasons": ["对科幻感兴趣", "咖啡爱好者"], "status": "matched"},
    {"score": 68, "reasons": ["面临相似考试压力", "想要找学习伙伴"], "status": "new"},
    {"score": 65, "reasons": ["参加软件工程比赛", "需要团队协作"], "status": "pending"},
]

# 先创建一些 plaza_posts 作为匹配来源
plaza_posts_for_match = []
post_types = ["find_partner", "help", "share", "love"]
post_contents = {
    "find_partner": [
        "找个一起刷算法题的学习搭子！我是软件工程的，有没有人想一起组队学习",
        "暑假想找个托福学习伙伴，互相监督打卡",
        "寻找同样准备秋招的后端开发同学，可以一起mock面试",
        "有没有喜欢摄影的同学？想组队去拍天津之眼",
        "找个一起健身的搭子，健身房在天津大学附近",
    ],
    "help": [
        "期末数据结构考试好慌，有没有大佬能帮忙讲讲图论",
        "软件工程比赛需要前端开发，有没有愿意组队的",
        "对考研还是就业很迷茫，有没有学长学姐能分享经验",
        "南开附近有什么适合自习的咖啡厅推荐吗",
        "室友关系有点紧张怎么处理啊，求建议",
    ],
    "share": [
        "今天在图书馆发现了一个超棒的自习位置，安静还有插座",
        "终于把算法笔记整理完了，分享给需要的小伙伴",
        "健身第30天，减了5斤，继续加油",
        "拍到了超级美的晚霞，南开的天空太美了",
        "推荐一本书《被讨厌的勇气》，真的改变了我很多",
    ],
    "love": [
        "喜欢上一起上自习的女生，要不要表白啊好纠结",
        "有人在图书馆遇到过那个经常坐靠窗位置的女生吗",
        "谈恋爱会影响学习吗，想听听大家看法",
        "有没有人和我一样，觉得单身也挺好的",
    ],
}

for i, (ptype, contents) in enumerate(post_contents.items()):
    for j, content in enumerate(contents):
        post_id = str(uuid4())
        plaza_posts_for_match.append({
            "id": post_id,
            "user_id": random.choice(OTHER_USER_IDS),
            "type": ptype,
            "content": content,
            "images": json.dumps([]),
            "location": random.choice(["南开大学", "天津大学", "天津图书馆", ""]),
            "tags": json.dumps(random.sample(["学习", "搭子", "求助", "分享", "恋爱", "健身", "摄影"], 2)),
            "likes": random.randint(0, 50),
            "comments": random.randint(0, 20),
            "agent_responses": random.randint(0, 3),
            "is_from_agent": False,
            "allow_agent_reply": True,
            "school_only": random.choice([True, False]),
            "created_at": ts(days_ago=random.randint(0, 14)),
        })

avatar_matches = []
for i, match_data in enumerate(avatar_matches_data):
    if i < len(plaza_posts_for_match):
        avatar_matches.append({
            "id": str(uuid4()),
            "user_id": KYLIN_USER_ID,
            "post_id": plaza_posts_for_match[i]["id"],
            "match_score": match_data["score"],
            "match_reasons": json.dumps(match_data["reasons"]),
            "agent_conversation": json.dumps([
                {"role": "user", "content": "推荐这篇帖子给你"},
                {"role": "assistant", "content": "好的，我看看这篇帖子觉得很适合你，你们有很多共同点。"}
            ]),
            "status": match_data["status"],
            "created_at": ts(days_ago=random.randint(0, 7)),
        })

# ============== Plaza 数据 ==============

# 1. plaza_posts - 更多帖子
plaza_posts = list(plaza_posts_for_match)

# 添加更多帖子（模拟不同用户发布）
more_posts = [
    {"type": "find_partner", "content": "计算机组成原理期末project组队，还缺一个人，有兴趣的私我", "school": "南开大学"},
    {"type": "help", "content": "有没有人知道南开图书馆的预约系统怎么用啊", "school": "南开大学"},
    {"type": "share", "content": "今天食堂的麻辣香锅太好吃了，必须安利给大家", "school": "南开大学"},
    {"type": "love", "content": "在体育馆看到一个打羽毛球的女生，动作好优美", "school": "天津大学"},
    {"type": "find_partner", "content": "MBA备考群有没有人想一起加入的", "school": "天津大学"},
    {"type": "help", "content": "秋招简历求修改，可以有偿，有意向的戳我", "school": "南开大学"},
    {"type": "share", "content": "考研自习室发现了一个宝藏位置，人少安静", "school": "南开大学"},
    {"type": "love", "content": "表白信科的那个戴眼镜的男生，笑起来好温暖", "school": "南开大学"},
    {"type": "find_partner", "content": "创业比赛找技术合伙人，有想法的来", "school": "天津大学"},
    {"type": "help", "content": "天津还有什么好吃的地方啊，求推荐", "school": "南开大学"},
    {"type": "share", "content": "第一次参加黑客松，拿了个优秀奖开心", "school": "天津大学"},
    {"type": "love", "content": "有人也是母胎solo到现在的吗", "school": "南开大学"},
    {"type": "find_partner", "content": "周六去爬长城有没有一起的", "school": "南开大学"},
    {"type": "help", "content": "代码出了bug调了两天还没解决，心态崩了", "school": "南开大学"},
    {"type": "share", "content": "今天终于把分布式系统的项目做完了", "school": "南开大学"},
]

for post in more_posts:
    plaza_posts.append({
        "id": str(uuid4()),
        "user_id": random.choice(OTHER_USER_IDS),
        "type": post["type"],
        "content": post["content"],
        "images": json.dumps([]),
        "location": post["school"],
        "tags": json.dumps(["搭子" if post["type"] == "find_partner" else random.choice(["求助", "分享", "恋爱"])]),
        "likes": random.randint(0, 100),
        "comments": random.randint(0, 30),
        "agent_responses": random.randint(0, 5),
        "is_from_agent": False,
        "allow_agent_reply": True,
        "school_only": False,
        "created_at": ts(days_ago=random.randint(0, 21)),
    })

# 2. plaza_comments - 评论
plaza_comments = []
comment_templates = [
    "太棒了，我也想找一个",
    "加我一个可以吗",
    "已加入，等你回复",
    "同感同感，我也有类似的经历",
    "这个建议好棒，谢谢分享",
    "请问有微信吗，想详细了解一下",
    "已私，期待回复",
    "我也遇到了同样的问题",
    "加油！你一定可以的",
    "哇，这也太厉害了吧",
    "求带！我也想参与",
    "mark一下，回头试试",
]

for post in plaza_posts[:20]:  # 为前20个帖子添加评论
    num_comments = random.randint(1, 5)
    for _ in range(num_comments):
        plaza_comments.append({
            "id": str(uuid4()),
            "post_id": post["id"],
            "user_id": random.choice(OTHER_USER_IDS + [KYLIN_USER_ID]),
            "content": random.choice(comment_templates),
            "is_agent": random.random() < 0.1,
            "created_at": ts(days_ago=random.randint(0, 14)),
        })

# 3. post_likes - 点赞
post_likes = []
for post in plaza_posts:
    # 随机点赞人数
    num_likes = random.randint(2, 15)
    likers = random.sample(OTHER_USER_IDS + [KYLIN_USER_ID], min(num_likes, len(OTHER_USER_IDS) + 1))
    for liker in likers:
        post_likes.append({
            "id": str(uuid4()),
            "post_id": post["id"],
            "user_id": liker,
            "created_at": ts(days_ago=random.randint(0, 14)),
        })

# ============== 插入数据库 ==============

def insert_data(table, data_list, columns):
    if not data_list:
        return
    for data in data_list:
        cols = ", ".join(columns)
        placeholders = ", ".join([f":{c}" for c in columns])
        sql = f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({placeholders})"
        try:
            db.execute(sql, data)
        except Exception as e:
            print(f"Insert error: {e}")

print("插入 avatar_status 数据...")
for s in avatar_statuses:
    db.execute(text("""INSERT OR REPLACE INTO avatar_status (id, user_id, is_active, browsed_count, matched_count, chatting_count, last_active_at, enabled_channels, enabled_actions, match_range)
                   VALUES (:id, :user_id, :is_active, :browsed_count, :matched_count, :chatting_count, :last_active_at, :enabled_channels, :enabled_actions, :match_range)"""), s)

print("插入 avatar_memories 数据...")
for m in avatar_memories:
    db.execute(text("""INSERT INTO avatar_memories (id, user_id, category, content, source, source_ref, confidence, is_active, is_pinned, need_type, urgency, expiry, match_status, tags, created_at, updated_at)
                   VALUES (:id, :user_id, :category, :content, :source, :source_ref, :confidence, :is_active, :is_pinned, :need_type, :urgency, :expiry, :match_status, :tags, :created_at, :updated_at)"""), m)

print("插入 avatar_profiles 数据...")
for p in avatar_profiles:
    db.execute(text("""INSERT OR REPLACE INTO avatar_profiles (id, user_id, summary, diary_count, chat_count, generated_at)
                   VALUES (:id, :user_id, :summary, :diary_count, :chat_count, :generated_at)"""), p)

print("插入 plaza_posts 数据...")
for p in plaza_posts:
    db.execute(text("""INSERT INTO plaza_posts (id, user_id, type, content, images, location, tags, likes, comments, agent_responses, is_from_agent, allow_agent_reply, school_only, created_at)
                   VALUES (:id, :user_id, :type, :content, :images, :location, :tags, :likes, :comments, :agent_responses, :is_from_agent, :allow_agent_reply, :school_only, :created_at)"""), p)

print("插入 plaza_comments 数据...")
for c in plaza_comments:
    db.execute(text("""INSERT INTO plaza_comments (id, post_id, user_id, content, is_agent, created_at)
                   VALUES (:id, :post_id, :user_id, :content, :is_agent, :created_at)"""), c)

print("插入 post_likes 数据...")
for l in post_likes:
    db.execute(text("""INSERT OR IGNORE INTO post_likes (id, post_id, user_id, created_at)
                   VALUES (:id, :post_id, :user_id, :created_at)"""), l)

print("插入 avatar_matches 数据...")
for m in avatar_matches:
    db.execute(text("""INSERT INTO avatar_matches (id, user_id, post_id, match_score, match_reasons, agent_conversation, status, created_at)
                   VALUES (:id, :user_id, :post_id, :match_score, :match_reasons, :agent_conversation, :status, :created_at)"""), m)

db.commit()
print("\n数据插入完成！")

# 统计
print("\n数据统计:")
for table in ["avatar_status", "avatar_memories", "avatar_profiles", "avatar_matches", "plaza_posts", "plaza_comments", "post_likes"]:
    result = db.execute(text(f"SELECT COUNT(*) FROM {table} WHERE user_id = :uid"), {"uid": KYLIN_USER_ID}).fetchone()
    total = db.execute(text(f"SELECT COUNT(*) FROM {table}")).fetchone()
    print(f"  {table}: kylin={result[0] if result else 0}, total={total[0]}")

db.close()