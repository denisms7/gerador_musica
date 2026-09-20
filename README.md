# MusicGen Local

Aplicacao Python que transforma **uma letra** em **musica completa** — voz cantada +
instrumental — rodando **100% na sua maquina**, sem API paga e sem enviar nada para fora.

Backend de inferencia: **[ACE-Step 1.5](https://github.com/ace-step/ACE-Step-1.5)**
(MIT, 50+ idiomas incluindo portugues, 10–600s por musica).

---

## Arquitetura

```
┌─────────────────────┐        HTTP         ┌──────────────────────────┐
│  Streamlit (app.py) │ ──────────────────> │  ACE-Step API :8001      │
│  UI + orquestracao  │ <────────────────── │  modelo residente em VRAM│
└──────────┬──────────┘   poll + download   └──────────────────────────┘
           │
           ├── services/generation.py   pipeline: validar → gerar → normalizar → persistir
           ├── providers/               contrato + implementacao (trocavel)
           ├── domain/                  letra, estilo, job — sem dependencia de framework
           └── persistence/             SQLite (historico, faixas, metricas)
```

**Por que dois processos.** O Streamlit reexecuta o script inteiro a cada clique; carregar
um modelo de 9 GB nesse processo seria inviavel. O servidor de inferencia roda separado,
mantem o modelo na VRAM entre geracoes e isola as dependencias pesadas (torch/vLLM/CUDA)
do venv da UI.

**Por que a camada `MusicProvider`.** Todo o app depende de uma interface de 4 metodos
(`health`, `submit`, `poll`, `fetch_artifacts`). Trocar ACE-Step por DiffRhythm, YuE ou
uma API remota e escrever uma classe nova e registra-la em `providers/registry.py` —
nenhum servico ou tela muda.

### Estrutura

| Caminho | Responsabilidade |
|---|---|
| `src/musicgen/domain/models.py` | Entidades e invariantes (BPM 30–300, duracao 10–600s...) |
| `src/musicgen/domain/lyrics.py` | Parser de tags `[Verse]/[Chorus]`, aliases PT-BR, estimativa de duracao |
| `src/musicgen/providers/` | Contrato + cliente REST do ACE-Step |
| `src/musicgen/services/prompt_builder.py` | Estilo estruturado → `caption`, com presets e teto de termos |
| `src/musicgen/services/generation.py` | Pipeline completo, emitindo progresso como iterador |
| `src/musicgen/services/postprocess.py` | Loudness (-14 LUFS), teto de pico, fades |
| `src/musicgen/services/stems.py` | Separacao Demucs opcional, em subprocesso |
| `src/musicgen/persistence/` | SQLite com WAL, upsert idempotente, cascade |
| `src/musicgen/server/supervisor.py` | Sobe/derruba o servidor de inferencia pela UI |
| `src/musicgen/ui/` | Streamlit: visao geral, gerar, biblioteca, diagnostico |
| `src/musicgen/cli.py` | `musicgen doctor / lint / generate / list` |

---

## Requisitos

| Item | Minimo | Recomendado |
|---|---|---|
| GPU | NVIDIA 6 GB | NVIDIA 12–24 GB |
| Disco | 20 GB livres | 40 GB |
| Python | 3.10 | 3.11 |
| Extras | `uv`, `git` | + `ffmpeg` |

Perfis de modelo por VRAM (o `scripts/diagnose.py` escolhe por voce):

| VRAM | DiT | LM |
|---|---|---|
| ≥24 GB | `acestep-v15-xl-sft` | `acestep-5Hz-lm-4B` |
| 16–20 GB | `acestep-v15-sft` | `acestep-5Hz-lm-1.7B` |
| 8–16 GB | `acestep-v15-turbo` | `acestep-5Hz-lm-1.7B` |
| 6–8 GB | `acestep-v15-turbo` | `acestep-5Hz-lm-0.6B` |

---

## Instalacao (Windows)

```powershell
cd C:\Projetos\musica
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

O script instala o `uv`, cria o venv do app, clona e sincroniza o ACE-Step em
`C:\Projetos\ACE-Step-1.5`, gera o `.env` e roda o diagnostico de GPU.

Ajuste `MUSICGEN_DIT_MODEL` / `MUSICGEN_LM_MODEL` no `.env` conforme a recomendacao.

### Dependencias

Dois ambientes, de proposito:

| Ambiente | Onde | Como instalar | O que tem |
|---|---|---|---|
| **App** | `C:\Projetos\musica\.venv` | `pip install -e .` ou `pip install -r requirements.txt` | Streamlit, pydantic, httpx, soundfile — leve, sem torch |
| **Inferencia** | `C:\Projetos\ACE-Step-1.5\.venv` | `uv sync` (na pasta do ACE-Step) | torch, vLLM, CUDA, pesos do modelo |

Arquivos de requisitos do app:

```bash
pip install -r requirements.txt         # runtime (UI + CLI + pipeline)
pip install -r requirements-dev.txt     # runtime + pytest, pytest-cov, ruff
pip install -r requirements-stems.txt   # OPCIONAL: torch + demucs, so p/ stems
```

`pyproject.toml` e a fonte canonica (e o que instala o comando `musicgen`); os
`requirements*.txt` espelham os mesmos pins para CI, Docker e quem prefere pip puro.
Pins usam compatible-release (`~=`): aceita patch/minor, bloqueia major.

`requirements-stems.txt` puxa torch (~2,5 GB) para o venv do app e so vale a pena com
`MUSICGEN_ENABLE_STEMS=true`. Para separar stems na GPU, instale o torch antes pelo
indice oficial (`--index-url https://download.pytorch.org/whl/cu126`, ajustando o build
ao seu driver) — o arquivo instala a build de CPU por padrao.

### Uso

Duas janelas do PowerShell, ambas a partir de `C:\Projetos\musica`:

```powershell
# janela 1 — servidor de inferencia (o primeiro start baixa os modelos)
.\scripts\start-backend.ps1

# janela 2 — aplicacao
.\scripts\run.ps1          # abre http://localhost:8501
```

> **`uv run acestep-api` so funciona dentro do repositorio do ACE-Step.**
> Rodado em `C:\Projetos\musica` ele falha com `program not found`, porque ali o
> projeto e o `musicgen`. O `start-backend.ps1` le `MUSICGEN_ACESTEP_HOME` do `.env`,
> valida a pasta e roda o comando no lugar certo.

O servidor tambem pode ser iniciado pela aba **Diagnostico** da propria UI.

> **Python:** use o CPython gerenciado pelo `uv` (o `setup.ps1` pede 3.11). O Python
> 3.13 do Microsoft Store (`...\WindowsApps\...`) e sandboxed e costuma quebrar venvs;
> torch e vLLM tambem ainda sao irregulares em 3.13.

---

## Como escrever a letra

A forma da musica vem das tags de estrutura. Sem elas o modelo improvisa.

```
[Intro]

[Verse 1]
o primeiro verso vai aqui
com quantas linhas voce quiser

[Pre-Chorus]
a tensao que sobe

[Chorus]
o gancho que gruda
o gancho que gruda

[Verse 2]
...

[Chorus]

[Bridge - whispered]
a virada

[Outro]
```

* Tags canonicas: `Intro`, `Verse`, `Pre-Chorus`, `Chorus`, `Post-Chorus`, `Bridge`,
  `Build`, `Drop`, `Breakdown`, `Instrumental`, `Guitar Solo`, `Piano Interlude`,
  `Hook`, `Outro`, `Fade Out`.
* Escrever em portugues funciona: `[Verso 1]`, `[Refrao]`, `[Ponte]` sao traduzidos
  automaticamente pelo parser.
* Modificador apos hifen ajusta a interpretacao: `[Chorus - anthemic]`.
* **Nao empilhe instrucoes** — mais de um modificador por secao confunde o modelo.

### Prompt de estilo

Especifico bate generico. Combine dimensoes:

```
sad piano ballad with female breathy vocal, sparse arrangement,
wide hall reverb, 90s analog warmth
```

Os presets prontos (MPB, Samba/Pagode, Sertanejo, Pop eletronico, Rock alternativo,
Balada piano, Trap, Gospel) ja seguem esse formato — use-os como ponto de partida e
edite no campo de descricao livre.

---

## Linha de comando

```bash
musicgen doctor                       # checa backend, modelos, banco
musicgen lint letra.txt               # valida estrutura da letra
musicgen generate letra.txt \
    --title "Minha musica" \
    --preset "MPB acustica" \
    --batch 2 --seed 42
musicgen list -n 10
```

---

## Iteracao pratica

1. Gere **2 takes** por vez (`batch=2`): a variancia entre seeds e alta e o custo marginal
   e baixo.
2. Gostou de um take? Anote a **seed** (aparece sob o player) e refine o prompt mantendo
   a seed fixa — muda o arranjo sem perder a identidade.
3. `thinking` ligado deixa o LM inferir BPM, tom e fraseado a partir da letra. Desligue e
   fixe BPM/tom quando quiser controle duro.
4. Modelos `turbo`: 8 passos, CFG ignorado. Modelos `sft`/`base`: 50 passos, CFG ~7.
5. Ative `MUSICGEN_ENABLE_STEMS=true` para receber vocal/bateria/baixo separados e mixar
   na sua DAW (exige `pip install -e .[stems]`).

---

## Desenvolvimento

```bash
pip install -e ".[dev]"
pytest -q          # 42 testes: dominio, letra, prompt, provider (HTTP mockado), pipeline
ruff check src app.py scripts tests
```

O provider e testado com `httpx.MockTransport` e o pipeline com um `FakeProvider` que
grava WAV real — a suite roda inteira sem GPU e sem o servidor de inferencia.

---

## Limites conhecidos

* Vocal em portugues e bom, mas nao perfeito: silabas atipicas as vezes saem mastigadas.
  Ajustar a divisao silabica na letra (separar palavras longas em linhas) ajuda.
* Musicas acima de ~4 minutos perdem coerencia estrutural; prefira gerar por secoes e
  montar na DAW.
* A separacao em stems via Demucs e pos-hoc — nao e o mesmo que o modelo gerar trilhas
  isoladas; espere vazamento entre stems.

## Licenca

Codigo deste app: use como quiser. ACE-Step 1.5: MIT. Os pesos dos modelos tem termos
proprios — verifique antes de uso comercial.
