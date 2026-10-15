import json
from pathlib import Path

import pytest

from echo_words.sanitizer import sanitize_html

# Article lines as models wrote them in recorded bench answers, with what the reader is shown;
# every clause of the bold rule that changes a recorded answer changes one of these lines.
_RECORDED_LINES = json.loads(
    (Path(__file__).parent / "data" / "markdown_bold_recorded.json").read_text(encoding="utf-8")
)


def test_stray_markup_characters_are_escaped():
    assert sanitize_html("one < two & three > zero") == ("one &lt; two &amp; three &gt; zero")


def test_disallowed_tags_are_escaped_but_emphasis_survives():
    assert sanitize_html("<script>x</script><b>safe</b>") == (
        "&lt;script&gt;x&lt;/script&gt;<b>safe</b>"
    )


def test_an_allowed_tag_can_be_split_between_replacement_updates():
    assert sanitize_html("word <") == "word &lt;"
    assert sanitize_html("word <b>bold</b>") == "word <b>bold</b>"


def test_an_unclosed_tag_is_closed_at_the_current_cut():
    assert sanitize_html("before <i>example") == "before <i>example</i>"


def test_forms_table_tags_survive_and_balance():
    table = "<table><tr><td><i>er steht auf</i></td><td>он встаёт</td></tr></table>"
    assert sanitize_html(table) == table


def test_a_table_tag_carrying_an_attribute_is_escaped():
    # The angle brackets go; the quotes stay, as they do everywhere else in text.
    assert sanitize_html('<table class="x">') == '&lt;table class="x"&gt;'


def test_an_unclosed_table_is_closed_in_order():
    assert sanitize_html("<table><tr><td>x") == "<table><tr><td>x</td></tr></table>"


def test_markdown_bold_reads_as_bold():
    assert sanitize_html("**x**") == "<b>x</b>"
    assert sanitize_html("**Sve mi se čini da …** x") == "<b>Sve mi se čini da …</b> x"


def test_an_unclosed_markdown_bold_stays_literal_until_its_pair_arrives():
    assert sanitize_html("word **bo") == "word **bo"
    assert sanitize_html("word **bold*") == "word **bold*"
    assert sanitize_html("word **bold**") == "word <b>bold</b>"


def test_a_lone_asterisk_survives():
    assert sanitize_html("от *or-* и *prъzъrcъ") == "от *or-* и *prъzъrcъ"
    assert sanitize_html("a ** b") == "a ** b"


def test_markdown_bold_does_not_span_a_line_break():
    assert sanitize_html("**one\ntwo**") == "**one\ntwo**"


def test_markdown_bold_keeps_the_lone_asterisks_inside_it():
    assert sanitize_html("1. **Артикль *the***: x") == "1. <b>Артикль *the*</b>: x"


def test_a_markdown_bold_nested_in_another_is_read():
    assert sanitize_html("2. **Предлог **on****: x") == "2. <b>Предлог <b>on</b></b>: x"


def test_a_bracket_doubling_a_bold_tag_is_dropped():
    assert sanitize_html("<<b>x</b>> y") == "<b>x</b> y"


def test_a_bracket_away_from_a_bold_tag_stays():
    assert sanitize_html("a < b") == "a &lt; b"
    assert sanitize_html("<b>x</b> > y") == "<b>x</b> &gt; y"
    assert sanitize_html("<<i>x</i>> y") == "&lt;<i>x</i>&gt; y"


def test_a_markdown_bold_never_crosses_an_allowed_tag():
    table = "<table><tr><td>**x*</td><td>**y**</td></tr></table>"
    assert sanitize_html(table) == "<table><tr><td>**x*</td><td><b>y</b></td></tr></table>"
    assert sanitize_html("<i>**x</i> y**") == "<i>**x</i> y**"
    assert sanitize_html("**<b>Bank</b>**") == "<b><b>Bank</b></b>"
    assert sanitize_html("**<i>x</i>**") == "<b><i>x</i></b>"
    assert sanitize_html("<i>**x</i><i>y**</i>") == "<i>**x</i><i>y**</i>"
    assert sanitize_html("<td>**x</td><td>y**</td>") == "<td>**x</td><td>y**</td>"
    assert sanitize_html("**x <i>y**</i>") == "**x <i>y**</i>"
    assert sanitize_html("<i>**x</b> y**</i>") == "<i>**x&lt;/b&gt; y**</i>"
    assert sanitize_html("**a <i>b</b> c** d</i>") == "**a <i>b&lt;/b&gt; c** d</i>"
    assert sanitize_html("**a <i>**b c****</i>") == "**a <i><b>b c</b>**</i>"
    assert sanitize_html("**a <i>b***c**</i>") == "**a <i>b***c**</i>"


def test_an_unclosed_markdown_bold_does_not_pair_with_one_after_punctuation():
    assert sanitize_html("Слово **ništa* в родительном падеже (**ničega**)") == (
        "Слово **ništa* в родительном падеже (<b>ničega</b>)"
    )


def test_a_markdown_bold_after_a_letter_does_not_open_onto_punctuation():
    assert sanitize_html("x**(y)**") == "x**(y)**"
    assert sanitize_html("a**→b**") == "a**→b**"


def test_a_bracket_beside_a_markdown_bold_stays():
    assert sanitize_html("*mirъ* <**мир**") == "*mirъ* &lt;<b>мир</b>"
    assert sanitize_html("**мир**> *mirъ*") == "<b>мир</b>&gt; *mirъ*"


@pytest.mark.parametrize(
    ("text", "html"),
    [
        ("рачун**а**", "рачун<b>а</b>"),
        ("**\\*iti**", "<b>\\*iti</b>"),
        ("*vъditi* и *rač‑*, далее **водити**", "*vъditi* и *rač‑*, далее <b>водити</b>"),
        ("***x***", "***x***"),
        ("***x**", "***x**"),
        ("2 ** 3", "2 ** 3"),
        ("x ** y ** z", "x ** y ** z"),
        ("** x **", "** x **"),
        ("* **x** and *y*", "* <b>x</b> and *y*"),
    ],
)
def test_markdown_bold_keeps_the_recorded_shapes(text, html):
    assert sanitize_html(text) == html


@pytest.mark.parametrize(
    "recorded",
    _RECORDED_LINES,
    ids=[f"{line['run']} {line['item']} line {line['line']}" for line in _RECORDED_LINES],
)
def test_a_recorded_article_line_reads_as_the_reader_sees_it(recorded):
    assert sanitize_html(recorded["text"]) == recorded["html"]
