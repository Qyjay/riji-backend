"""
AtoA 搭子模式端到端测试脚本
用 xu_yining 账号与候选搭子进行真实 AtoA 对话（调用蓝心 AI）
打印分身 3 轮对话内容
"""
import sys, os, json, time, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from uuid import uuid4
from app.database import SessionLocal
from app.models.user import User
from app.models.avatar import AvatarStatus, AvatarAtoaInteraction, AvatarAtoaSession
from app.models.memory import AvatarCard
from app.avatar import service as svc

db = SessionLocal()


# ── 辅助：创建/更新用户 ──────────────────────────────────────

def ensure_user(username, password, name):
    u = db.query(User).filter(User.username == username).first()
    if u:
        print(f"[已存在] {username}（{u.name}）id={u.id[:8]}...")
        return u
    from app.auth.router import hash_password
    ts = int(time.time() * 1000)
    u = User(id=str(uuid4()), username=username, password=hash_password(password),
             name=name, level=1, xp=0, diary_count=0, streak_days=0,
             pomodoro_count=0, created_at=ts, updated_at=ts)
    db.add(u)
    db.commit()
    db.refresh(u)
    print(f"[新建] {username}（{name}）id={u.id[:8]}...")
    return u


def ensure_avatar_status(user_id):
    ast = db.query(AvatarStatus).filter(AvatarStatus.user_id == user_id).first()
    if not ast:
        ts = int(time.time() * 1000)
        ast = AvatarStatus(user_id=user_id, auto_match_enabled=True,
                           is_active=True, last_active_at=ts)
        db.add(ast)
        db.commit()
        db.refresh(ast)
    elif not ast.auto_match_enabled:
        ast.auto_match_enabled = True
        db.commit()
    return ast


def ensure_avatar_card(user_id, display_name, public_summary, interest_tags,
                        social_intent, visibility="public"):
    card = db.query(AvatarCard).filter(AvatarCard.user_id == user_id).first()
    ts = int(time.time() * 1000)
    if card:
        card.display_name = display_name
        card.public_summary = public_summary
        card.interest_tags = json.dumps(interest_tags, ensure_ascii=False)
        card.social_intent = json.dumps(social_intent, ensure_ascii=False)
        card.visibility = visibility
        card.updated_at = ts
        db.commit()
        print(f"  分身名片已更新: {display_name}")
        return card
    card = AvatarCard(
        user_id=user_id,
        display_name=display_name,
        public_summary=public_summary,
        interest_tags=json.dumps(interest_tags, ensure_ascii=False),
        social_intent=json.dumps(social_intent, ensure_ascii=False),
        visibility=visibility,
        updated_at=ts
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    print(f"  分身名片已创建: {display_name}")
    return card


# ── 步骤 1：准备用户数据 ─────────────────────────────────────

print("=" * 65)
print("【步骤 1】准备用户与分身名片数据")
print("=" * 65)

xu = ensure_user("xu_yining", "123456", "许以宁")
ensure_avatar_status(xu.id)
card_xu = ensure_avatar_card(
    xu.id,
    display_name="以宁",
    public_summary="温柔细腻的文艺女生，喜欢安静读书、旅行拍照，享受慢生活。喝咖啡是日常仪式，听民谣是情绪出口。",
    interest_tags=["读书", "旅行", "摄影", "咖啡", "民谣", "文艺", "慢生活"],
    social_intent=["找旅行搭子", "找读书搭子", "闲聊"],
)

chen = ensure_user("chen_chen_photo", "123456", "陈晨")
ensure_avatar_status(chen.id)
card_chen = ensure_avatar_card(
    chen.id,
    display_name="陈晨",
    public_summary="用镜头记录城市与自然的摄影青年，热爱旅行探索，对独立音乐和咖啡有独特执念，喜欢和有趣的人闲聊。",
    interest_tags=["摄影", "旅行", "咖啡", "独立音乐", "读书", "文艺", "街头探索"],
    social_intent=["找旅行搭子", "找摄影搭子", "随缘"],
)

li = ensure_user("li_mingyuan_hike", "123456", "李明远")
ensure_avatar_status(li.id)
ensure_avatar_card(
    li.id,
    display_name="明远",
    public_summary="热爱山野与自然的徒步达人，每逢周末必出发，喝咖啡是出发前的仪式，读书是回来后的沉淀。",
    interest_tags=["徒步", "旅行", "咖啡", "阅读", "骑行", "慢生活"],
    social_intent=["找户外搭子", "找旅行搭子"],
)

wang = ensure_user("wang_zihan_book", "123456", "王子涵")
ensure_avatar_status(wang.id)
ensure_avatar_card(
    wang.id,
    display_name="子涵",
    public_summary="在独立书店兼职的安静女生，话不多但有内涵，对文字有深度感受，空余时间养猫、写字、喝咖啡。",
    interest_tags=["读书", "文学", "咖啡", "猫咪", "写作", "慢生活", "独立书店"],
    social_intent=["找读书搭子", "找文艺搭子"],
)

print(f"\n用户与名片准备完成！")

# ── 步骤 2：调用 _simulate_atoa_conversation（3轮，以宁×陈晨）──

print("\n" + "=" * 65)
print("【步骤 2】以宁 × 陈晨 — AtoA 三轮对话")
print("=" * 65)
print(f"\n甲：{card_xu.display_name}（许以宁）")
print(f"    标签: {', '.join(json.loads(card_xu.interest_tags))}")
print(f"    意图: {', '.join(json.loads(card_xu.social_intent))}")
print(f"    简介: {card_xu.public_summary}")
print(f"\n乙：{card_chen.display_name}（陈晨）")
print(f"    标签: {', '.join(json.loads(card_chen.interest_tags))}")
print(f"    意图: {', '.join(json.loads(card_chen.social_intent))}")
print(f"    简介: {card_chen.public_summary}")


async def run_three_rounds():
    """运行三轮 AtoA 对话，模拟用户「继续聊」决策"""
    print("\n─── 第 1 轮（初次探路） ───")
    r1 = await svc._simulate_atoa_conversation(card_xu, card_chen, max_rounds=3)
    for t in r1:
        label = f"以宁的分身" if t["role"] == "avatar_a" else f"陈晨的分身"
        print(f"  [{label}] {t.get('content', '')}")

    print("\n─── 第 2 轮（用户决定「继续聊」） ───")
    r2 = await svc._simulate_atoa_conversation(card_xu, card_chen, max_rounds=3,
                                                prior_conversation=r1)
    for t in r2:
        label = f"以宁的分身" if t["role"] == "avatar_a" else f"陈晨的分身"
        print(f"  [{label}] {t.get('content', '')}")

    print("\n─── 第 3 轮（再次「继续聊」） ───")
    r3 = await svc._simulate_atoa_conversation(card_xu, card_chen, max_rounds=3,
                                                prior_conversation=r1 + r2)
    for t in r3:
        label = f"以宁的分身" if t["role"] == "avatar_a" else f"陈晨的分身"
        print(f"  [{label}] {t.get('content', '')}")

    return r1, r2, r3


r1, r2, r3 = asyncio.run(run_three_rounds())
all_conv = r1 + r2 + r3

# ── 步骤 3：写入 AtoaSession + AtoaInteraction ─────────────────

print("\n" + "=" * 65)
print("【步骤 3】评分 → 构建 AtoaSession → 写入 AtoaInteraction")
print("=" * 65)

candidates = [chen, li, wang]
scored = svc._score_all_atoa_candidates(db, xu.id, candidates, set(), set())
print("\n候选评分结果:")
for s in scored:
    cand = s['user']
    print(f"  {cand.name}: 评分={s['score']}, 共同话题={s.get('shared_topics', [])}")

session = svc._build_atoa_session(db, xu.id, scored)
print(f"\nAtoaSession id={session.id[:8]}..., 候选人数={len(json.loads(session.candidate_ids))}")

chen_score = next((s['score'] for s in scored if s['user'].id == chen.id), 60)
score_data = {
    "outcome": "pending_user_decision",
    "score_ab": chen_score,
    "score_ba": 55,
    "shared_topics": ["旅行", "咖啡", "读书"],
    "reasons_ab": ["共同兴趣：旅行、咖啡、读书", "均有找搭子意图"],
    "reasons_ba": ["共同兴趣：旅行、咖啡", "对方有摄影专长"],
    "risk_flags": [],
    "conversation": all_conv,
    "intent_type": "buddy",
    "is_mutual": False,
}
interaction = svc._write_atoa_interaction(db, xu.id, chen.id, score_data, session_id=session.id)
db.commit()
print(f"AtoaInteraction id={interaction.id[:8]}..., outcome={interaction.outcome}, 对话条数={len(all_conv)}")

# ── 步骤 4：打印完整会话 ────────────────────────────────────

print("\n" + "=" * 65)
print("【步骤 4】完整 AtoA 会话（3 轮合并输出）")
print("=" * 65)
print(f"""
对话双方
  甲：以宁（许以宁）
      标签：{', '.join(json.loads(card_xu.interest_tags))}
      意图：{', '.join(json.loads(card_xu.social_intent))}
  乙：陈晨
      标签：{', '.join(json.loads(card_chen.interest_tags))}
      意图：{', '.join(json.loads(card_chen.social_intent))}
""")
for i, turn in enumerate(all_conv, 1):
    label = "以宁的分身" if turn["role"] == "avatar_a" else "陈晨的分身"
    content = turn.get('content', '')
    print(f"  [{i:02d}] 【{label}】{content}")

print("\n── Raw JSON ──")
print(json.dumps(all_conv, ensure_ascii=False, indent=2))

db.close()
print("\n[测试完成 OK]")
