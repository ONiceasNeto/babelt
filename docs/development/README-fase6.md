# babelt — Fase 6: omissão, listas, pager, e entrada que não é prosa

```
PYTHONPATH=. .venv/bin/pytest                              # 1374 testes
PYTHONPATH=. .venv/bin/mypy                                # strict, limpo
python tests/coverage/measure.py                           # mascaramento
python tests/coverage/measure_segment.py --corpus man|help|nonprose
python tests/quality/measure_translate.py --corpus man|help|nonprose
python tests/quality/measure_omission.py                   # cobertura de conteúdo
```

`PIPELINE_VERSION` foi para **4**: `mask` e `segment` mudaram.

## O número que mede a fase

**Sem guarda, 86 dos 110 segmentos de `ls`, `ps aux` e `df -h` são
"traduzidos" (78,2%).** Com a guarda, zero — e nenhuma inferência é gasta.

```
EN  -rw-r--r-- 1 root root 433 Apr 8 2024 apg.conf
PT  -rw-r--r-- 1 raiz raiz raiz raiz 433 Apr 8 2024 apg.conf

EN  4096 Aug 28 2025 apm
PT  28 2025 ampm
```

`root` virou `raiz` e depois se multiplicou; um tamanho de arquivo virou outro
número. Nenhuma regra de validação via nada disso: não há placeholder, nem
sentença, nem delimitador envolvido. O texto não estava corrompido — estava
certo para uma premissa errada.

## Parte D — a guarda de prosa, e por que ela é por documento

A métrica é a **densidade de palavras funcionais**: artigo, preposição,
conjunção, auxiliar. Prosa é feita de gramática; saída de comando é feita de
nomes. Medida sobre o texto mascarado, porque flag e caminho não são palavra
de idioma nenhum.

### Por segmento: as populações não se separam

| população | p05 | p10 | p25 | mediana | max |
|---|---|---|---|---|---|
| man PROSE | 0,000 | 0,000 | 0,182 | 0,333 | — |
| help COLUMNS | 0,000 | 0,000 | 0,000 | 0,167 | — |
| **nonprose** | 0,000 | 0,000 | 0,000 | 0,000 | **0,167** |

Metade das células de `--help` está dentro da faixa inteira do nonprose. É o
conflito que a spec mandou medir explicitamente, e ele existe: "Silent mode" e
uma linha de `ls` têm exatamente a mesma densidade, porque nenhuma das duas
tem espaço para uma preposição. **Por segmento a guarda é impossível.**

### Por documento: separam com folga

| corpus | pior documento | melhor |
|---|---|---|
| nonprose | `journal.txt` **0,128** | `ls.txt` 0,000 |
| --help | `ffmpeg.txt` **0,181** | `rg.txt` 0,456 |
| man | `dd.txt` 0,298 | `find.txt` 0,473 |

Vão livre de **0,053** entre 0,128 e 0,181. `PROSE_DENSITY_FLOOR = 0,14` fica
dentro dele, com 0,012 de margem para o log do journalctl e 0,041 para o
`ffmpeg --help`. A margem é maior do lado que importa: rejeitar um documento
de prosa inteiro é visível e irritante; deixar um log passar corrompe nomes de
serviço, que é ruim mas menos.

### "Intacta" precisou virar literal

A primeira versão da guarda pulava a tradução mas devolvia o texto pelo resto
do pipeline — e o resultado ainda saía errado:

```
$ ps aux | babelt        # guarda ligada, primeira versão
USER PID %CPU %MEM VSZ RSS TTY STAT START TIME COMMAND
root 1 0.0 0.2 22836 12672 ? Ss Aug18 0:13 /sbin/init splash
```

`normalize` colapsa o espaço de alinhamento — que ali é a tabela inteira — e
`rewrap` reflui parágrafo, o que juntou as 60 linhas de um `ls` num bloco
corrido. Quando a guarda dispara, o retorno agora é o **texto de entrada, byte
a byte**. O pipeline inteiro é para prosa, e esta não é.

### O resíduo: documento curto demais para julgar

Abaixo de **8 palavras** não há julgamento e o documento passa. É um
compromisso declarado, não uma medição: `Display current network sockets` tem
densidade zero e é prosa legítima; seis nomes de arquivo também têm densidade
zero e não são. Com o piso em 8, um `ls | head -12` já é barrado e uma frase
curta ainda é traduzida — mas `ls | head -5` continua passando, e continua
saindo traduzido. Não há sinal nesse tamanho.

### A lista de palavras funcionais teve de ser medida também

Com a lista inicial, `ps aux` dava densidade **0,161** e passava por prosa. A
causa era uma palavra só: **`i`**, que casava 20 vezes — é a letra da coluna
STAT (*idle*), não o pronome. Tirando os pronomes de primeira pessoa, que
documentação técnica não usa, `ps aux` volta a 0,000 e o vão livre aparece.

Está em `babelt/function_words.txt`, editável, com o motivo escrito no arquivo.

## Parte B — cobertura de conteúdo: medida, e **não ligada**

O caso que motivou a regra:

```
EN  Send User-Agent <name> to server
PT  Enviar ⟦0⟧ para o servidor
```

Distribuição da razão palavras(PT)/palavras(EN) entre as **773 traduções
aceitas** com pelo menos 4 palavras, nos dois corpora de prosa:

| min | p01 | p05 | p10 | mediana | max |
|---|---|---|---|---|---|
| 0,67 | 0,75 | 0,88 | 0,93 | 1,06 | 2,33 |

Os 55 segmentos abaixo de 0,90 foram rotulados à mão, um a um, e estão em
[`tests/quality/omission-labels.tsv`](../../tests/quality/omission-labels.tsv):
**24 omissões reais, 31 compressões legítimas.**

| limiar | rejeita | omissões pegas | boas perdidas | precisão | custo |
|---|---|---|---|---|---|
| 0,75 | 2 | 1 | 1 | 50% | 0,1% |
| 0,78 | 9 | 5 | 4 | 56% | 0,5% |
| 0,80 | 10 | 5 | 5 | 50% | 0,6% |
| **0,83** | 20 | **12** | 8 | **60%** | 1,0% |
| 0,85 | 29 | 16 | 13 | 55% | 1,7% |
| 0,88 | 49 | 24 | 25 | 49% | 3,2% |
| 0,90 | 55 | 24 | 31 | 44% | 4,0% |

**A precisão não passa de 60% em limiar nenhum, e não há ponto de virada.** As
populações se sobrepõem em toda a faixa. Seguindo a instrução da spec — "se as
populações não se separarem, diga isso e não force um número" — **a quinta
regra não foi ligada.** `validate_structure` continua com quatro.

O que impede a separação é a assimetria de comprimento entre segmento curto e
longo. Perder uma palavra num parágrafo de 93 dá razão 0,99; perder uma numa
célula de 4 dá 0,75. E é justamente na célula curta que vivem tanto as
omissões quanto as compressões legítimas:

```
omissão    curl - transfer a URL         ->  - transfira uma URL          0,75
legítima   do not follow symlinks        ->  não siga symlinks            0,75
```

### O achado por trás da cauda

Rotulando as 24 omissões, o padrão é gritante: **22 perderam a primeira
palavra do segmento.** Só duas foram no meio (`Send User-Agent` e `ps ax`).

Dessas 22, em **10** a palavra perdida era um identificador — `sync`, `fsync`,
`mroute`, `curl`, `journalctl`, `LAST`, `FILE`, `for`, `tfidf/bm25`, e o
marcador de item `o`. Nas outras 12 era o verbo que abre a descrição: `set`,
`show`, `start`, `list`, `output`, `enable`, `fail`, `request`.

Isto diz duas coisas. A primeira é que **o modelo engole o começo de segmento
curto** — é um comportamento posicional, não lexical, e uma regra de contagem
de palavras é uma forma indireta e cara de detectá-lo. A segunda é que os 10
identificadores, se estivessem mascarados, já seriam pegos pela validação de
placeholder da fase 1, sem regra nova nenhuma. Mascarar palavra nua é o que a
fase 1.1 declarou fora de escopo por não haver *forma* que a separe de prosa;
a fase 6 mostra que existe um critério melhor — a **posição**: primeira
palavra de uma descrição pendurada. Fica registrado para quem for atacar.

## Parte A — lista separada por vírgula

Confirmado em uso real: `(all,robotstxt,sitemapxml)` saía como
`(todos,robotstxt,sitemapxml)`.

| | fase 5 | fase 6 |
|---|---|---|
| tokens anotados | 202 | 203 |
| recall | 97,5% | **97,5%** |
| parciais | 0 | **0** |
| **FP em prosa** | 1 | **1** |

Catorze casamentos nos dois corpora, todos lista de valores:
`NAME,FSTYPE,LABEL,UUID` da lsblk, `euser,ruser,suser` da ps,
`php,html,js,none` do katana. **A ausência de espaço é a regra inteira** —
enumeração em prosa põe espaço depois da vírgula, lista de valores não põe,
porque o espaço quebraria o argumento no shell.

Três exclusões, cada uma medida:

- **Dois itens não bastam.** `foo,bar` aparece em prosa inglesa como par
  citado com mais frequência que como valor.
- **Só dígitos fica de fora.** `1,234,567` é número com separador de milhar,
  escrito em prosa — a mesma conta que deixou `[1]` de fora na fase 5.
- **O item aceita `:` e `-` no meio.** `U:53,111,T:21-25,80` da nmap é uma
  lista só; mascarar `53,111,T` deixando `U:` exposto seria a classe PARCIAL,
  que a medição trata como pior que não mascarar.

`e.g.` e `i.e.` não têm vírgula e nunca estiveram em risco.

Um falso positivo aparente foi outra lacuna de anotação: a lista de campos de
`ps -eo euser,ruser,...` nunca tinha sido anotada, embora traduzir um item dela
produza argumento inválido. Corrigido em `annotated.tsv`, com o motivo.

## Parte C — pager

Três defeitos, três correções:

| antes | depois |
|---|---|
| `katana --help` com 30 linhas abria o pager e exigia `q` | pagina só se a saída passar da altura do terminal |
| `less -R` limpava a tela ao sair, e a saída sumia | `less -RFX`: `-F` sai sozinho, `-X` não usa tela alternativa |
| só `$PAGER` | `$BABELT_PAGER` primeiro, depois `$PAGER`, depois o padrão |

`--no-pager` desliga sempre. `--help-of` e `--auto` não paginam por padrão: a
ajuda de um comando é curta e o usuário quer o resultado na tela, junto do que
já estava lá.

## Parte E — os dois defeitos de formatação

### 1. `Flags:` e `INPUT:` fundidas — causa: `segment`

Não era o modelo nem o `normalize`. As duas linhas estão no mesmo bloco, ambas
na coluna 0, e a regra de agrupamento por indentação as juntava num segmento
PROSE só — `'Flags:\nINPUT:'`. O modelo recebeu as duas juntas e devolveu uma
linha só, de quebra em minúscula.

A correção é a mesma que a fase 2 já usava para cabeçalho de seção de man
page: **título de bloco fica sozinho no segmento e é traduzido por tabela.**
`headers.txt` ganhou os títulos genéricos de `--help` — `Usage:`, `Flags:`,
`INPUT:`, `Common Commands:`. Título específico de ferramenta (`SCOPE:`,
`RATE-LIMIT:`) fica em inglês, que é a falha por omissão declarada desde a
fase 3.

O regex tem teto de seis palavras e classe sem vírgula nem ponto, e isso foi
medido: casa os 39 títulos dos dois corpora e nenhuma linha de prosa —
`The following options are supported, in order:` continua sendo prosa.

```
antes   flags: INPUT:
depois  Opções:
        ENTRADA:
```

### 2. Linha em branco entre células — **não reproduzida**

Rodei o pipeline inteiro, com as traduções reais do modelo, sobre os **27
documentos** dos corpora de man e de help, comparando a contagem de linhas em
branco da saída com a da origem. Nenhum documento inseriu uma linha em branco,
e nenhum produziu linha só de espaços.

A única mudança de estrutura de linha que encontrei foi a do defeito 1 — duas
linhas virando uma —, que está corrigida. Se o defeito reaparecer, é preciso a
entrada exata: pode ser uma ferramenta fora do corpus, e pode ser o pager
antigo (`less -R` sem `-X`) desenhando a tela alternativa.

## Parte F — as três medições, três corpora

| | man | --help | nonprose |
|---|---|---|---|
| arquivos | 20 | 7 | 6 |
| segmentos com conteúdo | 1145 | 483 | 125 |
| PROSE | 720 (62,9%) | 108 (22,4%) | 25 (20,0%) |
| LITERAL | 425 (37,1%) | 122 (25,3%) | 15 (12,0%) |
| COLUMNS | 0 | 253 (52,4%) | 85 (68,0%) |
| PROSE acima de 400 tokens | 0 | 0 | 0 |

| tradução | man | --help | nonprose |
|---|---|---|---|
| unidades traduzíveis | 720 | 361 | 110 |
| traduzidas | 627 (87,1%) | 319 (88,4%) | 86 (78,2%) |
| **em inglês** | **93 (12,9%)** | **42 (11,6%)** | 24 (21,8%) |

### Delta de inglês contra a fase 5, e sua composição

| | fase 5 | fase 6 | delta |
|---|---|---|---|
| man | 14,0% | **12,9%** | −1,1 pp |
| --help | 12,0% | **11,6%** | −0,4 pp |

Nos dois casos a queda é composta, e nenhuma parte dela é melhora de tradução:

- **man**: as unidades traduzíveis caíram de 724 para 720. Quatro linhas que
  eram prosa viraram literais pelo padrão de lista da parte A — eram
  `ps -eo pid,tid,class,...` e parentes. Saíram da conta por cima, e como
  eram justamente o tipo que a validação rejeitava, o percentual caiu.
- **--help**: as unidades caíram de 399 para 361. As 38 que saíram são os
  títulos de bloco da parte E, que agora são literais traduzidos por tabela —
  deixaram de ser tradução e passaram a ser acerto garantido.

A coluna do nonprose é o número **sem a guarda**, e existe para dizer o
tamanho do problema: 78,2% daquilo era "traduzido" com sucesso, segundo todas
as validações que existiam. Com a guarda da parte D, esses 110 segmentos não
chegam ao modelo.

## O que ficou fora

- **A quinta regra de validação.** Medida, rotulada, e recusada por falta de
  separação. A tabela de custo e ganho está acima; ligar em 0,83 custaria 1,0%
  das traduções boas para pegar metade das omissões, e é uma decisão de
  produto, não de medição.
- **Mascarar identificador nu no começo de descrição.** É a causa de 14 das 24
  omissões rotuladas, e a única correção que atacaria a raiz.
- **A guarda de prosa é por documento e não tem escape.** `ls | babelt` sai
  intacto, como deve; mas um documento legítimo de prosa muito técnica, com
  densidade abaixo de 0,14, também sairia — e não há flag para forçar. O
  corpus não tem nenhum caso assim (o pior é 0,181), mas a possibilidade está
  aberta.
- **Entrada com menos de 8 palavras não é julgada** e volta a ser corrompida:
  `ls | head -5` sai traduzido. É o resíduo declarado acima.
- **Fluência.** Continua sem medição, como em todas as fases.
