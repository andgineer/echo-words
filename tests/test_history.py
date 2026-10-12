from echo_words.history import Entry, History


def test_history_evicts_oldest_terminal_entry_at_its_bound():
    history = History(limit=2)
    for number in range(3):
        entry = Entry(str(number), "en", f"word-{number}")
        entry.action = "added"
        history.add(entry)

    assert [item["entry_id"] for item in history.recent()] == ["2", "1"]


def test_history_bounds_each_language_on_its_own():
    history = History(limit=2)
    for entry_id, lang in [("sr-0", "sr"), ("en-0", "en"), ("en-1", "en"), ("en-2", "en")]:
        entry = Entry(entry_id, lang, entry_id)
        entry.action = "added"
        history.add(entry)

    assert [item["entry_id"] for item in history.recent()] == ["en-2", "en-1", "sr-0"]


def test_history_never_evicts_pending_work_over_its_language_bound():
    history = History(limit=1)
    first = Entry("first", "en", "first")
    history.add(first)
    second = Entry("second", "en", "second")
    history.add(second)

    assert [item["entry_id"] for item in history.recent()] == ["second", "first"]

    first.action = "added"
    history.trim()
    assert [item["entry_id"] for item in history.recent()] == ["second"]


def test_history_updates_an_entry_in_place_instead_of_appending():
    history = History(limit=2)
    entry = Entry("one", "en", "word")
    history.add(entry)
    entry.analysis_html = "partial"
    history.add(entry)

    assert history.recent() == [entry.public()]
    assert history.recent()[0]["status"] == "pending"
    assert history.recent()[0]["text"] == "partial"


def test_public_history_carries_answer_and_segment_kinds_with_each_chip_context():
    entry = Entry("one", "en", "The bank opens.")
    entry.shape = "text"
    entry.segment_kind = "text"
    entry.segments = [
        {
            "label": "bank",
            "surface": "",
            "reason": "",
            "context": "The bank opens.",
        },
    ]

    public = entry.public()

    assert public["shape"] == "text"
    assert public["segment_kind"] == "text"
    assert public["segments"][0]["context"] == "The bank opens."
    assert "context_dropped" not in public
    assert "segments_are_senses" not in public


def test_public_history_carries_what_a_reverse_lookup_changed():
    entry = Entry("one", "en", "table", typed_word="сотл", read_as="стол")
    entry.reverse_offered = True
    entry.foreign_language = "fr"
    entry.segment_kind = "equivalents"
    entry.segments = [{"label": "desk", "surface": "", "reason": "", "context": "A desk."}]

    public = entry.public()

    assert (public["word"], public["typed_word"], public["read_as"]) == ("table", "сотл", "стол")
    assert (public["reverse_offered"], public["foreign_language"]) == (True, "fr")
    assert public["segment_kind"] == "equivalents"


def test_an_ordinary_entry_carries_none_of_it():
    public = Entry("one", "en", "table").public()

    assert (public["typed_word"], public["read_as"]) == (None, None)
    assert (public["reverse_offered"], public["foreign_language"]) == (False, None)
