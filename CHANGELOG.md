# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).
Versionamento semântico.

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
