from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def grade_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="الثالث الثانوي - علمي", callback_data="grade:12sci")]])


def subjects_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="فيزياء", callback_data="sub:physics")],
        [InlineKeyboardButton(text="رياضيات 1", callback_data="sub:math1")],
        [InlineKeyboardButton(text="رياضيات 2", callback_data="sub:math2")],
    ])


def actions_keyboard(remaining: int | None = None):
    labels = ["خطة الكتاب", "بحث داخل الكتاب", "شرح الدرس", "اختبار سريع", "اختبار امتحاني", "اسأل سؤال ضمن الدرس"]
    rows = [[InlineKeyboardButton(text=x, callback_data=f"act:{i}")] for i, x in enumerate(labels)]
    if remaining is not None:
        rows.append([InlineKeyboardButton(text=f"🎁 التجريبي المتبقي: {remaining}/10", callback_data="act:demo")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _pager_row(prefix: str, page: int, total_pages: int):
    row = []
    if page > 0:
        row.append(InlineKeyboardButton(text="◀️ السابق", callback_data=f"{prefix}:{page-1}"))
    row.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop"))
    if page + 1 < total_pages:
        row.append(InlineKeyboardButton(text="التالي ▶️", callback_data=f"{prefix}:{page+1}"))
    return row


def units_keyboard(units: list[tuple[int, str]], page: int = 0, per_page: int = 8):
    total_pages = max(1, (len(units) + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    selected = units[start : start + per_page]
    rows = [[InlineKeyboardButton(text=title[:55], callback_data=f"toc_unit:{uid}")] for uid, title in selected]
    rows.append(_pager_row("toc_units", page, total_pages))
    rows.append([InlineKeyboardButton(text="🔙 رجوع للخدمات", callback_data="menu:actions")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def lessons_keyboard(lessons: list[tuple[int, str]], unit_id: int, page: int = 0, per_page: int = 8):
    total_pages = max(1, (len(lessons) + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    selected = lessons[start : start + per_page]
    rows = [[InlineKeyboardButton(text=title[:55], callback_data=f"toc_lesson:{lid}")] for lid, title in selected]
    rows.append(_pager_row(f"toc_lessons:{unit_id}", page, total_pages))
    rows.append([InlineKeyboardButton(text="🔙 رجوع للوحدات", callback_data="toc_back_units")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def lesson_suggestions_keyboard(items: list[tuple[int, str]]):
    rows = [[InlineKeyboardButton(text=f"📘 {title[:52]}", callback_data=f"toc_lesson:{lid}")] for lid, title in items]
    rows.append([InlineKeyboardButton(text="📚 افتح الوحدات والدروس", callback_data="act:0")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
