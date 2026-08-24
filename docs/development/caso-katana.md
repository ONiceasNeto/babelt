# babelt — `katana --help` através das fases 4, 5 e 6

Gerado com `babelt --help-of katana`, cache frio, beam 1. Nada foi retocado.

## Original

```
Katana is a fast crawler focused on execution in automation pipelines offering both headless and non-headless crawling.

Usage:
  katana [flags]

Flags:
INPUT:
   -u, -list string[]     target url / list to crawl
   -resume string         resume scan using resume.cfg
   -e, -exclude string[]  exclude host matching specified filter ('cdn', 'private-ips', cidr, ip, regex)

CONFIGURATION:
```

## Antes (fase 4)

```
Katana é um crawler rápido focado na execução em pipelines de automação que
oferecem rastreamento sem cabeça e sem cabeça.

Uso:
  katana [band]

flags: INPUT:
   -u, -list string[] target url / list to crawl -resume string resume scan
   using resume.cfg -e, -exclude string[] exclude host matching specified filter
   ('cdn', 'private-ips', cidr, ip, regex)

CONFIGURATION:
```

Três defeitos, e os três aparecem nestas doze linhas:

1. **`katana [flags]` virou `katana [band]`.** O grupo entre colchetes não era
   mascarado quando aparecia solto, então "flags" chegou ao modelo como
   palavra comum e voltou traduzido. Um comando que o leitor copiaria e que
   não existe.
2. **A tabela de flags virou um parágrafo.** As linhas foram agrupadas por
   indentação num segmento PROSE só; o modelo devolveu prosa corrida e a
   requebra da fase 4 espalhou o resultado pela largura da página. A coluna da
   esquerda — as flags — deixou de existir como coluna.
3. **`headless` e `non-headless` viraram "sem cabeça" e "sem cabeça".** A
   negação sumiu, e as duas metades da frase passaram a dizer a mesma coisa.

## Depois (fase 5)

```
Katana is a fast crawler focused on execution in automation pipelines offering
both headless and non-headless crawling.

Uso:
  katana [flags]

flags: INPUT:
   -u, -list string[]     url de destino / lista para rastrear
   -resume string         resume scan using resume.cfg
   -e, -exclude string[]  exclude host matching specified filter ('cdn',
                          'private-ips', cidr, ip, regex)
```

E o bloco `CONFIGURATION`, que é onde a diferença fica óbvia:

### Antes

```
   -r, -resolvers string[] list of custom resolver (file or comma separated) -d,
   -depth int maximum depth to crawl (default 3) -jc, -js-crawl enable endpoint
   parsing / crawling in javascript file -jsl, -jsluice enable jsluice parsing
   in javascript file (memory intensive) -ct, -crawl-duration value maximum
   duration to crawl the target for (s, m, h, d) (default s) -kf, -known-files
   value enable crawling of known files (all,robotstxt,sitemapxml), a minimum
   depth of 3 is required to ensure all known files are properly crawled. -mrs,
   -max-response-size int maximum response size to read (default 4194304)
   -timeout int time to wait for request in seconds (default 10) -time-stable
   int time to wait until the page is stable in seconds (default 1) -aff,
```

### Depois

```
   -r, -resolvers string[]              lista de resolvedor personalizado
                                        (arquivo ou vírgula separada)
   -d, -depth int                       profundidade máxima para rastejar
                                        (padrão 3)
   -jc, -js-crawl                       Activar a análise de endpoint /
                                        rastejando em arquivo javascript
   -jsl, -jsluice                       habilit jsluice parsing in javascript
                                        ficheiro (memória intensiva)
   -ct, -crawl-duration value           Duração máxima para rastrear o alvo para
                                        (s, m, h, d) (padrão s)
   -kf, -known-files value              Ativar o rastreamento de arquivos
                                        conhecidos (todos,robotstxt,sitemapxml),
                                        uma profundidade mínima de 3 é
                                        necessária para garantir que todos os
```

A coluna esquerda não vai ao modelo. Cada célula da direita é traduzida
sozinha, com o próprio lugar no cache, e a que não cabe na largura quebra
**dentro da própria coluna** — a continuação alinha na coluna, nunca invade a
esquerda.

## Depois da fase 6

```
Katana is a fast crawler focused on execution in automation pipelines offering
both headless and non-headless crawling.

Uso:
  katana [flags]

Opções:
ENTRADA:
   -u, -list string[]     url de destino / lista para rastrear
   -resume string         resume scan using resume.cfg
   -e, -exclude string[]  exclude host matching specified filter ('cdn',
                          'private-ips', cidr, ip, regex)
```

Duas correções da fase 6 aparecem nestas linhas: `Flags:` e `INPUT:` não estão
mais fundidas em `flags: INPUT:` — viraram `Opções:` e `ENTRADA:`, traduzidas
por tabela, cada uma na própria linha — e `CONFIGURATION:` virou
`CONFIGURAÇÃO:` pelo mesmo caminho.

## O que continua errado (medido na fase 5)

Vale registrar o que a fase não resolveu, porque está visível na mesma saída:

- ~~**`Flags:` e `INPUT:` saíram na mesma linha.**~~ Corrigido na fase 6, e
  exatamente por onde este parágrafo apontava: título de bloco virou cabeçalho,
  isolado no próprio segmento e traduzido por `headers.txt`.
- ~~**`all,robotstxt,sitemapxml` virou `todos,robotstxt,sitemapxml`.**~~
  Corrigido na fase 6: lista separada por vírgula virou padrão de
  mascaramento. Catorze casamentos nos dois corpora, zero em prosa.
- **"rastejar", "habilit jsluice parsing in javascript ficheiro".** Qualidade
  do modelo. Nenhuma regra desta fase mede fluência, e continua assim.
- **A primeira frase ficou em inglês.** É consequência direta de mascarar
  `headless`: o modelo derrubou os dois placeholders e a validação rejeitou o
  parágrafo. Inglês em vez de uma negação invertida — a troca é deliberada.
