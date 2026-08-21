# manbr — Fase 2: normalize.py e segment.py

```
.venv/bin/pytest                                  # 1084 testes
.venv/bin/mypy                                    # strict, limpo
.venv/bin/python tests/coverage/measure_segment.py
```

`mask.py` e `validate.py` não foram tocados.

## O número que decide

**Zero.** Nenhum dos 828 segmentos PROSE passa de 400 tokens.

| | |
|---|---|
| segmentos PROSE acima de 400 tokens | **0 de 828 (0.0%)** |
| maior segmento PROSE | 236 tokens |
| mediana | 9 tokens |
| média | 19.9 tokens |

A distribuição é muito mais curta do que o orçamento: 55% dos segmentos de
prosa têm 10 tokens ou menos, e só 13 passam de 100. A estratégia
parágrafo → sentença **não precisa ser revista antes da fase 3** — o corte por
parágrafo já entrega segmentos pequenos, porque uma man page é feita de
descrições curtas de opção, não de ensaios.

A contagem é por palavra separada por branco, que é um piso: um tokenizer NMT
rende mais. Mesmo multiplicando por 3, o maior segmento fica em ~700 tokens e
só um segmento passaria do orçamento.

## Distribuição

| | segmentos | linhas |
|---|---|---|
| PROSE | 828 (70.8%) | 1798 (79.0%) |
| LITERAL | 341 (29.2%) | 479 (21.0%) |

```
PROSE      1-10:458   11-25:165   26-50:113   51-100:79   101-200:12   201-400:1
LITERAL    1-10:317   11-25: 19   26-50:  1   51-100: 3   201-400: 1
```

Segmentos LITERAL são curtos (mediana 2 tokens) porque a maioria é uma linha
de tag com flags (`-p, --processes`) ou um cabeçalho de seção.

### Tokens mascarados por tipo — a previsão não se confirmou

| | tokens mascarados |
|---|---|
| PROSE | 479 (43.2%) |
| LITERAL | 631 (56.8%) |

A spec previa "a maioria em PROSE". Ficou o contrário. O motivo é que os
blocos literais são poucos mas densos: uma linha de SYNOPSIS ou uma tabela de
saída concentra dezenas de tokens, enquanto a prosa cita uma ou duas flags por
parágrafo. Os 43% em PROSE continuam sendo o caso de uso de `mask`/`validate`
— são exatamente os que vão passar pelo modelo.

## A regra de indentação da spec não funciona, e os dados dizem por quê

Esta é a descoberta que mudou o desenho, então vale o detalhe.

A spec pede LITERAL quando a "indentação ≥ 4 espaços relativa ao bloco
corrente". Medindo o corpus por nível de recuo, com a razão de sintaxe de
`mask` como medida de "isto é código":

| recuo | linhas | razão média |
|---|---|---|
| 0 | 120 | 0.00 |
| 7 | 1191 | 0.16 |
| 11 | 336 | 0.10 |
| **14** | **426** | **0.06** |
| 15 | 141 | 0.13 |
| **21** | **46** | **0.01** |

Os níveis 14 e 21 são os mais fundos e os **menos** sintáticos do corpus: são
a descrição pendurada de listas com tag — `-h, --help` a 7, "Show summary of
options." a 14 — ou seja, o grosso da prosa útil da página. Aplicar a regra ao
pé da letra marcaria 472 linhas de texto traduzível como literal.

O que realmente separa é o **bloco**, não a linha:

- Um comando de exemplo da rsync ou uma tabela da systemctl é um bloco
  isolado por linhas em branco, indentado além do bloco anterior.
- A descrição pendurada mora *dentro* do mesmo bloco da tag, sem linha em
  branco no meio — o recuo muda, o bloco não.

E profundidade sozinha ainda erra: `ts     show string "ts" if ...` (ss) é um
bloco a 14 logo depois de um bloco a 7, com razão 0.00, e é prosa. Por isso a
regra de bloco fundo exige também densidade de sintaxe.

### As regras como ficaram

Sobre blocos delimitados por linha em branco:

1. **Bloco denso** — razão de sintaxe do bloco ≥ 0.5 → LITERAL inteiro.
2. **Bloco fundo** — recuo ≥ 4 além do bloco anterior **e** razão ≥ 0.15 →
   LITERAL inteiro.
3. **Cabeçalho de seção** — `^[A-Z][A-Z0-9 ]*$` → LITERAL.
4. **Linha densa** — razão da linha ≥ 0.5 → LITERAL.
5. Resto → PROSE.

A regra 1 entrou por medição, não por desenho: o bloco de exemplo da curl tem
quatro linhas, três acima de 0.5 e uma (`--expand-data "{{fix:trim:url}}"`,
0.42) abaixo. Sem coerência de bloco, essa linha saía do bloco e ia para
tradução no meio de um comando. Ela também é um dos oito intratáveis, e é o
único que a fase 2 resolveu.

Consequência aceita: **cabeçalhos de seção não são traduzidos.** `DESCRIPTION`
fica `DESCRIPTION`. A spec pede isso explicitamente; para uma man page em
pt-BR seria melhor traduzir, e é uma linha de código mudar de ideia.

## De-hifenização: a heurística não falhou

**11 de 11 corretos.** Todas as linhas do corpus que terminam em U+002D são
palavras compostas quebradas no hífen que já existia, e todas as 150 que
terminam em U+2010 são hifenização do groff.

| fim de linha | ocorrências | ação | exemplo |
|---|---|---|---|
| U+2010 `‐` | 150 | junta e **remove** o hífen | `notifica‐` + `tion` → `notification` |
| U+002D `-` | 11 | junta e **mantém** o hífen | `set-` + `group-ID` → `set-group-ID` |

Os 11 casos de U+002D, conferidos um a um: `auto-seeding`, `set-group-ID`,
`starting-point`, `git-diff(1)`, `git-shortlog(1)`,
`maximum-addr-flush-attempts`, `locally-generated`, `systemd.image-policy(7)`,
`remote-shell`, `remote-update`, `system-wide`. Em todos, apagar o hífen
produziria uma palavra errada.

Duas guardas impedem junção indevida, e ambas têm teste: o caractere antes do
hífen precisa ser alfanumérico (senão a régua `----` e um travessão solto no
fim da linha juntariam), e a linha seguinte precisa começar em minúscula
(senão uma linha de tabela terminada em `-` colaria na próxima).

**Onde pode falhar:** a heurística é do groff. Saída de `--help` escrita à mão
não usa U+2010 e quebra linhas onde quiser; ali nada será juntado. E um hífen
final legítimo seguido de linha começando em minúscula — uma frase terminada
em travessão, por exemplo — seria juntado. Não ocorre no corpus.

## Colagem de espaço: por que está em normalize

A spec põe a colagem em `normalize` e pede que
`reassemble(segment(normalize(t)))` seja idempotente sobre a saída de
`normalize`. Isso força a mão: se `segment` colapsasse espaço, a saída deixaria
de ser ponto fixo. Então `normalize` colapsa, e precisa decidir sozinho o que é
justificação e o que é layout, sem saber o que é prosa.

Decidido por medição. Das 2045 sequências de 2+ espaços entre palavras em
linhas de baixa sintaxe, 87.4% têm 2 espaços e 6.0% têm 3 — justificação do
roff. A cauda de 19 a 27 espaços é tabela. Limiar: **sequências de até 3
espaços colapsam, de 4 em diante ficam**. A tabela da systemctl sobrevive
intacta e há teste para isso.

## Os oito intratáveis: 1 resolvido, 7 continuam expostos

Verificado linha a linha, pelas linhas exatas anotadas na fase 1.2 — não por
presunção:

| caso | veredito |
|---|---|
| `curl.txt:122` `{{fix:trim:url}}` | **LITERAL — resolvido** |
| `awk.txt:58` `-` | PROSE — exposto |
| `awk.txt:75` `\n` | PROSE — exposto |
| `awk.txt:127` `\` | PROSE — exposto |
| `chmod.txt:29` `-` | PROSE — exposto |
| `chmod.txt:120` gramática BNF | PROSE — exposto |
| `curl.txt:91` `\{{` | PROSE — exposto |
| `ip.txt:75` `\` | PROSE — exposto |

A aposta da fase 2 era que a classificação de bloco resolveria os oito. **Não
resolveu, e não podia.** Os sete restantes não estão em blocos de código — são
metacaracteres citados dentro de frases perfeitamente traduzíveis:

> `forces mawk not to consider '\n' to be space.`
> `Long statements can be continued with a backslash, \.`
> `Each MODE is of the form '[ugoa]*([-+=]([rwxXst]*|[ugo]))+|[-+=][0-7]+'.`

Classificar essas linhas como LITERAL seria pior que o problema: perderia-se a
tradução de frases inteiras para proteger um caractere. A classificação está
certa; a proteção é que precisa vir de outro lugar.

### O padrão que aparece: cinco dos sete estão entre aspas

`'\n'`, `"\{{"`, `'[ugoa]*...'`, `'\'` e `“-”` — cinco dos sete casos estão
delimitados por aspas simples, duplas ou curvas. Os dois que não estão são
`\.` (awk:127) e `- causes them` (chmod:29).

Isso sugere um caminho concreto e barato para uma fase futura: **um padrão de
literal entre aspas em `mask.py`**, no mesmo espírito do padrão de crase que
existe desde a fase 1 — a crase já é tratada assim, e aspas são o mesmo
mecanismo tipográfico numa página que não usa crase. Resolveria 5 dos 7 sem
tocar na segmentação e sem risco de perder prosa. `mask.py` está congelado
nesta fase, então fica registrado, não implementado.

## Arquivos

```
manbr/normalize.py                 # overstrike, tabs, controles, hífen, espaço
manbr/segment.py                   # blocos, classificação, reassemble
tests/test_normalize.py            # 76 testes
tests/test_segment.py              # 71 testes
tests/fixtures/overstrike_raw.txt  # saída real de man, 271 backspaces
tests/fixtures/overstrike_col.txt  # a mesma, passada por col -bx
tests/coverage/measure_segment.py  # a medição acima
```

O corpus versionado foi gerado com `col -bx`, então **não tem overstrike nem
tabs** — o caminho mais delicado de `normalize` não seria exercitado por ele.
Por isso o fixture: `overstrike_raw.txt` é `man ss` com
`MAN_KEEP_FORMATTING=1`, com 271 backspaces de verdade. O teste que importa é
que `normalize(raw) == normalize(col)`: a implementação em Python puro
concorda com `col -bx` sem depender do binário.
