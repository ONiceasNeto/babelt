
<div align="center">

```
                              ▄▄▄▄▄▄▄▄▄
                          ▄▄█████████████▄▄
                        ██████████████████████
                      ▄▄██████████████████████▄▄
                  ▄▄██████████████████████████████▄▄
                ████████████████████████████████████
             ▄▄████████████████████████████████████████▄▄
           ██████████████████████████████████████████████████
        ▄▄██████████████████████████████████████████████████████▄▄
      ████████████████████████████████████████████████████████████████
```

```
      ██████╗  █████╗ ██████╗ ███████╗██╗  ████████╗
      ██╔══██╗██╔══██╗██╔══██╗██╔════╝██║  ╚══██╔══╝
      ██████╔╝███████║██████╔╝█████╗  ██║     ██║
      ██╔══██╗██╔══██║██╔══██╗██╔══╝  ██║     ██║
      ██████╔╝██║  ██║██████╔╝███████╗███████╗██║
      ╚═════╝ ╚═╝  ╚═╝╚═════╝ ╚══════╝╚══════╝╚═╝
```

**A torre caiu. O terminal continuou falando inglês.**

*Tradutor offline de saída de terminal, EN → pt-BR.*

[![CI](https://github.com/ONiceasNeto/babelt/actions/workflows/ci.yml/badge.svg)](https://github.com/ONiceasNeto/babelt/actions/workflows/ci.yml)
[![Licença: MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)

</div>

---

```console
$ babelt ls
Usage: ls [OPTION]... [FILE]...
Listar informações sobre os FILEs (o diretório atual por padrão). Classificar as
entradas em ordem alfabética se nenhum dos -cftuvSUX nem --sort for
especificado.

  -a, --all                  Não ignore as entradas que começam com .
  -A, --almost-all           não listar implícito . e ..
  -B, --ignore-backups       não listar entradas implícitas terminadas em ~
```

E uma man page inteira:

```console
$ babelt ss
SS(8) Manual do Gestor de Sistema SS(8)

NOME
       ss - outro utilitário para investigar sockets

SINOPSE
       ss [options] [ FILTER ]

DESCRIÇÃO
       ss é usado para despejar estatísticas socket. Ele permite mostrar
       informações semelhantes ao netstat. Ele pode exibir mais informações TCP
       e estado do que outras ferramentas.
```

Saída real, não retocada. `SINOPSE` fica em inglês de propósito: a sinopse é
gramática de comando, tratada como bloco literal e nunca enviada ao modelo.

Sem nuvem. Sem chave de API. Sem enviar seu terminal para lugar nenhum.
O modelo roda na sua máquina, em CPU, e o `--help` do `ls` sai em português
em menos de um segundo.

---

## Por que isso existe

A barreira de entrada do terminal não é conceitual. É linguística.

Quem está começando raramente trava porque `find` é difícil — trava porque a
resposta está num `man` de trezentas linhas em inglês técnico. A documentação
existe, está instalada na máquina, e é ilegível para boa parte de quem mais
precisa dela.

Isso não é um problema brasileiro. É a condição normal da maioria dos usuários
de Linux no mundo: a documentação de sistema é escrita em inglês e permanece
em inglês, independentemente de quem esteja lendo.

O babelt não simplifica nada e não reescreve nada. Traduz o que já está lá,
preservando cada flag, cada caminho e cada exemplo intactos, e devolve o
inglês original quando não consegue traduzir bem.

## Como ele evita estragar sua saída

Traduzir texto de terminal é diferente de traduzir prosa. `--block-size=SIZE`
não é uma frase. `/usr/local/bin` não deve virar `/usr/local/caixa`.

**Nenhuma flag, caminho, variável ou endereço chega ao modelo.** Antes de
traduzir, cada token de sintaxe é substituído por um marcador opaco; depois da
tradução, o literal original volta byte a byte.

```
Use --verbose to list the contents of /etc/services.
Use --verbose para listar o conteúdo de /etc/services.
     ^^^^^^^^^                         ^^^^^^^^^^^^^^ intactos, garantidos
```

Depois, cada segmento traduzido passa por um validador que confere se as
máscaras voltaram, se o comprimento é plausível e se não há corrupção.
**Segmento que não passa é descartado e o inglês original é devolvido no
lugar** — a saída pode ficar parcialmente em inglês, mas nunca sai errada.

Uma flag traduzida produz um comando inválido que o usuário vai copiar e
colar: pior que não traduzir. A garantia não vem da qualidade do modelo, vem
de mascarar antes e rejeitar por código depois.

Medido em `ls`, `grep`, `find`, `tar`, `ssh` e `git`: **85,4% da prosa é
traduzida** — 1.609 de 1.884 segmentos — e os outros 275 voltam ao inglês
original. `babelt --stats <comando>` mostra o número da sua máquina, com o
motivo de cada rejeição.

---

## Estado e direção

Hoje o babelt traduz **EN → pt-BR**. É o único par empacotado, porque é o que
foi medido, ajustado e validado a fundo.

O pipeline, porém, não sabe que existe português. `normalize`, `segment`,
`mask` e `restore` operam sobre estrutura de texto de terminal — flags,
caminhos, blocos literais, colunas alinhadas — e nada nesse caminho depende do
idioma de saída. O que depende:

| Componente | Depende do idioma de saída? |
| --- | --- |
| Segmentação, máscara e restauração | Não — leem estrutura e inglês de entrada |
| Validação de placeholder e de corrupção | Não |
| Contagem de sentenças e razão de comprimento | **Sim** — ver abaixo |
| Requebra de linha na largura do terminal | Só para escrita de largura dupla (CJK) |
| Modelo de tradução | Sim — o Helsinki-NLP publica centenas de pares |
| Glossário, literais e tabela de cabeçalhos | Sim — arquivos de texto simples |
| Guarda de prosa (`function_words.txt`) | Não — mede a **entrada**, que é sempre inglês |
| Caminho do modelo e do cache | Hoje fixo em `en-pt`; precisa virar parâmetro |

**Para um par latino — `en-es`, `en-fr`, `en-it` — o trabalho é sobretudo
configuração e medição.** Converter o modelo com `scripts/build-model.sh`,
montar glossário e tabela de cabeçalhos, tornar o par um parâmetro em vez de
uma constante, e medir a taxa de rejeição.

**Para escritas mais distantes o trabalho inclui código**, e vale ser honesto
sobre isso. Duas regras de validação hoje assumem o formato do português:

- **Contagem de sentenças** corta em `.`, `!`, `?` seguidos de espaço. Não
  reconhece o danda do hindi (`।`), o ponto de interrogação árabe (`؟`) nem a
  pontuação CJK (`。`), e em chinês e japonês não há espaço depois dela.
- **Razão de comprimento** aceita a janela `[0,5; 2,5]`, calibrada para um
  idioma que *expande*: medido em `ls`, EN → pt-BR tem mediana 1,13. Idiomas
  que contraem cairiam sistematicamente abaixo do piso e seriam rejeitados em
  massa.

Nenhuma das duas é reescrita profunda, mas nenhuma das duas é configuração.

Se você fala outro idioma e quer o terminal nele, esse é o maior espaço aberto
do projeto. Abra uma issue dizendo qual par te interessa.

---

## Contribuindo

O projeto é útil na medida em que mais gente consegue ler o próprio terminal.
Toda contribuição que amplie isso serve, e a maior parte delas não exige
escrever Python.

**Ampliar o alcance**

- **Um novo par de idiomas.** O maior espaço aberto. Converter o modelo,
  montar o glossário, medir a taxa de rejeição — e, para escrita não latina,
  ajustar as duas regras acima.
- **Testar em outra distro.** O instalador foi validado em Ubuntu 24.04 e
  Arch. Fedora, openSUSE, Alpine e Debian estável ainda não.
- **Traduzir as mensagens do próprio babelt.**

**Melhorar a qualidade**

- **Reportar tradução ruim.** Rode `babelt <comando>`, ache uma linha que saiu
  esquisita, abra uma issue com a saída e o `--stats`. Isso é dado de
  qualidade e vale mais que código.
- **Glossário e literais.** Termos técnicos que não devem ser traduzidos, ou
  que têm tradução consagrada em pt-BR. São arquivos de texto — bom primeiro
  PR.
- **Comandos ainda não medidos.** A medição cobre `ls`, `grep`, `find`, `tar`,
  `ssh` e `git`. Faltam muitos.

**Mexer no núcleo**

Segmentação, máscara e validação têm regras que existem por um motivo
documentado. [`docs/development/`](docs/development/) guarda a justificativa de
cada uma — vale ler a fase correspondente antes de mudar comportamento.

A suíte de testes é grande de propósito: ela existe para você poder quebrar
coisas e descobrir na hora.

**Se é seu primeiro pull request**, isso é bem-vindo aqui e não é motivo de
constrangimento. Issues marcadas `good first issue` são escolhidas para isso.
Comece por [`CONTRIBUTING.md`](CONTRIBUTING.md) — ele explica desde o que é um
fork até como rodar o CI localmente.

## Instalação

Requer Python 3.11+ e Linux.

```console
$ git clone https://github.com/ONiceasNeto/babelt && cd babelt
$ ./install.sh
$ babelt ss
```

`install.sh` monta um venv isolado em `~/.local/share/babelt/venv`, instala o
babelt lá dentro e liga `~/.local/bin/babelt` a ele. **Nada é instalado no
Python do sistema e você nunca precisa ativar venv nenhum** — o symlink aponta
para o interpretador certo. Se `~/.local/bin` não estiver no `PATH`, o
instalador diz a linha exata para adicionar, conforme o seu shell.

O modelo (~230 MB) é baixado ao final da instalação. Se o download falhar, a
instalação **não** é desfeita: o babelt fica utilizável e tenta de novo no
primeiro uso.

| Flag | Efeito |
| --- | --- |
| *(nenhuma)* | Instala e baixa o modelo. |
| `--no-model` | Instala sem baixar; o modelo vem no primeiro uso. |
| `--uninstall` | Remove binário, venv e cache. Pergunta antes de apagar o modelo. |
| `--help` | Resumo das opções. |

Reinstalar por cima é seguro e é como se atualiza: o venv é refeito e o
modelo já baixado é reaproveitado.

O modelo vai para `~/.local/share/babelt/models/en-pt`, respeitando
`XDG_DATA_HOME`. Ele é baixado já convertido para int8, com o SHA-256
conferido antes de qualquer extração — instalar o babelt **não** puxa `torch`
nem `transformers`.

Quem quiser converter o modelo por conta própria, em vez de baixar o artefato:

```console
$ .venv/bin/pip install 'babelt[convert]'
$ ./scripts/build-model.sh          # imprime o SHA-256 do artefato gerado
```

### Diagnóstico

```console
$ babelt doctor
ok    babelt                      0.4.0
ok    modelo                     /home/você/.local/share/babelt/models/en-pt (227 MiB)
ok    cache                      /home/você/.cache/babelt — 123 entradas, 16 KiB
ok    ctranslate2                4.8.1
```

Sai com 1 quando algo impede traduzir, 0 quando é só aviso.

## Uso

```console
$ babelt ss                    # executa `man ss` e traduz
$ man ss | babelt              # traduz a entrada padrão
$ nmap --help | babelt         # funciona com qualquer saída de terminal
$ babelt --help-of katana      # executa `katana --help` e traduz
$ babelt --auto katana         # tenta man; sem página, cai para --help
$ babelt ss > ss.pt.txt        # texto em stdout, limpo
```

| opção | efeito |
|---|---|
| `--help-of` | executa `<comando> --help` em vez de `man <comando>` |
| `--auto` | tenta `man`; se não houver página, cai para `--help` |
| `--beam N` | feixe da busca (padrão 1; 4 traduz melhor e demora ~2,5× mais) |
| `--no-cache` | ignora o cache, na leitura e na escrita |
| `--stats` | estatísticas em stderr ao final, com a taxa de rejeição por motivo |
| `--no-pager` | nunca pagina, mesmo em terminal |
| `--model-path P` | usa outro diretório de modelo |
| `--version` | versão |

`--stats` diz quanto ficou em inglês e **por quê**:

```console
$ babelt --stats ls
babelt: segmentos: 76 de prosa, 134 literais
babelt: traduzidos: 62 (81.6%); mantidos em inglês: 14 (18.4%)
babelt: rejeitados por motivo:
babelt:      5 (6.6%)  placeholder ausente
babelt:      4 (5.3%)  peça fora do vocabulário (oov)
babelt:      3 (3.9%)  delimitador
babelt:      2 (2.6%)  razão de comprimento
babelt: cache: 0 acertos de segmento
```

Segmento rejeitado sai em inglês, e isso é o comportamento desejado: uma
frase mal traduzida numa página de manual é pior que uma frase em inglês.
Os motivos são as regras de [`validate.py`](babelt/validate.py).

`babelt doctor` diagnostica a instalação: modelo, cache, bibliotecas e `man`.

> **`--help-of` e `--auto` executam o binário.** Ler uma man page é ler um
> arquivo; rodar `foo --help` roda `foo`. Por isso nenhum dos dois é o padrão,
> o comando é invocado só com o flag de ajuda (`--help`, depois `-h`, depois
> `--usage`), nunca com argumento a mais, e com timeout de 10 segundos.
> `--auto` só troca de fonte quando o `man` responde "No manual entry".

Texto traduzido vai **sempre** para stdout; progresso, avisos e estatísticas
vão **sempre** para stderr. Em pipe a saída sai crua. Em terminal ela é
paginada só quando não cabe na tela — com `$BABELT_PAGER`, senão `$PAGER`,
senão `less -RFX` (o `-F` sai sozinho em saída curta, o `-X` não apaga a tela
ao sair). `--help-of` e `--auto` não paginam por padrão.

Códigos de saída: `0` sucesso, `1` erro de execução, `2` uso inválido,
`127` página não encontrada, `130` interrompido.

## Desempenho

A primeira tradução de uma página custa caro; as seguintes não.

| | |
|---|---|
| `babelt ss` a frio (167 segmentos de prosa) | ~150 s |
| `babelt ss` com cache quente | **0,3 s** |
| idem, pelo binário PyInstaller | 3,3 s (2 s são descompactação) |
| memória, a frio | ~520 MB |
| memória, com cache quente | ~20 MB |
| corpus de 20 páginas, a frio | 1219 s |
| o mesmo corpus, quente | 0,9 s |

O cache fica em `~/.cache/babelt` (respeita `XDG_CACHE_HOME`), é por **segmento**
e é portável: pode ser gerado numa máquina e copiado para outra. Cada entrada
guarda o resultado inteiro, então uma segunda execução reproduz até as
estatísticas.

O cache se invalida sozinho quando o texto muda (a chave é o hash do texto),
quando o modelo muda, quando o feixe muda ou quando a versão do pipeline é
incrementada. Não há comando de limpeza porque não é preciso: apagar
`~/.cache/babelt` é seguro a qualquer momento.

## Entrada que não é prosa

`ls | babelt` costumava traduzir nome de arquivo — `Labs` virava `Laboratórios`
—, e nenhuma validação via o problema. Desde a 0.3.0 o documento inteiro é
medido antes de qualquer tradução: se a densidade de palavras funcionais
(artigo, preposição, conjunção) ficar abaixo de 14%, a entrada sai intacta,
com um aviso em stderr.

```console
$ ls /usr/share | babelt
babelt: a entrada não parece prosa em inglês (0.0% de palavras funcionais em
       85, mínimo 14%); saindo intacta
```

O limiar foi medido, não escolhido: saída de comando fica entre 0 e 12,8%, e o
pior documento de prosa dos corpora (`ffmpeg --help`) tem 18,1%. Ver
`docs/development/README-fase6.md`. A lista de palavras funcionais está em
`babelt/function_words.txt` e é editável.

## Limitações conhecidas

**14,6% dos segmentos de prosa saem em inglês** (275 de 1.884, medidos em
`ls`, `grep`, `find`, `tar`, `ssh` e `git`). Não é bug: é a validação
funcionando. Um
segmento é recusado quando

- perde, duplica ou inventa um marcador de sintaxe;
- contém caractere que o tokenizer do modelo não conhece (`{`, `}`, `|`, `^`);
- volta com número de sentenças diferente do original;
- repete uma sentença que aparecia uma vez;
- perde um colchete, chave ou parêntese.

Quando um parágrafo é recusado, ele é tentado de novo frase a frase, e só as
frases que falharem ficam em inglês.

Outras limitações, medidas e não escondidas:

- **Lista de valores separada por vírgula ainda chega ao modelo.**
  `all,robotstxt,sitemapxml` pode sair com o primeiro item traduzido. São 13
  ocorrências nos corpora medidos; ver `docs/development/README-fase5.md`.
- **A qualidade do português é a de um modelo genérico de 2022.** Sai
  "O daemon bifurca" e "deixa cair o pacote". Não há afinação para texto
  técnico.
- **Cabeçalhos de seção vêm de uma tabela** (`babelt/headers.txt`), não do
  modelo, para que `SEE ALSO` seja sempre `VEJA TAMBÉM`. Cabeçalho fora da
  tabela fica em inglês.
- **Alguns termos nunca vão ao modelo** (`babelt/literals.txt`): ele traduz
  `headless` e `non-headless` para a mesma coisa e a negação some. Mascarar
  custa tradução — placeholder perdido reprova o parágrafo —, e o parágrafo
  sai em inglês em vez de dizer o contrário do original.
- **O glossário é cego a contexto.** `babelt/glossary.txt` devolve termos
  técnicos ao inglês (`soquete` → `socket`), mas não sabe qual palavra
  inglesa gerou a portuguesa. Entradas ambíguas foram removidas por medição.
- **A linha de título perde o alinhamento em colunas.** `SS(8) Manual do
  Gestor de Sistema SS(8)` sai com espaço simples: a linha é tratada como
  prosa, e o que volta traduzido não tem como preservar a centralização.
- **Só inglês → pt-BR.** O par é fixo hoje, e o caminho do modelo e do cache
  ainda é a constante `en-pt`. O que separa isso de um segundo par está em
  [Estado e direção](#estado-e-direção).

## Como funciona

```
man ss
  → normalize   remove overstrike do roff, junta hifenização, colapsa
                justificação
  → segment     separa prosa, bloco literal (sinopse, exemplos, tabelas) e
                tabela de duas colunas — nesta, só a célula da direita é
                traduzida, e a coluna da esquerda passa intacta
  → mask        troca flags, caminhos, IPs, variáveis, URLs e literais
                citados por marcadores
  → translate   CTranslate2 int8, com cache por segmento
  → validate    marcadores intactos? sentenças preservadas? delimitadores?
                  sim  → restaura os literais
                  não  → tenta por sentença; o que falhar sai em inglês
  → reassemble  remonta o documento, com cabeçalhos traduzidos por tabela
  → rewrap      requebra a prosa na largura da página (MANWIDTH, padrão 80)
```

Blocos literais nunca chegam ao modelo.

## Desenvolvimento

Para mexer no código, o caminho é o editável — não o `install.sh`, que existe
para quem só quer usar:

```console
$ python -m venv .venv && .venv/bin/pip install -e '.[dev,convert]'
$ .venv/bin/pytest                              # 1422 testes
$ .venv/bin/mypy                                # strict
$ .venv/bin/mypy --python-version 3.11 babelt    # piso de execução
```

Testes que precisam do modelo baixado estão marcados `model` e são pulados
sem ele:

```console
$ .venv/bin/pytest -m 'not model'
```

O histórico de decisões — com as medições que as sustentam — está em
[`docs/development/`](docs/development/), com um índice por fase.

[`CONTRIBUTING.md`](CONTRIBUTING.md) tem o passo a passo completo, incluindo o
que o CI verifica e como rodar o mesmo antes de enviar.

## Licença

MIT. Veja [LICENSE](LICENSE).

O modelo de tradução é `Helsinki-NLP/opus-mt-tc-big-en-pt`, licenciado
separadamente (CC-BY-4.0) e baixado sob demanda.

---

<div align="center">

Feito por [Niceas Neto](https://www.linkedin.com/in/niceas-neto-b37b3a359/).

Modelo por [Helsinki-NLP](https://huggingface.co/Helsinki-NLP), sob CC-BY-4.0.
Código sob [MIT](LICENSE).

**Quer o terminal em outro idioma?**
[Abra uma issue](https://github.com/ONiceasNeto/babelt/issues/new/choose).

</div>
