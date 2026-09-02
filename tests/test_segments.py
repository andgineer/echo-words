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


def test_leading_negation_is_dropped_from_the_unit_the_label_names(languages):
    segments = fill_text_segments(
        [{"label": "bojati se", "surface": "Ne bojim se", "why": "Verb."}],
        "Ne bojim se više ničega.",
        languages["sr"],
    )

    assert [item.label for item in segments if len(item.label.split()) > 1] == ["bojim se"]


def test_a_copied_auxiliary_the_dictionary_form_does_not_carry_is_dropped(languages):
    segments = fill_text_segments(
        [{"label": "look forward to", "surface": "is looking forward to"}],
        "He is looking forward to the trip.",
        languages["en"],
    )

    assert [item.label for item in segments if len(item.label.split()) > 1] == [
        "looking forward to",
    ]


def test_a_trailing_subordinator_is_dropped_even_when_the_label_repeats_it(languages):
    segments = fill_text_segments(
        [{"label": "nadati se da", "surface": "Nadam se da"}],
        "Nadam se da ćeš doći na vreme.",
        languages["sr"],
    )

    assert [item.label for item in segments if len(item.label.split()) > 1] == ["Nadam se"]


def test_the_reflexive_the_label_names_is_taken_in_when_the_copy_left_it_out(languages):
    segments = fill_text_segments(
        [{"label": "sich freuen auf", "surface": "freue ... auf"}],
        "Ich freue mich schon sehr auf den Sommer.",
        languages["de"],
    )

    assert [item.label for item in segments if len(item.label.split()) > 1] == [
        "freue mich auf",
    ]


def test_a_label_reflexive_maps_onto_the_form_the_sentence_actually_uses(languages):
    segments = fill_text_segments(
        [{"label": "sich beschränken auf", "surface": "sich ... beschränken auf"}],
        "Wir müssen uns auf das Wesentliche beschränken.",
        languages["de"],
    )

    assert [item.label for item in segments if len(item.label.split()) > 1] == [
        "uns auf beschränken",
    ]


def test_negation_stays_when_free_material_would_survive_the_trim(languages):
    segments = fill_text_segments(
        [{"label": "u redu", "surface": "nešto nije u redu"}],
        "Sve mi se čini da nešto nije u redu.",
        languages["sr"],
    )

    assert [item.label for item in segments if len(item.label.split()) > 1] == [
        "nešto nije u redu",
    ]


def test_a_trim_below_two_words_drops_the_chip_and_keeps_the_words_clickable(languages):
    segments = fill_text_segments(
        [{"label": "rennen", "surface": "nicht rennt"}],
        "Er rennt nicht schnell.",
        languages["de"],
    )

    assert [item.label for item in segments] == ["Er", "rennt", "nicht", "schnell"]


def test_an_untouched_boundary_keeps_the_reason_and_the_source_order(languages):
    segments = fill_text_segments(
        [{"label": "izvinuti se", "surface": "se izvinio", "why": "Возвратный глагол."}],
        "On se juče izvinio svima.",
        languages["sr"],
    )

    assert Segment("se izvinio", "Возвратный глагол.", "On se juče izvinio svima.") in segments
