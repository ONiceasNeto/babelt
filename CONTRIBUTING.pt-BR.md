# Como contribuir

[English](CONTRIBUTING.md) · **Português**

Este projeto quer contribuidores iniciantes. Se você nunca abriu um pull
request, este é um bom lugar para o primeiro — e este arquivo assume que você
nunca abriu.

Nada aqui é pergunta boba. Se algo neste texto te confundiu, isso é um bug do
texto: [abra uma issue](https://github.com/ONiceasNeto/babelt/issues/new/choose)
dizendo o que não ficou claro.

## Índice

- [A contribuição mais útil não exige código](#a-contribuição-mais-útil-não-exige-código)
- [Rodando o projeto na sua máquina](#rodando-o-projeto-na-sua-máquina)
- [Abrindo um pull request, passo a passo](#abrindo-um-pull-request-passo-a-passo)
- [O que o CI verifica](#o-que-o-ci-verifica)
- [Onde mexer, e onde ler antes](#onde-mexer-e-onde-ler-antes)

---

## A contribuição mais útil não exige código

**Reportar uma tradução ruim.** Sério. O babelt é medido por quanto ele acerta
em texto real, e cada exemplo de saída esquisita é dado de qualidade que não
existe em lugar nenhum. Isso vale mais que código.

Como fazer:

1. Rode `babelt <algum comando>` — por exemplo `babelt tar`, `babelt find`.
2. Ache uma linha que saiu errada, sem sentido, ou que devia ter sido
   traduzida e não foi.
3. Abra a issue **Tradução ruim** e cole os três campos que ela pede: o
   comando, a saída que você viu, e o que está errado nela.

Não precisa saber por que está errado. "Isso não faz sentido em português"
é um relato completo.

Outras formas de ajudar sem escrever Python:

- **Testar em outra distro.** O instalador foi validado em Ubuntu 24.04 e
  Arch. Fedora, openSUSE, Alpine e Debian estável ainda não. Rodar
  `./install.sh` numa delas e contar o que aconteceu é uma contribuição
  inteira.
- **Melhorar a documentação.** Inclusive esta.
- **Traduzir as mensagens do próprio babelt.**

---

## Rodando o projeto na sua máquina

Você precisa de **Python 3.11 ou mais novo** e Linux. Para conferir a sua
versão:

```console
$ python3 --version
```

### 1. Baixe o código

```console
$ git clone https://github.com/ONiceasNeto/babelt
$ cd babelt
```

### 2. Crie um ambiente virtual

Um *ambiente virtual* (venv) é uma pasta onde as bibliotecas do projeto ficam
isoladas do resto do seu sistema. Sem ele, instalar as dependências do babelt
poderia quebrar outro programa seu.

```console
$ python3 -m venv .venv
```

Se der erro dizendo que falta o módulo `venv`, no Ubuntu/Debian/Mint instale
com `sudo apt install python3-venv`.

### 3. Instale o babelt em modo editável

```console
$ .venv/bin/pip install -e '.[dev]'
```

O `-e` quer dizer *editável*: o Python passa a usar os arquivos desta pasta
diretamente, então toda mudança que você fizer no código vale na hora, sem
reinstalar. O `[dev]` traz junto as ferramentas de teste.

> **Não use `./install.sh` para desenvolver.** Aquele script existe para quem
> só quer usar o programa: ele copia o código para um venv separado, e as suas
> edições não teriam efeito.

### 4. Rode os testes

```console
$ .venv/bin/pytest
```

Devem passar todos. Se algum falhar **antes** de você mexer em qualquer coisa,
isso já é uma issue — abra.

Os testes que carregam o modelo de tradução (230 MB) são pulados
automaticamente se você não tiver o modelo. Para rodar só o que não precisa
dele:

```console
$ .venv/bin/pytest -m 'not model'
```

### 5. (Opcional) Baixe o modelo

Só é preciso se você quiser **rodar** o babelt, não para mexer na maior parte
do código:

```console
$ .venv/bin/babelt ls
```

Ele pergunta antes de baixar.

---

## Abrindo um pull request, passo a passo

Um *pull request* (PR) é o pedido "peguem minha mudança". O caminho tem seis
passos e nenhum deles é irreversível.

### 1. Faça um fork

No [GitHub do projeto](https://github.com/ONiceasNeto/babelt), clique em
**Fork**, no alto à direita. Isso cria uma cópia do repositório na sua conta,
que é sua para estragar à vontade.

### 2. Baixe o *seu* fork

Troque `SEU-USUARIO` pelo seu nome de usuário do GitHub:

```console
$ git clone https://github.com/SEU-USUARIO/babelt
$ cd babelt
```

### 3. Crie um branch

Um *branch* é uma linha de trabalho paralela. Trabalhar num branch em vez de
direto no `main` deixa você tocar em várias coisas sem misturá-las.

```console
$ git checkout -b conserta-traducao-do-tar
```

O nome é livre; use algo que descreva a mudança.

### 4. Faça a mudança e commite

```console
$ git add .
$ git commit -m "corrige tradução de --wildcards no tar"
```

`git add .` marca tudo o que você mudou. `git commit` grava um ponto na
história, com a mensagem explicando o quê. Uma mensagem boa diz **o que muda e
por quê**, não "ajustes".

### 5. Envie e abra o PR

```console
$ git push origin conserta-traducao-do-tar
```

O GitHub vai imprimir um link no terminal. Abra, clique em **Create pull
request**, escreva o que você mudou e por quê, e envie.

### 6. Espere a revisão

O CI roda sozinho e diz se algo quebrou. Se quebrar, não é problema: é o
sistema fazendo o trabalho dele. Faça mais commits no mesmo branch e dê `git
push` de novo — o PR se atualiza sozinho.

Revisão mal-humorada não é aceita aqui. Se um comentário da revisão parecer
rude, me diga.

### Se algo der errado

- **Commitei no branch errado.** Não commitou ainda? `git checkout -b
  nome-certo` leva as mudanças junto.
- **Quero desfazer o último commit, mas manter o que escrevi.**
  `git reset --soft HEAD~1`.
- **Me perdi.** Apague a pasta, clone o fork de novo, e recomece. Nada se
  perde no repositório original.

---

## O que o CI verifica

Toda vez que você dá push, o GitHub roda três comandos. São exatamente estes,
e você pode rodar os três na sua máquina antes de enviar:

```console
$ .venv/bin/pytest -m 'not model'                 # testes, sem os 230 MB do modelo
$ .venv/bin/mypy                                  # tipagem, modo estrito
$ .venv/bin/mypy --python-version 3.11 babelt     # tipagem no Python mais antigo suportado
```

Se os três passarem localmente, o CI passa.

O terceiro existe porque o projeto suporta Python 3.11 em diante, e é fácil
escrever sem querer algo que só funciona no 3.12. Ele confere isso sem você
precisar instalar o 3.11.

Além disso, se você mexer em `install.sh`, rode o `shellcheck`. Ele não vem
com o `[dev]` nem com o sistema; instale de um destes jeitos:

```console
$ .venv/bin/pip install shellcheck-py       # funciona em qualquer distro
$ sudo apt install shellcheck               # Debian/Ubuntu/Mint
$ sudo pacman -S shellcheck                 # Arch
```

E então:

```console
$ .venv/bin/shellcheck install.sh           # se instalou via pip
$ shellcheck install.sh                     # se instalou pela distro
```

### Sobre escrever testes

Toda mudança de comportamento precisa de um teste. O padrão do projeto é: **o
teste falha antes da correção e passa depois**. Escreva-o primeiro, veja-o
falhar, e só então conserte — se ele passar antes da correção, ele não está
testando o que você pensa.

Os testes ficam em `tests/`, um arquivo por módulo. Comentários em português
explicando *por que* o teste existe são bem-vindos: quase todo teste ali é
resposta a um defeito real, e saber qual defeito ajuda quem vier depois.

---

## Onde mexer, e onde ler antes

| Se você quer... | Mexa em | Leia antes |
| --- | --- | --- |
| Corrigir uma palavra traduzida errada | `babelt/glossary.txt` | — |
| Impedir que um termo seja traduzido | `babelt/literals.txt` | — |
| Traduzir um cabeçalho de seção novo | `babelt/headers.txt` | — |
| Proteger uma sintaxe que está sendo traduzida | `babelt/mask.py` | [fases 1 a 1.2](docs/development/) |
| Mudar como o texto é dividido | `babelt/segment.py` | [fases 2 e 5](docs/development/) |
| Mudar quando uma tradução é rejeitada | `babelt/validate.py` | [fase 3.1](docs/development/) |

Os três primeiros são arquivos de texto simples, uma entrada por linha. São o
melhor lugar para uma primeira contribuição em código.

**As regras de `mask.py`, `segment.py` e `validate.py` não são arbitrárias.**
Cada uma é resposta a um falso positivo ou falso negativo medido num corpus
real, e várias hipóteses óbvias já foram testadas e reprovadas. O histórico
está em [`docs/development/`](docs/development/), com os números. Ler a fase
correspondente antes de mudar uma regex economiza refazer um caminho que já
foi andado.

---

## Código de conduta

Trate as pessoas bem. Quem está começando tem prioridade na paciência de
todos. Comportamento que faça alguém desistir de contribuir não é tolerado,
por mais correto que esteja tecnicamente.
