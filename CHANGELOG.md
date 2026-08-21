# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).
Versionamento semântico.

## [0.2.0] — 2026-08-21

Saída de `--help` deixa de ser um caso degenerado.

### Adicionado

- `manbr --help-of <cmd>` executa `<cmd> --help` (depois `-h`, depois
  `--usage`) e traduz; `manbr --auto <cmd>` tenta `man` e cai para a ajuda
  quando não há página. Os dois executam o binário, com timeout e sem nenhum
  argumento além do flag de ajuda.
- Segmentação de tabela de duas colunas (`SegmentKind.COLUMNS`): a coluna
  esquerda passa intacta, cada célula da direita é traduzida sozinha e a
  requebra acontece dentro da própria coluna. É metade do conteúdo de um
  `--help` medido.
- Mascaramento de grupo isolado (`{action}`, `[flags]`), sufixo de tipo
  (`string[]`) e alternância solta (`yes|no`). Recall de 96,9% para 97,5%,
  com falso positivo em prosa ainda em 1.
- `manbr/literals.txt`: termos que nunca vão ao modelo, porque a tradução
  deles perde informação. Começa com `headless` e `non-headless`.
- Corpus de saída de `--help` em `tests/corpus/help/`, com `refresh-help.sh`.

### Corrigido

- `normalize` colapsava o intervalo de duas colunas quando ele tinha 2 ou 3
  espaços, tratando alinhamento de `--help` como justificação de man page.
- A profundidade de bloco contava o cabeçalho de seção, e por isso o segundo
  parágrafo de uma DESCRIPTION podia ser classificado como literal.

### Mudou

- `PIPELINE_VERSION` para 3: o cache da 0.1.0 se invalida sozinho.

## [0.1.0] — 2026-08-21

Primeira versão utilizável: traduz man pages para pt-BR sem rede.

### Adicionado

- `manbr <comando>` executa `man` e traduz; `… | manbr` traduz a entrada
  padrão. Texto em stdout, tudo o mais em stderr.
- Mascaramento de sintaxe de comando (`mask`) e validação obrigatória da
  tradução (`validate`): flags, caminhos, IPs, variáveis, URLs, expressões
  sed e literais citados nunca chegam ao modelo.
- Validação estrutural além dos placeholders: token desconhecido, contagem de
  sentenças, repetição e delimitadores.
- Normalização de saída de roff (`normalize`) e segmentação em prosa e blocos
  literais (`segment`). A sinopse é bloco literal: é gramática de comando, não
  frase, e nunca vai ao modelo.
- Requebra da prosa traduzida na largura da página (`MANWIDTH`, padrão 80).
  Flags, caminhos e URLs longos nunca são partidos no fim da linha.
- Tradução com CTranslate2 int8 sobre `Helsinki-NLP/opus-mt-tc-big-en-pt`,
  com recuperação por sentença quando o parágrafo é rejeitado.
- Cache em disco por segmento em `~/.cache/manbr`, com escrita atômica e
  invalidação por versão de pipeline.
- Tradução de cabeçalhos de seção por tabela (`headers.txt`) e glossário de
  termos técnicos (`glossary.txt`), ambos editáveis.
- Empacotamento com PyInstaller (`manbr.spec`).

### Limitações conhecidas

- Cerca de 14% dos segmentos de prosa saem em inglês, por rejeição da
  validação. É deliberado: não traduzir é melhor que corromper um comando.
- Primeira execução de uma página custa ~165 s; as seguintes saem do cache em
  0,3 s. Pelo binário `--onefile`, some 2 s de descompactação a cada execução.
- A linha de título sai sem o alinhamento em colunas.
- A qualidade do português é a de um modelo genérico de 2022, sem afinação
  para texto técnico.
