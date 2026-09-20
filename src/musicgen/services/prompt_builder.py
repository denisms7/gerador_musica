"""Construcao do ``caption`` (prompt de estilo) a partir de um StyleSpec.

A documentacao do ACE-Step e explicita: descricoes especificas e
multidimensionais superam tags genericas, mas empilhar instrucoes demais degrada
o resultado. Este modulo ordena as dimensoes por peso perceptual e aplica um
teto de tokens.
"""
from __future__ import annotations

from musicgen.domain.models import StyleSpec, VocalGender

#: Ordem = prioridade. O corte por ``max_terms`` remove das dimensoes finais.
_DIMENSION_ORDER = ("genres", "moods", "instruments", "vocal", "production", "era")

_VOCAL_PHRASE = {
    VocalGender.FEMALE: "female vocal",
    VocalGender.MALE: "male vocal",
    VocalGender.DUET: "male and female duet vocals",
    VocalGender.CHOIR: "choir vocals",
}

#: Presets prontos, em vocabulario que o modelo reconhece bem.
STYLE_PRESETS: dict[str, StyleSpec] = {
    "MPB acustica": StyleSpec(
        genres=["brazilian mpb", "acoustic folk"],
        moods=["intimate", "nostalgic"],
        instruments=["nylon string guitar", "upright bass", "brushed drums"],
        vocal_gender=VocalGender.MALE,
        vocal_traits=["warm", "breathy"],
        production=["natural room reverb", "analog warmth"],
    ),
    "Samba / Pagode": StyleSpec(
        genres=["samba", "pagode"],
        moods=["joyful", "danceable"],
        instruments=["cavaquinho", "pandeiro", "surdo", "seven string guitar"],
        vocal_gender=VocalGender.MALE,
        vocal_traits=["expressive", "call and response backing vocals"],
        production=["live band feel"],
    ),
    "Sertanejo moderno": StyleSpec(
        genres=["sertanejo universitario", "country pop"],
        moods=["heartbroken", "anthemic"],
        instruments=["acoustic guitar", "accordion", "electric bass", "punchy drums"],
        vocal_gender=VocalGender.DUET,
        production=["modern polished mix", "wide stereo"],
    ),
    "Pop eletronico": StyleSpec(
        genres=["electropop", "synth pop"],
        moods=["euphoric", "driving"],
        instruments=["analog synth", "sidechained pads", "808 bass"],
        vocal_gender=VocalGender.FEMALE,
        vocal_traits=["airy", "layered harmonies"],
        production=["loud modern master", "gated reverb"],
    ),
    "Rock alternativo": StyleSpec(
        genres=["alternative rock", "indie rock"],
        moods=["urgent", "melancholic"],
        instruments=["distorted electric guitar", "driving bass", "live drums"],
        vocal_gender=VocalGender.MALE,
        vocal_traits=["raw", "strained"],
        production=["garage energy", "tape saturation"],
    ),
    "Balada piano": StyleSpec(
        genres=["piano ballad"],
        moods=["sad", "cinematic"],
        instruments=["grand piano", "string section"],
        vocal_gender=VocalGender.FEMALE,
        vocal_traits=["breathy", "vulnerable"],
        production=["sparse arrangement", "wide hall reverb"],
    ),
    "Trap / Hip-hop": StyleSpec(
        genres=["trap", "brazilian hip hop"],
        moods=["dark", "confident"],
        instruments=["808 sub bass", "hi-hat rolls", "atmospheric keys"],
        vocal_gender=VocalGender.MALE,
        vocal_traits=["rhythmic flow", "ad-libs"],
        production=["heavy low end", "tight mix"],
    ),
    "Gospel / Worship": StyleSpec(
        genres=["contemporary gospel", "worship"],
        moods=["uplifting", "reverent"],
        instruments=["piano", "organ", "swelling strings", "gospel choir"],
        vocal_gender=VocalGender.FEMALE,
        vocal_traits=["powerful", "melismatic"],
        production=["big arena build"],
    ),
}

#: Idiomas aceitos, mapeados para o vocabulario do modelo.
LANGUAGES: dict[str, str] = {
    "Portugues (BR)": "portuguese",
    "Ingles": "english",
    "Espanhol": "spanish",
    "Italiano": "italian",
    "Frances": "french",
    "Automatico": "unknown",
}


def _dedupe(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for t in terms:
        key = t.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(t.strip())
    return out


def build_caption(
    style: StyleSpec,
    *,
    vocal_language: str = "unknown",
    max_terms: int = 14,
) -> str:
    """Serializa o estilo em uma caption compacta e especifica.

    Args:
        style: dimensoes escolhidas pelo usuario.
        vocal_language: idioma do vocal, anexado como dica textual.
        max_terms: teto de termos. Acima disso o modelo perde foco.
    """
    if style.free_text and style.free_text.strip():
        base = style.free_text.strip()
        if vocal_language not in ("unknown", "", None) and "vocal" not in base.lower():
            base = f"{base}, {vocal_language} vocals"
        return base

    buckets: dict[str, list[str]] = {
        "genres": _dedupe(style.genres),
        "moods": _dedupe(style.moods),
        "instruments": _dedupe(style.instruments),
        "vocal": _dedupe(
            ([_VOCAL_PHRASE[style.vocal_gender]] if style.vocal_gender in _VOCAL_PHRASE else [])
            + style.vocal_traits
        ),
        "production": _dedupe(style.production),
        "era": [style.era] if style.era else [],
    }

    terms: list[str] = []
    for dim in _DIMENSION_ORDER:
        for term in buckets[dim]:
            if len(terms) >= max_terms:
                break
            terms.append(term)

    if not terms:
        terms = ["modern pop", "clear vocals"]

    if vocal_language not in ("unknown", "", None):
        terms.append(f"{vocal_language} lyrics")

    return ", ".join(terms)


def suggest_bpm(style: StyleSpec) -> int | None:
    """Heuristica de BPM por genero. ``None`` deixa o modelo decidir."""
    table = {
        "ballad": 68,
        "piano ballad": 68,
        "samba": 100,
        "pagode": 96,
        "mpb": 84,
        "brazilian mpb": 84,
        "sertanejo": 92,
        "sertanejo universitario": 92,
        "trap": 140,
        "electropop": 118,
        "synth pop": 118,
        "alternative rock": 132,
        "indie rock": 130,
        "worship": 74,
        "contemporary gospel": 76,
    }
    for genre in style.genres:
        if (bpm := table.get(genre.strip().lower())) is not None:
            return bpm
    return None
