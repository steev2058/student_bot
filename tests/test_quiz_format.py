def build_quiz():
    return {"question": "سؤال؟", "choices": ["أ", "ب", "ج", "د"], "answer": "أ"}


def test_quiz_format():
    q = build_quiz()
    assert set(q.keys()) == {"question", "choices", "answer"}
    assert len(q["choices"]) == 4
