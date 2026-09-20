from musicgen.domain.models import StyleSpec, VocalGender
from musicgen.services.prompt_builder import (
    STYLE_PRESETS,
    build_caption,
    suggest_bpm,
)


def test_free_text_overrides_structured_fields():
    style = StyleSpec(genres=["samba"], free_text="dark cinematic score")
    assert build_caption(style, vocal_language="unknown") == "dark cinematic score"


def test_free_text_gets_language_hint():
    style = StyleSpec(free_text="sad piano ballad")
    assert "portuguese vocals" in build_caption(style, vocal_language="portuguese")


def test_vocal_gender_is_rendered_as_phrase():
    style = StyleSpec(genres=["pop"], vocal_gender=VocalGender.FEMALE)
    assert "female vocal" in build_caption(style)


def test_max_terms_is_enforced():
    style = StyleSpec(genres=[f"g{i}" for i in range(30)])
    caption = build_caption(style, vocal_language="unknown", max_terms=5)
    assert len(caption.split(", ")) == 5


def test_dimension_priority_keeps_genres_first():
    style = StyleSpec(genres=["samba"], production=["tape saturation"], moods=["joyful"])
    parts = build_caption(style, vocal_language="unknown", max_terms=2).split(", ")
    assert parts == ["samba", "joyful"]


def test_duplicates_are_removed():
    style = StyleSpec(genres=["pop", "Pop", " pop "])
    assert build_caption(style, vocal_language="unknown") == "pop"


def test_empty_style_falls_back_to_default():
    assert build_caption(StyleSpec(), vocal_language="unknown")


def test_all_presets_produce_captions():
    for name, style in STYLE_PRESETS.items():
        caption = build_caption(style, vocal_language="portuguese")
        assert caption and "portuguese" in caption, name


def test_suggest_bpm_matches_known_genre():
    assert suggest_bpm(StyleSpec(genres=["Samba"])) == 100
    assert suggest_bpm(StyleSpec(genres=["genero inexistente"])) is None
