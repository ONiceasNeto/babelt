# manbr — Fase 4: cache em disco e CLI

```
PYTHONPATH=. .venv/bin/pytest                     # 1274 testes
PYTHONPATH=. .venv/bin/pytest -m 'not model'      # 1267, sem os 230 MB
PYTHONPATH=. .venv/bin/mypy                       # strict, limpo
PYTHONPATH=. .venv/bin/mypy --python-version 3.11 manbr
python tests/quality/measure_cache.py             # medição desta fase
pyinstaller manbr.spec --noconfirm                # binário
```

## O número que mede a fase

**`manbr ss`: 165 s a frio, 0,3 s com o cache quente — 500×.** É a fase que
transforma um experimento em algo que se digita no terminal sem pensar.

| | |
|---|---|
| `manbr ss` a frio (167 segmentos de prosa) | 165 s |
| `manbr ss` quente, pela fonte | **0,31 s** |
| `manbr ss` quente, pelo binário | 3,3 s |
| memória a frio | 520 MB |
| memória quente | 23 MB |

A saída fria e a quente são **byte a byte idênticas** (`cmp`), porque o cache
guarda o resultado inteiro — texto, se foi traduzido, e o motivo da recusa —
e não só o texto. Uma segunda execução reproduz até as estatísticas.

## Cache: o que a medição desmentiu

Aqui está o resultado desconfortável da fase, e ele contradiz a premissa que
levou o cache a ser por segmento.

A fase 3.1 mediu **46,6% de acerto** no cache em memória e concluiu que a
granularidade por segmento se pagava porque "man pages repetem parágrafos
inteiros entre páginas diferentes". Sobre o corpus de 20 páginas, com cache em
disco de verdade:

| | |
|---|---|
| segmentos de prosa | 724 |
| **acertos entre páginas, passada fria** | **6 (0,8%)** |
| acertos na passada quente | 724 (100%) |

**A repetição era quase toda dentro do mesmo documento, não entre
documentos.** Os 46,6% da fase 3.1 contavam repetição intra-lote — cinco
cópias da mesma frase na mesma página — e essa parte continua sendo resolvida
pelo cache em memória, antes de o disco entrar na conta. Entre 20 ferramentas
diferentes, `awk` e `iptables` simplesmente não compartilham parágrafos: só
6 em 724.

A granularidade por segmento **não** se justifica pelo que a fase 3.1
afirmava. Ela se justifica por outras duas coisas, que a medição sustenta:

1. **Reabrir a mesma página acerta 100%** — que é o caso de uso real, e cache
   por documento também resolveria.
2. **Interromper no meio não joga fora o trabalho feito.** Cache por documento
   só grava no fim; por segmento, um Ctrl-C aos 80% preserva os 80%. Há teste
   para isso.

Fica registrado que a hipótese "páginas diferentes compartilham prosa" só teria
chance num corpus de páginas da mesma família (`git-log`, `git-commit`,
`git-diff`), que este corpus não tem.

## Corpus inteiro

| | fria | quente |
|---|---|---|
| tempo | 1219 s | **0,9 s** |
| acertos de cache | 6/724 (0,8%) | 724/724 (100%) |
| traduzidos | 623 (86,0%) | idem |
| em inglês | 101 (14,0%) | idem |

A taxa de inglês caiu de 18,9% (fase 3.1) para 14,0% sem nenhuma mudança na
validação. A causa provável é a sinopse ter virado bloco literal (veja
abaixo): são 102 segmentos de prosa a menos que a fase 3.1, e sinopse é
exatamente o tipo de texto que a validação recusava. Não isolei a atribuição —
seria preciso reexecutar a fase 3.1 com a classificação nova.

O tempo por segmento na passada fria (1,68 s) está acima dos 0,97 s da fase
3.1 porque a medição dividiu a máquina com execuções de teste. Isolada, uma
página sai a 0,76 s/segmento. A comparação que importa aqui é fria contra
quente, e essa não é afetada.

### Tamanho em disco

| | |
|---|---|
| entradas | 716 |
| conteúdo | 138 KiB |
| **ocupação real** | **3,8 MiB** |

198 bytes de conteúdo por entrada, 5,3 KiB ocupados. **O cache custa 27× o
que guarda**, porque cada entrada é um arquivo e cada arquivo paga um bloco
inteiro do sistema de arquivos. Em valor absoluto não importa — o corpus
inteiro cabe em 4 MiB, e o modelo sozinho tem 230 MB. Fica anotado porque é o
preço da escolha "um arquivo por segmento", e porque um dia, se o cache virar
artefato distribuído com milhares de páginas, esse fator de 27 vira o número
que decide entre arquivos soltos e um banco embutido.

## PIPELINE_VERSION 2: a sinopse virou bloco literal

Único ajuste em módulo congelado nesta fase, e entra como bug encontrado por
ela: a seção `SYNOPSIS` era classificada como prosa e ia ao modelo. Sinopse é
gramática de comando — `ss [ OPTIONS ] [ FILTER ]` — e não é frase. O
resultado era o pior tipo de saída: um comando plausível e errado.

O bump de `PIPELINE_VERSION` para 2 invalida o cache antigo sozinho, sem
apagar nada e sem migração, porque a versão entra na chave.

Custo declarado: **a sinopse fica em inglês**, sempre. O README mostra isso na
primeira tela, sem retoque.

## Requebra de linha

A fase 3.1 deixou registrado que "prosa de várias linhas volta numa linha só —
é problema de renderização, para a fase 4". Estava pior do que parecia:

| `manbr ss` | linhas acima de 80 colunas | linha mais longa |
|---|---|---|
| sem requebra | 62 de 423 | 457 caracteres |
| **com requebra** | **0 de 538** | **80** |

`rewrap` mora em `__main__.py`, não em `segment.py`: é decisão de saída, não
de estrutura do documento, e assim nenhum módulo congelado foi tocado. Só
prosa é requebrada; bloco literal é tabela, exemplo ou sinopse, onde a quebra
é significado. `break_long_words` e `break_on_hyphens` ficam desligados de
propósito — partir `--exclude-from=ARQUIVO` no fim da linha seria o mesmo erro
que o mascaramento inteiro existe para evitar.

A largura vem de `MANWIDTH` (padrão 80), que é a mesma variável usada para ler
o `man`, e valores absurdos são ignorados.

## CLI

Todos os códigos de saída verificados no binário empacotado:

| código | como | verificado |
|---|---|---|
| 0 | `echo ... \| manbr` | binário e teste |
| 1 | modelo ausente; degrada para o texto original | teste |
| 2 | sem argumento e sem stdin (pty) | binário e teste |
| 127 | `manbr paginainexistente` | binário e teste |
| 130 | Ctrl-C durante a tradução | teste |

O contrato de fluxo tem teste dedicado: com `--stats`, nenhuma linha `manbr:`
aparece em stdout e as estatísticas aparecem em stderr.

**Ctrl-C não despeja a página.** A regra "nenhum caminho de erro produz stdout
vazio" vale para falha; interrupção é ordem do usuário, e quem aperta Ctrl-C
não quer 500 linhas na tela. O que já foi traduzido fica no cache — a
tradução é gravada em blocos de 16 — e a execução seguinte continua de onde
parou. São dois testes.

## Empacotamento

| | |
|---|---|
| binário | **74 MiB** (77.474.312 bytes) |
| partida do binário (`--version`) | **1,8 s** |
| `manbr ss` quente, binário | 3,3 s |
| `manbr ss` quente, fonte | 0,31 s |

**Os 3 segundos do caminho quente são quase todos descompactação.** O
`--onefile` do PyInstaller extrai 74 MiB para um temporário a cada execução, e
`--version` sozinho custa 1,8 s. Ou seja: depois de todo o trabalho para
levar a segunda execução a 0,3 s, o empacotamento devolve 2 s. Trocar para
`--onedir` resolveria; fica para a fase 5, junto com a decisão de distribuição.

`torch` e `transformers` estão excluídos do binário — só existem para
converter o modelo, e sem eles o executável cai de centenas de MB para 74.
As tabelas editáveis (`extensions.txt`, `headers.txt`, `glossary.txt`) viajam
como `datas`, no mesmo caminho relativo em que são lidas.

## Testes

1274 testes. Os 7 que carregam o modelo agora usam `@pytest.mark.model`, com o
pulo automático num `conftest.py` só — antes era um `skipif` copiado em dois
arquivos, e `pytest -m 'not model'` (que o README anunciava) não deselecionava
nada. Sem o modelo, a suíte roda em 12 s.

Novos nesta fase, além dos de cache e CLI que já existiam: interrupção
(cache parcial, retomada, código 130) e requebra (largura, indentação,
literal intocado, token longo não partido, `MANWIDTH`).

## Higiene

`README.md`, `LICENSE` (MIT), `.gitignore`, `CHANGELOG.md` em 0.1.0, e os
`README-faseN.md` movidos para `docs/development/`. O exemplo de saída no topo
do README foi trocado pela saída real do binário: o anterior mostrava a linha
de título alinhada em colunas e a sinopse traduzida, e o programa não faz nem
uma coisa nem outra.

## O que ficou fora

- **A linha de título perde o alinhamento.** `SS(8) Manual do Gestor de
  Sistema SS(8)` sai com espaço simples. O segmento chega ao tradutor com a
  justificação intacta — `normalize` a preserva —, mas o texto traduzido é
  outro e a centralização não sobrevive. Tratar a linha de título como caso
  próprio exigiria mexer em `segment.py`. Cosmético, e é a primeira linha.
- **`--onefile` custa 2 s por execução.** É o maior item isolado do caminho
  quente agora.
- **Nenhuma distribuição de cache pré-traduzido.** O formato está pronto para
  isso — `meta.json` grava modelo, versão de pipeline e datas —, mas não há
  comando para exportar, importar ou verificar um cache de outra máquina.
- **`--beam 4` não tem número novo.** Continuam valendo as medições da fase
  3.1; com cache em disco, o argumento de custo único a favor do 4 ficou mais
  forte, e a decisão não foi revisitada.
- **Fluência.** Nada nesta fase mede português, como em todas as anteriores.
