import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.logging import setup_logging
from app.db.session import SessionLocal
from app.bot.keyboards import grade_keyboard, subjects_keyboard, actions_keyboard
from app.services.coupons import generate_coupons, redeem_coupon
from app.services.rate_limit import check_limit
from app.models.entities import Subject, User, UserSession, EventLog, Subscription, SubjectUnlock
from app.services.rag_service import answer_question

setup_logging(settings.LOG_LEVEL)
bot = Bot(settings.BOT_TOKEN)
dp = Dispatcher()


def is_admin(uid: int) -> bool:
    ids = [int(x.strip()) for x in settings.ADMIN_USER_IDS.split(",") if x.strip().isdigit()]
    return uid in ids


@dp.message(Command("start"))
async def start(m: Message):
    await m.answer("اختر الصف:", reply_markup=grade_keyboard())


@dp.callback_query(F.data == "grade:12sci")
async def choose_subject(c: CallbackQuery):
    await c.message.answer("اختر المادة:", reply_markup=subjects_keyboard())
    await c.answer()


@dp.callback_query(F.data.startswith("sub:"))
async def subject_menu(c: CallbackQuery):
    code = c.data.split(":", 1)[1]
    with SessionLocal() as db:
        s = db.query(Subject).filter(Subject.code == code).first()
        u = db.query(User).filter(User.telegram_id == c.from_user.id).first()
        if not u:
            u = User(telegram_id=c.from_user.id, username=c.from_user.username, grade="الثالث الثانوي - علمي")
            db.add(u)
            db.commit()
            db.refresh(u)
        sess = db.query(UserSession).filter(UserSession.user_id == u.id).first()
        if not sess:
            sess = UserSession(user_id=u.id)
            db.add(sess)
        if s:
            sess.subject_id = s.id
        db.commit()
    await c.message.answer("اختر الخدمة:", reply_markup=actions_keyboard())
    await c.answer()


@dp.callback_query(F.data.startswith("act:"))
async def action_handler(c: CallbackQuery):
    aid = int(c.data.split(":", 1)[1])
    msgs = {
        0: "خطة الكتاب: استخدم التنقل بالوحدات ثم الدروس (يتم دعمه عبر TOC).",
        1: "أرسل كلمة البحث الآن وسأقترح أفضل 3 دروس.",
        2: "أرسل اسم الدرس أو سؤالك لشرح الدرس مع توثيق.",
        3: "اختبار سريع: قريباً (صيغة MCQ أساسية موجودة في الاختبارات).",
        4: "اختبار امتحاني: قريباً.",
        5: "اسأل سؤال ضمن الدرس الآن.",
    }
    await c.message.answer(msgs.get(aid, "خيار غير معروف"))
    await c.answer()


@dp.message(Command("redeem"))
async def redeem(m: Message):
    args = (m.text or "").split(maxsplit=1)
    if len(args) < 2:
        await m.answer("استخدم: /redeem CODE")
        return
    with SessionLocal() as db:
        ok, msg = redeem_coupon(db, m.from_user.id, args[1].strip())
    await m.answer(msg)


@dp.message(Command("admin_gen_coupons"))
async def admin_gen(m: Message):
    if not is_admin(m.from_user.id):
        return await m.answer("غير مصرح")
    # /admin_gen_coupons subscription 10
    parts = (m.text or "").split()
    if len(parts) < 3:
        return await m.answer("/admin_gen_coupons subscription|subject_unlock count [subject_code]")
    kind, count = parts[1], int(parts[2])
    subject_code = parts[3] if len(parts) > 3 else None
    with SessionLocal() as db:
        codes = generate_coupons(db, kind, count, subject_code)
    await m.answer("\n".join(codes[:30]))


@dp.message(Command("admin_reindex"))
async def admin_reindex(m: Message):
    if not is_admin(m.from_user.id):
        return await m.answer("غير مصرح")
    await m.answer("أعد الفهرسة عبر سكربت: python scripts/reindex_subject.py <subject_code>")


@dp.message()
async def on_text(m: Message):
    text = (m.text or "").strip()
    if not text:
        return
    with SessionLocal() as db:
        if not check_limit(db, m.from_user.id, "global", 30, 600):
            return await m.answer("تم تجاوز الحد المسموح (30 رسالة/10 دقائق). حاول لاحقاً.")
        if not check_limit(db, m.from_user.id, "ai_heavy", 10, 600):
            return await m.answer("تم تجاوز حد الاستخدام الذكي (10 طلبات/10 دقائق). الرجاء الانتظار قليلاً.")

        u = db.query(User).filter(User.telegram_id == m.from_user.id).first()
        if not u:
            u = User(telegram_id=m.from_user.id, username=m.from_user.username, grade="الثالث الثانوي - علمي")
            db.add(u)
            db.commit()
            db.refresh(u)
        sess = db.query(UserSession).filter(UserSession.user_id == u.id).first()
        if not sess or not sess.subject_id:
            return await m.answer("اختر المادة أولاً عبر /start")

        # simple free demo gating: 10 questions per subject unless unlocked
        used = db.query(EventLog).filter(EventLog.user_id == u.id, EventLog.event_type == f"q:{sess.subject_id}").count()
        has_sub = db.query(Subscription).filter(Subscription.user_id == u.id, Subscription.active == True).first() is not None  # noqa: E712
        has_unlock = db.query(SubjectUnlock).filter(SubjectUnlock.user_id == u.id, SubjectUnlock.subject_id == sess.subject_id).first() is not None
        if not (has_sub and has_unlock) and used >= 10:
            return await m.answer("انتهت النسخة التجريبية لهذه المادة (10 أسئلة). فعّل الاشتراك وكود فتح المادة.")

        db.add(EventLog(user_id=u.id, event_type=f"q:{sess.subject_id}", payload=text))
        db.commit()

        ans = answer_question(
            db,
            user_id=m.from_user.id,
            subject_id=sess.subject_id,
            question=text,
            lesson_range=[sess.selected_range_start or 0, sess.selected_range_end or 99999],
            watermark=f"User: @{m.from_user.username or 'unknown'} / id: {m.from_user.id}",
        )
    await m.answer(ans["answer"])


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
