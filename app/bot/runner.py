import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from app.core.config import settings
from app.core.logging import setup_logging
from app.db.session import SessionLocal
from app.bot.keyboards import (
    grade_keyboard,
    subjects_keyboard,
    actions_keyboard,
    units_keyboard,
    lessons_keyboard,
    lesson_suggestions_keyboard,
)
from app.services.coupons import generate_coupons, redeem_coupon
from app.services.rate_limit import check_limit
from app.models.entities import Subject, User, UserSession, EventLog, Subscription, SubjectUnlock, TocItem
from app.services.rag_service import answer_question
from app.services.toc_service import get_units, get_lessons_for_unit, search_lessons

setup_logging(settings.LOG_LEVEL)
bot = Bot(settings.BOT_TOKEN)
dp = Dispatcher()

# Lightweight ephemeral flow-state for UX modes.
FLOW_STATE: dict[int, str] = {}


def is_admin(uid: int) -> bool:
    ids = [int(x.strip()) for x in settings.ADMIN_USER_IDS.split(",") if x.strip().isdigit()]
    return uid in ids


def _get_or_create_user(db, tg_id: int, username: str | None):
    u = db.query(User).filter(User.telegram_id == tg_id).first()
    if not u:
        u = User(telegram_id=tg_id, username=username, grade="الثالث الثانوي - علمي")
        db.add(u)
        db.commit()
        db.refresh(u)
    return u


def _get_or_create_session(db, user_id: int):
    sess = db.query(UserSession).filter(UserSession.user_id == user_id).first()
    if not sess:
        sess = UserSession(user_id=user_id)
        db.add(sess)
        db.commit()
        db.refresh(sess)
    return sess


def _demo_usage(db, user_id: int, subject_id: int) -> tuple[int, int]:
    used = db.query(EventLog).filter(EventLog.user_id == user_id, EventLog.event_type == f"q:{subject_id}").count()
    return used, max(0, 10 - used)


@dp.message(Command("start"))
async def start(m: Message):
    FLOW_STATE[m.from_user.id] = "idle"
    await m.answer("أهلاً 👋\nاختر الصف:", reply_markup=grade_keyboard())


@dp.callback_query(F.data == "grade:12sci")
async def choose_subject(c: CallbackQuery):
    await c.message.answer("اختر المادة:", reply_markup=subjects_keyboard())
    await c.answer()


@dp.callback_query(F.data == "menu:actions")
async def back_actions(c: CallbackQuery):
    with SessionLocal() as db:
        u = _get_or_create_user(db, c.from_user.id, c.from_user.username)
        sess = _get_or_create_session(db, u.id)
        remaining = None
        if sess.subject_id:
            _, remaining = _demo_usage(db, u.id, sess.subject_id)
    await c.message.answer("اختر الخدمة:", reply_markup=actions_keyboard(remaining))
    await c.answer()


@dp.callback_query(F.data.startswith("sub:"))
async def subject_menu(c: CallbackQuery):
    code = c.data.split(":", 1)[1]
    with SessionLocal() as db:
        s = db.query(Subject).filter(Subject.code == code).first()
        u = _get_or_create_user(db, c.from_user.id, c.from_user.username)
        sess = _get_or_create_session(db, u.id)
        if not s:
            await c.message.answer("تعذّر العثور على هذه المادة حالياً. جرّب /start مرة أخرى.")
            return await c.answer()

        sess.subject_id = s.id
        sess.toc_item_id = None
        sess.selected_range_start = None
        sess.selected_range_end = None
        db.commit()
        used, remaining = _demo_usage(db, u.id, s.id)
    FLOW_STATE[c.from_user.id] = "idle"
    await c.message.answer(
        f"✅ تم اختيار المادة.\n🎁 النسخة التجريبية: {remaining}/10 متبقية في هذه المادة.",
        reply_markup=actions_keyboard(remaining),
    )
    await c.answer()


@dp.callback_query(F.data.startswith("act:"))
async def action_handler(c: CallbackQuery):
    aid = c.data.split(":", 1)[1]
    with SessionLocal() as db:
        u = _get_or_create_user(db, c.from_user.id, c.from_user.username)
        sess = _get_or_create_session(db, u.id)
        if not sess.subject_id:
            await c.message.answer("اختر المادة أولاً عبر /start")
            return await c.answer()

        if aid == "demo":
            used, remaining = _demo_usage(db, u.id, sess.subject_id)
            await c.message.answer(f"🎁 المتبقي لك في هذه المادة: {remaining}/10 (المستخدم: {used}/10)")
        elif aid == "0":
            units = get_units(db, sess.subject_id)
            if not units:
                await c.message.answer("لا توجد فهرسة وحدات حالياً لهذه المادة. جرّب البحث باسم الدرس.")
            else:
                data = [(x.id, x.title) for x in units]
                await c.message.answer("📚 اختر الوحدة:", reply_markup=units_keyboard(data, page=0))
            FLOW_STATE[c.from_user.id] = "toc"
        elif aid == "1":
            FLOW_STATE[c.from_user.id] = "search"
            await c.message.answer("🔎 اكتب كلمة البحث الآن، وسأقترح أفضل 3 دروس مع أزرار فتح مباشر.")
        elif aid in {"2", "5"}:
            FLOW_STATE[c.from_user.id] = "ask"
            await c.message.answer("✍️ أرسل سؤالك الآن. يفضّل اختيار درس أولاً لتحسين الدقة والتوثيق.")
        elif aid == "3":
            await c.message.answer("اختبار سريع: قريباً (صيغة MCQ الأساسية موجودة في الاختبارات).")
        elif aid == "4":
            await c.message.answer("اختبار امتحاني: قريباً.")
        else:
            await c.message.answer("خيار غير معروف")
    await c.answer()


@dp.callback_query(F.data.startswith("toc_units:"))
async def toc_units_page(c: CallbackQuery):
    page = int(c.data.split(":", 1)[1])
    with SessionLocal() as db:
        u = _get_or_create_user(db, c.from_user.id, c.from_user.username)
        sess = _get_or_create_session(db, u.id)
        units = get_units(db, sess.subject_id) if sess.subject_id else []
    await c.message.edit_reply_markup(reply_markup=units_keyboard([(x.id, x.title) for x in units], page=page))
    await c.answer()


@dp.callback_query(F.data == "toc_back_units")
async def toc_back_units(c: CallbackQuery):
    with SessionLocal() as db:
        u = _get_or_create_user(db, c.from_user.id, c.from_user.username)
        sess = _get_or_create_session(db, u.id)
        units = get_units(db, sess.subject_id) if sess.subject_id else []
    await c.message.answer("📚 اختر الوحدة:", reply_markup=units_keyboard([(x.id, x.title) for x in units], page=0))
    await c.answer()


@dp.callback_query(F.data.startswith("toc_unit:"))
async def toc_select_unit(c: CallbackQuery):
    unit_id = int(c.data.split(":", 1)[1])
    with SessionLocal() as db:
        u = _get_or_create_user(db, c.from_user.id, c.from_user.username)
        sess = _get_or_create_session(db, u.id)
        lessons = get_lessons_for_unit(db, sess.subject_id, unit_id) if sess.subject_id else []
    if not lessons:
        await c.message.answer("لا توجد دروس داخل هذه الوحدة حالياً.")
    else:
        await c.message.answer(
            "📖 اختر الدرس:",
            reply_markup=lessons_keyboard([(x.id, x.title) for x in lessons], unit_id=unit_id, page=0),
        )
    await c.answer()


@dp.callback_query(F.data.startswith("toc_lessons:"))
async def toc_lessons_page(c: CallbackQuery):
    _, unit_id_str, page_str = c.data.split(":")
    unit_id = int(unit_id_str)
    page = int(page_str)
    with SessionLocal() as db:
        u = _get_or_create_user(db, c.from_user.id, c.from_user.username)
        sess = _get_or_create_session(db, u.id)
        lessons = get_lessons_for_unit(db, sess.subject_id, unit_id) if sess.subject_id else []
    await c.message.edit_reply_markup(reply_markup=lessons_keyboard([(x.id, x.title) for x in lessons], unit_id=unit_id, page=page))
    await c.answer()


@dp.callback_query(F.data.startswith("toc_lesson:"))
async def toc_select_lesson(c: CallbackQuery):
    lesson_id = int(c.data.split(":", 1)[1])
    with SessionLocal() as db:
        u = _get_or_create_user(db, c.from_user.id, c.from_user.username)
        sess = _get_or_create_session(db, u.id)
        lesson = db.query(TocItem).filter(TocItem.id == lesson_id).first()
        if not lesson:
            await c.message.answer("تعذّر فتح هذا الدرس. جرّب من جديد.")
            return await c.answer()

        sess.toc_item_id = lesson.id
        sess.selected_range_start = lesson.start_pdf_page if lesson.start_pdf_page is not None else 0
        sess.selected_range_end = lesson.end_pdf_page if lesson.end_pdf_page is not None else 99999
        db.commit()
        start = (sess.selected_range_start or 0) + 1
        end = (sess.selected_range_end + 1) if sess.selected_range_end is not None else "آخر الكتاب"
    FLOW_STATE[c.from_user.id] = "ask"
    await c.message.answer(
        f"✅ تم اختيار الدرس: {lesson.title}\n"
        f"📄 نطاق الصفحات المعتمد: PDF {start} → {end}\n"
        f"الآن أرسل سؤالك وسألتزم بهذا النطاق مع توثيق.",
    )
    await c.answer()


@dp.callback_query(F.data == "noop")
async def noop_handler(c: CallbackQuery):
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

        u = _get_or_create_user(db, m.from_user.id, m.from_user.username)
        sess = _get_or_create_session(db, u.id)
        if not sess.subject_id:
            return await m.answer("اختر المادة أولاً عبر /start")

        flow = FLOW_STATE.get(m.from_user.id, "ask")
        if flow == "search":
            suggestions = search_lessons(db, sess.subject_id, text, limit=3)
            if not suggestions:
                return await m.answer("لم أجد دروساً مطابقة بوضوح. جرّب كلمة أدق أو افتح الفهرس لاختيار الدرس.")
            msg = "أفضل الدروس المطابقة لسؤالك:\n" + "\n".join(
                [f"{i+1}) {s.unit_title + ' — ' if s.unit_title else ''}{s.title}" for i, s in enumerate(suggestions)]
            )
            kb = lesson_suggestions_keyboard([(s.id, f"{s.unit_title + ' — ' if s.unit_title else ''}{s.title}") for s in suggestions])
            return await m.answer(msg, reply_markup=kb)

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
            lesson_range=[sess.selected_range_start, sess.selected_range_end],
            watermark=f"User: @{m.from_user.username or 'unknown'} / id: {m.from_user.id}",
        )
        _, remaining = _demo_usage(db, u.id, sess.subject_id)

    await m.answer(f"{ans['answer']}\n\n🎁 المتبقي في النسخة التجريبية لهذه المادة: {remaining}/10")


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
