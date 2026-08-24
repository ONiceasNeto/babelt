# babelt — Fase 11: proposta de suporte a múltiplos pares

**Este documento é proposta, não registro.** Nada aqui foi implementado. Ele
avalia um desenho contra o código de hoje (0.5.0, `PIPELINE_VERSION` 5), diz
onde encaixa, onde não encaixa, e em que ordem valeria fazer.

## Resumo do veredito

| Ponto do desenho | Veredito |
| --- | --- |
| `models.toml` em árvore, com `model_id`, `url`, `sha256` | **Aceito.** Resolve um problema que já existe hoje. |
| `babelt/lang/<código>/` com os três `.txt` | **Aceito**, com uma correção no fallback. |
| Idioma sem arquivo funciona, só traduz pior | **Aceito**, e é o ponto mais importante do desenho. |
| Par no caminho do modelo | **Aceito.** |
| Par na chave do cache | **Já está lá.** O problema real é outro, e é o diretório. |
| Campo `script` seleciona regex e janela | **Aceito em intenção, recusado na forma.** São dois eixos, não um. |
| `--lang`, `BABELT_LANG`, padrão `en-pt` | **Aceito**, com uma ressalva sobre `--model-path`. |

Dois achados que o desenho não previa estão em [O que o desenho não
viu](#o-que-o-desenho-não-viu). O segundo deles muda o que a primeira etapa
tem de fazer.

---

## 1. `models.toml` em árvore

**Aceito, e resolve um problema que já existe.**

Hoje `babelt/model.py` carrega três constantes de um par só:

```python
MODEL_ID: Final = "Helsinki-NLP/opus-mt-tc-big-en-pt"
MODEL_URL: Final = "https://github.com/.../v0.5.0/babelt-model-en-pt-int8.tar.gz"
MODEL_SHA256: Final = "0f4dfcc6..."
```

Isso já dói com **um** par: publicar uma release nova exige editar código
Python e passar por revisão de código para trocar um hash. Um manifesto
transforma isso em dado.

A escolha de manter em árvore em vez de buscar por rede está certa e a razão
dada é a boa: **o SHA-256 precisa continuar auditável em PR.** Um manifesto
remoto move a raiz de confiança do repositório para um servidor, e o
`verify_archive` de hoje perderia o sentido — ele confere o artefato contra um
hash que o próprio distribuidor serviria.

Forma sugerida:

```toml
[pairs.en-pt]
model_id = "Helsinki-NLP/opus-mt-tc-big-en-pt"
url = "https://github.com/ONiceasNeto/babelt/releases/download/v0.5.0/babelt-model-en-pt-int8.tar.gz"
sha256 = "0f4dfcc6ff9819babdf3914cca58166a73d439a10f03a3c0b48328b88a0c11ea"
sentence_style = "latin"
length_ratio = [0.5, 2.5]
```

`tomllib` está na stdlib desde o 3.11, que é o piso de execução do projeto —
sem dependência nova. O arquivo entra no pacote pelo mesmo caminho que
`glossary.txt` e os outros já usam.

**Um detalhe que não pode ser perdido na migração.** `model.py` tem uma
constante `_PLACEHOLDER = "PREENCHER"` e `download()` falha com instrução
quando as constantes não foram preenchidas. Há teste para isso
(`test_sem_url_publicada_falha_com_instrucao`), e ele existe porque a
alternativa é uma falha de rede confusa. O manifesto precisa do equivalente:
um par declarado sem `url` ou sem `sha256` tem de falhar cedo, com a mesma
mensagem útil, e não tentar baixar de uma string vazia.

---

## 2. `babelt/lang/<código>/` e o fallback

**Aceito. E o fallback é o ponto mais importante do desenho inteiro.**

"Idioma sem arquivo deve funcionar, só traduzir pior" é o que permite alguém
contribuir um par antes do glossário existir. Sem isso, o primeiro
contribuidor de `en-es` teria de entregar modelo, glossário, literais e
cabeçalhos de uma vez — e não entregaria nada.

**Mas o fallback tem de ser vazio, não pt-BR.** Os três arquivos de hoje
carregam no import:

```python
GLOSSARY: Final = load_glossary()      # translate.py
HEADERS: Final = load_headers()        # headers.py
```

Se `en-es` cair para os arquivos de pt-BR, `apply_glossary` vai procurar
`soquete` num texto em espanhol e `translate_header` vai devolver `NOME` para
`NAME`. **Português no meio de espanhol é pior que inglês:** o leitor não
sabe se é erro de tradução ou termo técnico. Diretório ausente carrega tabela
vazia, e ponto.

Isso já funciona quase de graça: `load_headers` devolve dicionário e
`translate_header` devolve o texto intacto quando não conhece a chave;
`apply_glossary` já testa `if _GLOSSARY_RE is None: return text`. As três
funções aceitam tabela vazia sem mudança.

**O que muda de verdade:** as três constantes são carregadas no import e a
seleção de idioma acontece depois, no `argparse`. Ou elas viram lazy, ou
passam a ser resolvidas por uma função que recebe o par. Prefiro a segunda —
estado global carregado no import é o que torna a coisa difícil de testar,
e há testes que dependem de poder passar tabela por argumento
(`apply_glossary(text, table=...)` já aceita).

Migração: `git mv babelt/{glossary,literals,headers}.txt babelt/lang/pt-BR/`.
`function_words.txt` **não** se move — ele mede a entrada, que é sempre
inglês, e pertence a `babelt/` como está.

---

## 3. Par no caminho do modelo e na chave do cache

**No caminho do modelo: aceito, e é trivial.**

```python
def model_path() -> Path:
    return _data_home() / "babelt" / "models" / "en-pt"   # hoje
```

Passa a receber o par. Já existe `--model-path` para sobrepor, e ele continua
válido: quem aponta um diretório explícito está dizendo "use este", e o par
não deve reescrever isso.

**Na chave do cache: já está lá, e o desenho descreve um problema que não é
esse.**

```python
def make_key(text, *, model, beam, pipeline_version=PIPELINE_VERSION) -> str:
    for part in (str(pipeline_version), model, str(beam), text):
```

`model` é o `MODEL_ID`, que muda de `opus-mt-tc-big-en-pt` para
`...-en-es`. **Duas traduções da mesma frase para idiomas diferentes já têm
chaves diferentes hoje.** Acrescentar o par explicitamente seria redundante.

O problema real é o `meta.json`, e ele é concreto:

```python
def _write_meta(self) -> None:
    """Proveniência do cache. Sem isto o artefato não é portável."""
```

`_write_meta` roda a cada `put` e sobrescreve a proveniência inteira, que hoje
é `{"model": MODEL_ID, "beam": args.beam}`. Com dois pares alternando, o
`meta.json` oscila entre `en-pt` e `en-es` conforme o último comando rodado, e
`babelt doctor` reporta o último. Pior: a docstring diz que a proveniência é o
que torna o cache **portável** — um cache exportado com meta de um par e
entradas de dois não é portável, é enganoso.

Duas saídas, e prefiro a primeira:

- **Um diretório por par**: `~/.cache/babelt/en-pt/`. `meta.json` volta a
  descrever exatamente o que está ali. Apagar o cache de um par não toca o
  outro. Custo: `cache_root()` passa a receber o par, e há testes de
  `cache_root` a ajustar.
- Proveniência com lista de pares. Mantém um diretório, mas o `meta.json`
  vira acumulador, e `doctor` tem de decidir o que reportar. Mais código para
  um resultado pior.

---

## 4. O campo `script`: aceito em intenção, recusado na forma

**A intenção está certa e o argumento é o correto** — sem isso alguém
adiciona `en-hi` e rejeita 80% em silêncio, porque o validador aprova cada
rejeição individualmente e nada soma.

**Mas `latin/cjk/indic/arabic` mistura dois eixos que não variam juntos.**

O campo governa duas coisas na proposta: qual regex de sentença e qual janela
de razão de comprimento. Elas não são a mesma dimensão:

| Par | Pontuação de sentença | Comprimento vs. inglês |
| --- | --- | --- |
| `en-pt` | latina | expande (~1,13, medido) |
| `en-de` | latina | expande mais que o pt |
| `en-vi` | latina | contrai |
| `en-ru` | latina (cirílico usa `.!?`) | expande |
| `en-ja` | CJK | contrai muito |

Vietnamita é escrita latina e contrai. Russo é cirílico e a pontuação é a
latina — o valor `latin` estaria certo para a regex e mentiria sobre o
alfabeto. Alemão e português são ambos `latin` e têm janelas diferentes.

**Proposta: dois campos, com a janela obrigatoriamente medida.**

```toml
sentence_style = "latin"     # latin | cjk | indic | arabic
length_ratio = [0.5, 2.5]    # medido, não herdado
```

`sentence_style` é honesto sobre o que seleciona: o estilo de pontuação de
fim de frase, não o sistema de escrita. Cirílico e grego declaram `latin` sem
constrangimento, porque é da regra de corte que se está falando.

`length_ratio` explícito por par, sem default herdado do estilo. A razão é a
lição da fase 6 e da fase 7: **limite herdado é limite não medido.** A janela
de hoje, `[0,5; 2,5]`, saiu de EN→pt-BR e tem mediana 1,13, com folga 0,63
abaixo e 1,37 acima — assimétrica para cima porque o português expande. Quem
adiciona um par tem de rodar a medição, e um campo obrigatório é o que
força isso.

Um par novo sem `length_ratio` deve **falhar ao carregar o manifesto**, com
mensagem dizendo como medir. É o mesmo espírito do `_PLACEHOLDER`: falhar
cedo e com instrução vale mais que degradar em silêncio.

---

## 5. CLI: `--lang`, `BABELT_LANG`, padrão `en-pt`

**Aceito.** Precedência: `--lang` > `BABELT_LANG` > `en-pt`. É a mesma que
`$BABELT_PAGER` > `$PAGER` > `less -RFX` já usa, então não é convenção nova.

Três ressalvas:

- **`--lang` com um par que não está no manifesto** deve listar os pares
  conhecidos, não dizer "desconhecido". `argparse` com `choices=` lidos do
  manifesto resolve isso de graça.
- **`--lang` e `--model-path` juntos.** Hoje `--model-path` sobrepõe o
  caminho. Com `--lang`, o usuário pode pedir duas coisas incompatíveis. A
  saída mais simples é `--model-path` vencer, com aviso — e as tabelas de
  idioma continuarem vindo do `--lang`, porque um modelo em outro diretório
  ainda é de algum par.
- **`babelt doctor` precisa saber o par.** Hoje ele checa um modelo em
  `model_path()`. Com múltiplos pares, o interessante é listar os instalados.

---

## O que o desenho não viu

### `split_sentences` corta origem e destino com a mesma regra

Este é o achado que mais importa, e muda o que a primeira etapa faz.

`validate.py` tem um comentário explícito sobre por que a regra mora lá:

> Mora aqui, e não em translate.py, porque a regra de contagem de sentenças e
> o caminho de recuperação por sentença precisam cortar exatamente igual — se
> divergirem, a validação reprova o que a recuperação produziu.

Mas os dois usos cortam textos em **idiomas diferentes**:

- `translate.py:376` — `split_sentences(masked[index][0])` corta o texto de
  **origem** mascarado, que é sempre inglês.
- `validate.py:67` — `_sentences(translated)` conta sentenças na **saída**,
  no idioma de destino.

Hoje isso é invisível porque inglês e português usam a mesma pontuação. Assim
que `sentence_style` existir, **as duas chamadas precisam de regras
diferentes**: a origem sempre corta com a regra do inglês; só a contagem do
destino usa a regra do par. Trocar as duas pela regra do alvo quebraria a
recuperação por sentença em `en-ja` — o texto inglês seria cortado por
pontuação CJK que não existe nele, e o segmento inteiro viraria uma sentença
só.

A invariante do comentário continua valendo, mas passa a ser: *a regra de
corte da origem e a de contagem da origem são a mesma.* Vale reescrever o
comentário junto com a mudança, porque quem ler o atual vai unificar as duas.

### `PIPELINE_VERSION` não cobre mudança de tabela de idioma

A constante manda incrementar ao mudar `mask`, `segment`, `normalize` ou
`validate`. Mas o cache guarda o resultado **depois** do glossário: uma
entrada nova em `glossary.txt` muda a saída e não invalida nada — o texto de
entrada, o modelo, o beam e a versão do pipeline continuam iguais.

Isso já é verdade hoje e ninguém tropeçou porque o glossário quase não muda.
Com `babelt/lang/<código>/` e contribuidores mexendo em glossário como
primeiro PR, vira problema recorrente: o contribuidor adiciona uma entrada,
roda, não vê diferença, e conclui que não funcionou.

Não proponho resolver na fase 11 — só registro, porque a mudança de estrutura
é o momento em que se decide. A saída provável é um hash das tabelas de
idioma entrando em `make_key`.

---

## Etapas, tamanho e o primeiro PR

### Primeiro PR isolado: manifesto, sem multi-idioma

**`models.toml` com um par (`en-pt`), lido por `model.py`, sem `--lang`,
sem `babelt/lang/`, sem mexer no cache.**

- `babelt/models.toml` com o par de hoje, incluindo `sentence_style` e
  `length_ratio` já preenchidos com os valores atuais — declarados, ainda
  não consumidos.
- `model.py` lê do manifesto. `MODEL_ID`, `MODEL_URL` e `MODEL_SHA256`
  continuam existindo como nomes públicos, resolvidos na carga: a API pública
  não muda e os testes de `download()` continuam valendo.
- Falha cedo, com instrução, quando falta `url` ou `sha256` — o papel que o
  `_PLACEHOLDER` tem hoje.

**Tamanho:** pequeno. Um módulo novo de ~60 linhas, `model.py` encolhe,
`test_model.py` ganha casos de manifesto malformado.

**Por que este primeiro:** entrega valor sozinho, mesmo que a fase pare aqui —
publicar release deixa de exigir editar Python. Não muda comportamento
observável, então a suíte inteira serve de rede. E é o único passo que
nenhum dos outros pode dispensar.

### Etapas seguintes

| # | Etapa | Tamanho | Observação |
| --- | --- | --- | --- |
| 2 | `babelt/lang/pt-BR/` com os três `.txt`, carga por par, fallback vazio | médio | `git mv` mais lazy-loading das três constantes. Nenhum comportamento muda com um par só. |
| 3 | Par no `model_path()` e diretório de cache por par | pequeno | Toca `doctor.py` e os testes de caminho. Decide o `meta.json`. |
| 4 | `--lang` e `BABELT_LANG`, padrão `en-pt` | pequeno | Só amarra o que 1–3 construíram. |
| 5 | `sentence_style` e `length_ratio` consumidos por `validate.py` | **médio-grande** | Onde mora o risco. Exige separar corte de origem de contagem de destino. |
| 6 | Primeiro par novo de verdade (`en-es`) | médio, mas quase todo medição | Converter, medir, calibrar a janela, glossário. É contribuição externa, não sua. |

As etapas 1 a 4 não mudam nenhum comportamento com um par só — a suíte de
1422 testes cobre isso, e cada uma deve passar sem teste novo *e* ganhar
testes do caminho novo.

A etapa 5 é a única que muda decisão de validação, e deve vir com a medição
de pelo menos dois pares de estilos diferentes. Antes disso, `sentence_style`
e `length_ratio` ficam declarados e não lidos — o que é deliberado: melhor um
campo inerte no manifesto desde o começo que um manifesto que precisa mudar
de forma na etapa 5.

## O que continua fora

- **Requebra de linha para escrita de largura dupla.** `rewrap` conta
  caracteres, não largura de exibição. Só afeta CJK, e nenhum par CJK entra
  antes da etapa 6.
- **Mensagens de interface do próprio babelt.** São português fixo em
  `__main__.py` e `doctor.py`. Ortogonal a isto: um usuário de `en-es`
  provavelmente prefere a interface em inglês, e essa é outra fase.
- **Detecção automática de idioma.** Fora de escopo e provavelmente
  indesejável: o par é decisão do usuário, e adivinhar erraria em máquina com
  locale mal configurado.
