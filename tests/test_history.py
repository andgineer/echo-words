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
