from cortex_vec import parser


def test_extract_wikilinks_basic():
    text = "see [[Web benchmark]] and [[ SPACED ]] plus [[A|alias]]."
    links = parser.extract_wikilinks(text)
    assert "Web benchmark" in links
    assert "SPACED" in links
    assert "A" in links


def test_extract_wikilinks_none():
    assert parser.extract_wikilinks("no links here") == []


def test_extract_wikilinks_dedup():
    links = parser.extract_wikilinks("[[X]] [[X]] [[Y]]")
    assert sorted(links) == ["X", "Y"]
