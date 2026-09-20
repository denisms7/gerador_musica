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
#:
#: Cada preset descreve o MESMO conjunto de dimensoes (genero, clima,
#: instrumentos, vocal, producao) para que a troca entre eles mude o resultado
#: de forma previsivel. Termos em ingles porque e o vocabulario em que o modelo
#: foi treinado; o nome do genero em portugues entra junto quando ele e
#: especifico da musica brasileira e nao tem equivalente.
STYLE_PRESETS: dict[str, StyleSpec] = {
    # ------------------------------------------------------------------ Brasil
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
    # -------------------------------------------------------------- Sertanejo
    "Sertanejo universitario": StyleSpec(
        genres=["sertanejo universitario", "brazilian country pop"],
        moods=["heartbroken", "anthemic"],
        instruments=["acoustic guitar", "accordion", "electric bass", "punchy drums"],
        vocal_gender=VocalGender.DUET,
        vocal_traits=["clear", "conversational"],
        production=["modern polished mix", "wide stereo"],
    ),
    "Sertanejo raiz": StyleSpec(
        genres=["sertanejo raiz", "brazilian rural folk"],
        moods=["longing", "storytelling"],
        instruments=["viola caipira", "nylon guitar", "accordion"],
        vocal_gender=VocalGender.DUET,
        vocal_traits=["nasal close harmony", "two-part thirds"],
        production=["sparse arrangement", "natural room"],
    ),
    "Sertanejo romantico 90s": StyleSpec(
        genres=["sertanejo romantico", "90s brazilian country ballad"],
        moods=["romantic", "melodramatic"],
        instruments=["accordion", "acoustic guitar", "lush strings", "soft drums"],
        vocal_gender=VocalGender.DUET,
        vocal_traits=["emotive", "close harmonies"],
        production=["warm 90s production", "wide reverb"],
    ),
    "Modao / sofrencia": StyleSpec(
        genres=["modao", "sofrencia", "brazilian heartbreak country"],
        moods=["devastated", "drunken melancholy"],
        instruments=["accordion", "viola caipira", "acoustic guitar", "slow drums"],
        vocal_gender=VocalGender.MALE,
        vocal_traits=["cracking", "pleading"],
        production=["intimate", "dry vocal upfront"],
    ),
    "Sertanejo rock": StyleSpec(
        genres=["sertanejo rock", "brazilian country rock"],
        moods=["defiant", "anthemic"],
        instruments=[
            "overdriven electric guitar",
            "steel-string acoustic guitar",
            "accordion",
            "powerful live drums",
        ],
        vocal_gender=VocalGender.MALE,
        vocal_traits=["powerful chest voice", "natural grit"],
        production=["organic dynamic mix", "guitars wide"],
    ),
    "Feminejo": StyleSpec(
        genres=["feminejo", "sertanejo pop"],
        moods=["confident", "celebratory"],
        instruments=["acoustic guitar", "accordion", "programmed and live drums", "synth pads"],
        vocal_gender=VocalGender.FEMALE,
        vocal_traits=["assertive", "layered backing vocals"],
        production=["loud modern master", "polished"],
    ),
    "Agronejo / arrocha": StyleSpec(
        genres=["agronejo", "arrocha sertanejo"],
        moods=["party", "swaggering"],
        instruments=["accordion", "electric guitar", "heavy kick", "electronic bass"],
        vocal_gender=VocalGender.MALE,
        vocal_traits=["rhythmic", "shouted gang vocals"],
        production=["club-ready mix", "heavy low end"],
    ),
    # ------------------------------------------------------------------- Rock
    "Rock alternativo": StyleSpec(
        genres=["alternative rock", "indie rock"],
        moods=["urgent", "melancholic"],
        instruments=["distorted electric guitar", "driving bass", "live drums"],
        vocal_gender=VocalGender.MALE,
        vocal_traits=["raw", "strained"],
        production=["garage energy", "tape saturation"],
    ),
    "Rock nacional 80s": StyleSpec(
        genres=["brazilian rock", "80s new wave rock"],
        moods=["restless", "ironic"],
        instruments=["chorused electric guitar", "melodic bass", "gated drums", "analog synth"],
        vocal_gender=VocalGender.MALE,
        vocal_traits=["declamatory", "nasal"],
        production=["80s gated reverb", "bright mix"],
        era="1980s",
    ),
    "Hard rock": StyleSpec(
        genres=["hard rock", "blues rock"],
        moods=["swaggering", "energetic"],
        instruments=["crunchy electric guitar riffs", "hammond organ", "thick bass", "big drums"],
        vocal_gender=VocalGender.MALE,
        vocal_traits=["raspy", "belted high notes"],
        production=["analog warmth", "room drums"],
    ),
    "Grunge": StyleSpec(
        genres=["grunge", "90s alternative rock"],
        moods=["angsty", "brooding"],
        instruments=["fuzzy detuned guitar", "sludgy bass", "heavy drums"],
        vocal_gender=VocalGender.MALE,
        vocal_traits=["anguished", "shifting from mumble to scream"],
        production=["raw unpolished mix", "loud quiet loud dynamics"],
        era="1990s",
    ),
    "Punk rock": StyleSpec(
        genres=["punk rock", "melodic hardcore"],
        moods=["angry", "urgent"],
        instruments=["buzzsaw guitar", "galloping bass", "fast drums"],
        vocal_gender=VocalGender.MALE,
        vocal_traits=["shouted", "gang backing vocals"],
        production=["fast and raw", "compressed"],
    ),
    "Rock progressivo": StyleSpec(
        genres=["progressive rock"],
        moods=["epic", "contemplative"],
        instruments=["mellotron", "hammond organ", "intricate guitar", "complex drums"],
        vocal_gender=VocalGender.MALE,
        vocal_traits=["theatrical", "layered harmonies"],
        production=["dynamic shifts", "wide stereo field"],
    ),
    "Post-rock instrumental": StyleSpec(
        genres=["post-rock", "cinematic instrumental"],
        moods=["expansive", "bittersweet"],
        instruments=["tremolo picked guitar", "ambient textures", "swelling drums", "strings"],
        vocal_gender=VocalGender.UNSET,
        production=["slow build to climax", "huge reverb"],
    ),
    "Arena rock": StyleSpec(
        genres=["arena rock", "stadium rock"],
        moods=["triumphant", "anthemic"],
        instruments=["soaring lead guitar", "big bass", "thundering drums", "synth pads"],
        vocal_gender=VocalGender.MALE,
        vocal_traits=["powerful sustained notes", "crowd backing vocals"],
        production=["huge polished mix", "stadium ambience"],
    ),
    # ------------------------------------------------------------------ Metal
    "Heavy metal classico": StyleSpec(
        genres=["classic heavy metal", "nwobhm"],
        moods=["heroic", "driving"],
        instruments=["twin lead guitars", "galloping bass", "double kick drums"],
        vocal_gender=VocalGender.MALE,
        vocal_traits=["soaring clean vocals", "high wails"],
        production=["punchy analog mix"],
        era="1980s",
    ),
    "Power metal": StyleSpec(
        genres=["power metal", "symphonic metal"],
        moods=["epic", "uplifting"],
        instruments=["fast tremolo guitars", "orchestral keys", "double bass drums", "choir pads"],
        vocal_gender=VocalGender.MALE,
        vocal_traits=["operatic clean vocals", "sustained high notes"],
        production=["grand cinematic mix", "layered choirs"],
    ),
    "Thrash metal": StyleSpec(
        genres=["thrash metal"],
        moods=["aggressive", "relentless"],
        instruments=["palm-muted riffing", "aggressive bass", "blast-adjacent drums"],
        vocal_gender=VocalGender.MALE,
        vocal_traits=["shouted aggressive vocals"],
        production=["tight dry mix", "scooped guitars"],
    ),
    "Metal melodico": StyleSpec(
        genres=["melodic metal", "melodic death metal"],
        moods=["dark", "sorrowful"],
        instruments=["harmonized lead guitars", "heavy rhythm guitar", "double kick", "keys"],
        vocal_gender=VocalGender.MALE,
        vocal_traits=["harsh verses", "clean soaring chorus"],
        production=["modern heavy mix", "wide guitars"],
    ),
    "Metalcore": StyleSpec(
        genres=["metalcore", "modern heavy"],
        moods=["cathartic", "intense"],
        instruments=["chugging downtuned guitar", "breakdown riffs", "punchy drums", "ambient pads"],
        vocal_gender=VocalGender.MALE,
        vocal_traits=["screamed verses", "melodic sung chorus"],
        production=["loud modern master", "tight low end"],
    ),
    "Gothic / doom": StyleSpec(
        genres=["gothic metal", "doom metal"],
        moods=["mournful", "heavy and slow"],
        instruments=["downtuned distorted guitar", "church organ", "slow crushing drums", "strings"],
        vocal_gender=VocalGender.MALE,
        vocal_traits=["deep baritone", "occasional growls"],
        production=["thick and cavernous", "long reverb tails"],
    ),
    "Metal sinfonico": StyleSpec(
        genres=["symphonic metal", "orchestral metal"],
        moods=["dramatic", "grandiose"],
        instruments=["full orchestra", "heavy guitars", "double kick drums", "choir"],
        vocal_gender=VocalGender.FEMALE,
        vocal_traits=["operatic soprano", "powerful vibrato"],
        production=["cinematic layering", "wide dynamic range"],
    ),
    # --------------------------------------------------------- Pop e restante
    "Pop eletronico": StyleSpec(
        genres=["electropop", "synth pop"],
        moods=["euphoric", "driving"],
        instruments=["analog synth", "sidechained pads", "808 bass"],
        vocal_gender=VocalGender.FEMALE,
        vocal_traits=["airy", "layered harmonies"],
        production=["loud modern master", "gated reverb"],
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

#: Agrupamento para a UI. Com quase trinta presets, um unico selectbox vira uma
#: lista de rolagem inutil; a categoria estreita a escolha antes do preset.
PRESET_CATEGORIES: dict[str, tuple[str, ...]] = {
    "Sertanejo": (
        "Sertanejo universitario",
        "Sertanejo rock",
        "Sertanejo romantico 90s",
        "Sertanejo raiz",
        "Modao / sofrencia",
        "Feminejo",
        "Agronejo / arrocha",
    ),
    "Rock": (
        "Rock alternativo",
        "Rock nacional 80s",
        "Hard rock",
        "Arena rock",
        "Grunge",
        "Punk rock",
        "Rock progressivo",
        "Post-rock instrumental",
    ),
    "Metal": (
        "Heavy metal classico",
        "Power metal",
        "Thrash metal",
        "Metal melodico",
        "Metalcore",
        "Metal sinfonico",
        "Gothic / doom",
    ),
    "Brasil": (
        "MPB acustica",
        "Samba / Pagode",
    ),
    "Pop e outros": (
        "Pop eletronico",
        "Balada piano",
        "Trap / Hip-hop",
        "Gospel / Worship",
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
        # brasil
        "brazilian mpb": 84,
        "mpb": 84,
        "acoustic folk": 88,
        "samba": 100,
        "pagode": 96,
        # sertanejo
        "sertanejo universitario": 92,
        "sertanejo rock": 104,
        "sertanejo romantico": 76,
        "sertanejo raiz": 80,
        "modao": 68,
        "sofrencia": 70,
        "feminejo": 98,
        "agronejo": 96,
        "arrocha sertanejo": 92,
        # rock
        "alternative rock": 132,
        "indie rock": 130,
        "brazilian rock": 138,
        "hard rock": 124,
        "blues rock": 112,
        "arena rock": 126,
        "stadium rock": 126,
        "grunge": 116,
        "punk rock": 176,
        "melodic hardcore": 180,
        "progressive rock": 108,
        "post-rock": 92,
        # metal
        "classic heavy metal": 144,
        "nwobhm": 148,
        "power metal": 172,
        "thrash metal": 190,
        "melodic metal": 150,
        "melodic death metal": 155,
        "metalcore": 145,
        "symphonic metal": 130,
        "gothic metal": 84,
        "doom metal": 68,
        # pop e outros
        "piano ballad": 68,
        "ballad": 68,
        "electropop": 118,
        "synth pop": 118,
        "trap": 140,
        "brazilian hip hop": 138,
        "contemporary gospel": 76,
        "worship": 74,
    }
    for genre in style.genres:
        if (bpm := table.get(genre.strip().lower())) is not None:
            return bpm
    return None
