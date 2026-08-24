from echo_words.sanitizer import sanitize_html


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
