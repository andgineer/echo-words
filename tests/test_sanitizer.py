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
