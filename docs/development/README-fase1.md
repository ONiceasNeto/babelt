# manbr — Fase 1: masking e validação

Implementa `manbr/mask.py` e `manbr/validate.py`. Sem tradução, CLI, cache ou
empacotamento — só a garantia de que nenhuma tradução futura pode corromper
sintaxe de comando.

```
python -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pytest      # 210 testes
.venv/bin/mypy        # strict, limpo
```

## O viés de projeto

As duas falhas não custam a mesma coisa:

- **Mascarar demais** (falso positivo) custa qualidade: um trecho de prosa
  fica em inglês. Chato, reversível, visível.
- **Mascarar de menos** (falso negativo) custa correção: uma flag exposta ao
  modelo pode ser traduzida ou perdida, e o usuário copia um comando inválido.

Todo empate nas regex foi resolvido a favor de mascarar. E nenhuma regex é
tratada como garantia: a garantia é `validate`, que rejeita por contagem de
placeholders, sem depender de nada ter sido reconhecido corretamente.

## Falsos positivos que não consegui eliminar

Nenhum destes corrompe nada — só deixa texto sem traduzir.

1. **Alternância em prosa com barra depois de pontuação.**
   Em `TCP SYN/Connect()/ACK/Window/Maimon scans` (nmap), o trecho
   `/ACK/Window/Maimon` vira um caminho. O lookbehind `(?<![\w/])` bloqueia
   `SYN/Connect`, mas o `)` antes de `/ACK` não é `\w`, então o padrão 6
   dispara. Distinguir `/ACK/Window` de `/usr/share` exigiria conhecer os
   nomes reais dos diretórios; não dá por forma.

2. **Palavras coladas por ponto sem espaço.** `leia isso.no arquivo` vira
   `leia ⟦0⟧ arquivo`. O padrão 7 não tem como saber se `isso.no` é um
   domínio `.no` (Noruega) ou um erro de digitação. Frases coladas com
   maiúscula (`termina.Assim`) escapam porque o sufixo exige `[a-z]{2,6}`.

3. **Palavras com ponto que são sintaxe de linguagem.** `obj.get`,
   `foo.bar()` viram placeholders. No contexto (man pages) isso quase sempre
   é desejável, mas em prosa comum seria ruído.

4. **Flags de um traço que são palavras.** `-family`, `-follow`, `-batch`
   (find, ip) são flags reais nessas páginas, mas a mesma forma apareceria em
   texto que use um travessão colado numa palavra. Não achei nenhum caso no
   corpus real, e o lookbehind já cobre o caso comum (`well-known`).

Falsos positivos que **estão** eliminados e têm teste: `well-known`,
`read-only`, `1-1024`, `1/2`, `and/or`, `TCP/IP`, `24/7`, `e.g.`, `i.e.`,
`1.2.3`, `A-Z`, `-` isolado, `/` isolado, `- item de lista`, `R$5`.

## Falsos negativos conhecidos (mais graves que os acima)

Estes deixam sintaxe exposta ao modelo. Nenhum é coberto pelos padrões
especificados; todos ficam para uma fase futura.

1. **`--` sozinho** (fim de opções). O padrão 4 exige `[A-Za-z]` depois dos
   traços. Um `--` traduzido ou perdido muda o significado do comando.
   É o mais importante da lista.
2. **Endereços IP e CIDR**: `192.168.1.1`, `10.0.0.0/16` não casam com nada.
   Baixo risco (são dígitos), mas nada garante.
3. **`$1`, `$$`, `$@`**: o padrão 3 exige `[A-Za-z_]` depois do `$`.
4. **Scripts sed / expressões com barra**: `s/regexp/replacement/` não casa,
   porque o `/` vem depois de `\w`. Bloquear a fração `1/2` e casar `s/x/y/`
   são requisitos incompatíveis nesse formato.
5. **Metassintaxe angular não alfabética**: `-T<0-5>` mascara só `-T`;
   `<n1=v1,[n2=v2,...]>` não casa (padrão 2 aceita só `[\w.-]` dentro).
6. **`-sS/sT/sA`**: mascara só `-sS`; o resto fica exposto.
7. **Caminhos relativos sem prefixo**: `lib/util.c` não casa. Casar exigiria
   aceitar `palavra/palavra`, o que traria `and/or` junto.

## Decisões de regex frágeis, e por quê

- **Precedência por alternância única.** Os sete padrões viram uma alternação
  só, e a precedência vem da ordem dentro dela. Isso depende do `re` do
  Python resolver alternativas na ordem escrita, na posição mais à esquerda.
  É comportamento documentado e estável, mas é uma dependência implícita: se
  alguém reordenar `_PATTERNS` por estética, crases deixam de ter precedência
  sobre caminhos e `` `cat /etc/passwd` `` vira três placeholders.

- **Segmento de caminho que não termina em ponto.**
  `\.?[\w@-](?:[\w.@-]*[\w@-])?` existe só para que `veja /dev/null.` não
  engula o ponto final da frase. Custa legibilidade e depende de backtracking
  para casos como `/var/log/`. Um `[\w.@-]+` simples seria mais claro e
  erraria a pontuação.

- **`[a-z]{2,6}` no padrão 7.** O limite superior 6 é arbitrário e já é curto
  demais: `.software`, `.technology` não casam. Aumentar aumenta os falsos
  positivos com prosa colada. O limite inferior 2 é o que salva `e.g.` e
  `i.e.` — e é a única coisa que os salva.

- **Domínios de vários rótulos.** Estendi o padrão 7 da spec de
  `\b[\w-]+\.[a-z]{2,6}\b` para `\b[\w-]+(?:\.[\w-]+)*\.[a-z]{2,6}\b`. Com a
  forma original, `scanme.nmap.org` mascarava só `scanme.nmap` e deixava
  `.org` exposto — mascarar pela metade é a pior das saídas, porque parece
  protegido e não está. Mesma razão para `backup.tar.gz`.

- **`~/` no padrão 6.** Também uma extensão da spec. `~/.ssh/config` mascarava
  só `/.ssh/config`, deixando o til de fora; um til perdido muda o caminho.
  `~` sozinho continua sendo prosa.

- **Lookbehind de largura fixa.** `(?<![\w-])` só funciona porque tem um
  caractere. Qualquer condição mais rica (por exemplo "não precedido por uma
  palavra em inglês") exigiria trocar a estratégia por um scanner manual.

- **Crase sem par.** `` `[^`\n]+` `` não atravessa linha, então uma crase
  solta não engole o resto do parágrafo. Mas a spec manda `mask` operar sobre
  texto já segmentado; se a fase 2 segmentar por sentença em vez de por linha,
  uma crase que abre numa linha e fecha noutra deixa de ser reconhecida.

- **`(?:=\S+)?` no padrão 4.** `\S+` é ganancioso e vai até o próximo espaço.
  Em `--exclude='*.log' -czf`, o valor entre aspas é capturado inteiro (bom),
  mas se um valor citado contiver espaço (`--opt='a b'`), a captura para no
  espaço e deixa ` b'` exposto.

## Escape de ⟦ ⟧

Por duplicação: `⟦` → `⟦⟦`, `⟧` → `⟧⟧`, resolvido da esquerda para a direita.
Um `⟦0⟧` literal no texto de origem vira `⟦⟦0⟧⟧` e não é confundido com
placeholder. `validate` descarta os pares escapados antes de contar, então
`⟦⟦` não é reportado como placeholder malformado.

Terminal ASCII não produz esses caracteres, então o caminho de escape quase
nunca roda em produção — mas é ele que impede que um texto malicioso ou
inesperado injete placeholders falsos.

## Ordem das regras em `validate`

Vazio → malformado → índice inesperado → ausente/duplicado → razão de
comprimento. A ordem é escolhida por qualidade de diagnóstico: se o modelo
devolveu `⟦0` quebrado, `"placeholder malformado"` é mais útil que
`"placeholder 0 ausente"`, que é a consequência. Reordenar placeholders é
explicitamente permitido — inglês e português não têm a mesma ordem de
palavras.

Razão de comprimento com `original_masked` vazio é pulada em vez de dividir
por zero; a regra 3 já garantiu que a tradução não é vazia.

## Corpus

`tests/corpus/` tem 20 páginas reais (3179 linhas, 1012 tokens mascarados),
geradas por `refresh.sh` num Ubuntu 24.04 com `man ... | col -bx`. Inclui
hífen tipográfico U+2010 da hifenização de fim de linha, travessões e bullets
— entrada não-ASCII que o round-trip precisa preservar.

`refresh.sh` regenera tudo ou só as páginas nomeadas (`./refresh.sh tar find`)
e preserva o arquivo antigo quando a página não existe na máquina.
