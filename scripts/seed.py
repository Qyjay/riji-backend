"""
种子数据脚本
创建测试用户 + 日记 + 番茄钟 + 待办

运行方式：
    python scripts/seed.py
"""
import json
import sys
import os
import time
from uuid import uuid4

# 将项目根目录加入 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, init_db
from app.models.user import User, UserSettings
from app.models.diary import Diary
from app.models.study import Pomodoro, Todo
from app.auth.service import hash_password


def now_ms():
    """当前毫秒时间戳"""
    return int(time.time() * 1000)


def days_ago_ms(days: int) -> int:
    """N 天前的毫秒时间戳"""
    return int((time.time() - days * 86400) * 1000)


# ==================== 测试用户数据 ====================

USERS = [
    {
        "username": "kylin",
        "password": "123456",
        "name": "麒麟",
        "school": "南开大学",
        "major": "软件工程",
        "grade": "大三",
        "signature": "每天进步一点点 🌟",
    },
    {
        "username": "xiaolu",
        "password": "123456",
        "name": "小鹿",
        "school": "天津大学",
        "major": "计算机科学",
        "grade": "大二",
        "signature": "代码改变世界 💻",
    },
    {
        "username": "test",
        "password": "123456",
        "name": "测试同学",
        "school": "测试大学",
        "major": "测试专业",
        "grade": "大一",
        "signature": "这只是个测试账号",
    },
]

# ==================== 日记模板 ====================

DIARY_TEMPLATES = [
    {
        "content": "今天去图书馆学习了一整天，感觉充实极了！下午喝了一杯奶茶，甜甜的，整个人都精神了。晚上和室友一起看了电影，很开心。",
        "emotion": {"emoji": "😊", "label": "开心", "score": 85},
        "tags": ["学习", "图书馆", "奶茶", "室友"],
        "weather": "晴",
        "location": "图书馆",
        "style": "日记式",
    },
    {
        "content": "考试周压力好大，感觉脑子都要爆炸了。已经连续学习6小时，番茄钟完成了8个，但还是有好多没看完。加油！",
        "emotion": {"emoji": "😰", "label": "焦虑", "score": 35},
        "tags": ["考试", "复习", "压力", "坚持"],
        "weather": "阴",
        "location": "宿舍",
        "style": "日记式",
    },
    {
        "content": "今天课程结束后，一个人漫步在校园里。秋天的银杏叶黄了，风吹过来有点凉，但心里暖暖的。这就是大学生活吧。",
        "emotion": {"emoji": "🍂", "label": "平静", "score": 70},
        "tags": ["散步", "校园", "秋天", "思考"],
        "weather": "多云",
        "location": "校园",
        "style": "散文式",
    },
    {
        "content": "社团活动今天举办了新生欢迎会，认识了好多新朋友！大家来自五湖四海，聊得特别投机。感觉大学生活越来越丰富多彩了。",
        "emotion": {"emoji": "🎉", "label": "兴奋", "score": 92},
        "tags": ["社团", "新朋友", "欢迎会", "交友"],
        "weather": "晴",
        "location": "学生活动中心",
        "style": "日记式",
    },
    {
        "content": "今天收到了实习 offer，终于不用愁暑假了！虽然薪资不高，但是大公司的经验很宝贵。和父母视频通话，他们都很开心。",
        "emotion": {"emoji": "🎊", "label": "激动", "score": 95},
        "tags": ["实习", "offer", "工作", "成长"],
        "weather": "晴",
        "location": "宿舍",
        "style": "日记式",
    },
]

# ==================== 番茄钟模板 ====================

POMODORO_TEMPLATES = [
    {"task": "高数复习", "subject": "数学", "duration": 25},
    {"task": "英语四级单词", "subject": "英语", "duration": 25},
    {"task": "操作系统课程预习", "subject": "计算机", "duration": 50},
    {"task": "Python 项目实践", "subject": "编程", "duration": 25},
    {"task": "论文文献阅读", "subject": "研究", "duration": 50},
]

# ==================== 待办模板 ====================

TODO_TEMPLATES = [
    {"content": "完成高数作业", "priority": "high"},
    {"content": "预约体育馆", "priority": "low"},
    {"content": "给辅导员发邮件", "priority": "medium"},
    {"content": "复习数据结构", "priority": "high"},
    {"content": "买新的笔记本", "priority": "low"},
]


def create_user(db, user_data: dict) -> User:
    """创建用户（如已存在则跳过）"""
    existing = db.query(User).filter(User.username == user_data["username"]).first()
    if existing:
        print(f"  用户 {user_data['username']} 已存在，跳过")
        return existing

    now = now_ms()
    user = User(
        id=str(uuid4()),
        username=user_data["username"],
        password=hash_password(user_data["password"]),
        name=user_data.get("name", ""),
        school=user_data.get("school", ""),
        major=user_data.get("major", ""),
        grade=user_data.get("grade", ""),
        signature=user_data.get("signature", ""),
        level=1,
        xp=0,
        created_at=now,
        updated_at=now,
    )
    db.add(user)

    # 创建默认设置
    settings = UserSettings(
        id=str(uuid4()),
        user_id=user.id,
    )
    db.add(settings)
    db.flush()

    print(f"  创建用户: {user.username} ({user.name})")
    return user


def create_diaries(db, user: User):
    """为用户创建 5 篇测试日记"""
    count = 0
    for i, template in enumerate(DIARY_TEMPLATES):
        diary = Diary(
            id=str(uuid4()),
            user_id=user.id,
            content=template["content"],
            images=json.dumps([]),
            emotion=json.dumps(template["emotion"]),
            tags=json.dumps(template["tags"]),
            weather=template.get("weather", ""),
            location=template.get("location", ""),
            style=template.get("style", "日记式"),
            created_at=days_ago_ms(i * 2),      # 每隔 2 天
            updated_at=days_ago_ms(i * 2),
        )
        db.add(diary)
        count += 1

    user.diary_count = count
    print(f"  创建日记: {count} 篇")


def create_pomodoros(db, user: User):
    """为用户创建番茄钟记录"""
    count = 0
    for i, template in enumerate(POMODORO_TEMPLATES):
        created = days_ago_ms(i)
        completed = created + template["duration"] * 60 * 1000  # 完成时间
        pomodoro = Pomodoro(
            id=str(uuid4()),
            user_id=user.id,
            task=template["task"],
            subject=template["subject"],
            duration=template["duration"],
            completed_at=completed,
            created_at=created,
        )
        db.add(pomodoro)
        count += 1

    user.pomodoro_count = count
    print(f"  创建番茄钟: {count} 个")


def create_todos(db, user: User):
    """为用户创建待办事项"""
    count = 0
    for i, template in enumerate(TODO_TEMPLATES):
        todo = Todo(
            id=str(uuid4()),
            user_id=user.id,
            content=template["content"],
            completed=i < 2,  # 前 2 个标记为已完成
            priority=template["priority"],
            created_at=days_ago_ms(i),
        )
        db.add(todo)
        count += 1

    print(f"  创建待办: {count} 个（其中 2 个已完成）")


def main():
    print("=" * 50)
    print("日迹 App - 种子数据初始化")
    print("=" * 50)

    # 初始化数据库（创建表）
    print("\n[1] 初始化数据库...")
    init_db()
    print("  数据库表创建完成")

    db = SessionLocal()
    try:
        for user_data in USERS:
            print(f"\n[+] 处理用户: {user_data['username']}")
            user = create_user(db, user_data)
            create_diaries(db, user)
            create_pomodoros(db, user)
            create_todos(db, user)

        db.commit()
        print("\n" + "=" * 50)
        print("✓ 种子数据初始化完成！")
        print("\n测试账号：")
        for u in USERS:
            print(f"  用户名: {u['username']:<10} 密码: {u['password']}")
        print("\n启动服务：uvicorn app.main:app --reload")
        print("Swagger 文档：http://localhost:8000/docs")
        print("=" * 50)

    except Exception as e:
        db.rollback()
        print(f"\n✗ 初始化失败: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
