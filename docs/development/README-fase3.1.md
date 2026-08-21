# manbr — Fase 3.1: validação além dos placeholders

```
.venv/bin/pytest                                  # 1211 testes
.venv/bin/mypy                                    # strict, limpo
python tests/quality/measure_translate.py
```

## O número que mede a fase

**106 segmentos que a fase 3 aprovava agora são rejeitados — 15.1% de tudo o
que ela aprovava.** Cada um é uma linha que teria saído corrompida.

| regra que pegou | segmentos |
|---|---|
| guarda de vocabulário (oov) | 53 |
| contagem de sentenças mudou | 29 |
| token desconhecido na saída | 9 |
| delimitador `(` | 6 |
| delimitador `[` | 5 |
| delimitador `]` | 4 |

Comparação feita sobre **as mesmas saídas do modelo**, aplicando os dois
conjuntos de regras — não são duas execuções com aleatoriedade diferente.

| | fase 3 | fase 3.1 |
|---|---|---|
| parágrafos aprovados | 703 (85.1%) | 597 (72.3%) |

## Fase 3 vs 3.1, execução completa

| | fase 3 | **fase 3.1** |
|---|---|---|
| segmentos PROSE | 826 | 826 |
| parágrafos aceitos direto | 752 (91.0%) | **641 (77.6%)** |
| parágrafos rejeitados | 74 (9.0%) | **185 (22.4%)** |
| — recuperados por sentença | 18 | **29** |
| **segmentos em inglês na saída** | 56 (6.8%) | **156 (18.9%)** |
| dos que tinham placeholder | 39 (14.2%) | 90 (32.8%) |
| **deriva de sentenças nos aceitos** | **11.6%** | **1.6%** |

Como avisado, a taxa de inglês subiu — de 6.8% para 18.9%. É o resultado
pretendido. A linha que importa é a última: a deriva de sentenças entre os
segmentos **aceitos** caiu de 11.6% para 1.6%. O que sai traduzido agora é
muito mais confiável.

O resíduo de 1.6% existe porque a recuperação por sentença valida cada frase
isoladamente: uma frase traduzida por duas frases passa na regra local. Fechar
isso exigiria validar a junção também, e fica registrado.

## Parte A — guarda de vocabulário, e o diagnóstico dos 71

Dos 826 segmentos de prosa, **71 (8.6%)** contêm pedaço que o tokenizer não
conhece. Nenhum deles gasta inferência agora: são detectados com o
sentencepiece, que é barato, sem carregar os 228 MB de pesos (há teste).

Do diagnóstico pedido:

| | segmentos |
|---|---|
| **buraco de cobertura do `mask`** | **64** |
| buraco de vocabulário do modelo | 7 |

**64 dos 71 são cobertura, não vocabulário.** Os pedaços desconhecidos são
metacaracteres de shell — `{`, `}`, `|`, `=`, `^`, `` ` ``, `\`, `@` — dentro
de trechos que são sintaxe e deveriam ter virado placeholder:

```
{ } = { }        An AWK program is a sequence of pattern {action} pairs…
{ } { } { }      One, but not both, of pattern {action} can be omitted…
{ } \ ||         Statements are terminated by newlines, semi-colons or both…
```

O padrão que falta é claro e tem forma: **grupo entre chaves** (`{action}`,
`{A|c|d|r|t}`) e **alternância com `|`**. São os mesmos `{...}` que a fase 1.2
já reconhece *coladas* num caminho ou numa flag (`/dev/disk/by-{label,uuid}`,
`-c[color][={always|auto|never}`) — só não os reconhece soltos. Isto sim
justifica descongelar `mask.py` numa fase futura: é um padrão, não um remendo,
e fecharia 64 dos 71 casos.

Os 7 restantes são vocabulário de verdade e mascarar não resolveria — o
caractere está no meio de uma frase traduzível:

```
•        • forces mawk not to consider '\n' to be space.
=        mawk allows multiple -W options to be combined by separating…
```

O critério que separa as duas classes: se **todo** pedaço desconhecido é
metacaractere de shell, é cobertura; se houver tipografia de prosa (`•`, `©`,
travessão), é vocabulário. Está em `Translator.oov_diagnosis`, com testes.

## Parte B — validate_structure

`validate.py` foi descongelado só para adição. `validate` não mudou uma linha;
`validate_structure(source, translated)` é nova, e a divisão de sentenças
mudou de casa: saiu de `translate.py` e foi para `validate.py`, porque a regra
de contagem e o caminho de recuperação **precisam cortar exatamente igual** —
se divergissem, a validação reprovaria o que a recuperação produziu.
`translate.split_sentences` continua existindo, reexportado.

As quatro regras, na ordem em que são checadas:

1. **Token desconhecido** (`U+2047`, `<unk>`, `U+FFFD`) — primeiro por ser o
   sinal mais barato e o que explica os outros sintomas quando aparece junto.
2. **Contagem de sentenças** igual entre origem e tradução.
3. **Repetição** — nenhuma sentença aparece mais vezes na tradução do que na
   origem. É o modo de falha do `</s>` ausente, e sobrevive à regra 2 quando o
   modelo repete e omite na mesma proporção.
4. **Delimitadores** `[ ] { } ( )` com contagem preservada.

Falha em qualquer uma → mesmo tratamento de antes: cai para o caminho de
sentença, e sentença que falhar sai em inglês.

O caso que abriu a fase — `chmod [OPTION]...` virando `[OP ⁇ O]...` com
aprovação — é pego duas vezes agora: pela guarda de vocabulário, antes de
gastar inferência, e pela regra 1, se chegasse lá.

## Parte D — performance

### beam_size, default 1

| | beam 1 | beam 4 |
|---|---|---|
| aprovados (232 segmentos sem OOV, regras 3.1) | 189 (81.5%) | 193 (83.2%) |
| tempo | 239s | 666s |
| `man ss` frio (48 segmentos) | **26.6s** | 65.7s |
| pico de memória | 1194 MB | 1628 MB |

**Estruturalmente, beam 1 custa 1.7 pp de aprovação por 2.8× menos tempo.**
Pelo critério de aceitação, o default 1 se paga com folga.

**Mas a qualidade cai de forma perceptível, sim.** Numa amostra de 30, 13
saídas diferem entre os dois, e as diferenças que inspecionei favorecem beam 4:

```
EN: Suppress normal output; instead print a count of matching lines…
b1: Suprimir a saída normal; em vez imprimir uma contagem…      <- falta "disso"
b4: Suprima a saída normal; em vez disso, imprima uma contagem…

EN: DICT Lets you lookup words using online dictionaries.
b1: DICTO Permite pesquisar palavras…                            <- inventou letra
b4: Permite pesquisar palavras…

EN: -B     shortcut for -family bridge.
b1: [1] ⟦0⟧ atalho para [1] ponte.                               <- placeholder quebrado
b4: Atalho para ⟦1⟧ ponte.
```

O terceiro é o mais relevante: beam 1 devolveu `[0]` onde devia devolver
`[[0]]`, e `from_wire` — estrito de propósito — não converte. Ou seja, parte
da diferença de 1.7 pp é exatamente isto: beam 1 estraga mais placeholders.

Recomendação: manter o default 1 enquanto não houver cache em disco, e trocar
para 4 quando o custo virar único. A constante é `BEAM_SIZE` e o construtor
aceita `beam_size=`.

### Cache em memória

**46.6% de acerto** (921 de 1977 consultas) numa passada pelo corpus inteiro.
Man page repete muito, e a conta inclui repetição dentro do mesmo lote — cinco
cópias da mesma frase são quatro inferências que não aconteceram, tanto quanto
se viessem de uma chamada anterior.

O efeito é visível: a segunda passada pelos mesmos parágrafos custou 194s
contra 800s da primeira. Cache em disco (fase 4) transformaria isso no custo
da segunda passada, sempre.

### Tempos

| | |
|---|---|
| import dos módulos | 0.028s |
| carga do modelo | 4.4s |
| **passada de parágrafos, cache frio** | **800s** (0.97s/segmento) |
| `translate_all` com cache quente | 194s |
| `man ss` frio, beam 1 | 26.6s |
| pico de memória | 1194 MB |

Contra a fase 3 (beam 4, sem cache): 2839s para o corpus e 69s para `man ss`.
São **3.5×** mais rápido no corpus e **2.6×** numa página, com 434 MB a menos
de pico. Ainda assim, 26.6s para abrir uma man page não é interativo — o cache
em disco da fase 4 é o que resolve isso, não mais ajuste de beam.

## Amostra

`tests/quality/sample.md` regenerado com beam 1 e as regras novas: 30
traduções lado a lado, 5 mantidas em inglês (contra 4 na fase 3), uma delas
com `reason="oov"`.

## O que continua sem cobertura

- **Junção de sentenças na recuperação.** Cada frase é validada sozinha; uma
  frase traduzida por duas passa. É o resíduo de 1.6% de deriva.
- **Prosa de várias linhas volta numa linha só.** O modelo junta as quebras de
  largura. Para prosa isso é semanticamente correto, mas a saída não é
  requebrada — é problema de renderização, para a fase 4.
- **Fluência.** Nenhuma regra aqui mede português. "Omit características",
  "O daemon bifurca" e "deixa cair o pacote" passam em todas as quatro. A
  validação garante que a sintaxe sobreviveu, não que o texto esteja bom.
