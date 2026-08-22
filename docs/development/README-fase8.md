# babelt — Fase 8: renomeação, e o build que não rodava

```
PYTHONPATH=. .venv/bin/pytest                 # 1396 testes
PYTHONPATH=. .venv/bin/pytest -m 'not model'  # 1389, o que o CI roda
PYTHONPATH=. .venv/bin/mypy                   # strict, limpo
babelt doctor
```

Versão **0.5.0**. `PIPELINE_VERSION` continua **4** — o texto não mudou.

## A contagem de testes não mudou com a renomeação

O número que a spec pediu para confirmar:

| momento | coletados | resultado |
|---|---|---|
| antes da renomeação (fase 7) | 1392 | 1385 passaram, 7 com o modelo |
| **logo depois da renomeação** | **1392** | **1385 passaram, 7 pulados**¹ |
| no fim da fase | 1396 | 1389 + 7 |

¹ Pulados, e não falhos: os 7 testes marcados `model` procuram o modelo em
`~/.local/share/babelt/`, e ele está em `~/.local/share/manbr/`. É o efeito
pretendido de não migrar nada. Rodando com `XDG_DATA_HOME` apontando para o
modelo antigo, os 1396 passam.

Os **4 testes a mais** no fim da fase são os do aviso de diretório órfão, que
a própria spec pediu. Nenhum teste foi alterado por causa do nome além das
strings literais.

## Ocorrências residuais de "manbr"

**Nenhuma acidental.** As 12 que restam são deliberadas, e todas dizem
respeito ao nome antigo enquanto nome antigo:

| arquivo | o que é |
|---|---|
| `babelt/doctor.py:30` | `_FORMER_NAMES = ("manbr",)` — a lista que faz o aviso de órfão funcionar |
| `babelt/doctor.py:25` | o comentário que explica por quê |
| `tests/test_doctor.py` (6) | os testes desse aviso |
| `CHANGELOG.md` (3) | a entrada 0.5.0, que registra a renomeação |
| `TODO.md` (1) | o item de renomeação, agora marcado |

Verificado com `grep -rnI "manbr\|MANBR"` sobre a árvore inteira, fora
`.git`, `.venv`, `build`, `dist` e caches.

### Uma coisa que fiz e você deve conferir

A substituição foi global, e **isso inclui `docs/development/`**. Os
README-fase1 a fase7 agora dizem `babelt` onde diziam `manbr`, inclusive em
blocos que citam saída de terminal real da época (`$ manbr ss` virou
`$ babelt ss`). Nenhum número mudou; só o nome do comando.

Foi o que a spec pediu ("README, CHANGELOG, TODO, docs/development/"), e para
um projeto não publicado é o resultado mais útil — quem ler os docs amanhã vai
querer comandos que funcionam. Mas é reescrita de registro histórico, e se
você preferir os docs de fase com o nome da época, é um `git checkout` dos
sete arquivos.

O mesmo vale para as entradas 0.1.0 a 0.4.0 do CHANGELOG, que descrevem
versões que se chamavam `manbr`.

## O que a renomeação alcançou

| | de | para |
|---|---|---|
| pacote | `manbr/` | `babelt/` |
| comando e binário | `manbr` | `babelt` |
| pager | `$MANBR_PAGER` | `$BABELT_PAGER` |
| corpus | `$MANBR_CORPUS_LINES` | `$BABELT_CORPUS_LINES` |
| cache | `~/.cache/manbr` | `~/.cache/babelt` |
| modelo | `~/.local/share/manbr` | `~/.local/share/babelt` |
| temporário de download | `.manbr-download-*` | `.babelt-download-*` |
| artefato do modelo | `manbr-model-en-pt-int8.tar.gz` | `babelt-model-en-pt-int8.tar.gz` |
| prefixo das mensagens | `manbr: …` | `babelt: …` |

Duas coisas **não** foram renomeadas, e são suas:

- **O repositório no GitHub** (`ONiceasNeto/manbr`) e, por consequência, as
  três URLs do `pyproject.toml`, que hoje apontam para `.../babelt` — o nome
  que o repositório ainda não tem.
- **O diretório local** `~/Projetos/manbr`.

## O aviso de órfão

Não migrar deixa 227 MB parados. `doctor` os encontra:

```
aviso órfão de manbr (cache)   /home/você/.cache/manbr (0 MiB) — de quando o
                               programa se chamava manbr; nada mais lê, pode remover
aviso órfão de manbr (modelo)  /home/você/.local/share/manbr (227 MiB) — …
```

É **aviso**, não impedimento: o programa funciona sem tocar naquilo, e apagar
coisa de 227 MB do usuário sem ele pedir é outro assunto. A saída acima é real,
desta máquina.

## Parte A — os dois bugs do build-model.sh

**1. `python` não existe em Debian, Ubuntu e derivados.** O script chamava
`python -m ctranslate2.converters.transformers` no ramo de fallback e morria
com "command not found" — numa distro onde só `python3` existe, e num projeto
que declara Linux como plataforma. Agora usa `.venv/bin/python` se houver,
senão `$PYTHON`, senão `python3`.

**2. Nada verificava o converter antes de começar.** A falha aparecia depois
de o script já ter entrado na conversão. Agora a checagem é a primeira coisa,
em três degraus — `.venv/bin/ct2-transformers-converter`, o do `PATH`, o
módulo via `-m` — e a mensagem de erro traz a linha que resolve:

```
    python3 -m venv .venv
    .venv/bin/pip install -e '.[convert]'
```

Com o `-e '.'` explicado no próprio texto: `pip install 'babelt[convert]'`
iria ao PyPI, onde o pacote não está.

**Verificado rodando de verdade**, não só lendo: o script converteu o modelo e
produziu `dist/babelt-model-en-pt-int8.tar.gz` com o SHA-256 impresso no fim.

## O que ficou fora

- **Migração automática do cache e do modelo antigos.** Deliberada, e a spec
  pediu assim. O aviso do `doctor` é o que sobrou no lugar.
- **Renomear o repositório e o diretório local.** Fora do alcance de código.
- **`babelt doctor --fix`.** Continua dizendo o que remover, sem remover.
