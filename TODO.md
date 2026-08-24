# TODO

## Bloqueadores de publicação

- [x] Corrigir URLs falsas no `pyproject.toml` (fase 7 — apontam para
      github.com/ONiceasNeto/babelt; conferir se o repositório será
      renomeado junto com o pacote)
- [ ] Verificar disponibilidade do nome `babelt` no PyPI e no AUR
- [x] Decidir renomeação: **feito na fase 8**. `manbr` fixava pt-BR no
      binário e o plano inclui outros idiomas; o nome agora é `babelt`.
      Falta renomear o repositório no GitHub e o diretório local
- [x] `babelt setup`: baixar artefato já convertido em vez de converter
      localmente (fase 7 — `download()` baixa tar.gz pronto; não virou
      subcomando próprio, mora no fluxo normal da primeira execução)
- [x] Gerar e publicar o artefato convertido (~206 MB, GitHub Releases).
      Publicado como asset de `v0.5.0`; responde 200 anonimamente e o
      download foi exercitado de ponta a ponta pelo `install.sh`
- [x] Verificação SHA-256 do download (fase 7 — conferido antes de
      qualquer extração; artefato divergente é apagado sem ser aberto)
- [x] Mover `transformers` e `torch` de `dependencies` para
      `optional-dependencies.convert` (fase 7 — `huggingface-hub` saiu
      junto)
- [x] Licença do modelo: atribuição ao Helsinki-NLP (fase 7 — no README
      e em NOTICE dentro do artefato, gerado por build-model.sh)
- [x] Preencher `MODEL_URL` e `MODEL_SHA256` em `babelt/model.py` depois
      de publicar o artefato (fase 9)

## Distribuição

- [x] Instalação em um comando: `install.sh` com venv isolado, symlink em
      `~/.local/bin`, `--no-model` e `--uninstall` (fase 9)
- [ ] Renomear o repositório no GitHub e o diretório local para `babelt`
- [ ] PKGBUILD para o AUR
- [ ] Publicar no PyPI
- [x] CI no GitHub Actions rodando a suíte (fase 7 — pytest sem o modelo
      e mypy strict, em push e PR)
- [x] `babelt doctor`: diagnostica modelo ausente, cache corrompido,
      versão de pipeline divergente (fase 7; a fase 8 acrescentou o aviso
      de diretório órfão do nome antigo)
- [ ] Avaliar PPA (Launchpad) para `apt install`
- [ ] `--onedir` no PyInstaller: `--onefile` custa ~2s de descompressão
      em todo caminho quente (medido na Fase 4)

## Idiomas

**Suporte a um segundo par.** Auditado na fase 10: o pipeline de
segmentação, máscara e restauração não depende do idioma de saída, e a
guarda de prosa (`prose.py` + `function_words.txt`) mede a *entrada*, que
é sempre inglês. O que está preso ao pt-BR fora do modelo e dos arquivos
de glossário, e teria de mudar:

- [ ] **Parametrizar o par.** `model_path()` devolve
      `~/.local/share/babelt/models/en-pt` com o `en-pt` literal, e
      `MODEL_ID`/`MODEL_URL` em `babelt/model.py` são constantes de um par
      só. Não há dimensão de idioma na CLI, no caminho do modelo nem no do
      cache. `make_key` já inclui o modelo na proveniência, então o cache
      se invalida sozinho quando o par muda — mas os dois pares
      dividiriam o mesmo diretório
- [ ] **Arquivos de dados por idioma.** `glossary.txt`, `literals.txt` e
      `headers.txt` são pt-BR. Formato já é texto simples, uma entrada por
      linha; falta o eixo de idioma no caminho
- [ ] **Contagem de sentenças** (`validate.py:_SENTENCE_RE`) corta em
      `.`, `!`, `?` seguidos de espaço. Não reconhece o danda do hindi
      (`।`), o ponto de interrogação árabe (`؟`) nem a pontuação CJK
      (`。`), e em chinês e japonês não há espaço depois dela. Bloqueia
      `en-hi`, `en-ar`, `en-zh`, `en-ja`; irrelevante para pares latinos
- [ ] **Razão de comprimento** (`validate.py`, `[0,5; 2,5]`) está
      calibrada para um idioma que expande: medido em `ls`, EN → pt-BR tem
      mediana 1,13, com folga 0,63 abaixo e 1,37 acima. Idioma que contrai
      cairia sistematicamente sob o piso. Precisa virar par de limites por
      idioma, com medição
- [ ] **Requebra de linha** (`__main__.py:rewrap`) conta caracteres, não
      largura de exibição. Só afeta escrita de largura dupla (CJK)
- [ ] Definir política de qualidade para idioma sem revisão humana

Um par latino (`en-es`, `en-fr`, `en-it`) precisa só dos dois primeiros
itens mais medição. Escrita não latina precisa dos cinco.

## Limitações conhecidas, sem solução prevista

- [ ] Alinhamento da linha de título se perde (exigiria mexer em
      `segment.py`)
- [ ] `headless` / `non-headless` colapsam no modelo; mitigado por
      `literals.txt` ao custo de a frase sair em inglês
- [ ] Dois intratáveis de mascaramento: `\` nu e `-` nu em meio de frase
- [ ] **Identificador de coluna traduzido** (`NEXT`, `LEFT` do
      `systemctl list-timers`): invisível por qualquer regra de saída, já
      que a tradução fica bem formada — a contagem de palavras bate e os
      delimitadores batem. Exigiria detecção posicional na entrada:
      primeira palavra de descrição pendurada. Medido na fase 7
- [ ] **Prefixo comido antes de placeholder inicial** (fase 9, diagnosticado
      e não corrigido). `with -lt: sort by` sai `-lt: classificar por`: o
      `with` some. **Não é a máscara** — ela entrega `with ⟦0⟧: sort by`
      intacto ao modelo, que devolve `⟦0⟧: classificar por`. É o modelo
      descartando o que vem antes de um placeholder que aparece cedo num
      segmento curto. Reproduz com `like -l but`, `same as -l but`,
      `use -l to`, `in /etc/services the` — todos perdem o prefixo. Não
      reproduz quando há mais contexto depois (`with --color the output is
      colored` → `com ⟦0⟧ a saída é colorida`) nem quando há conteúdo lexical
      entre a preposição e o placeholder (`with the option -lt` → `com a
      opção ⟦0⟧`). **O validador aprova os oito casos**: o placeholder volta,
      o comprimento é plausível, não há `<unk>` e a contagem de sentenças
      bate. É a mesma classe do item abaixo, e detectá-la esbarra no mesmo
      problema de separação entre as populações
- [ ] Omissão de palavra pela tradução: medida na fase 6 (razão de
      conteúdo) e na fase 7 (perda da primeira palavra), reprovada nas
      duas por falta de separação entre as populações — 60% e 19% de
      precisão
