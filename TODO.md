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

## Multi-idioma (depois de publicar pt-BR)

- [ ] Refatorar para `--lang`, com `headers.txt` e `glossary.txt` por
      idioma
- [ ] Calibrar limites de comprimento de `validate` por idioma
- [ ] Definir política de qualidade para idioma sem revisão humana

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
- [ ] Omissão de palavra pela tradução: medida na fase 6 (razão de
      conteúdo) e na fase 7 (perda da primeira palavra), reprovada nas
      duas por falta de separação entre as populações — 60% e 19% de
      precisão
