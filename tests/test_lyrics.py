from musicgen.domain import lyrics as L


def test_parse_sections_and_order():
    doc = L.parse("[Intro]\n\n[Verse 1]\nline a\nline b\n\n[Chorus]\nhook")
    assert [s.tag for s in doc.sections] == ["Intro", "Verse 1", "Chorus"]
    assert doc.sections[1].lines == ["line a", "line b"]
    assert doc.total_words == 5


def test_portuguese_aliases_are_canonicalized():
    doc = L.parse("[Verso 1]\num dois\n\n[Refrao]\ntres")
    assert [s.tag for s in doc.sections] == ["Verse 1", "Chorus"]


def test_modifier_is_extracted():
    doc = L.parse("[Chorus - anthemic]\nhook")
    assert doc.sections[0].tag == "Chorus"
    assert doc.sections[0].modifier == "anthemic"
    assert doc.render().startswith("[Chorus - anthemic]")


def test_pre_chorus_hyphen_is_not_a_modifier():
    doc = L.parse("[Pre-Chorus]\nsobe")
    assert doc.sections[0].tag == "Pre-Chorus"
    assert doc.sections[0].modifier is None


def test_untagged_text_becomes_single_verse_with_warning():
    doc = L.parse("so uma letra solta")
    assert len(doc.sections) == 1
    assert doc.sections[0].tag == "Verse"
    assert any(i.severity is L.Severity.WARNING for i in doc.issues)


def test_preamble_before_first_tag_is_wrapped_in_intro():
    doc = L.parse("texto solto\n\n[Chorus]\nhook")
    assert doc.sections[0].tag == "Intro"
    assert "texto solto" in doc.sections[0].lines


def test_empty_lyrics_is_error():
    doc = L.parse("   ")
    assert doc.has_errors


def test_render_roundtrip_is_stable():
    src = "[Verse 1]\na\nb\n\n[Chorus]\nc"
    once = L.parse(src).render()
    assert L.parse(once).render() == once


def test_duration_estimate_accounts_for_instrumental_sections():
    with_solo = L.parse("[Verse]\n" + "pa " * 70 + "\n\n[Guitar Solo]\n")
    without = L.parse("[Verse]\n" + "pa " * 70)
    assert with_solo.estimated_duration_s() > without.estimated_duration_s()


def test_modifier_on_compound_tag_is_recognized():
    """Regressao: 'Pre-Chorus - building' caia numa excecao por prefixo e a tag
    inteira virava desconhecida."""
    doc = L.parse("[Pre-Chorus - building]\nsobe")
    assert doc.sections[0].tag == "Pre-Chorus"
    assert doc.sections[0].modifier == "building"
    assert not any("nao e canonica" in i.message for i in doc.issues)


def test_post_chorus_with_modifier():
    doc = L.parse("[Post-Chorus - chanted]\nlala")
    assert doc.sections[0].tag == "Post-Chorus"
    assert doc.sections[0].modifier == "chanted"


def test_hyphen_without_spaces_stays_part_of_the_tag():
    doc = L.parse("[Pre-Chorus]\nx")
    assert doc.sections[0].tag == "Pre-Chorus"
    assert doc.sections[0].modifier is None


def test_multiword_tag_with_modifier():
    doc = L.parse("[Guitar Solo - screaming]\n")
    assert doc.sections[0].tag == "Guitar Solo"
    assert doc.sections[0].modifier == "screaming"


def test_numbered_tag_with_modifier():
    doc = L.parse("[Verse 2 - whispered]\nx")
    assert doc.sections[0].tag == "Verse 2"
    assert doc.sections[0].modifier == "whispered"
