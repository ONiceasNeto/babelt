# manbr — Fase 2.1: literais entre aspas e cabeçalhos

```
.venv/bin/pytest                                  # 1141 testes
.venv/bin/mypy                                    # strict, limpo
.venv/bin/python tests/coverage/measure.py
.venv/bin/python tests/coverage/measure_segment.py
```

## O padrão de aspas sobreviveu à medição

Sim. O critério era: recall sobe, FP de apóstrofo em zero. O apóstrofo gerou
**zero** falsos positivos.

| | fase 1.2 | fase 2 | **fase 2.1** |
|---|---|---|---|
| tokens anotados | 189 | 189 | 194 |
| **cobertos** | 177 (93.7%) | 177 (93.7%) | **188 (96.9%)** |
| parciais | 0 | 0 | **0** |
| ausentes | 12 | 12 | **6** |
| candidatos a FP | 0 | 0 | 1 |

Com a anotação **congelada** da fase 1.2, sem nenhuma correção: 183/189 =
**96.8%**, 0 parciais, 6 candidatos a FP. Os dois números sobem; a correção de
anotação (abaixo) vale 0.1 pp.

Excluindo os dois casos que continuam intratáveis por forma: **188/192 =
97.9%**.

## Parte A — o que a medição decidiu

### O apóstrofo: zero FP, e como

O risco principal era `don't`, `user's`, `it's`. A primeira tentativa, com
lookbehind `(?<![\w'])`, passava no apóstrofo mas falhava noutro lugar: o
groff escreve citação como `` `assim' ``, com crase de um lado e apóstrofo do
outro. Em `find.txt:27`, o `'` de fechamento de `` `-' `` vinha depois de um
hífen — que não é `\w` — e abria uma citação que só fechava a meia frase de
distância.

A guarda que ficou é mais estreita: **a aspa de abertura precisa vir depois de
branco, de `(`/`[`/`{`, ou do começo da linha** — `(?<![^\s([{])`. Isso barra
`don't` (precedido por `n`), barra `` `-' `` (precedido por `-`), e deixa
passar `'\n'`, `'[ugoa]*...'` e `('x')`. Há teste para cada.

### O limite de comprimento era necessário — medido, não chutado

A restrição 4 pedia para medir antes de decidir. As 113 citações do corpus,
por número de palavras internas:

| palavras | ocorrências | o que são |
|---|---|---|
| 1 | 82 | metacaracteres, valores, nomes de campo |
| 2 | 18 | comandos curtos, pares chave/valor |
| 3 | 6 | `'ip address flush'`, `'(coreutils) dd invocation'` |
| **4+** | **3** | **prosa citada** |

As três de 4 ou mais são exatamente o caso que a restrição temia:

> `"must have a tty"` (ps)
> `"copy the contents of this directory"` (rsync)
> `"copy the directory by name"` (rsync)

Se virassem placeholder, três frases perderiam tradução. O corte ficou em
`MAX_QUOTED_WORDS = 3`, que separa os 106 literais dos 3 trechos de prosa sem
nenhum caso ambíguo no meio. Não é um limite de caracteres: `'[ugoa]*([-+=]
([rwxXst]*|[ugo]))+|[-+=][0-7]+'` tem 44 caracteres e uma palavra só, e é
literal; `"must have a tty"` tem 15 caracteres e quatro palavras, e é prosa.
Palavras discriminam, comprimento não.

### O achado colateral: a crase nunca funcionou

Olhando os falsos positivos do apóstrofo, dei de cara com um problema mais
antigo. O padrão de crase existe desde a fase 1, justificado por
`` `ss -tulpn` `` — crase contendo flags vira um placeholder só. No corpus
real de man pages ele casou **duas vezes, e as duas eram falso positivo**:

```
find.txt:27   `-', or the argument `
find.txt:38   `-'). Now, if a path argument would start with a `
```

Zero acertos, dois erros. A causa é a mesma: o groff não usa crases pareadas,
usa `` `assim' ``, então a "crase de fechamento" que o padrão encontrava era a
abertura da citação seguinte, e o que ficava no meio era prosa.

Apliquei ao corpo da crase o mesmo limite de palavras das aspas. Os dois
falsos positivos sumiram, `` `ss -tulpn` `` e `` `cat /etc/passwd` `` continuam
passando (os testes da fase 1 não mudaram), e a crase agora casa **zero** vezes
no corpus — o que é o resultado correto para este corpus. O padrão continua
ganhando o lugar dele em saída de `--help` e em exemplos de shell, que usam
crase de verdade.

Efeito colateral visível na segmentação: `find.txt:37` era um parágrafo
parcialmente mascarado e virou um segmento PROSE de 190 tokens, íntegro.

### O custo real: aspas de ênfase

Um candidato a FP sobrou, e é verdadeiro:

```
ssh.txt:81   “dynamic”   em: Specifies a local “dynamic” application-level port forward
```

Aqui as aspas são de ênfase, não de citação literal, e o termo fica em inglês
no meio de uma frase traduzida. Varrendo o corpus inteiro, **cerca de 6 das
106 citações (≈6%) são termo de prosa entre aspas de ênfase** — `"globbing"`,
`"understand"`, `"download"`, `"identical"`, `“dynamic”` e afins. As outras
~94% são literais de verdade: `'none'`, `'noxfer'` e `'progress'` (valores de
`status=` da dd), `"adm"` e `"wheel"` (grupos), `"sack"`, `"ecn"`,
`"fastopen"` (strings que a ss imprime), `“yes”` e `“none”` (valores de
configuração da ssh).

Não tentei separar os dois casos. `"sack"` (literal que a ss imprime) e
`"globbing"` (termo de prosa) são **idênticos em forma**: uma palavra em
minúscula entre aspas. Qualquer regra que separasse os dois seria exatamente a
heurística frágil que a spec mandou não tentar. Fica o custo declarado: ~6% das
citações perdem tradução de uma palavra, contra 5 metacaracteres protegidos e
3.2 pp de recall.

### Correção de anotação, declarada

Cinco dos seis candidatos a FP eram buraco de anotação, não erro do
mascarador: `"file"`, `"1 MiB"`, `"1 K"`, `"1 M"` e
`'systemctl list-unit-files'`. Os quatro primeiros são valores literais. O
último é o caso mais interessante: a regra da fase 1.1 excluía subcomandos
como `list-unit-files` justamente porque *"nenhuma marca de forma os separa de
prosa"* — e as aspas são a marca que faltava. Anotados, com o registro no
`annotated.tsv`.

`“dynamic”` **não** foi anotado, de propósito, para que a medição continue
mostrando o custo do padrão em vez de escondê-lo.

## Os intratáveis: 5 dos 7 fechados

A fase 2 tinha fechado 1 dos 8 por segmentação (`curl.txt:122`). Dos 7 que
sobraram, o padrão de aspas fechou **5** — exatamente os que a fase 2 previu:

| caso | citação | veredito |
|---|---|---|
| `awk.txt:58` | `“-”` | **fechado** |
| `awk.txt:75` | `'\n'` | **fechado** |
| `chmod.txt:120` | `'[ugoa]*([-+=]([rwxXst]*\|[ugo]))+\|[-+=][0-7]+'` | **fechado** |
| `curl.txt:91` | `"\{{"` | **fechado** |
| `ip.txt:75` | `'\'` | **fechado** |
| `awk.txt:127` | — | continua exposto |
| `chmod.txt:29` | — | continua exposto |

Os dois que restam são os dois que a fase 2 já tinha identificado como *não*
estando entre aspas:

> `Long statements can be continued with a backslash, \.`
> `existing file mode bits of each file; - causes them to be removed;`

Uma barra invertida e um hífen soltos no meio de uma frase, sem nenhuma marca
tipográfica. Não têm solução por forma, e continuo não recomendando persegui-los
— casar hífen isolado é casar todo travessão de prosa. Ficam como custo
conhecido.

### O que deixei de fora: a citação `` `assim' `` do groff

Reconhecer a forma crase-abre/apóstrofo-fecha resolveria também `` `-' `` e
`` `./' ``. Não implementei, por dois motivos. Não está na lista da Parte A, e
mediria negativo: `find.txt:37` diz *"talks about `options' within the
expression list"*, onde `options` é termo de prosa, não sintaxe — mascará-lo
criaria um FP novo na amostra, contra o critério desta fase. Fica registrado.

## Parte B — cabeçalhos por tabela

`manbr/headers.txt`, 56 entradas, formato `INGLÊS<TAB>PORTUGUÊS`, lido no
import. Cobre os 26 pedidos, mais os 15 que aparecem no corpus além do mínimo
(`USAGE`, `VARIABLES`, `OPTIONS SUMMARY`, `SIMPLE PROCESS SELECTION`…), mais
15 comuns em outras páginas.

```
NAME -> NOME        SEE ALSO -> VEJA TAMBÉM      EXIT STATUS -> STATUS DE SAÍDA
SYNOPSIS -> SINOPSE REPORTING BUGS -> RELATANDO BUGS
```

- **Ausente da tabela fica em inglês, sem erro.** `THE AWK LANGUAGE` passa
  intacto. Falhar por omissão é visível e se corrige acrescentando uma linha —
  o mesmo raciocínio de `extensions.txt` na fase 1.2.
- **A classificação do segmento não muda.** `apply_headers` é substituição de
  saída; o segmento continua LITERAL, e `segment`/`reassemble` seguem sem
  perda.
- **A busca é exata em caixa e só casa o segmento inteiro.** Uma linha `NAME`
  dentro de uma tabela do lsblk não vira `NOME`, e `Name` em prosa também não.
- O carregador rejeita linha sem TAB e lado vazio, com o número da linha.

`BUGS` é a única entrada cuja tradução é a própria palavra, e há um teste que
falha se qualquer outra ficar igual — para que uma entrada esquecida não passe
por tradução.

No corpus, 60+ cabeçalhos são traduzidos.

## Efeito na segmentação

Mudar `mask` muda `syntax_ratio`, que muda a classificação. O deslocamento foi
pequeno e para o lado certo:

| | fase 2 | fase 2.1 |
|---|---|---|
| PROSE | 828 seg. / 1798 linhas | 826 / 1792 |
| LITERAL | 341 / 479 | 344 / 485 |
| **PROSE acima de 400 tokens** | **0** | **0** |

O maior segmento PROSE continua em 236 tokens. A conclusão da fase 2 não
muda: a estratégia parágrafo → sentença não precisa ser revista.

## Arquivos

```
manbr/headers.py      manbr/headers.txt     # Parte B
tests/test_headers.py                       # 55 testes
```

`mask.py` ganhou o padrão `quoted` e o limite de palavras na crase.
`validate.py`, `normalize.py` e `segment.py` não foram tocados.
