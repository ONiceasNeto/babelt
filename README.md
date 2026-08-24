
<div align="center">

```
                              ▄▄▄▄▄▄▄▄▄
                          ▄▄█████████████▄▄
                        ██████████████████████
                      ▄▄██████████████████████▄▄
                  ▄▄██████████████████████████████▄▄
                ████████████████████████████████████
             ▄▄████████████████████████████████████████▄▄
           ██████████████████████████████████████████████████
        ▄▄██████████████████████████████████████████████████████▄▄
      ████████████████████████████████████████████████████████████████
```

```
      ██████╗  █████╗ ██████╗ ███████╗██╗  ████████╗
      ██╔══██╗██╔══██╗██╔══██╗██╔════╝██║  ╚══██╔══╝
      ██████╔╝███████║██████╔╝█████╗  ██║     ██║
      ██╔══██╗██╔══██║██╔══██╗██╔══╝  ██║     ██║
      ██████╔╝██║  ██║██████╔╝███████╗███████╗██║
      ╚═════╝ ╚═╝  ╚═╝╚═════╝ ╚══════╝╚══════╝╚═╝
```

**The tower fell. The terminal kept speaking English.**

*Offline translator for terminal output. Ships with English → Brazilian
Portuguese; the pipeline is not tied to it.*

[![CI](https://github.com/ONiceasNeto/babelt/actions/workflows/ci.yml/badge.svg)](https://github.com/ONiceasNeto/babelt/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)

**English** · [Português](README.pt-BR.md)

</div>

---

```console
$ babelt ls
Usage: ls [OPTION]... [FILE]...
Listar informações sobre os FILEs (o diretório atual por padrão). Classificar as
entradas em ordem alfabética se nenhum dos -cftuvSUX nem --sort for
especificado.

  -a, --all                  Não ignore as entradas que começam com .
  -A, --almost-all           não listar implícito . e ..
  -B, --ignore-backups       não listar entradas implícitas terminadas em ~
```

And a whole man page:

```console
$ babelt ss
SS(8) Manual do Gestor de Sistema SS(8)

NOME
       ss - outro utilitário para investigar sockets

SINOPSE
       ss [options] [ FILTER ]

DESCRIÇÃO
       ss é usado para despejar estatísticas socket. Ele permite mostrar
       informações semelhantes ao netstat. Ele pode exibir mais informações TCP
       e estado do que outras ferramentas.
```

Real output, not touched up. `SINOPSE` stays in English on purpose: a synopsis
is command grammar, treated as a literal block and never sent to the model.

No cloud. No API key. Nothing about your terminal leaves your machine. The
model runs locally, on CPU, and `ls --help` comes back translated in under a
second.

---

## Why this exists

The barrier to entry in the terminal is not conceptual. It is linguistic.

Beginners rarely get stuck because `find` is hard — they get stuck because the
answer sits in a three-hundred-line man page written in technical English. The
documentation exists, it is already installed on the machine, and it is
unreadable to a large share of the people who need it most.

This is not a Brazilian problem. It is the ordinary condition of most Linux
users worldwide: system documentation is written in English and stays in
English, no matter who is reading it.

babelt does not simplify anything and does not rewrite anything. It translates
what is already there, keeping every flag, path and example intact, and gives
you back the original English when it cannot translate well.

## How it avoids wrecking your output

Translating terminal text is not the same as translating prose.
`--block-size=SIZE` is not a sentence. `/usr/local/bin` must not become
`/usr/local/caixa`.

**No flag, path, variable or address ever reaches the model.** Before
translation, every syntax token is replaced by an opaque marker; afterwards,
the original literal comes back byte for byte.

```
Use --verbose to list the contents of /etc/services.
Use --verbose para listar o conteúdo de /etc/services.
     ^^^^^^^^^                         ^^^^^^^^^^^^^^ intact, guaranteed
```

Each translated segment then goes through a validator that checks whether the
masks came back, whether the length is plausible, and whether anything is
corrupted. **A segment that fails is discarded and the original English is
returned in its place** — the output may end up partly in English, but it
never comes out wrong.

A translated flag produces an invalid command that the user will copy and
paste: worse than not translating at all. The guarantee does not come from the
quality of the model. It comes from masking first and rejecting in code after.

Measured across `ls`, `grep`, `find`, `tar`, `ssh` and `git`: **85.4% of prose
is translated** — 1,609 of 1,884 segments — and the other 275 fall back to the
original English. `babelt --stats <command>` reports the number on your own
machine, with the reason for each rejection.

---

## Status and direction

Today babelt translates **EN → pt-BR**. It is the only packaged pair, because
it is the one that has been measured, tuned and validated in depth.

The pipeline, however, does not know Portuguese exists. `normalize`, `segment`,
`mask` and `restore` operate on the structure of terminal text — flags, paths,
literal blocks, aligned columns — and nothing along that path depends on the
output language. What does depend on it:

| Component | Depends on the output language? |
| --- | --- |
| Segmentation, masking and restoration | No — they read structure and English input |
| Placeholder and corruption validation | No |
| Sentence counting and length ratio | **Yes** — see below |
| Line rewrapping at terminal width | Only for double-width scripts (CJK) |
| Translation model | Yes — Helsinki-NLP publishes hundreds of pairs |
| Glossary, literals and section-header table | Yes — plain text files |
| Prose guard (`function_words.txt`) | No — it measures the **input**, always English |
| Model and cache paths | Currently hardcoded to `en-pt`; needs to become a parameter |

**For a Latin-script pair — `en-es`, `en-fr`, `en-it` — the work is mostly
configuration and measurement.** Convert the model with
`scripts/build-model.sh`, build the glossary and header table, make the pair a
parameter instead of a constant, and measure the rejection rate.

**For more distant scripts the work includes code**, and it is worth being
honest about that. Two validation rules currently assume the shape of
Portuguese:

- **Sentence counting** splits on `.`, `!`, `?` followed by whitespace. It does
  not recognise the Hindi danda (`।`), the Arabic question mark (`؟`) or CJK
  punctuation (`。`) — and in Chinese and Japanese there is no space after it.
- **Length ratio** accepts the window `[0.5, 2.5]`, calibrated for a language
  that *expands*: measured on `ls`, EN → pt-BR has a median of 1.13. Languages
  that contract would fall below the floor systematically and be rejected en
  masse.

Neither is a deep rewrite, but neither is configuration either.

If you speak another language and want your terminal in it, this is the
largest open space in the project. Open an issue naming the pair you care
about.

---

## Contributing

The project is useful to the extent that more people can read their own
terminal. Any contribution that widens that helps, and most of them do not
require writing Python.

**Widening the reach**

- **A new language pair.** The biggest open space. Convert the model, build
  the glossary, measure the rejection rate — and, for non-Latin scripts,
  adjust the two rules above.
- **Test on another distro.** The installer has been validated on Ubuntu 24.04
  and Arch. Fedora, openSUSE, Alpine and Debian stable have not.
- **Translate babelt's own messages.**

**Improving quality**

- **Report a bad translation.** Run `babelt <command>`, find a line that came
  out odd, and open an issue with the output and `--stats`. That is quality
  data, and it is worth more than code.
- **Glossary and literals.** Technical terms that should not be translated, or
  that have an established translation. They are plain text files — a good
  first PR.
- **Commands not yet measured.** Measurement covers `ls`, `grep`, `find`,
  `tar`, `ssh` and `git`. Many are missing.

**Touching the core**

Segmentation, masking and validation have rules that exist for a documented
reason. [`docs/development/`](docs/development/) holds the justification for
each one — read the relevant phase before changing behaviour.

The test suite is large on purpose: it exists so you can break things and find
out immediately.

**If this is your first pull request**, it is welcome here and nothing to be
embarrassed about. Issues labelled `good first issue` are picked for that.
Start with [`CONTRIBUTING.md`](CONTRIBUTING.md) — it explains everything from
what a fork is to how to run the CI locally.

## Installation

Requires Python 3.11+ and Linux.

```console
$ git clone https://github.com/ONiceasNeto/babelt && cd babelt
$ ./install.sh
$ babelt ss
```

`install.sh` builds an isolated venv in `~/.local/share/babelt/venv`, installs
babelt into it, and links `~/.local/bin/babelt` to it. **Nothing is installed
into the system Python and you never need to activate a venv** — the symlink
points at the right interpreter. If `~/.local/bin` is not on your `PATH`, the
installer prints the exact line to add for your shell.

The model (~230 MB) is downloaded at the end of the install. If the download
fails, the install is **not** rolled back: babelt stays usable and retries on
first use.

| Flag | Effect |
| --- | --- |
| *(none)* | Installs and downloads the model. |
| `--no-model` | Installs without downloading; the model arrives on first use. |
| `--uninstall` | Removes binary, venv and cache. Asks before deleting the model. |
| `--help` | Summary of the options. |

Reinstalling over an existing install is safe, and is how you upgrade: the
venv is rebuilt and an already-downloaded model is reused.

The model goes to `~/.local/share/babelt/models/en-pt`, honouring
`XDG_DATA_HOME`. It is downloaded already converted to int8, with the SHA-256
checked before any extraction — installing babelt does **not** pull in `torch`
or `transformers`.

To convert the model yourself instead of downloading the artifact:

```console
$ python3 -m venv .venv
$ .venv/bin/pip install -e '.[convert]'   # from the clone: `-e '.'`, not `babelt[...]`
$ ./scripts/build-model.sh                # prints the SHA-256 of the artifact
```

The `-e '.'` is required: `pip install 'babelt[convert]'` would go to PyPI,
where the package is not published yet.

### Diagnostics

```console
$ babelt doctor
ok    babelt                0.5.0
ok    versão de pipeline    5
ok    modelo                /home/you/.local/share/babelt/models/en-pt (227 MiB)
ok    modelo: proveniência  {
                              "model_id": "Helsinki-NLP/opus-mt-tc-big-en-pt",
                              "quantization": "int8",
                              "converted": "2026-08-22T13:44:29Z",
                              "converter": "ctranslate2",
                              "license": "CC-BY-4.0",
                              "attribution": "Helsinki-NLP / ..."
                            }
ok    cache                 /home/you/.cache/babelt — 123 entries, 16 KiB
ok    ctranslate2           4.8.1
ok    sentencepiece         0.2.2
ok    man                   /usr/bin/man
```

Exits 1 when something prevents translation, 0 when it is only a warning.

> babelt's own interface messages are in Portuguese today. Translating them is
> [an open contribution](#contributing).

## Usage

```console
$ babelt ss                    # runs `man ss` and translates
$ man ss | babelt              # translates standard input
$ nmap --help | babelt         # works with any terminal output
$ babelt --help-of katana      # runs `katana --help` and translates
$ babelt --auto katana         # tries man; falls back to --help
$ babelt ss > ss.pt.txt        # clean text on stdout
```

| option | effect |
|---|---|
| `--help-of` | runs `<command> --help` instead of `man <command>` |
| `--auto` | tries `man`; falls back to `--help` if there is no page |
| `--beam N` | search beam (default 1; 4 translates better and takes ~2.5× longer) |
| `--no-cache` | bypasses the cache, both reading and writing |
| `--stats` | statistics on stderr at the end, with the rejection rate by reason |
| `--no-pager` | never paginate, even on a terminal |
| `--model-path P` | use a different model directory |
| `--version` | version |

`--stats` reports how much stayed in English and **why**:

```console
$ babelt --stats ls
babelt: segmentos: 76 de prosa, 134 literais
babelt: traduzidos: 62 (81.6%); mantidos em inglês: 14 (18.4%)
babelt: rejeitados por motivo:
babelt:      5 (6.6%)  placeholder ausente
babelt:      4 (5.3%)  peça fora do vocabulário (oov)
babelt:      3 (3.9%)  delimitador
babelt:      2 (2.6%)  razão de comprimento
babelt: cache: 0 acertos de segmento
```

A rejected segment comes out in English, and that is the desired behaviour: a
badly translated sentence in a manual page is worse than a sentence in
English. The reasons are the rules in [`validate.py`](babelt/validate.py).

`babelt doctor` diagnoses the install: model, cache, libraries and `man`.

> **`--help-of` and `--auto` execute the binary.** Reading a man page is
> reading a file; running `foo --help` runs `foo`. That is why neither is the
> default, why the command is invoked only with a help flag (`--help`, then
> `-h`, then `--usage`), never with extra arguments, and always with a
> 10-second timeout. `--auto` only switches source when `man` answers
> "No manual entry".

Translated text **always** goes to stdout; progress, warnings and statistics
**always** go to stderr. In a pipe the output comes out raw. On a terminal it
is paginated only when it does not fit the screen — using `$BABELT_PAGER`,
else `$PAGER`, else `less -RFX` (`-F` quits on its own for short output, `-X`
does not clear the screen on exit). `--help-of` and `--auto` do not paginate
by default.

Exit codes: `0` success, `1` runtime error, `2` invalid usage, `127` page not
found, `130` interrupted.

## Performance

The first translation of a page is expensive; the rest are not.

| | |
|---|---|
| `babelt ss` cold (167 prose segments) | ~150 s |
| `babelt ss` with a warm cache | **0.3 s** |
| same, via the PyInstaller binary | 3.3 s (2 s is decompression) |
| memory, cold | ~520 MB |
| memory, warm cache | ~20 MB |
| 20-page corpus, cold | 1219 s |
| same corpus, warm | 0.9 s |

The cache lives in `~/.cache/babelt` (honours `XDG_CACHE_HOME`), is
per-**segment**, and is portable: it can be generated on one machine and
copied to another. Each entry stores the whole result, so a second run
reproduces even the statistics.

The cache invalidates itself when the text changes (the key is a hash of the
text), when the model changes, when the beam changes, or when the pipeline
version is bumped. There is no cleanup command because none is needed:
deleting `~/.cache/babelt` is safe at any time.

## Input that is not prose

`ls | babelt` used to translate filenames — `Labs` became `Laboratórios` — and
no validation caught it. Since 0.3.0 the whole document is measured before any
translation: if the density of function words (articles, prepositions,
conjunctions) falls below 14%, the input passes through untouched, with a
warning on stderr.

```console
$ ls /usr/share | babelt
babelt: a entrada não parece prosa em inglês (0.0% de palavras funcionais em
       85, mínimo 14%); saindo intacta
```

The threshold was measured, not chosen: command output sits between 0 and
12.8%, and the worst prose document in the corpora (`ffmpeg --help`) is at
18.1%. See `docs/development/README-fase6.md`. The function-word list is in
`babelt/function_words.txt` and is editable.

## Known limitations

**14.6% of prose segments come out in English** (275 of 1,884, measured on
`ls`, `grep`, `find`, `tar`, `ssh` and `git`). That is not a bug: it is the
validation working. A segment is rejected when it

- loses, duplicates or invents a syntax marker;
- contains a character the model's tokenizer does not know (`{`, `}`, `|`, `^`);
- comes back with a different number of sentences;
- repeats a sentence that appeared once;
- loses a bracket, brace or parenthesis.

When a paragraph is rejected, it is retried sentence by sentence, and only the
sentences that fail stay in English.

Other limitations, measured and not hidden:

- **Comma-separated value lists still reach the model.**
  `all,robotstxt,sitemapxml` may come back with the first item translated. 13
  occurrences across the measured corpora; see
  `docs/development/README-fase5.md`.
- **The Portuguese is that of a generic 2022 model.** It produces "O daemon
  bifurca" and "deixa cair o pacote". There is no fine-tuning for technical
  text.
- **Section headers come from a table** (`babelt/headers.txt`), not from the
  model, so that `SEE ALSO` is always the same thing. A header missing from
  the table stays in English.
- **Some terms never reach the model** (`babelt/literals.txt`): it translates
  `headless` and `non-headless` to the same thing and the negation vanishes.
  Masking costs translation — a lost placeholder rejects the paragraph — and
  the paragraph comes out in English rather than saying the opposite of the
  original.
- **The glossary is context-blind.** `babelt/glossary.txt` returns technical
  terms to English (`soquete` → `socket`), but does not know which English
  word produced the translated one. Ambiguous entries were removed by
  measurement.
- **The title line loses its column alignment.** `SS(8) Manual do Gestor de
  Sistema SS(8)` comes out with single spaces: the line is treated as prose,
  and what comes back translated cannot preserve the centring.
- **English → pt-BR only.** The pair is fixed today, and the model and cache
  paths are still the `en-pt` constant. What separates that from a second pair
  is in [Status and direction](#status-and-direction).

## How it works

```
man ss
  → normalize   strips roff overstrike, joins hyphenation, collapses
                justification
  → segment     separates prose, literal blocks (synopsis, examples, tables)
                and two-column tables — in those, only the right cell is
                translated, and the left column passes through untouched
  → mask        replaces flags, paths, IPs, variables, URLs and quoted
                literals with markers
  → translate   CTranslate2 int8, with a per-segment cache
  → validate    markers intact? sentences preserved? delimiters?
                  yes → restore the literals
                  no  → retry per sentence; whatever fails stays in English
  → reassemble  rebuilds the document, with headers translated from the table
  → rewrap      rewraps prose to page width (MANWIDTH, default 80)
```

Literal blocks never reach the model.

## Development

To work on the code, use the editable install — not `install.sh`, which exists
for people who only want to run the program:

```console
$ python3 -m venv .venv && .venv/bin/pip install -e '.[dev,convert]'
$ .venv/bin/pytest                              # 1422 tests
$ .venv/bin/mypy                                # strict
$ .venv/bin/mypy --python-version 3.11 babelt    # execution floor
```

Tests that need the downloaded model are marked `model` and are skipped
without it:

```console
$ .venv/bin/pytest -m 'not model'
```

The history of design decisions — with the measurements behind them — is in
[`docs/development/`](docs/development/), with an index by phase. Those
documents are in Portuguese.

[`CONTRIBUTING.md`](CONTRIBUTING.md) has the full walkthrough, including what
CI checks and how to run the same thing before you submit.

## License

MIT. See [LICENSE](LICENSE).

The translation model is `Helsinki-NLP/opus-mt-tc-big-en-pt`, licensed
separately (CC-BY-4.0) and downloaded on demand.

---

<div align="center">

Made by [Niceas Neto](https://www.linkedin.com/in/niceas-neto-b37b3a359/).

Model by [Helsinki-NLP](https://huggingface.co/Helsinki-NLP), under CC-BY-4.0.
Code under [MIT](LICENSE).

**Want your terminal in another language?**
[Open an issue](https://github.com/ONiceasNeto/babelt/issues/new/choose).

</div>
