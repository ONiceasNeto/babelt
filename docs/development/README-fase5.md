# babelt — Fase 5: saída de `--help` e segmentação por colunas

```
PYTHONPATH=. .venv/bin/pytest                          # 1348 testes
PYTHONPATH=. .venv/bin/pytest -m 'not model'           # 1341, sem o modelo
PYTHONPATH=. .venv/bin/mypy                            # strict, limpo
python tests/coverage/measure.py                       # mascaramento
python tests/coverage/measure_segment.py               # segmentação, man
python tests/coverage/measure_segment.py --help-corpus # segmentação, --help
python tests/quality/measure_translate.py --help-corpus # tradução, --help
```

`PIPELINE_VERSION` foi para **3**: `mask`, `segment` e `normalize` mudaram, e o
cache da fase 4 se invalida sozinho.

## O número que mede a fase

**Das 109 unidades traduzíveis de `katana --help`, 100 saem em português
(91,7%) com a coluna da esquerda intacta.** Na fase 4 a mesma página produzia
um parágrafo corrido em inglês e um comando inventado (`katana [band]`).

O lado a lado está em [fase5-katana.md](fase5-katana.md).

## Parte A — mask: a fase 3.2 pendente

| | fase 4 | **fase 5** |
|---|---|---|
| tokens anotados | 194 | 202 |
| recall | 96,9% | **97,5%** |
| parciais (classe crítica) | 0 | **0** |
| ausentes | 6 | 5 |
| **falsos positivos em prosa** | 1 | **1** |

O critério de morte era FP em prosa continuar zero. Continuou: o único
candidato apontado pela medição é `'“dynamic”'`, o mesmo de antes desta fase.

### A anotação estava incompleta, e a medição mostrou

Os padrões novos passaram a mascarar oito tokens que apareciam como falso
positivo — `[OPTIONS]`, `[FILE...]`, `[MEMBER...]`, `[chain]`,
`[per-target-options]`, `[PATTERN...]`. Todos em linha de sinopse, e todos
anotáveis pela regra que o próprio arquivo declara: traduzir `[OPTIONS]` para
`[OPÇÕES]` produz comando inválido. A fase 1 não tinha padrão que os pegasse e
a omissão passou despercebida. Foram acrescentados a `annotated.tsv`, com o
motivo registrado lá — daí os 202 tokens contra 194.

Sem essa correção o relatório mostraria "FP: 9", e nenhum dos nove seria FP.

### Os quatro padrões

1. **Grupo isolado** `{action}`, `[flags]`, `{always|auto|never}`. Fecha, sem
   espaço dentro. O espaço é o que separa sintaxe de prosa: `[see below]` não
   casa, `[flags]` casa.
2. **Sufixo colado**, dentro do mesmo padrão: `[DD-]hh:mm:ss` é um token só.
   Sem ele o grupo mascarava a metade esquerda e deixava a direita exposta —
   a classe PARCIAL, que a medição trata como pior que AUSENTE.
3. **Sufixo de tipo** `string[]`, `int[]`. Colchete vazio não existe em prosa,
   então o padrão não tem como gerar FP. Treze ocorrências no corpus de help.
4. **Alternância solta** `yes|no`, `open|filtered`. Os dois lados colados no
   `|`; com espaço em volta é tabela ou prosa.

Uma exceção medida: **grupo só de dígitos fica de fora.** `[1]` em página de
systemd é referência de nota de rodapé no meio de uma frase. Mascará-lo não
corromperia nada, mas põe um placeholder a mais num parágrafo de prosa, e
placeholder perdido reprova o parágrafo inteiro.

### `value` nu: medido, e não vale

O item 3 da spec pedia para medir se `value` depois de uma flag compensa.
Não compensa, e o motivo é a Parte B:

| | ocorrências |
|---|---|
| metavariável de tipo depois de flag, corpus de help | 66 |
| **dentro da coluna esquerda (já literal por COLUMNS)** | **63 (95%)** |

Mascarar a palavra `value` custaria um padrão que casa uma palavra inglesa
comum em prosa — o tipo de FP que o critério de morte proíbe — para cobrir
três casos que a segmentação por colunas não pega. O padrão não entrou.

## Parte B — segmentação por colunas

`SegmentKind.COLUMNS` é uma **linha lógica de tabela**: `left` é a coluna
esquerda (literal, nunca traduzida), `text` é só a célula da direita, e
`column` é onde a direita começa. Cada célula vai ao modelo sozinha e tem o
próprio lugar no cache.

### Detecção

Bloco com ≥3 linhas cujo intervalo de ≥2 espaços termina na mesma coluna. A
coluna vencedora é a mais frequente do bloco — um `--help` mistura título de
seção e linha de flag no mesmo bloco, e só as últimas contam. Uma linha que
começa na coluna da direita, sem nada à esquerda, é continuação: entra na
mesma célula, com a quebra original, e o modelo recebe a frase inteira.

Duas guardas, e as duas foram medidas:

- **Por bloco.** Bloco já literal como bloco — denso, fundo, ou dentro de
  SYNOPSIS — não vira tabela. Tabela de saída de exemplo tem exatamente a
  forma de duas colunas, e traduzir a direita dela seria traduzir o que o
  comando imprime.
- **Por célula.** Quem decide é a direita, não a linha inteira. A linha
  `-d, --data <data>   HTTP POST data` passa de 0.5 de densidade por causa da
  esquerda; a célula é prosa. Julgar a linha deixaria metade da tabela da
  curl(1) em inglês — 8 linhas em vez de 10.

### Distribuição

| corpus de man | fase 4 | fase 5 |
|---|---|---|
| PROSE | 724 (63,5%) | 723 (63,1%) |
| LITERAL | 417 (36,5%) | 422 (36,9%) |
| COLUMNS | — | **0** |
| PROSE acima de 400 tokens | 0 | **0** |

**Zero tabela detectada no corpus de man**, que é o resultado certo: man page
usa tag com descrição pendurada, não duas colunas. Os cinco segmentos que
mudaram de PROSE para LITERAL são efeito do mascaramento novo, e cada um foi
inspecionado: `--[no-]mailmap`, `-D [bind_address:]port`, e quatro
`list-units [PATTERN...]` da systemctl. Todos sintaxe de comando que nunca
deveria ter sido prosa.

| corpus de --help | |
|---|---|
| PROSE | 144 (29,9%) |
| LITERAL | 82 (17,0%) |
| **COLUMNS** | **255 (53,0%)** |
| PROSE acima de 400 tokens | 0 |

Metade do conteúdo de um `--help` é tabela de duas colunas. Era metade do
conteúdo que a fase 4 tratava como um parágrafo só.

### Dois bugs que a fase encontrou em módulo congelado

**1. `normalize` comia o intervalo de coluna de dois espaços.**
`MAX_JUSTIFICATION_RUN = 3` foi medido em man page, onde justificação usa 2 a
3 espaços e tabela usa de 19 a 27. Saída de `--help` não é justificada e
alinha coluna com dois espaços — a mesma sequência, com o sentido oposto. O
gap de `-e, -exclude string[]  exclude host…` desaparecia e a tabela do katana
ficava com duas linhas alinhadas, abaixo do mínimo de três.

A exceção é de vizinhança: um intervalo curto sobrevive quando termina na
mesma coluna de um intervalo **inequívoco** — acima do teto de justificação —
na linha de cima ou de baixo. Aceitar apoio de intervalo curto fazia dois
acasos sustentarem um ao outro, e três linhas de prosa justificada da
iptables(8) viravam tabela; com a regra estrita, o corpus de man volta a zero.

O colapso agora itera até o ponto fixo: colapsar um intervalo desloca os
seguintes da linha, e sem o laço `normalize` deixava de ser idempotente —
invariante que a fase 1 testa.

**2. A profundidade de bloco contava o cabeçalho de seção.** Um bloco que
começa com `DESCRIPTION` na coluna 0 tem indent 0, e fazia o parágrafo
seguinte, a 7, parecer recuado além dele. Com o mascaramento melhor, a
densidade do segundo parágrafo da DESCRIPTION da ssh(1) passou de 0.15 e ele
virou literal — prosa pura que deixaria de ser traduzida. A profundidade agora
é a do corpo do bloco.

## Parte C — modo `--help`

```
babelt <cmd>              man <cmd>
babelt --help-of <cmd>    <cmd> --help, depois -h, depois --usage
babelt --auto <cmd>       man; cai para --help só em "No manual entry"
```

`--help-of` **executa o binário**, e isso está dito no README. A superfície de
risco fica no mínimo: o comando é invocado só com o flag de ajuda, nunca com
argumento a mais, com timeout de 10 s. Há teste que verifica que nenhuma
invocação leva um terceiro argumento.

`stderr` é capturado junto com `stdout` e o código de saída é ignorado: metade
das ferramentas Go escreve a ajuda em stderr e sai com 1 depois de imprimi-la.
O que decide é ter vindo texto.

`--auto` só troca de fonte quando a mensagem do `man` é "No manual entry".
Seção inválida ou catman quebrado são erro, e trocar de fonte esconderia isso.

## Parte D — corpus de `--help`

`tests/corpus/help/`, com `refresh-help.sh`. Sete ferramentas: **katana, nmap,
curl, ffmpeg, docker, rg, fd**. `kubectl` não está instalado nesta máquina e
foi registrado na lista do script, que o pula com aviso.

O corpus se paga na primeira medição: das sete, quatro têm tabela de duas
colunas (katana, docker, ffmpeg, curl) e três não (nmap usa `flag: descrição`
na mesma linha, rg e fd usam descrição pendurada como man page). A detecção
acerta as sete.

### Tradução, os dois corpora lado a lado

`measure_translate.py` ganhou `--help-corpus`, e com ele as células de tabela
entram na conta — deixá-las de fora mediria metade do corpus.

| | man (fase 4) | **--help (fase 5)** |
|---|---|---|
| unidades traduzíveis | 724 | 399 |
| aceitas direto | — | 343 (86,0%) |
| **saem em inglês** | 101 (14,0%) | **48 (12,0%)** |
| segmentos com `<unk>` na origem | 71 (8,6%, fase 3.1) | **9 (2,3%)** |
| — buraco de cobertura do mask | 64 | 9 |
| — buraco de vocabulário do modelo | 7 | **0** |
| custo a frio | 0,97 s/segmento | 0,50 s/segmento |
| acerto do cache em memória | 46,6% | 50,5% |

Duas leituras que importam:

**Os 8,6% de OOV da fase 3.1 caíram para 2,3%**, e os nove que sobraram são
todos da nmap — `<port ranges>`, `{target specification}`, `<Lua scripts>`:
grupos **com espaço dentro**, que os padrões desta fase excluem de propósito
para não casar prosa entre colchetes. O buraco de vocabulário de verdade, que
mascarar não resolveria, está em zero neste corpus.

**Célula de tabela é mais barata que parágrafo** — 0,50 s contra 0,97 s por
unidade — porque é curta. A mediana de uma célula é 6 tokens.

## Parte E — glossário: a entrada foi recusada

A spec pedia `headless → headless` e `non-headless → non-headless` no
glossário. **Medido com o modelo real, o glossário não resolve, e a entrada
pioraria:**

```
EN  offering both headless and non-headless support
PT  oferecem suporte tanto sem cabeça quanto sem cabeça
EN  start the browser in non-headless mode
PT  iniciar o navegador no modo sem cabeça
```

As duas formas colapsam em "sem cabeça". O glossário é PT→EN e roda depois da
tradução: ao ver "sem cabeça" não tem como saber qual das duas gerou, e
devolver sempre `headless` inverteria o sentido de metade das ocorrências. É o
mesmo teste que reprovou `núcleo → kernel` na fase 3.

O que resolve é mascarar na origem, e é o que foi feito: `babelt/literals.txt`,
uma lista de termos que nunca chegam ao modelo. A diferença de classe está
escrita no arquivo — glossário é para o termo que o modelo traduz **bem, mas
de forma indesejada** (reversível); a lista é para o termo cuja tradução
**perde informação** (irreversível).

Custo declarado, medido nas mesmas frases:

```
start the browser in ⟦0⟧ mode  ->  Iniciar o navegador no modo non-headless
offering both ⟦0⟧ and ⟦1⟧ ...  ->  o modelo derrubou os dois placeholders,
                                   a validação rejeitou, a frase sai em inglês
```

Inglês em vez de negação invertida. A troca é deliberada.

## O que ficou fora

- **Lista de valores separada por vírgula chega ao modelo.** É o achado mais
  sério da fase, e está fora dos quatro padrões que a spec autorizou.
  `all,robotstxt,sitemapxml` saiu como `todos,robotstxt,sitemapxml` na amostra
  do katana: `all` traduzido dentro de um valor que o leitor vai copiar.
  Medido: **13 listas assim chegam ao modelo** (6 no corpus de man —
  `NAME,FSTYPE,LABEL,UUID` da lsblk, `euser,ruser,suser` da ps — e 7 no de
  help). O padrão candidato, `\w+(?:,\w+){2,}` sem espaços, casa 17 vezes nos
  dois corpora e **zero vezes em prosa**. Está pronto para medir numa fase que
  o autorize.
- **`Flags:` e `INPUT:` saem na mesma linha.** Título de bloco de `--help` é
  vocabulário fechado, como cabeçalho de seção de man page, e pede a mesma
  solução: uma tabela, não o modelo.
- **Tabela de duas colunas com gap de 2 espaços em todas as linhas.** A
  exceção de vizinhança precisa de ao menos um intervalo inequívoco no bloco
  para se ancorar. Uma tabela inteiramente alinhada com dois espaços continua
  invisível depois do `normalize`.
- **`nmap --help` usa `flag: descrição`**, um layout de coluna sem coluna. Não
  é detectado, e a linha inteira segue como prosa.
- **Palavra omitida não é detectada por nenhuma validação.** Visto no
  `curl --help` desta fase: `Send User-Agent <name> to server` saiu como
  `Enviar ⟦0⟧ para o servidor` — o placeholder voltou intacto, a contagem de
  sentenças bateu, os delimitadores bateram, e "User-Agent" simplesmente não
  está lá. As quatro regras da fase 3.1 medem estrutura; omissão de conteúdo
  passa por todas.
- **Fluência.** "rastejar" para *crawl*, "habilit jsluice parsing in javascript
  ficheiro". Nenhuma regra desta fase mede português, como em todas as
  anteriores.
