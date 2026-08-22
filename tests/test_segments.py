import pytest

from echo_words.segments import (
    MAX_REASON_LENGTH,
    MAX_SEGMENTS,
    MAX_SURFACE_LENGTH,
    Segment,
    SegmentParseError,
    parse_segments_payload,
)


def payload(*segments: str) -> str:
    return '{"segments": [' + ",".join(segments) + "]}"


def test_a_well_formed_payload_becomes_suggested_units(languages):
    parsed = parse_segments_payload(
        payload(
            '{"label":"aufstehen","surface":"steht … auf","why":"Trennbares Verb."}',
            '{"label":"in Frage kommen","surface":"kommt … in Frage","why":"Feste Wendung."}',
        ),
        languages["de"],
    )
    assert parsed == [
        Segment("aufstehen", "steht … auf", "Trennbares Verb."),
        Segment("in Frage kommen", "kommt … in Frage", "Feste Wendung."),
    ]


def test_a_text_with_nothing_hard_in_it_yields_an_empty_list(languages):
    assert parse_segments_payload('{"segments": []}', languages["de"]) == []


def test_a_label_that_would_be_refused_as_input_is_dropped_with_its_neighbours_kept(languages):
    parsed = parse_segments_payload(
        payload(
            '{"label":"vratiti се","surface":"се … вратио","why":"Повратна речца."}',
            '{"label":"јавити се","surface":"ми се … јавио","why":"Повратни глагол."}',
        ),
        languages["sr"],
    )
    assert [segment.label for segment in parsed] == ["јавити се"]


@pytest.mark.parametrize(
    "entry",
    ['{"label":""}', '{"label":42}', '{"surface":"steht … auf"}', '"aufstehen"', "null"],
)
def test_a_segment_without_a_usable_label_is_dropped(languages, entry):
    assert parse_segments_payload(payload(entry), languages["de"]) == []


def test_a_generous_model_is_truncated_rather_than_refused(languages):
    labels = [f"wort{'e' * index}" for index in range(MAX_SEGMENTS + 2)]
    entries = [f'{{"label":"{label}"}}' for label in labels]
    parsed = parse_segments_payload(payload(*entries), languages["de"])
    assert [segment.label for segment in parsed] == labels[:MAX_SEGMENTS]


def test_the_same_unit_is_offered_once(languages):
    parsed = parse_segments_payload(
        payload(
            '{"label":"aufstehen","surface":"steht … auf"}',
            '{"label":"aufstehen","surface":"stand … auf"}',
            '{"label":"ausfallen"}',
        ),
        languages["de"],
    )
    assert [segment.label for segment in parsed] == ["aufstehen", "ausfallen"]


def test_a_dropped_label_does_not_spend_one_of_the_offered_slots(languages):
    entries = ['{"label":"vratiti се"}'] + [
        f'{{"label":"reč{"i" * index}"}}' for index in range(MAX_SEGMENTS)
    ]
    parsed = parse_segments_payload(payload(*entries), languages["sr"])
    assert len(parsed) == MAX_SEGMENTS


def test_display_fields_are_optional_trimmed_and_bounded(languages):
    parsed = parse_segments_payload(
        payload(
            '{"label":"aufstehen","surface":"  steht … auf  ","why":42}',
            f'{{"label":"ausfallen","surface":"{"s" * 300}","why":"{"w" * 300}"}}',
        ),
        languages["de"],
    )
    assert parsed[0] == Segment("aufstehen", "steht … auf", "")
    assert len(parsed[1].surface) == MAX_SURFACE_LENGTH
    assert len(parsed[1].reason) == MAX_REASON_LENGTH


def test_junk_after_the_object_is_ignored(languages):
    parsed = parse_segments_payload(
        '{"segments":[{"label":"aufstehen"}]} and one closing remark',
        languages["de"],
    )
    assert [segment.label for segment in parsed] == ["aufstehen"]


@pytest.mark.parametrize(
    "broken",
    ["{broken", '{"segments": {}}', '{"units": []}', '["aufstehen"]'],
)
def test_an_unusable_payload_is_an_error(languages, broken):
    with pytest.raises(SegmentParseError):
        parse_segments_payload(broken, languages["de"])
