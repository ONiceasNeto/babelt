# Histórico de desenvolvimento

Um documento por fase, escrito no fim dela, com **as medições que sustentam as
decisões** — não só o que foi feito, mas o que foi tentado e recusado, e o
número que decidiu.

Vale a leitura antes de mexer em `mask.py`, `segment.py` ou `validate.py`:
quase toda regra ali é resposta a um falso positivo ou falso negativo medido
no corpus, e várias hipóteses óbvias já foram testadas e reprovadas.

> **Estes arquivos são registro de época e não foram atualizados.** Eles usam
> o nome antigo do projeto, `manbr` (a renomeação está na fase 8), e comandos
> que não são mais o procedimento atual — `PYTHONPATH=. .venv/bin/pytest`, por
> exemplo, que a instalação editável de hoje dispensa. Para rodar o projeto,
> siga o [README](../../README.pt-BR.md) ou o
> [CONTRIBUTING](../../CONTRIBUTING.pt-BR.md); daqui, leia o raciocínio, não
> copie os comandos.

## As fases, em ordem

| Fase | Assunto | O que ficou decidido |
| --- | --- | --- |
| [1](README-fase1.md) | `mask.py` e `validate.py` | Mascarar a sintaxe **antes** do modelo e validar o retorno depois. Sem tradução ainda: primeiro a garantia de que nenhuma tradução futura pode corromper um comando. |
| [1.1](README-fase1.1.md) | Falsos negativos | A cobertura do mascaramento passou a ser **medida** numa amostra estratificada de 200 linhas, não estimada. Variáveis especiais (`$1`, `$@`, `$?`) entraram com lookbehind — sem ele, `US$100` virava mascaramento pela metade, a pior saída possível. |
| [1.2](README-fase1.2.md) | Recall a 97,8% | O limite `[a-z]{2,6}` de extensões caiu e virou `extensions.txt`, editável. A regra que salva `e.g.` e `i.e.` ficou explícita — nenhuma extensão de uma letra —, com `ValueError` se alguém adicionar uma. **Zero parciais**: nenhum token parece protegido sem estar. |
| [2](README-fase2.md) | `normalize.py` e `segment.py` | Indentação sozinha não separa nada; **o que separa é o bloco**. Nenhum dos 828 segmentos de prosa passa de 400 tokens, o que fixou o teto de entrada do modelo. |
| [2.1](README-fase2.1.md) | Aspas e cabeçalhos | Literal entre aspas virou padrão de mascaramento com **zero falsos positivos**, e os cabeçalhos de seção passaram a vir de `headers.txt` (56 entradas) em vez do modelo, para que `SEE ALSO` seja sempre a mesma coisa. Recall a 96,8%. |
| [3](README-fase3.md) | Tradução NMT | CTranslate2 + Marian em int8, na CPU. Rejeição por validação: 9,0% dos parágrafos. Mediu também o que inviabilizava o uso interativo — 69 s por man page — e preparou o terreno para o cache. |
| [3.1](README-fase3.1.md) | Validação estrutural | **106 segmentos que a fase 3 aprovava passaram a ser rejeitados**, 15,1% do que ela aprovava, e cada um teria saído corrompido. Contagem de sentenças, repetição e delimitadores: o que os placeholders não pegam. |
| [4](README-fase4.md) | Cache em disco e CLI | **165 s a frio, 0,3 s quente — 500×.** A repetição que o cache explora é quase toda dentro do mesmo documento, não entre documentos. É a fase que transformou o experimento em algo que se digita sem pensar. |
| [5](README-fase5.md) | `--help` e colunas | Layout de duas colunas não é prosa nem literal: virou `SegmentKind.COLUMNS`. Das 109 unidades de `katana --help`, 100 saem em português com a coluna esquerda intacta. Zero tabelas detectadas no corpus de man — o resultado certo. |
| [6](README-fase6.md) | Omissão, listas, pager | Guarda de prosa por **documento**: sem ela, 86 dos 110 segmentos de `ls`, `ps aux` e `df -h` eram "traduzidos"; com ela, zero, e nenhuma inferência é gasta. Título de bloco virou cabeçalho e lista separada por vírgula virou padrão de máscara. |
| [7](README-fase7.md) | Distribuição | O modelo passou a ser baixado pronto: `torch` e `transformers` saíram das dependências. Build sem URL publicada falha na hora, com instrução, em vez de tentar baixar do nada. Duas métricas de omissão foram medidas e **recusadas** por falta de separação entre as populações. |
| [8](README-fase8.md) | Renomeação | `manbr` → `babelt`. Nada é migrado do nome antigo; `doctor` avisa dos diretórios órfãos. Corrigiu também o `build-model.sh`, que chamava `python` — inexistente em Debian e derivados. |

As fases 9 e 10 não têm documento próprio: estão no
[CHANGELOG](../../CHANGELOG.md).

## Estudo de caso

- [`caso-katana.md`](caso-katana.md) — a mesma saída de `katana --help`
  acompanhada ao longo do tempo: como saía na fase 4, o que a fase 5 consertou,
  o que a fase 6 consertou depois, e o que continua errado. Não é apêndice de
  uma fase: é um documento longitudinal, com os itens riscados conforme foram
  resolvidos. Serve de referência de qualidade para um `--help` denso de flags.

  *(Chamava-se `fase5-katana.md`. O nome sugeria apêndice da fase 5, e o
  conteúdo já atravessava três fases.)*

## O padrão

Cada documento abre com os comandos que reproduzem os números e fecha com o
que **não** foi resolvido. Uma hipótese medida e reprovada vale tanto quanto
uma aceita: as duas evitam que alguém refaça o mesmo caminho.
