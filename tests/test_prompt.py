from echo_words.prompt import build_prompt


def test_prompt_carries_the_language_word_target_context_and_hints(languages):
    prompt = build_prompt(
        languages["sr"],
        "глава",
        "Russian",
        context="прва глава књиге",
    )
    assert "Српски" in prompt
    assert "глава" in prompt
    assert "WRITE YOUR ENTIRE ANSWER IN Russian" in prompt
    assert "прва глава књиге" in prompt
    assert "for nouns give gender and plural" in prompt
    assert "===CARD===" in prompt
    assert "label is a\n1-3 word tag in Russian" in prompt
    assert "pos is that\nsense's part of speech as one short abbreviation in Russian" in prompt
    assert "text is a\nsentence in Српски, translation is its rendering in Russian" in prompt
    assert "(colloquial, formal, slang, vulgar\n   and so on)" in prompt
    assert "If there is no typo, suggestion is an\nempty string." in prompt
    assert "with no punctuation used for emphasis\nanywhere?" in prompt
