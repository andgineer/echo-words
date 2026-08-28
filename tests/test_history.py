from echo_words.history import Entry, History


def test_history_evicts_oldest_terminal_entry_at_its_bound():
    history = History(limit=2)
    for number in range(3):
        entry = Entry(str(number), "en", f"word-{number}")
        entry.action = "added"
        history.add(entry)

    assert [item["entry_id"] for item in history.recent()] == ["2", "1"]


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
