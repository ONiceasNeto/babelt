# Histórico de desenvolvimento

Um documento por fase, escrito no fim dela, com **as medições que sustentam as
decisões** — não só o que foi feito, mas o que foi tentado e recusado, e o
número que decidiu.

Vale a leitura antes de mexer em `mask.py`, `segment.py` ou `validate.py`:
quase toda regra ali é resposta a um falso positivo ou falso negativo medido
no corpus, e várias hipóteses óbvias já foram testadas e reprovadas. As fases
1 a 4 usam o nome antigo do projeto, `manbr`; a renomeação está na fase 8.

| Fase | Assunto | O que ficou decidido |
| --- | --- | --- |
| [1](README-fase1.md) | `mask.py` e `validate.py` | Mascarar sintaxe **antes** do modelo e validar depois; nada de tradução ainda. |
| [1.1](README-fase1.1.md) | Falsos negativos | Cobertura de mascaramento passou a ser medida, não estimada. |
| [1.2](README-fase1.2.md) | Recall a 97,8% | Limite `[a-z]{2,6}` caiu; entrou `extensions.txt`, editável. |
| [2](README-fase2.md) | `normalize.py` e `segment.py` | Indentação sozinha não separa nada — **o que separa é o bloco**. |
| [2.1](README-fase2.1.md) | Aspas e cabeçalhos | Literal entre aspas e `headers.txt` com 56 entradas. |
| [3](README-fase3.md) | Tradução NMT | CTranslate2 + Marian, int8, em CPU. |
| [3.1](README-fase3.1.md) | Validação estrutural | Contagem de sentenças, repetição e delimitadores — o que os placeholders não pegam. |
| [4](README-fase4.md) | Cache e CLI | Cache em disco: 165 s a frio, 0,31 s quente. |
| [5](README-fase5.md) | `--help` e colunas | Layout de duas colunas não é prosa nem literal: virou `SegmentKind.COLUMNS`. |
| [6](README-fase6.md) | Omissão, listas, pager | Guarda de prosa: `ls \| babelt` traduzia nome de diretório. |
| [7](README-fase7.md) | Distribuição | Artefato pronto em vez de conversão local; `torch` e `transformers` saíram das dependências. |
| [8](README-fase8.md) | Renomeação | `manbr` → `babelt`; nada é migrado, `doctor` avisa dos órfãos. |

## Fora da sequência

- [`fase5-katana.md`](fase5-katana.md) — saída completa de `babelt --help-of
  katana`, original e traduzida, sem retoque. Serve de referência de qualidade
  para um `--help` denso de flags.

## O padrão

Cada documento abre com os comandos que reproduzem os números e fecha com o
que **não** foi resolvido. Uma hipótese medida e reprovada vale tanto quanto
uma aceita: as duas evitam que alguém refaça o mesmo caminho. A fase 7 recusou
duas métricas de omissão por falta de separação entre as populações, e isso
está lá escrito.
