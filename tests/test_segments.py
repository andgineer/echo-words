from echo_words.segments import (
    Segment,
    fill_text_segments,
    parse_component_segments,
)


def test_reordered_separated_and_capitalized_parts_map_to_source_order(languages):
    segments = fill_text_segments(
        [{"label": "aufstehen", "surface": "AUF … steht", "why": "Verb."}],
        "Er steht jeden Morgen auf.",
        languages["de"],
    )

    assert segments == [
        Segment("Er", "", "Er steht jeden Morgen auf."),
        Segment("steht auf", "Verb.", "Er steht jeden Morgen auf."),
        Segment("steht", "", "Er steht jeden Morgen auf."),
        Segment("jeden", "", "Er steht jeden Morgen auf."),
        Segment("Morgen", "", "Er steht jeden Morgen auf."),
        Segment("auf", "", "Er steht jeden Morgen auf."),
    ]


def test_one_unmatchable_proposal_does_not_erase_other_combinations_or_words(languages):
    segments = fill_text_segments(
        [
            {"label": "nope", "surface": "missing pieces"},
            {"label": "javiti se", "surface": "се … јавио"},
        ],
        "Он ми се јавио.",
        languages["sr"],
    )

    assert [segment.label for segment in segments] == ["Он", "ми", "се јавио", "се", "јавио"]


def test_no_arbitrary_combination_count_limit_remains(languages):
    words = [f"word{chr(ord('a') + index)}" for index in range(14)]
    proposals = [
        {"surface": f"{words[index]} {words[index + 1]}"} for index in range(0, len(words), 2)
    ]

    segments = fill_text_segments(proposals, " ".join(words), languages["en"])

    assert len(segments) == 21


def test_repeated_words_claim_distinct_earliest_occurrences(languages):
    segments = fill_text_segments(
        [
            {"surface": "go home", "why": "first"},
            {"surface": "go home", "why": "second"},
        ],
        "go home then go home",
        languages["en"],
    )

    assert [(item.label, item.reason) for item in segments] == [
        ("go home", "first"),
        ("go", ""),
        ("home", ""),
        ("then", ""),
        ("go home", "second"),
        ("go", ""),
        ("home", ""),
    ]


def test_first_overlapping_proposal_wins(languages):
    segments = fill_text_segments(
        [{"surface": "take care"}, {"surface": "care of"}],
        "take care of it",
        languages["en"],
    )

    assert [item.label for item in segments] == ["take care", "take", "care", "of", "it"]


def test_an_unusable_internal_label_does_not_delete_a_surface_match(languages):
    segments = fill_text_segments(
        [{"label": "вратити se!", "surface": "се вратио"}],
        "Он се вратио",
        languages["sr"],
    )
    assert [item.label for item in segments] == ["Он", "се вратио", "се", "вратио"]


def test_expression_components_have_backend_owned_context_and_no_cap(languages):
    values = [{"surface": f"word{letter}"} for letter in "abcdefgh"]
    segments = parse_component_segments(values, languages["en"], context="Example sentence.")

    assert len(segments) == 8
    assert all(segment.context == "Example sentence." for segment in segments)


def test_the_text_branch_combinations_fill_every_chip(languages):
    segments = fill_text_segments(
        [{"surface": "looks forward", "why": "phrasal verb"}],
        "She looks forward to it.",
        languages["en"],
    )

    assert [segment.label for segment in segments] == [
        "She",
        "looks forward",
        "looks",
        "forward",
        "to",
        "it",
    ]
    assert all(segment.context == "She looks forward to it." for segment in segments)


def test_a_transliterated_serbian_surface_still_finds_its_words_in_the_text(languages):
    segments = fill_text_segments(
        [{"surface": "се играју", "why": "повратни глагол"}],
        "Deca se igraju napolju ceo dan.",
        languages["sr"],
    )

    assert [segment.label for segment in segments] == [
        "Deca",
        "se igraju",
        "se",
        "igraju",
        "napolju",
        "ceo",
        "dan",
    ]


def test_script_folding_does_not_reach_a_single_script_language(languages):
    segments = fill_text_segments(
        [{"surface": "се вратио", "why": "повратни глагол"}],
        "Er steht jeden Morgen auf.",
        languages["de"],
    )

    assert [segment.label for segment in segments] == ["Er", "steht", "jeden", "Morgen", "auf"]


def test_a_word_inside_a_combination_keeps_its_own_chip(languages):
    segments = fill_text_segments(
        [{"surface": "looks forward", "why": "phrasal verb"}],
        "She looks forward to it.",
        languages["en"],
    )

    assert [segment.label for segment in segments] == [
        "She",
        "looks forward",
        "looks",
        "forward",
        "to",
        "it",
    ]
    assert segments[1].reason == "phrasal verb"
    assert segments[2].reason == ""


def test_a_token_the_submission_endpoint_would_reject_gets_no_chip(languages):
    segments = fill_text_segments([], "In 2024 the price was 30 euro", languages["en"])

    assert [segment.label for segment in segments] == [
        "In",
        "the",
        "price",
        "was",
        "euro",
    ]
