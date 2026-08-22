# babelt — Fase 7: distribuição

```
PYTHONPATH=. .venv/bin/pytest                 # 1392 testes
PYTHONPATH=. .venv/bin/pytest -m 'not model'  # 1385, o que o CI roda
PYTHONPATH=. .venv/bin/mypy                   # strict, limpo
babelt doctor                                  # diagnóstico da instalação
```

`PIPELINE_VERSION` **não** mudou: nada nesta fase toca o texto. O cache da
0.3.0 continua válido.

## Parte A — omissão de primeira palavra: **medida e recusada**

A hipótese: 22 das 24 omissões rotuladas na fase 6 perderam a primeira palavra
do segmento, então detectar essa perda pegaria a maioria delas.

Ela é verdadeira e inútil, porque a recíproca não vale: **tradução legítima
também "perde" a primeira palavra — traduzindo-a.**

| variante | rejeita | omissões pegas | **precisão** |
|---|---|---|---|
| V1: primeira palavra de conteúdo some | 614 de 773 (79,4%) | 22 | **3,6%** |
| V2: só quando parece identificador¹ | 16 | 3 | **19%** |
| V3: só quando é MAIÚSCULA | 12 | 2 | **17%** |

¹ "parece identificador" = o tokenizer parte a palavra em mais de duas peças.
Palavra inglesa comum é uma peça só; `mroute`, `fsync`, `tfidf` são várias.

A barra era superar claramente os 60% da parte B da fase 6. **A melhor
variante fez 19%.** Não foi implementada.

Os falsos positivos dizem por quê:

```
[Disables]  EN -a Disables forwarding of the authentication agent
            PT -a Desativa o encaminhamento do agente de autenticação
[PASSED]    EN PASSED shows how long has passed since the timer last ran
            PT PASSADO mostra quanto tempo se passou desde que o temporizador
```

Nos dois casos a primeira palavra sumiu **porque foi traduzida**, que é o
trabalho. Nenhuma regra do lado da saída distingue isso de omissão sem saber o
que a palavra deveria virar — e se soubesse, seria um tradutor, não uma
validação.

### O que a medição encontrou de novo

Entre os falsos positivos da V3 aparece outra classe, que não é omissão e é
pior que ela:

```
EN  NEXT shows the next time the timer will run.
PT  A próxima mostra a próxima vez que o temporizador vai rodar.

EN  LEFT shows how long till the next time the timer runs
PT  A esquerda mostra quanto tempo até a próxima vez
```

`NEXT` e `LEFT` são **nomes de coluna** da saída de `systemctl list-timers`.
Foram traduzidos, e a contagem de palavras bateu — então a regra de cobertura
de conteúdo da fase 6 também não pegaria. O defeito não é perder palavra: é
**traduzir identificador**, e nenhuma regra do lado da saída o vê, porque a
saída está bem formada.

Isso reforça a conclusão da fase 6 por outro caminho: o conserto é do lado da
entrada, mascarando pela **posição** — primeira palavra de descrição pendurada
—, não do lado da saída.

## Parte B — `model.py` sem torch

Antes: `download()` chamava `ct2-transformers-converter`, e `transformers` +
`torch` estavam em `dependencies`. Cerca de **2 GB de dependência** para uma
conversão que sempre produz o mesmo resultado.

Agora a conversão acontece uma vez, em `scripts/build-model.sh`, por quem
publica. O usuário baixa o `tar.gz` já convertido.

| | antes | depois |
|---|---|---|
| `pip install babelt` puxa | ctranslate2, sentencepiece, huggingface-hub, **transformers, torch** | ctranslate2, sentencepiece |
| primeira execução | baixa pesos e converte na máquina | baixa artefato pronto |
| confiança | "a sua máquina converte certo" | "este arquivo é este hash" |

O SHA-256 é conferido **antes de qualquer extração**, e um artefato que não
bata é apagado sem ser aberto — deixá-lo no disco convidaria a próxima
execução a reusá-lo, e um arquivo com hash errado é ou corrupção de rede ou
coisa pior. A extração usa `filter="data"`, que recusa link, dispositivo e
caminho com `..`; há teste que tenta escapar do destino e falha.

A instalação continua atômica: extrai num irmão do destino e só então
`os.replace`. Se outro processo instalou primeiro, o nosso trabalho é
descartado em vez de sobrescrever.

`huggingface-hub` saiu de `dependencies` e foi para `convert`, junto de
`transformers` e `torch`: só o script de build usa.

### Enquanto a URL não existe

`MODEL_URL` e `MODEL_SHA256` estão com `PREENCHER`. Nesse estado `download()`
**não tenta baixar** — falha imediatamente com a instrução de rodar
`build-model.sh` ou apontar `--model-path` para um modelo já convertido. É
melhor que uma falha de rede confusa, e há teste.

## Parte C — `babelt doctor`

Subcomando, não flag: não modifica uma tradução, substitui a execução. Roda
antes de qualquer leitura de entrada, porque diagnosticar uma instalação
quebrada não pode depender de ela funcionar.

```
$ babelt doctor
ok    babelt                      0.4.0
ok    versão de pipeline         4
ok    modelo                     /home/…/babelt/models/en-pt (227 MiB)
aviso modelo: proveniência       sem meta.json — não dá para saber de onde veio
ok    cache                      /home/…/.cache/babelt — 123 entradas, 16 KiB
aviso cache: versão de pipeline  entradas gravadas na versão 3, o programa está
                                 na 4 — elas nunca mais serão lidas e podem ser
                                 apagadas (`rm -rf …`)
ok    ctranslate2                4.8.1
ok    sentencepiece              0.2.2
ok    man                        /usr/bin/man
```

A distinção que o código de saída carrega é **impedimento contra aviso**:
modelo ausente e biblioteca que não importa bloqueiam (exit 1); cache
obsoleto, `meta.json` faltando e `man` fora do PATH são avisos (exit 0) —
o programa funciona, só não do jeito completo.

Os dois avisos acima são reais, colhidos nesta máquina: o cache local ficou na
versão 3 depois do bump da fase 6, e o modelo aqui foi convertido à mão, antes
de `build-model.sh` existir.

Tudo vai para **stderr**, como todo o resto que não é tradução.

## Parte D — higiene

`git ls-files` está limpo: **nenhum** dos 81 arquivos rastreados é ambiente,
build, bytecode, cache ou modelo. Não houve nada a remover.

`.gitignore` ganhou `.mypy_cache/`, `.ruff_cache/` e `.eggs/`, que faltavam.

As URLs do `pyproject.toml` apontavam para `github.com/babelt/babelt`, que não
existe. Foram trocadas pelo remote real deste repositório,
`github.com/ONiceasNeto/babelt` — não é placeholder, é o `origin` configurado
aqui. Se o projeto mudar de nome ou de dono antes de publicar, estas três
linhas e o `MODEL_URL` mudam junto.

## Parte E — CI

`.github/workflows/ci.yml`: `pytest -m "not model"` e `mypy` (strict, mais uma
passada no piso 3.11) em push e PR, Python 3.12, sem baixar modelo. São os
1385 testes que não precisam de pesos; os 7 que precisam ficam de fora pela
marca criada na fase 4 exatamente para isto.

## Pendente, e é seu

Três coisas que dependem de você e não de código:

1. **Gerar o artefato**: `pip install 'babelt[convert]' && ./scripts/build-model.sh`.
   Sai um `dist/babelt-model-en-pt-int8.tar.gz` com `meta.json` e `NOTICE`
   dentro, e o script imprime o SHA-256.
2. **Publicar o artefato** (GitHub Releases é o caminho mais direto) e
   **preencher `MODEL_URL` e `MODEL_SHA256`** em `babelt/model.py`.
3. **Publicar o pacote** no PyPI, e o PKGBUILD no AUR se for por aí.

O `TODO.md` na raiz tem esses itens e os demais; nenhum foi marcado.

## O que ficou fora

- **Retomada de download.** `_fetch` baixa do zero se cair no meio. Um
  `Range:` resolveria, mas exige o servidor cooperar e um arquivo parcial no
  disco — que é justamente o que a fase evita ter.
- **Espelho ou fallback de URL.** Uma URL só, um ponto de falha.
- **`babelt doctor --fix`.** Ele diz que o cache está obsoleto e qual comando
  apaga; não apaga. Apagar coisa do usuário sem ele pedir é outro assunto.
