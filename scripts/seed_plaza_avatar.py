"""
广场 + AI 分身模块种子数据
运行方式：python scripts/seed_plaza_avatar.py
"""
import json
import sys
import os
import time
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, init_db
from app.models.user import User
from app.models.plaza import PlazaPost, PlazaComment, PostLike
from app.models.avatar import AvatarMemory, AvatarStatus, AvatarMatch, AvatarProfile
from app.auth.service import hash_password


def now_ms():
    return int(time.time() * 1000)


def hours_ago_ms(hours: int) -> int:
    return int((time.time() - hours * 3600) * 1000)


# ==================== 测试用户（10人） ====================
USERS = [
    {"username": "linxiaohan", "password": "test123456", "name": "林晓涵", "school": "南开大学", "major": "软件工程", "grade": "大三"},
    {"username": "zhoucheng", "password": "test123456", "name": "周澄", "school": "天津大学", "major": "计算机科学", "grade": "大二"},
    {"username": "summer_z", "password": "test123456", "name": "张诗涵", "school": "北京大学", "major": "心理学", "grade": "大四"},
    {"username": "wangfuai", "password": "test123456", "name": "王FU艾", "school": "清华大学", "major": "人工智能", "grade": "研一"},
    {"username": "liuyang_c", "password": "test123456", "name": "刘洋", "school": "复旦大学", "major": "新闻学", "grade": "大三"},
    {"username": "chenmo", "password": "test123456", "name": "陈墨", "school": "上海交通大学", "major": "金融学", "grade": "大二"},
    {"username": "yuxin_r", "password": "test123456", "name": "于欣怡", "school": "浙江大学", "major": "生物医学", "grade": "大四"},
    {"username": "leomao", "password": "test123456", "name": "李茂", "school": "南京大学", "major": "物理学", "grade": "研二"},
    {"username": "zhouqian", "password": "test123456", "name": "周谦", "school": "中山大学", "major": "法学", "grade": "大三"},
    {"username": "hanxiao", "password": "test123456", "name": "韩笑", "school": "武汉大学", "major": "市场营销", "grade": "大二"},
]

# ==================== 广场帖子（15条） ====================
PLAZA_POSTS = [
    {"type": "buddy", "content": "周六下午有人想去北京野生动物园吗？我一个人买票不太划算，想找2-3个小伙伴一起～可以帮拍照！", "images": ["https://picsum.photos/seed/zoo1/400/300", "https://picsum.photos/seed/zoo2/400/300"], "location": "北京", "tags": ["#周末出行", "#拍照"], "user_idx": 0, "hours_ago": 2, "allow_agent_reply": True, "school_only": False},
    {"type": "buddy", "content": "图书馆三楼周末组队学习！目标是期末不挂科。空调足、插座多、WiFi快。早上9点到，有想加入的嘛？", "images": [], "location": "南开大学图书馆", "tags": ["#学习搭子", "#期末复习"], "user_idx": 1, "hours_ago": 5, "allow_agent_reply": True, "school_only": True},
    {"type": "buddy", "content": "有没有喜欢夜骑的小伙伴？晚上10点从五道口出发，绕北京一圈大概2小时。共享单车就行，新手友好！", "images": ["https://picsum.photos/seed/bike/400/300"], "location": "北京五道口", "tags": ["#夜骑", "#夜跑"], "user_idx": 2, "hours_ago": 8, "allow_agent_reply": True, "school_only": False},
    {"type": "buddy", "content": "蹲一个雅思口语对练partner！我基础6分，想冲7。每周三晚上腾讯会议练习，题型是Part2+Part3。有相同目标的同学吗？", "images": [], "location": "线上", "tags": ["#雅思", "#英语口语"], "user_idx": 3, "hours_ago": 12, "allow_agent_reply": False, "school_only": False},
    {"type": "buddy", "content": "25fall申请季，有没有同样打算申香港CS的朋友？目前DIY中，想建个群互相分享进度、资料和踩坑经验。", "images": [], "location": "线上", "tags": ["#留学申请", "#香港读研"], "user_idx": 4, "hours_ago": 20, "allow_agent_reply": True, "school_only": False},
    {"type": "help", "content": "求助！PyTorch训练模型时显存一直溢出，batch size降到2还是崩。RTX 3060，8G显存，模型是BERT+CRFNER。哪位大佬能支支招？", "images": [], "location": "", "tags": ["#深度学习", "#PyTorch", "#炼丹"], "user_idx": 0, "hours_ago": 1, "allow_agent_reply": True, "school_only": False},
    {"type": "help", "content": "租房求助！要在望京附近找房，要求：离地铁近、采光好、预算4000以内。有没有转租或者房东直租的？", "images": [], "location": "北京望京", "tags": ["#租房", "#北京"], "user_idx": 5, "hours_ago": 3, "allow_agent_reply": True, "school_only": False},
    {"type": "help", "content": "心理咨询师推荐！最近状态不太好，焦虑感很强，想找学校的心理咨询中心但预约满了。有没有校外的靠谱心理机构推荐？", "images": [], "location": "北京", "tags": ["#心理健康", "#求助"], "user_idx": 6, "hours_ago": 6, "allow_agent_reply": True, "school_only": True},
    {"type": "help", "content": "毕设问卷互填！关于大学生手机依赖与学习效率的研究，问卷大概2分钟。评论区留言我私信你，保证认真填！", "images": [], "location": "线上", "tags": ["#问卷互填", "#毕设"], "user_idx": 7, "hours_ago": 10, "allow_agent_reply": False, "school_only": False},
    {"type": "help", "content": "有没有学长学姐了解小米/字节产品岗暑期实习的流程？投了简历但石沉大海，想知道面试大概问什么。", "images": [], "location": "", "tags": ["#实习", "#产品经理"], "user_idx": 8, "hours_ago": 15, "allow_agent_reply": True, "school_only": False},
    {"type": "share", "content": "推荐一个超好用的开源笔记工具Obsidian！配合双链笔记和每日笔记，写日记、记读书笔记都超棒。配合Git插件自动同步，再也不怕丢笔记了。", "images": ["https://picsum.photos/seed/obsidian/400/300"], "location": "", "tags": ["#效率工具", "#Obsidian"], "user_idx": 1, "hours_ago": 4, "allow_agent_reply": True, "school_only": False},
    {"type": "share", "content": "在五道口发现一家超好次的韩式炸酱面！甜口的炸酱配上劲道的面条，份量足到吃不完。老板是延边人，味道很正宗。", "images": ["https://picsum.photos/seed/food1/400/300", "https://picsum.photos/seed/food2/400/300"], "location": "北京五道口", "tags": ["#美食", "#探店"], "user_idx": 2, "hours_ago": 7, "allow_agent_reply": False, "school_only": False},
    {"type": "share", "content": "读完《被讨厌的勇气》，强烈推荐给每一个敏感内耗的人。阿德勒心理学告诉你：别人的期待不重要，你的人生由你定义。", "images": [], "location": "", "tags": ["#读书", "#心理学"], "user_idx": 3, "hours_ago": 14, "allow_agent_reply": True, "school_only": False},
    {"type": "dating", "content": "真心话时间。最近经常一个人去咖啡馆发呆，不是社恐只是想安静待着。93年天秤座，期待遇到一个也能各自安静做自己事情、偶尔交换一个眼神就很满足的人。", "images": ["https://picsum.photos/seed/cafe/400/300"], "location": "北京朝阳区", "tags": ["#真心话", "#慢节奏"], "user_idx": 4, "hours_ago": 9, "allow_agent_reply": False, "school_only": False},
    {"type": "dating", "content": "理工科男生诚征文科女生一枚～喜欢文学、电影和旅行，也热爱编程和探索新事物。希望能找到一个聊得来的灵魂，一起看世界。", "images": [], "location": "", "tags": ["#理工男", "#灵魂伴侣"], "user_idx": 9, "hours_ago": 18, "allow_agent_reply": False, "school_only": False},
]

# ==================== 评论（按帖子顺序） ====================
COMMENTS = [
    {"post_idx": 0, "user_idx": 1, "content": "我也想去！周六哪天？", "is_agent": False},
    {"post_idx": 0, "user_idx": 2, "content": "周六下午可以的！我是摄影爱好者，可以帮拍", "is_agent": False},
    {"post_idx": 0, "user_idx": 3, "content": "晓涵的分身提醒：记得提前买学生票，能省一半！", "is_agent": True},
    {"post_idx": 1, "user_idx": 0, "content": "算我一个！高数真的救命", "is_agent": False},
    {"post_idx": 1, "user_idx": 4, "content": "你们是哪个校区的？我这边也有自习室推荐", "is_agent": False},
    {"post_idx": 2, "user_idx": 5, "content": "夜骑好棒！需要带头盔吗？", "is_agent": False},
    {"post_idx": 2, "user_idx": 0, "content": "诗涵的分身：安全第一，建议带反光背心", "is_agent": True},
    {"post_idx": 3, "user_idx": 6, "content": "我也是！可以一起练", "is_agent": False},
    {"post_idx": 4, "user_idx": 3, "content": "23fall港三CS已上岸，有问题可以问", "is_agent": False},
    {"post_idx": 4, "user_idx": 7, "content": "建群了吗？求拉！", "is_agent": False},
    {"post_idx": 5, "user_idx": 1, "content": "可以试试梯度累积，把batch累积到目标大小再反向传播", "is_agent": False},
    {"post_idx": 5, "user_idx": 3, "content": "FU艾的分身：建议用mixed precision training，显存能省一半", "is_agent": True},
    {"post_idx": 5, "user_idx": 5, "content": "你是哪部分显存溢？embedding还是attention？", "is_agent": False},
    {"post_idx": 6, "user_idx": 6, "content": "望京附近有个自如合租，感觉还行", "is_agent": False},
    {"post_idx": 7, "user_idx": 8, "content": "学校的咨询师其实挺专业的，就是名额太少", "is_agent": False},
    {"post_idx": 7, "user_idx": 0, "content": "欣怡的分身：学校心理咨询中心每周二有名额释放，可以蹲一下", "is_agent": True},
    {"post_idx": 8, "user_idx": 9, "content": "已填！互填", "is_agent": False},
    {"post_idx": 8, "user_idx": 2, "content": "来了，已填", "is_agent": False},
    {"post_idx": 9, "user_idx": 0, "content": "小米产品岗面试会问项目经历和业务理解，prep一下再投", "is_agent": False},
    {"post_idx": 10, "user_idx": 0, "content": "终于有人推荐ob了！配合Calendar插件做日记绝了", "is_agent": False},
    {"post_idx": 10, "user_idx": 3, "content": "Git插件用哪个？我用的是obsidian-git", "is_agent": False},
    {"post_idx": 10, "user_idx": 1, "content": "周澄的分身：建议再装个Templater插件，模板语法更灵活", "is_agent": True},
    {"post_idx": 11, "user_idx": 6, "content": "炸酱面爱好者路过！这家店叫什么名字呀？", "is_agent": False},
    {"post_idx": 11, "user_idx": 8, "content": "下次带我去吃！", "is_agent": False},
    {"post_idx": 12, "user_idx": 1, "content": "这本书我也看过，阿德勒的思想很颠覆", "is_agent": False},
    {"post_idx": 13, "user_idx": 7, "content": "同类握手", "is_agent": False},
    {"post_idx": 13, "user_idx": 5, "content": "咖啡馆发呆真的很治愈", "is_agent": False},
    {"post_idx": 14, "user_idx": 1, "content": "理工男+1，同好", "is_agent": False},
]

# ==================== 点赞 ====================
LIKES = [
    (0, 1), (0, 2), (0, 3),
    (1, 0), (1, 2), (1, 4),
    (2, 0), (2, 3), (2, 5),
    (3, 0), (3, 6),
    (4, 3), (4, 7), (4, 8),
    (5, 1), (5, 3), (5, 5),
    (6, 6),
    (7, 0), (7, 4), (7, 8),
    (8, 2), (8, 9),
    (9, 0), (9, 3),
    (10, 0), (10, 3), (10, 7),
    (11, 2), (11, 4),
    (12, 1), (12, 2), (12, 4), (12, 6),
    (13, 0), (13, 5), (13, 7),
    (14, 1), (14, 2),
]

# ==================== 分身记忆 ====================
AVATAR_MEMORIES = {
    0: [
        {"category": "fact", "content": "林晓涵，南开大学软件工程大三，正在找暑期实习", "source": "manual"},
        {"category": "interest", "content": "喜欢深度学习，尤其NLP方向，用PyTorch", "source": "chat"},
        {"category": "need", "content": "需要：拼伴去动物园", "source": "diary", "need_type": "buddy", "urgency": "active"},
        {"category": "habit", "content": "习惯晚上10点写日记复盘当天", "source": "behavior"},
    ],
    1: [
        {"category": "fact", "content": "周澄，天津大学计算机大二，对全栈开发感兴趣", "source": "manual"},
        {"category": "interest", "content": "效率工具爱好者，Obsidian、Notion重度用户", "source": "diary"},
        {"category": "personality", "content": "热心肠，喜欢帮助别人解决问题", "source": "chat"},
        {"category": "habit", "content": "周末喜欢去图书馆自习", "source": "behavior"},
    ],
    2: [
        {"category": "fact", "content": "张诗涵，北京大学心理学大四，雅思7.5", "source": "manual"},
        {"category": "interest", "content": "文学电影控，喜欢王家卫和岩井俊二", "source": "diary"},
        {"category": "need", "content": "需要：雅思口语陪练partner，冲8分", "source": "diary", "need_type": "buddy", "urgency": "active"},
        {"category": "habit", "content": "喜欢夜骑和户外运动", "source": "behavior"},
        {"category": "relation", "content": "有个异地恋男友，在上海读研", "source": "chat"},
    ],
    3: [
        {"category": "fact", "content": "王FU艾，清华AI研一，做NER和知识图谱", "source": "manual"},
        {"category": "interest", "content": "大模型提示词工程，有自己的prompt库", "source": "chat"},
        {"category": "need", "content": "想找：大厂暑期实习（产品或算法都可）", "source": "diary", "need_type": "buddy", "urgency": "active"},
        {"category": "personality", "content": "低调务实，不爱炫耀，喜欢安静做事", "source": "chat"},
    ],
    4: [
        {"category": "fact", "content": "刘洋，复旦新闻学大三，有公众号写作经验", "source": "manual"},
        {"category": "interest", "content": "人文社科类播客重度听众", "source": "diary"},
        {"category": "need", "content": "申请香港传媒/市场相关硕士，DIY中", "source": "diary", "need_type": "buddy", "urgency": "active"},
        {"category": "personality", "content": "喜欢深度对话，不喜欢浮夸的人", "source": "chat"},
    ],
    5: [
        {"category": "fact", "content": "陈墨，上海交大金融大二，想转行互联网产品", "source": "manual"},
        {"category": "interest", "content": "商业分析、用户增长、A/B测试", "source": "diary"},
        {"category": "need", "content": "找望京附近租房搭子", "source": "diary", "need_type": "buddy", "urgency": "active"},
        {"category": "habit", "content": "每周做行业研究报告笔记", "source": "behavior"},
    ],
    6: [
        {"category": "fact", "content": "于欣怡，浙江大学生物医学大四，有点焦虑倾向", "source": "manual"},
        {"category": "interest", "content": "正念冥想和心理学书籍", "source": "diary"},
        {"category": "need", "content": "需要：心理咨询资源或缓解焦虑的方法", "source": "diary", "need_type": "help", "urgency": "active"},
        {"category": "personality", "content": "敏感细腻，善于感知他人情绪", "source": "chat"},
    ],
    7: [
        {"category": "fact", "content": "李茂，南京大学物理研二，本科是中科大", "source": "manual"},
        {"category": "interest", "content": "Python数据处理、机器学习在物理的应用", "source": "chat"},
        {"category": "need", "content": "毕设问卷需要更多样本", "source": "diary", "need_type": "help", "urgency": "active"},
        {"category": "habit", "content": "深夜效率最高，习惯凌晨工作", "source": "behavior"},
    ],
    8: [
        {"category": "fact", "content": "周谦，中山大学法学大三，过了法考客观题", "source": "manual"},
        {"category": "interest", "content": "互联网法律、数据合规、个人信息保护", "source": "diary"},
        {"category": "need", "content": "想了解产品经理岗位具体做什么", "source": "chat", "need_type": "buddy", "urgency": "passive"},
        {"category": "personality", "content": "逻辑清晰，表达有条理", "source": "chat"},
    ],
    9: [
        {"category": "fact", "content": "韩笑，武汉大学市场营销大二，南昌人", "source": "manual"},
        {"category": "interest", "content": "品牌策划、内容营销、社交媒体运营", "source": "diary"},
        {"category": "need", "content": "想找：能一起安静做事、互相陪伴的人", "source": "diary", "need_type": "dating", "urgency": "passive"},
        {"category": "habit", "content": "喜欢用备忘录随手记灵感", "source": "behavior"},
    ],
}

# ==================== 分身推荐匹配 ====================
AVATAR_MATCHES = [
    {"user_idx": 0, "post_idx": 4, "score": 88, "reasons": ["留学申请同伴", "都是理工科申请者"], "status": "new"},
    {"user_idx": 0, "post_idx": 2, "score": 75, "reasons": ["户外活动爱好者", "都喜欢骑行"], "status": "new"},
    {"user_idx": 0, "post_idx": 5, "score": 70, "reasons": ["同为AI/NLP方向", "可交流技术"], "status": "chatting"},
    {"user_idx": 1, "post_idx": 3, "score": 85, "reasons": ["雅思口语对练", "学习方法交流"], "status": "new"},
    {"user_idx": 1, "post_idx": 10, "score": 80, "reasons": ["效率工具同好", "Obsidian玩家"], "status": "new"},
    {"user_idx": 2, "post_idx": 2, "score": 92, "reasons": ["夜骑活动匹配", "都喜欢户外"], "status": "new"},
    {"user_idx": 2, "post_idx": 13, "score": 78, "reasons": ["都爱文学电影", "精神契合度高"], "status": "viewed"},
    {"user_idx": 3, "post_idx": 9, "score": 83, "reasons": ["暑期实习信息", "目标一致"], "status": "new"},
    {"user_idx": 3, "post_idx": 5, "score": 77, "reasons": ["AI方向同行", "可技术互助"], "status": "dismissed"},
    {"user_idx": 4, "post_idx": 12, "score": 86, "reasons": ["人文社科爱好者", "读书品味相近"], "status": "new"},
    {"user_idx": 4, "post_idx": 13, "score": 81, "reasons": ["都追求深度交流"], "status": "viewed"},
    {"user_idx": 5, "post_idx": 6, "score": 79, "reasons": ["租房搭子匹配"], "status": "new"},
    {"user_idx": 5, "post_idx": 9, "score": 68, "reasons": ["互联网产品方向"], "status": "new"},
    {"user_idx": 6, "post_idx": 7, "score": 90, "reasons": ["心理健康互助", "同校学姐经历"], "status": "new"},
    {"user_idx": 6, "post_idx": 12, "score": 72, "reasons": ["心理学书籍同好"], "status": "chatting"},
    {"user_idx": 7, "post_idx": 8, "score": 88, "reasons": ["毕设问卷互填", "都是研究型"], "status": "new"},
    {"user_idx": 8, "post_idx": 9, "score": 82, "reasons": ["产品实习信息", "法学+产品交叉"], "status": "new"},
    {"user_idx": 8, "post_idx": 5, "score": 65, "reasons": ["AI合规方向", "技术+法律结合"], "status": "new"},
    {"user_idx": 9, "post_idx": 13, "score": 85, "reasons": ["都渴望深度陪伴", "价值观契合"], "status": "new"},
    {"user_idx": 9, "post_idx": 14, "score": 70, "reasons": ["校园恋爱话题"], "status": "dismissed"},
]

# ==================== 分身侧写 ====================
AVATAR_PROFILES = [
    {"user_idx": 0, "summary": "务实的技术派女生，主攻NLP方向。正在找暑期实习，生活规律，晚上有写日记复盘的习惯。喜欢有深度的技术交流，不擅长社交但真诚。", "diary_count": 3, "chat_count": 5},
    {"user_idx": 1, "summary": "热心肠的全栈爱好者，效率工具重度用户。自律型选手，周末泡图书馆。对新工具充满好奇，乐于分享。", "diary_count": 2, "chat_count": 8},
    {"user_idx": 2, "summary": "北大心理系文艺女生，雅思高分党。喜欢文学电影和户外骑行，对感情认真但不强求。精神世界丰富，需要精神契合的伴侣。", "diary_count": 4, "chat_count": 3},
    {"user_idx": 3, "summary": "清华AI研究生，低调务实型。熟悉大模型和提示词工程，有自己的技术积累。求职目标明确，实习经验优先。", "diary_count": 2, "chat_count": 6},
    {"user_idx": 4, "summary": "复旦新闻系才女，有公众号写作经验。播客重度听众，喜欢深度对话。申请港硕DIY中，喜欢独立思考的人。", "diary_count": 3, "chat_count": 4},
    {"user_idx": 5, "summary": "上交金融转产品型选手，商业思维活跃。关注用户增长和数据分析，想转互联网。租房中，寻求搭子。", "diary_count": 2, "chat_count": 5},
    {"user_idx": 6, "summary": "浙大生物医学女生，略焦虑但善于自我觉察。正念冥想爱好者，喜欢心理学。正在寻找心理支持资源。", "diary_count": 3, "chat_count": 2},
    {"user_idx": 7, "summary": "中科大→南大物理研究生，代码能力强。毕设用Python做数据分析，习惯深夜工作。有问卷收集需求。", "diary_count": 2, "chat_count": 4},
    {"user_idx": 8, "summary": "中山法学女生，过法考客观题，对互联网法律感兴趣。逻辑清晰，表达有条理。想了解产品经理岗位。", "diary_count": 2, "chat_count": 5},
    {"user_idx": 9, "summary": "武大市场营销大二学生，南昌人。喜欢品牌策划和内容创作，随手记灵感。渴望能一起安静做事、互相陪伴的感情。", "diary_count": 3, "chat_count": 3},
]


# ==================== 主函数 ====================
def main():
    print("=" * 50)
    print("日迹 App - 广场+分身模块种子数据")
    print("=" * 50)

    print("\n[1] 初始化数据库...")
    init_db()
    print("  数据库表创建完成")

    db = SessionLocal()
    created = {"users": 0, "posts": 0, "comments": 0, "likes": 0, "memories": 0, "statuses": 0, "matches": 0, "profiles": 0}

    try:
        # --- 创建/获取用户 ---
        users = {}
        print("\n[2] 创建测试用户...")
        for i, ud in enumerate(USERS):
            existing = db.query(User).filter(User.username == ud["username"]).first()
            if existing:
                users[i] = existing
                print(f"  [skip] 用户已存在: {ud['username']}")
            else:
                now = now_ms()
                u = User(
                    id=str(uuid4()),
                    username=ud["username"],
                    password=hash_password(ud["password"]),
                    name=ud["name"],
                    school=ud["school"],
                    major=ud["major"],
                    grade=ud["grade"],
                    avatar=f"https://api.dicebear.com/7.x/avataaars/svg?seed={ud['username']}",
                    created_at=now,
                    updated_at=now,
                )
                db.add(u)
                db.flush()
                users[i] = u
                created["users"] += 1
                print(f"  [new] 用户: {ud['username']} ({ud['name']}, {ud['school']})")

        # --- 创建广场帖子 ---
        posts = {}
        print("\n[3] 创建广场帖子...")
        for i, pd in enumerate(PLAZA_POSTS):
            user = users[pd["user_idx"]]
            p = PlazaPost(
                id=str(uuid4()),
                user_id=user.id,
                type=pd["type"],
                content=pd["content"],
                images=json.dumps(pd["images"]),
                location=pd.get("location", ""),
                tags=json.dumps(pd.get("tags", [])),
                likes=0,
                comments=0,
                agent_responses=0,
                is_from_agent=False,
                allow_agent_reply=pd.get("allow_agent_reply", True),
                school_only=pd.get("school_only", False),
                created_at=hours_ago_ms(pd["hours_ago"]),
            )
            db.add(p)
            db.flush()
            posts[i] = p
            created["posts"] += 1
            print(f"  [{pd['type']}] {pd['content'][:35]}...")

        # --- 创建评论 + 更新评论数 ---
        comment_count = {i: 0 for i in range(len(PLAZA_POSTS))}
        print("\n[4] 创建评论...")
        for cd in COMMENTS:
            user = users[cd["user_idx"]]
            post = posts[cd["post_idx"]]
            c = PlazaComment(
                id=str(uuid4()),
                post_id=post.id,
                user_id=user.id,
                content=cd["content"],
                is_agent=cd["is_agent"],
                created_at=hours_ago_ms(PLAZA_POSTS[cd["post_idx"]]["hours_ago"] + 1),
            )
            db.add(c)
            comment_count[cd["post_idx"]] += 1
            created["comments"] += 1
            tag = "[分身]" if cd["is_agent"] else ""
            print(f"  {tag} {cd['content'][:35]}...")

        for i, post in posts.items():
            post.comments = comment_count[i]

        # --- 创建点赞 + 更新点赞数 ---
        print("\n[5] 创建点赞...")
        for post_idx, user_idx in LIKES:
            post = posts[post_idx]
            existing = db.query(PostLike).filter(
                PostLike.post_id == post.id, PostLike.user_id == users[user_idx].id
            ).first()
            if not existing:
                pl = PostLike(
                    id=str(uuid4()),
                    post_id=post.id,
                    user_id=users[user_idx].id,
                    created_at=hours_ago_ms(PLAZA_POSTS[post_idx]["hours_ago"] + 2),
                )
                db.add(pl)
                post.likes = (post.likes or 0) + 1
                created["likes"] += 1
        print(f"  插入 {created['likes']} 条点赞记录")

        # --- 创建分身记忆 ---
        print("\n[6] 创建分身记忆...")
        for user_idx, memories in AVATAR_MEMORIES.items():
            user = users[user_idx]
            for mem in memories:
                m = AvatarMemory(
                    id=str(uuid4()),
                    user_id=user.id,
                    category=mem["category"],
                    content=mem["content"],
                    source=mem.get("source", "manual"),
                    source_ref="",
                    confidence=1.0,
                    is_active=True,
                    is_pinned=False,
                    need_type=mem.get("need_type"),
                    urgency=mem.get("urgency"),
                    expiry=None,
                    match_status=mem.get("need_type") and "searching",
                    tags=json.dumps([]),
                    created_at=hours_ago_ms(72),
                    updated_at=hours_ago_ms(72),
                )
                db.add(m)
                created["memories"] += 1
        print(f"  插入 {created['memories']} 条分身记忆")

        # --- 创建分身状态 ---
        print("\n[7] 创建分身状态...")
        for i, user in users.items():
            s = AvatarStatus(
                id=str(uuid4()),
                user_id=user.id,
                is_active=True,
                browsed_count=(i + 1) * 3,
                matched_count=min(i + 2, 8),
                chatting_count=min(i, 3),
                last_active_at=hours_ago_ms(i),
                enabled_channels='["buddy","help","share","dating"]',
                enabled_actions='["browse","match","comment"]',
                match_range=f'{{"school":"","distanceKm":10}}',
            )
            db.add(s)
            created["statuses"] += 1
        print(f"  插入 {created['statuses']} 条分身状态")

        # --- 创建分身推荐匹配 ---
        print("\n[8] 创建分身推荐...")
        for md in AVATAR_MATCHES:
            user = users[md["user_idx"]]
            post = posts[md["post_idx"]]
            m = AvatarMatch(
                id=str(uuid4()),
                user_id=user.id,
                post_id=post.id,
                match_score=md["score"],
                match_reasons=json.dumps(md["reasons"]),
                agent_conversation=json.dumps([]),
                status=md["status"],
                created_at=hours_ago_ms(PLAZA_POSTS[md["post_idx"]]["hours_ago"] + 3),
            )
            db.add(m)
            created["matches"] += 1
        print(f"  插入 {created['matches']} 条推荐匹配")

        # --- 创建分身侧写 ---
        print("\n[9] 创建分身侧写...")
        for pd in AVATAR_PROFILES:
            user = users[pd["user_idx"]]
            p = AvatarProfile(
                id=str(uuid4()),
                user_id=user.id,
                summary=pd["summary"],
                diary_count=pd["diary_count"],
                chat_count=pd["chat_count"],
                generated_at=hours_ago_ms(24),
            )
            db.add(p)
            created["profiles"] += 1
        print(f"  插入 {created['profiles']} 条分身侧写")

        db.commit()

        # --- 验证 ---
        print("\n[10] 验证数据...")
        print(f"  plaza_posts: {db.query(PlazaPost).count()} 条")
        print(f"  plaza_comments: {db.query(PlazaComment).count()} 条")
        print(f"  post_likes: {db.query(PostLike).count()} 条")
        print(f"  avatar_memories: {db.query(AvatarMemory).count()} 条")
        print(f"  avatar_statuses: {db.query(AvatarStatus).count()} 条")
        print(f"  avatar_matches: {db.query(AvatarMatch).count()} 条")
        print(f"  avatar_profiles: {db.query(AvatarProfile).count()} 条")

        print("\n" + "=" * 50)
        print("✓ 广场+分身种子数据初始化完成！")
        print(f"\n创建统计：")
        for k, v in created.items():
            print(f"  {k}: {v}")
        print(f"\n测试账号（统一密码 test123456）：")
        for u in USERS:
            print(f"  {u['username']:<15} {u['name']} @ {u['school']}")
        print(f"\n启动服务：uvicorn app.main:app --reload")
        print("=" * 50)

    except Exception as e:
        db.rollback()
        print(f"\n✗ 初始化失败: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
