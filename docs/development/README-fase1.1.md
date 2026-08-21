# manbr — Fase 1.1: falsos negativos e cobertura medida

```
.venv/bin/pytest                        # 854 testes
.venv/bin/mypy                          # strict, limpo
.venv/bin/python tests/coverage/measure.py
```

## Os números

Amostra de 200 linhas, estratificada sobre os 20 arquivos do corpus
(8 linhas com sintaxe + 2 de prosa pura por arquivo, espaçadas ao longo do
arquivo para pegar SYNOPSIS, OPTIONS, FILES e EXAMPLES). Anotação manual em
`tests/coverage/annotated.tsv`: **186 tokens**.

| métrica | valor |
|---|---|
| **recall** | **75.8%** (141/186) |
| parciais — parte do token exposta | 3.2% (6/186) |
| ausentes — nada mascarado | 21.0% (39/186) |
| candidatos a falso positivo | **0** |

Zero falso positivo não é um artefato de anotação frouxa: das 200 linhas, 86
não têm nenhuma anotação (são prosa), e `mask` não produziu **nenhum**
placeholder em nenhuma delas. O viés declarado na fase 1 — na dúvida,
mascarar — não está sendo pago em ruído nesta amostra. Está sobrando margem
para ser mais agressivo.

### Como a cobertura é medida

Por caractere, não por igualdade de string. Um token anotado conta como
coberto quando **cada caractere dele** cai dentro de algum placeholder. Três
consequências que importam:

- `$HOME/.secret` conta como coberto mesmo se `mask` o partir em dois
  placeholders adjacentes — nada ficou exposto.
- `https://download.samba.org/pub/...` conta como **parcial**, porque o
  `https://` sobrou de fora. Parcial é uma categoria separada de ausente, e é
  a mais grave das duas: parece protegido e não está.
- Todas as ocorrências do token na linha precisam estar cobertas. Mascarar o
  primeiro `-L` da linha e deixar o segundo exposto não é proteção.

Ocorrências são casadas com fronteira de palavra (`[A-Za-z0-9_-]` dos dois
lados). Sem isso, o `-f` anotado em `-f script-file` também casaria dentro de
`script-file` e de `--file`, e o veredito viraria artefato da medição — foi
exatamente o que aconteceu na primeira rodada, que reportou 74.7% em vez de
75.3%.

A seleção da amostra é de propósito **independente de `mask`**: o critério é a
presença de caracteres de sintaxe (`build_sample.py`), nunca "as linhas onde
mask encontrou algo". Selecionar pelo resultado daria recall 100% por
construção.

### O que a medição já pagou

Duas correções saíram da medição, não da leitura de regex:

- **`$HOME/.secret` mascarava só `$HOME`.** O lookbehind `(?<![\w/])` do
  padrão de caminho barra a `/` colada no `E` de `$HOME`, então `/.secret`
  ficava exposto. Variáveis agora absorvem o caminho que as segue. (+0.5 pp)
- **`-g/tmp/snar.db` mascarava só `-g/tmp/snar`**, porque o segmento de
  alternativa de flag não aceitava ponto. Achado pelo teste dedicado da
  Parte A, antes da medição. (Não entra no recall; a linha não caiu na
  amostra.)

## Parte A — os três falsos negativos críticos

Todos fechados, com teste dedicado (`TestFimDeOpcoes`,
`TestFlagsComAlternativas`, `TestEnderecosIP`).

1. **`--` isolado.** Novo padrão entre as flags longas e as curtas, com
   `(?![\w-])` para não casar `--flag` nem a régua `----` de algumas páginas.
2. **`-sS/sT/sA`.** O padrão de flag curta ganhou um sufixo `(?:/alt)*`. A
   alternativa exige letra inicial (para não casar a fração de `-x/2`) e
   nunca termina em ponto (para não engolir a pontuação final da frase).
   Cobre também `-R/-r`, `-PS/PA/PU/PY` e o `-g/tmp/snar.db` da tar, em que o
   valor vem colado na flag.
3. **IPs e CIDR.** Precedência acima de caminhos, senão o `/24` de
   `192.168.0.0/24` não entraria no placeholder. O ramo IPv6 exige `::` ou os
   8 grupos completos — sem isso, `18:17:16` (hora) e `aa:bb:cc:dd:ee:ff`
   (MAC) casariam.

## Parte B — implementados, com uma exclusão

Os três foram avaliados e implementados, nenhum introduziu falso positivo na
amostra. As restrições que cada um carrega:

**`$1`, `$@`, `$$`, `$?` — implementado com um lookbehind.**
O ramo dos especiais é `(?<![A-Za-z])\$(?:\d+|[@*#?!$])`. Sem o lookbehind,
`US$100` viraria `US` + `⟦0⟧` — mascaramento pela metade, a pior das saídas.
Com ele, um `$` colado numa letra é lido como moeda e fica de fora, e
`$1` depois de espaço, `(` ou aspas é lido como campo do awk. A alternativa
seria escolher entre proteger `$1` e não partir `US$100`; o lookbehind dá os
dois.

**`<n1=v1,n2=v2>` — implementado alargando o interior para `[^<>\s]*`.**
A proibição de espaço é o que segura o falso positivo: sem ela, qualquer
comparação em prosa (`a < b > c`) viraria placeholder. Efeito colateral bom:
URLs e e-mails entre `<>` (`<https://www.gnu.org/software/sed/>`,
`<bug-sed@gnu.org>`) passaram a ser mascarados inteiros — 10 ocorrências no
corpus real.

**`s/re/rep/` — implementado só com o delimitador `/`.**
`s|a|b|`, `s#a#b#`, `s,a,b,` ficaram **de fora**, e é a exclusão desta fase.
Razão: o delimitador do sed é qualquer caractere, então reconhecer a forma
geral significa casar `X<qualquer><corpo><qualquer><corpo><qualquer>`. Com
`|` e `,` como delimitadores candidatos, isso casa dentro de prosa comum e
dentro de listas separadas por vírgula (`euser,ruser,suser,fuser`), que
aparecem à vontade nas man pages. O ganho é hipotético — não há uma única
ocorrência de delimitador alternativo nas 3179 linhas do corpus — e o custo é
uma classe de falso positivo em texto corrido. Fica fora até que apareça
evidência de que é necessário.

A forma com `/` é segura pelo lookbehind `(?<![\w/])`: no corpus real ele
barra corretamente `refs/heads/`, `/sys/module/fuse` e `options/flags`, que
seriam os falsos positivos óbvios.

## Falsos negativos remanescentes, por severidade

Severidade = chance de o modelo realmente estragar o token × consequência de
estragar. Contagens sobre os 186 anotados.

### 1. Mascaramento parcial — 6 tokens (3.2%)

A classe mais grave, porque o placeholder dá a impressão de que a linha está
protegida.

| token | o que sobra exposto |
|---|---|
| `https://download.samba.org/pub/rsync/rsync.1` | `https://` |
| `http://example.com/archive[1996-1999]/vol[1-4]/part{a,b,c}.html` | o esquema e os colchetes |
| `--script-help=<Lua scripts>` | ` scripts>` — o `\S+` do valor para no espaço |
| `knuth.cwi.nl:/dir` | o `:` entre o host e o caminho |
| `/dev/disk/by-{label,uuid,id,...}` | a expansão em chaves |
| `-c[color][={always\|auto\|never}` | tudo depois de `-c` |

Três dessas (`{...}`, `[...]`, `:` entre host e caminho) são a mesma coisa: os
padrões de caminho e de nome param no primeiro caractere que não seja de
palavra, e a sintaxe de shell continua depois dele.

### 2. Operandos `chave=valor` — 17 tokens (9.1%)

`conv=CONVS`, `oflag=sync`, `c=1`, `K=1024`, `time=TIME`, `pid=`,
`PARTUUID=uuid`, `Storage=`. Nenhum padrão os alcança: só a flag longa aceita
`=`, e essas não têm hífen. É de longe a maior classe isolada e a de correção
mais barata — um padrão `\b[A-Za-z_][\w-]*=[^\s,]*` levaria o recall de 75.8%
para ~84.9%. O risco de falso positivo é baixo (prosa quase nunca tem `=` sem
espaço em volta), mas não foi implementado: a Parte C foi definida como
medição, e o limiar e as correções ficaram para depois de ver os números.
**É a recomendação número um para a fase 2.**

### 3. Sufixo de mais de 6 letras — 3 tokens (1.6%)

`systemd-initctl.service` e companhia não são mascarados porque `.service` tem
7 letras e o padrão termina em `[a-z]{2,6}`. `.timer`, `.socket`, `.device`,
`.path`, `.mount` e `.target` passam; `.service` e `.automount` não. É a
fragilidade que a fase 1 já tinha apontado como arbitrária, agora com número:
subir o limite para `{2,9}` resolve as três, ao custo de casar mais prosa
colada por ponto sem espaço.

### 4. URLs e esquemas — 3 ausentes + 2 parciais (2.7%)

`protocol://`, `rsync://`, `http://site.{one,two,three}.com`. Severidade alta
apesar da contagem baixa: uma URL é feita de palavras em inglês
(`download`, `software`, `archive`), que é exatamente o que um modelo NMT
traduz com gosto. Um padrão de esquema (`\b[a-z][a-z0-9+.-]*://\S*`) resolve
os cinco de uma vez e não tem como colidir com prosa.

### 5. Um token, uma causa — 8 tokens (4.3%)

- `<port ranges>` — o interior do bloco angular proíbe espaço, e é essa
  proibição que segura `a < b > c`. Conflito real: não dá para ter os dois
  sem olhar o contexto.
- `-46AaCfGgKkMNnqsTtVvXxYy` — o pacote de flags da ssh começa com dígito, e
  o padrão exige `[A-Za-z]` logo após o hífen. Trivial de relaxar; o único
  motivo de não ter relaxado é que `-4` e `-1` também aparecem como números
  em prosa ("a NUM of -1").
- `*.c` — glob. O `.c` tem uma letra só, abaixo do `{2,6}`.
- `./` sozinho, `refs/remotes/` — caminho relativo sem prefixo reconhecível.
  Já documentado na fase 1: casar `palavra/palavra` traria `and/or` junto.
- `log.excludeDecoration` — chave de configuração do git; o último rótulo tem
  maiúscula e o padrão exige `[a-z]`.
- `foo:src/bar/` — destino de rsync, mesma classe do `knuth.cwi.nl:/dir`.
- `[DD-]hh:mm:ss` — especificação de formato.

### 6. Intratáveis por forma — 8 tokens (4.3%)

Não têm nenhuma marca que os separe de prosa. Não recomendo persegui-los por
regex; se importarem, o caminho é reconhecimento de bloco de código na fase 2
(`segment.py`), que protege a linha inteira em vez de token a token.

- `-` sozinho como opção (stdin) e como operador de modo do chmod — 2. Casar
  um hífen isolado significaria casar todo travessão de prosa.
- `\n`, `\`, `\{{` — escapes citados no meio de uma frase — 4.
- `[ugoa]*([-+=]([rwxXst]*|[ugo]))+|[-+=][0-7]+` — a gramática de modo do
  chmod — 1.
- `{{fix:trim:url}}` — sintaxe de template da curl — 1.

## Fora do escopo da anotação

Declarado em `annotated.tsv` e vale registrar, porque muda o denominador:
**argumentos que são palavras nuas não foram anotados** — `posix` em
`-W posix`, `sync` em `conv=sync`, subcomandos como `list-unit-files`,
metavariáveis como `ARCHIVE`, `FILE`, `MODE`. Nenhuma marca de forma os separa
de prosa traduzível, então não são alvo do mascaramento por regex e anotá-los
mediria uma ambição que o projeto não tem nesta fase. Se essa classe importar,
ela também é problema de `segment.py`, não de `mask.py`.

Datas, horas e dados de exemplo dentro de blocos de saída também ficaram fora;
endereços (IP, host) dentro desses blocos foram anotados.

## Falsos positivos novos, introduzidos nesta fase

Zero na amostra medida, mas o corpus inteiro mostra um:

- **`--` como travessão em prosa.** `find.txt:41` ("ble dash -- could
  theoretically") e `nmap.txt:108` ("online -- skip host discovery") viram
  placeholder. Dos casos de `--` isolado no corpus, cerca de dois terços são
  travessão e não fim de opções. O custo é um travessão que fica sem traduzir;
  o benefício é não perder o `--` de `awk.txt:41`, que é fim de opções de
  verdade. Pela ordem de custo declarada na fase 1, o troco vale a pena.
- **`::` em `HOST::SRC`** (rsync) casa pelo ramo IPv6. Por acaso está certo:
  ali o `::` é o separador de daemon do rsync, sintaxe crítica. Em
  `"a double colon (::) separator"` é prosa, e fica sem traduzir.

## Arquivos

```
tests/coverage/
├── build_sample.py     # congela a amostra (critério independente de mask)
├── sample.tsv          # 200 linhas, com o texto embutido
├── annotated.tsv       # 186 tokens, anotação manual + regra de anotação
└── measure.py          # recall, parciais, ausentes, candidatos a FP
tests/test_coverage_harness.py   # guarda a medição, não fixa limiar
```

`sample.tsv` guarda o texto da linha, não só o número, para que a anotação
sobreviva a um `refresh.sh`. `test_amostra_bate_com_o_corpus` avisa quando o
corpus mudou debaixo da amostra.

Nenhum teste fixa limiar de recall: a fase 1.1 é medição.
