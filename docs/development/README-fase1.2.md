# manbr — Fase 1.2: recall a 97.8%, zero parciais

```
.venv/bin/pytest                         # 937 testes
.venv/bin/mypy                           # strict, limpo
.venv/bin/python tests/coverage/measure.py
```

## Números, lado a lado

| | fase 1.1 | fase 1.2 |
|---|---|---|
| tokens anotados | 186 | 189 |
| **cobertos** | 141 (75.8%) | **177 (93.7%)** |
| **parciais** | 6 (3.2%) | **0** |
| ausentes | 39 (21.0%) | 12 (6.3%) |
| candidatos a falso positivo | 0 | **0** |
| **recall, excluindo os intratáveis por forma** | 78.3% (141/180) | **97.8% (177/181)** |

Alvo era 90% com FP zero em prosa. **97.8%**, e as 86 linhas de prosa pura da
amostra continuam produzindo **zero** placeholders.

No corpus inteiro (3179 linhas), 1111 tokens mascarados contra 1026 na fase
1.1, e o round-trip continua exato.

### A correção de anotação, declarada

O denominador subiu de 186 para 189, e isso precisa ser dito com todas as
letras porque mexer na verdade-base depois de ver o resultado é exatamente
como se lava uma métrica.

Quando o padrão `chave=valor` entrou, `measure.py` acusou 3 candidatos a falso
positivo: `var=value` (awk), `name=content` e `%name=content` (curl). Não eram
falsos positivos — eram **buracos na anotação original**: eu tinha anotado 17
operandos da mesma classe (`conv=CONVS`, `time=TIME`, `pid=`, `PARTUUID=uuid`)
e deixado esses três de fora por inconsistência minha, não por regra. A regra
declarada em `annotated.tsv` sempre incluiu a classe.

Os três foram anotados, com a correção registrada em comentário no próprio
`annotated.tsv`. Para não esconder nada, os dois números:

- **com a anotação congelada da fase 1.1** (186 tokens): 172 cobertos,
  **92.5%**, 0 parciais, 3 candidatos a FP
- **com a anotação corrigida** (189 tokens): 177 cobertos, **93.7%**,
  0 parciais, 0 candidatos a FP

Os dois passam de 90%. A correção mudou o recall em 1.2 pp; o resultado não
depende dela.

## Prioridade 1 — os 6 parciais: todos fechados

Nenhum era irredutível. O padrão da fase 1.1 se manteve: cada parcial tinha
solução.

| parcial | o que sobrava | como fechou |
|---|---|---|
| `https://download.samba.org/...` | `https://` | padrão de URL com esquema |
| `http://example.com/archive[...]/...` | esquema e colchetes | idem, escopo até whitespace |
| `--script-help=<Lua scripts>` | ` scripts>` | valor de flag longa aceita `<...>` com espaço |
| `knuth.cwi.nl:/dir` | o `:` | novo padrão `host:caminho` |
| `/dev/disk/by-{label,uuid,...}` | a expansão em chaves | sufixo `{...}` no padrão de caminho |
| `-c[color][={always\|auto\|never}` | tudo depois de `-c` | sufixo `[...]`/`{...}` na flag curta |

Dois detalhes que só apareceram porque havia teste:

- **`-PO[protocol list]`.** A primeira versão do sufixo colchetado aceitava
  colchete sem fechar, e transformava `-PO` num parcial novo: mascarava
  `-PO[protocol` e deixava `" list]"` exposto. Agora o grupo precisa fechar e
  não pode ter espaço dentro; o ramo em chaves cobre separadamente o
  `[={always|auto|never}` da ip(8), que a página realmente escreve sem fechar
  o colchete.
- **`{_SEG}?` era um bug de quantificador.** Colar `?` na string de `_SEG`
  aplica o `?` ao último elemento dela, virando `(?:...)??` — lazy. O padrão
  `host:caminho` casava `knuth.cwi.nl:/d` em vez de `knuth.cwi.nl:/dir`. Só
  aparece quando o segmento tem mais de um caractere; por isso `a.b.nl:/x`
  passava e `/dir` não. Corrigido com `(?:{_SEG})?`.

## Prioridade 2 — URLs e esquemas

`\b[a-z][a-z0-9+.-]*://[^\s"'`<>]*(?<![.,;:])`

O esquema entra no placeholder por decisão, não por acaso: deixar `https://`
de fora é a mesma falha pela metade de `~/.ssh/config`. O lookbehind final
devolve pontuação de fim de frase, e as aspas ficam de fora do token.

Efeito colateral bom: `http://[fe80::3%25eth0]/` (curl) agora é um token só,
onde antes o `fe80::3` era mascarado sozinho pelo ramo IPv6 e o resto da URL
ficava exposto.

## Prioridade 3 — `chave=valor`

`(?<![\w.=-])%?[A-Za-z_][\w.-]*=[^\s,;)\]}'"]*(?<!\.)`

As duas verificações pedidas:

- **Prosa com sinal de igual.** O `=` tem de estar colado no nome, sem espaço.
  `a = b`, `o resultado = 4`, `se x = y então` não casam — há teste para os
  três. Prosa com `x=y` colado praticamente não existe; nas 200 linhas da
  amostra e nas 3179 do corpus não apareceu nenhum caso.
- **Precedência sobre a flag longa.** `--flag=valor` é resolvido pela regra 6,
  que casa mais à esquerda (no `-`) e consome tudo. `--reference=RFILE` e
  `--file=script-file` continuam saindo como um token só; há teste.

O `%?` inicial cobre `--variable %name=content` da curl: sem ele o sigilo `%`
ficava exposto e o resto virava placeholder — parcial.

O valor para na vírgula (`c=1, w=2, b=512` são três tokens, não um) e devolve
`)`, `]`, `;`, aspas e o ponto final da frase.

## Prioridade 4 — `extensions.txt`

O limite `[a-z]{2,6}` saiu; entrou `manbr/extensions.txt`, com 101 entradas,
lido em tempo de import. A lista tem tudo que a fase 1.2 pediu, mais os
sufixos que já estavam em uso no corpus (`com`, `org`, `nl`, `html`, `image`,
`out`) — sem eles, trocar o limite pela lista teria quebrado todo domínio.
Verifiquei a troca comparando cobertura por caractere antes e depois em todo o
corpus: nenhum token da fase 1.1 perdeu cobertura, exceto duas vírgulas e um
dois-pontos de fim de token que agora ficam de fora, o que é melhoria.

**`e.g.` e `i.e.` continuam fora, e o mecanismo mudou.** Antes era o limite
inferior do `{2,6}` que os salvava. Agora é uma regra explícita: *nenhuma
extensão de uma letra*. `_load_extensions` levanta `ValueError` se alguém
adicionar uma, e há teste tanto para a invariante quanto para `e.g.`/`i.e.`
diretamente. Globs como `*.c` não dependem da lista — têm padrão próprio, com
o asterisco como marca.

## Três acréscimos fora das quatro prioridades

Pequenos, não frágeis, e fecharam 3 ausentes. Registro por transparência:

- **Glob `*.ext`** (`\*\.[\w-]+`). O asterisco identifica a forma sozinho.
  Aparece em `--exclude='*.log'`, `(*.c)`.
- **Flag começando com dígito, desde que contenha uma letra.** Fecha o pacote
  `-46AaCfGgKkMNnqsTtVvXxYy` da ssh sem abrir a porta para `-1` em prosa
  ("a NUM of -1 is"), `-4`, `1-1024` ou `2012-10-30` — todos testados.
- **`./` e `../` sozinhos**, que a find documenta como sintaxe.

## Parciais remanescentes

**Nenhum.** É o resultado que mais importa desta fase: não há mais nenhum
token na amostra que pareça protegido sem estar.

## Ausentes remanescentes — 12

### Intratáveis por forma — 8, vão para `segment.py`

Não têm nenhuma marca que os separe de prosa. Perseguir qualquer um deles por
regex custa falso positivo em texto corrido, que é o que esta fase manteve em
zero. O caminho é reconhecimento de bloco de código na fase 2, que protege a
linha inteira em vez de token a token.

| token | onde | por que não dá |
|---|---|---|
| `-` | awk:58, chmod:29 | opção stdin e operador de modo. Casar hífen isolado é casar todo travessão de prosa |
| `\` | awk:127, ip:75 | barra invertida citada no meio de uma frase |
| `\n` | awk:75 | idem |
| `\{{` | curl:91 | idem |
| `[ugoa]*([-+=]([rwxXst]*\|[ugo]))+\|[-+=][0-7]+` | chmod:120 | gramática BNF do modo |
| `{{fix:trim:url}}` | curl:122 | sintaxe de template da curl |

### Tratáveis, deixados de fora — 4

Cada um tem solução conhecida e um custo que não quis pagar nesta fase:

- **`<port ranges>`** (nmap:126). O interior do bloco angular proíbe espaço, e
  é essa proibição que segura `a < b > c` em prosa. Conflito real: não dá para
  ter os dois sem olhar contexto.
- **`refs/remotes/`** (git-log:58). Caminho relativo sem prefixo. Casar
  `palavra/palavra` traria `and/or`, `TCP/IP` e `24/7` junto — já documentado
  desde a fase 1.
- **`log.excludeDecoration`** (git-log:72). Chave de configuração do git; o
  último rótulo tem maiúscula e não é extensão. Aceitar rótulo final
  arbitrário transformaria o padrão de nome pontuado em "qualquer
  palavra.palavra", que é prosa.
- **`[DD-]hh:mm:ss`** (ps:31). Especificação de formato; a forma é
  indistinguível de um intervalo em prosa.

## Sobre o falso positivo do `--`

Mantido como está, conforme decidido. `--` como travessão em prosa
(`find.txt:41`, `nmap.txt:108`) vira placeholder e fica sem traduzir; em troca
o `--` de fim de opções da `awk.txt:41` não se perde. Pela assimetria de custo
declarada na fase 1 — mascarar demais custa qualidade, mascarar de menos custa
correção — o troco vale. Sem tentativa de distinguir por contexto nesta fase.

Um segundo caso da mesma natureza: `::` em `"a double colon (::) separator"`
(rsync) casa pelo ramo IPv6 e fica sem traduzir. Em `HOST::SRC`, na mesma
página, o mesmo casamento está certo — ali o `::` é o separador de daemon do
rsync.

## Nota para a fase 2

`curl.txt:98` mostra um problema que não é de `mask.py`: a linha termina em
`%name=con‐` com um hífen tipográfico U+2010, e `tent` está na linha seguinte.
O token está partido pela hifenização da man page. `mask` faz o que pode com o
que recebe; juntar linhas hifenizadas antes de mascarar é trabalho de
`segment.py`.

## Arquivos novos

```
manbr/extensions.txt              # 101 extensões e sufixos de unit, editável
```

`measure.py`, `build_sample.py`, `sample.tsv` e `annotated.tsv` seguem como na
fase 1.1. Nenhum teste fixa limiar de recall; `test_coverage_harness.py`
continua garantindo só que a amostra e a anotação estão sincronizadas com o
corpus.
