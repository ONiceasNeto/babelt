# manbr — Fase 3: tradução NMT

```
.venv/bin/pytest                                    # 1194 testes
.venv/bin/mypy                                      # strict, limpo
python -c "from manbr.model import download; download()"
python tests/quality/measure_translate.py
```

Primeira fase que produz português. Modelo: `Helsinki-NLP/opus-mt-tc-big-en-pt`
convertido para CTranslate2 int8 (228 MB em disco).

## O número que decide

**Rejeição por validação: 9.0% dos parágrafos. 6.8% dos segmentos saem em
inglês.**

| | |
|---|---|
| segmentos PROSE traduzidos | 826 |
| com ao menos um placeholder | 274 |
| **parágrafos aceitos direto** | **752 (91.0%)** |
| parágrafos rejeitados | 74 (9.0%) |
| — recuperados por sentença | 18 |
| — nada aproveitável | 56 (6.8%) |
| **segmentos que saíram em inglês** | **56 (6.8%)** |
| dos que tinham placeholder | 39 de 274 (14.2%) |

Não é alto o bastante para bloquear a CLI, **mas só depois de uma correção que
esta fase teve de fazer**. Sem ela a rejeição teria sido de praticamente 100%.

## O placeholder ⟦n⟧ não sobrevive ao tokenizer

A fase 1 escolheu `⟦`/`⟧` (U+27E6/U+27E7) com a justificativa de que "o
tokenizer NMT tende a preservá-los como unidade". **Medido, é falso para este
modelo.** O sentencepiece do opus-mt não tem nenhum dos dois caracteres no
vocabulário:

```
'⟦0⟧'  ->  pieces=['▁', '⟦', '0', '⟧']   unk=2
```

Cada placeholder vira dois `<unk>` e o modelo devolve `⁇ 0 ⁇`. Num teste
controlado de 10 frases com placeholders:

| formato | preservados |
|---|---|
| `⟦n⟧` | **0/10** |
| `<n>` | 0/10 |
| `@@n@@` | 0/10 |
| `#n#` | 9/10 |
| `%n%` | 10/10 |
| **`[[n]]`** | **10/10** |

### A correção, e onde ela foi colocada

`mask.py` está congelado, e continua: `⟦n⟧` segue sendo o formato do projeto e
`validate` segue conferindo `⟦n⟧`. O que mudou é a **roupa de viagem**: em
`translate.py`, `to_wire()` troca `⟦n⟧` por `[[n]]` antes do modelo e
`from_wire()` desfaz depois. Trocar de modelo é trocar duas constantes.

`from_wire` é deliberadamente estrito: `[[ 0 ]]` com espaços **não** volta a
placeholder, e o segmento é rejeitado. Aceitar formas frouxas seria aceitar
saída que o modelo já mexeu.

Caso de borda registrado: quando o texto de origem contém `⟦` literal,
`mask` o escapa como `⟦⟦`, e não há conversão segura. Esses segmentos vão sem
conversão, o modelo destrói os escapes, a validação rejeita e a linha sai em
inglês — seguro, e exige uma man page com `⟦` no texto.

## O segundo bug: Marian precisa de `</s>`

Sem `</s>` no fim da sequência de origem, o modelo não sabe onde parar:

```
'Show summary of options.'
-> 'Mostrar resumo das opções.. Mostrar resumo das opções.. Mostrar resumo
    das opções. Mostrar resumo das opções. Mostrar resumo das opções.'
```

Com `</s>`: `'Mostrar resumo das opções.'` Erro meu de inferência, não do
modelo, mas vale registrar porque a saída *parece* plausível e passaria
despercebida numa inspeção rápida.

## Tempo e memória

| | |
|---|---|
| import dos módulos | 0.034s |
| carga do modelo | 4.5s |
| corpus (826 segmentos, 3179 linhas) | 2839s — 47 min |
| — por segmento | 3.44s |
| — vazão | ~6 palavras/s |
| `man ss` (48 segmentos de prosa) | 69s |
| pico de memória | 1628 MB |

**69 segundos para uma man page é inviável para uso interativo**, e 1.6 GB de
pico é muito para uma CLI. Quatro núcleos, beam 4, int8. Medido à parte:
beam 1 é ~3× mais rápido que beam 4 (16 frases em 6.6s contra 20.8s). A fase 4
precisa tratar disto — cache de tradução por linha, beam menor por padrão, ou
as duas coisas. O cache tende a resolver: man pages repetem muito
("Show summary of options.").

A carga preguiçosa funciona e está testada: construir um `Translator` e
traduzir uma página só de blocos literais não carrega o modelo nem gasta os
4.5s.

## O que a validação não vê

Esta é a parte que merece mais atenção antes da fase 4. `validate` confere
placeholders. Tudo o que estraga fora deles passa.

### 1. Caracteres fora do vocabulário — 8.6% dos segmentos

Medido estaticamente sobre os 826 segmentos de prosa, depois de mascarar e
converter para o formato de fio: **71 segmentos (8.6%) contêm ao menos um
`<unk>`**, 156 no total. Os caracteres:

```
}  {  |  =  ^  @  `  \  •  ©  ‐  ~
```

São metacaracteres de shell. O efeito aparece na amostra 3 de
`tests/quality/sample.md`, e é o pior caso que encontrei:

```
EN : chmod [OPTION]... MODE[,MODE]... FILE...
pt : [OP ⁇ O]... MODE[,MODE]... FILE... chmod [OP ⁇ O]... ...
```

`[OPTION]` virou `[OP ⁇ O]`, e **a validação aceitou** — o único placeholder
da linha (`--reference=RFILE`) sobreviveu, então a regra passou. Um usuário
copiaria `[OP ⁇ O]`.

Há duas causas somadas, e nenhuma é de `mask`:

- Um bloco de SYNOPSIS foi classificado **PROSE** pela fase 2, porque
  `[OPTION]`, `MODE` e `FILE` são palavras nuas e a densidade de sintaxe ficou
  abaixo do limiar. Deveria ser LITERAL.
- A prosa de várias linhas é enviada como uma string só, e o modelo junta as
  linhas. Para prosa quebrada por largura isso é até correto, mas aqui juntou
  três linhas de sinopse.

**Recomendação para a fase 4:** rejeitar toda saída que contenha `⁇` (ou,
melhor, todo segmento cuja origem produza `<unk>` na tokenização — dá para
saber antes de traduzir, é barato, e evita gastar inferência). É uma regra de
uma linha e fecha a classe inteira.

### 2. Deriva de sentenças — 11.6%

Dos 284 parágrafos multi-frase traduzidos, **33 (11.6%) voltaram com número
de frases diferente** — frase somida ou duplicada. Exemplo real:

```
EN : Display only listening sockets. The kernel uses a pipe.
pt : O kernel usa um pipe. O kernel usa um pipe.
```

A primeira frase desapareceu, a segunda duplicou, e a validação aprovou:
nenhum placeholder envolvido, nada a perder. Modelos Marian são treinados por
sentença; parágrafo é fora da distribuição.

Contar frases antes e depois é barato e pega o caso. Como a recuperação por
sentença já existe, seria só mais um critério de rejeição do caminho de
parágrafo.

## Glossário: onde piorou

O glossário é aplicado depois da tradução e antes do restore, como pedido, e
não como placeholder — o modelo precisa ver "socket" para concordar género e
número na frase em volta.

Disparou em 7 de 26 segmentos do corpus com termo candidato, e nesses acertou:

```
String constants are enclosed…  ->  Constantes de cordas…   ->  Constantes de strings…
…investigate sockets            ->  …investigar soquetes    ->  …investigar sockets
This flag is obsolete           ->  Esta bandeira é obsoleta ->  Esta flag é obsoleta
```

**Mas o glossário é cego ao contexto**: ele mapeia a palavra portuguesa de
volta ao inglês sem saber qual palavra inglesa a produziu. Onde a palavra
portuguesa tem sentido comum, ele estraga uma tradução que estava certa:

| origem | sem glossário (certo) | com glossário (errado) |
|---|---|---|
| The **core** of the system | O **núcleo** do sistema | O **kernel** do sistema |
| Connect the **wire** to the pin | Conecte o **fio** ao pino | Conecte o **thread** ao pino |
| The **shell** of the nut | A **casca** da porca | A **shell** da porca |
| Each **rope** is measured | Cada **corda** é medida | Cada **string** é medida |

### A entrada que foi removida por medição

`núcleo -> kernel` **saiu**. Duas razões, as duas medidas:

- O modelo já devolve "kernel" sozinho (`The kernel drops the packet.` ->
  `O kernel deixa cair o pacote.`), então a entrada nunca ajudava.
- "core" é palavra comum em man page — `find files named core`, core dump —
  e vira "núcleo". A entrada transformava uma tradução certa em erro.

Entrada que não ajuda e às vezes atrapalha é só risco. As que ficaram foram
verificadas contra o modelo: `shell -> concha`, `socket -> soquete`,
`pipe -> tubo`, `string -> corda` e `flag -> bandeira` são mistraduções
**reais** deste modelo, então as entradas se pagam. `driver` e `daemon` o
modelo já mantém em inglês; as entradas correspondentes ficaram por segurança,
sem custo observado.

Risco residual declarado: `corda` (rope), `concha`/`casca` (shell de noz),
`fio` (wire), `tubo`/`cano` (encanamento). Nenhum aparece no corpus, todos são
possíveis. Plurais são entradas próprias, não regra — uma regra de plural em
português erraria em "anfitriões".

Limitação que o glossário não cobre: `core dump` -> `depósito central`. É
frase feita, não termo isolado; substituição palavra a palavra não alcança.

## Fluxo, como ficou

```
LITERAL  -> intacto, translated=False
PROSE    -> mask -> to_wire -> modelo -> from_wire -> validate
              ok    -> glossário -> restore -> translated=True
              falha -> divide em sentenças (no texto mascarado)
                         cada uma: validate própria, com o subconjunto de
                         placeholders que aparece nela
                         a que falhar fica em inglês
                         reason = "N de M sentenças rejeitadas"
```

A divisão só corta depois de `.`/`!`/`?`, e um `⟦n⟧` só contém dígitos, então
nenhum corte cai dentro de um placeholder — há asserção e teste. Os
separadores são preservados, e `"".join(partes)` devolve a entrada caractere a
caractere.

Lotes são ordenados por comprimento antes de ir ao modelo, para reduzir
padding, e a ordem original é restaurada na saída (testado).

## Amostra

`tests/quality/sample.md` traz 30 traduções lado a lado, 4 delas mantidas em
inglês. A validação garante que a sintaxe sobreviveu, não que o português
esteja bom — e não está sempre: "Omit características" (verbo não traduzido),
"O daemon bifurca", "deixa cair o pacote". É um modelo de 2022 de propósito
geral, sem afinação para texto técnico.

## Arquivos

```
manbr/model.py        manbr/translate.py     manbr/glossary.txt
tests/test_model.py   tests/test_translate.py
tests/quality/measure_translate.py   tests/quality/sample.md
```

Os testes que exigem o modelo estão marcados `model` e são pulados sem ele; a
suíte roda inteira sem download. O fluxo de decisão — literal passa, tradução
rejeitada volta ao inglês, sentença ruim não derruba o parágrafo — é testado
com um tradutor falso, sem modelo.

Nota de ferramenta: `python_version` do mypy subiu para 3.12 porque
`import pytest` arrasta os stubs do numpy, que usam sintaxe de 3.12. O piso de
execução continua 3.11 e o pacote é verificado nele com
`mypy --python-version 3.11 manbr`.
