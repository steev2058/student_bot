from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def grade_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="الثالث الثانوي - علمي", callback_data="grade:12sci")]])


def subjects_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="فيزياء", callback_data="sub:physics")],
        [InlineKeyboardButton(text="رياضيات 1", callback_data="sub:math1")],
        [InlineKeyboardButton(text="رياضيات 2", callback_data="sub:math2")],
    ])


def actions_keyboard():
    labels = ["خطة الكتاب", "بحث داخل الكتاب", "شرح الدرس", "اختبار سريع", "اختبار امتحاني", "اسأل سؤال ضمن الدرس"]
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=x, callback_data=f"act:{i}")] for i, x in enumerate(labels)])
