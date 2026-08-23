# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).
Versionamento semântico.

## [Não publicado]

### Adicionado

- **`install.sh`: instalação em um comando.** `./install.sh` monta um venv
  isolado em `~/.local/share/babelt/venv`, instala o babelt lá e liga
  `~/.local/bin/babelt` a ele. Nada toca o Python do sistema e o usuário nunca
  ativa venv — a alternativa era `pip install --user`, que quebra em distro com
  ambiente gerenciado (PEP 668), ou pedir que o usuário mantivesse um venv
  ativo, que é justamente o atrito que o instalador existe para tirar.
- `--no-model` instala sem baixar os 230 MB; o modelo vem no primeiro uso.
- `--uninstall` remove binário, venv e cache de tradução, e pergunta antes de
  apagar o modelo — 230 MB rebaixáveis não se apagam sem confirmar. Sem
  terminal para perguntar, mantém.
- O instalador falha cedo e com a linha exata que resolve quando falta Python
  >= 3.11 ou o módulo `venv`, com o comando por distro.

- **`--stats` reporta a taxa de rejeição por motivo.** Antes dizia quantos
  segmentos ficaram em inglês, e não por quê — o que deixava "o validador está
  rejeitando demais" no terreno da impressão. Agora agrupa por família de
  motivo (`placeholder ausente`, `oov`, `razão de comprimento`, …) com a
  contagem e o percentual sobre a prosa do documento.

### Mudou

- `PIPELINE_VERSION` foi para 5. A eleição da coluna sobre o documento muda a
  segmentação de todo `--help` com linha em branco no meio da lista de opções,
  e o motivo de rejeição guardado mudou de formato — sem o bump, `--stats`
  contaria motivo velho de cache junto com motivo novo, que foi exatamente o
  que aconteceu ao medir `ls` pela primeira vez.
- A segunda tentativa de tradução, frase a frase, resumia a falha em
  `N de M sentenças rejeitadas` e descartava o veredito do validador. O motivo
  da primeira frase rejeitada passa a viajar junto; sem ele a medição por
  motivo era impossível a partir do relatório. O validador não mudou.
- README: `install.sh` passou a ser o caminho principal de instalação;
  `pip install -e '.[dev,convert]'` ficou documentado como caminho de
  desenvolvimento.
- `MODEL_URL` e `MODEL_SHA256` preenchidos com o artefato de `v0.5.0`
  publicado no GitHub Releases.

### Corrigido

- A guarda de `venv` do `install.sh` testava `import venv`, que é a checagem
  errada em Debian e derivados: `venv` vem na stdlib e importa mesmo sem o
  pacote `python3-venv`; o que falta é o `ensurepip`. A guarda não disparava,
  `python3 -m venv` montava meio ambiente e o erro vinha do Python, já com o
  venv quebrado no disco. Agora checa `ensurepip`, e um `venv` que falhe
  mesmo assim é removido antes de sair.
- A sugestão de `PATH` do instalador ia para stdout enquanto o aviso que a
  introduz ia para stderr, e as duas apareciam deslocadas uma da outra.
- Falha no download do modelo não desfaz mais nada: o babelt fica instalado e
  utilizável, e tenta o download de novo no primeiro uso. `ModelError` sai como
  mensagem, não como traceback, espelhando `ensure_model()`.
- `tests/test_model.py::test_sem_url_publicada_falha_com_instrucao` verificava
  a detecção de placeholder testando o valor real das constantes, e por isso
  passou a baixar 230 MB de verdade — numa suíte que não é marcada `model` —
  assim que a URL foi preenchida. Agora força o placeholder com `monkeypatch`
  e falha se algum código tentar ir à rede.

## [0.5.0] — 2026-08-22

### Mudou

- **O projeto passou a se chamar `babelt`.** `manbr` prendia o nome ao par
  en→pt-BR, e o plano inclui outros idiomas. Mudaram o comando, o pacote, o
  binário, `$MANBR_PAGER` (agora `$BABELT_PAGER`) e os diretórios de dados:
  `~/.cache/babelt` e `~/.local/share/babelt`.
- Nada é migrado do nome antigo. `babelt doctor` avisa se encontrar
  `~/.cache/manbr` ou `~/.local/share/manbr` órfãos, com o tamanho, e sugere
  remover — 227 MB não somem sozinhos.
- `PIPELINE_VERSION` continua 4: o texto não mudou, só o nome.

### Corrigido

- `scripts/build-model.sh` chamava `python`, que não existe em Debian, Ubuntu
  e derivados. Agora usa o interpretador do `.venv` se houver, senão
  `python3`, e falha cedo — antes de qualquer download — quando o
  `ct2-transformers-converter` não está instalado, com a linha exata que
  resolve (`pip install -e '.[convert]'`, do repositório, não do PyPI).

## [0.4.0] — 2026-08-22

Instalar deixa de exigir 2 GB de dependência.

### Adicionado

- `babelt doctor`: diagnostica modelo, cache, bibliotecas nativas e `man`.
  Sai com 1 quando algo impede traduzir, 0 quando é só aviso.
- `scripts/build-model.sh`: converte e empacota o artefato do modelo, com
  `meta.json` de proveniência e `NOTICE` de atribuição ao Helsinki-NLP. É para
  quem publica, não para quem instala.
- CI no GitHub Actions: `pytest -m "not model"` e `mypy --strict`, sem baixar
  modelo.

### Mudou

- **`transformers` e `torch` saíram das dependências.** O modelo agora é
  baixado já convertido, com verificação de SHA-256 antes de qualquer
  extração; a conversão passou a ser feita uma vez, por quem publica.
  `huggingface-hub` também saiu — nada em tempo de execução usa.
- As URLs do projeto apontavam para um repositório que não existe.

## [0.3.0] — 2026-08-21

A entrada deixa de ser presumida como prosa.

### Adicionado

- Guarda de prosa: um documento cuja densidade de palavras funcionais fique
  abaixo de 14% sai intacto, sem gastar inferência. `ls | babelt` traduzia nome
  de arquivo e nenhuma validação via isso. O limiar e a lista de palavras
  (`babelt/function_words.txt`) foram medidos sobre três corpora.
- Mascaramento de lista de valores separada por vírgula: `all,robotstxt,
  sitemapxml` saía com o primeiro item traduzido.
- `--no-pager`, e `$BABELT_PAGER` com precedência sobre `$PAGER`.
- Corpus de saída não-prosa em `tests/corpus/nonprose/`.

### Corrigido

- O pager abria para saída que cabia na tela e, ao sair, apagava o que tinha
  mostrado. Agora só pagina o que não cabe, e o padrão é `less -RFX`.
- Título de bloco de `--help` era agrupado com o seguinte: `Flags:` e `INPUT:`
  saíam fundidos como `flags: INPUT:`. Viraram cabeçalho, isolados no próprio
  segmento e traduzidos por `headers.txt`.

### Mudou

- `PIPELINE_VERSION` para 4: o cache da 0.2.0 se invalida sozinho.

## [0.2.0] — 2026-08-21

Saída de `--help` deixa de ser um caso degenerado.

### Adicionado

- `babelt --help-of <cmd>` executa `<cmd> --help` (depois `-h`, depois
  `--usage`) e traduz; `babelt --auto <cmd>` tenta `man` e cai para a ajuda
  quando não há página. Os dois executam o binário, com timeout e sem nenhum
  argumento além do flag de ajuda.
- Segmentação de tabela de duas colunas (`SegmentKind.COLUMNS`): a coluna
  esquerda passa intacta, cada célula da direita é traduzida sozinha e a
  requebra acontece dentro da própria coluna. É metade do conteúdo de um
  `--help` medido.
- Mascaramento de grupo isolado (`{action}`, `[flags]`), sufixo de tipo
  (`string[]`) e alternância solta (`yes|no`). Recall de 96,9% para 97,5%,
  com falso positivo em prosa ainda em 1.
- `babelt/literals.txt`: termos que nunca vão ao modelo, porque a tradução
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

- `babelt <comando>` executa `man` e traduz; `… | babelt` traduz a entrada
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
- Cache em disco por segmento em `~/.cache/babelt`, com escrita atômica e
  invalidação por versão de pipeline.
- Tradução de cabeçalhos de seção por tabela (`headers.txt`) e glossário de
  termos técnicos (`glossary.txt`), ambos editáveis.
- Empacotamento com PyInstaller (`babelt.spec`).

### Limitações conhecidas

- Cerca de 14% dos segmentos de prosa saem em inglês, por rejeição da
  validação. É deliberado: não traduzir é melhor que corromper um comando.
- Primeira execução de uma página custa ~165 s; as seguintes saem do cache em
  0,3 s. Pelo binário `--onefile`, some 2 s de descompactação a cada execução.
- A linha de título sai sem o alinhamento em colunas.
- A qualidade do português é a de um modelo genérico de 2022, sem afinação
  para texto técnico.
