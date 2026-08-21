#!/usr/bin/env bash
# Regenera o corpus de saída de --help a partir dos binários locais.
#
# Análogo ao refresh.sh das man pages, com três diferenças que importam:
#
# 1. **Executa o binário.** `man` lê um arquivo; `--help` roda o programa.
#    Por isso a lista é fixa e explícita: nada aqui é derivado de $PATH.
# 2. **Cada ferramenta usa um flag diferente.** Vários programas Go escrevem
#    a ajuda em stderr, e `docker` só aceita `--help` sem subcomando.
# 3. **A largura não é controlável.** Não existe MANWIDTH para --help: o
#    programa decide, e é justamente essa liberdade de layout — tabela de
#    duas colunas com a coluna direita em posição arbitrária — que a fase 5
#    precisa exercitar.
#
#     ./refresh-help.sh            # regenera tudo que estiver instalado
#     ./refresh-help.sh katana rg  # regenera só esses
#
# Ferramentas ausentes são puladas com aviso; o arquivo antigo fica.
set -uo pipefail

cd "$(dirname "$0")"

# nome_do_arquivo:comando:flag
TOOLS=(
  katana:katana:--help
  nmap:nmap:--help
  curl:curl:--help
  ffmpeg:ffmpeg:--help
  docker:docker:--help
  rg:rg:--help
  fd:fd:--help
  kubectl:kubectl:--help
)

LINES=${MANBR_CORPUS_LINES:-160}

want=("$@")

skipped=0
for entry in "${TOOLS[@]}"; do
  name=${entry%%:*}
  rest=${entry#*:}
  command_name=${rest%%:*}
  flag=${rest##*:}

  if [ ${#want[@]} -gt 0 ]; then
    found=0
    for w in "${want[@]}"; do [ "$w" = "$name" ] && found=1; done
    [ $found -eq 1 ] || continue
  fi

  if ! command -v "$command_name" > /dev/null 2>&1; then
    echo "aviso: $command_name não instalado, mantendo $name.txt" >&2
    skipped=$((skipped + 1))
    continue
  fi

  # 2>&1 porque metade das ferramentas Go escreve a ajuda em stderr, e
  # `|| true` porque várias saem com código 1 depois de imprimir a ajuda.
  # col -bx pela mesma razão do refresh.sh: tirar overstrike e expandir tabs
  # — tab dentro de tabela de duas colunas destruiria a posição da coluna.
  "$command_name" "$flag" 2>&1 | col -bx > "$name.txt.new" || true

  if [ ! -s "$name.txt.new" ]; then
    echo "aviso: $command_name $flag veio vazio, mantendo $name.txt" >&2
    rm -f "$name.txt.new"
    skipped=$((skipped + 1))
    continue
  fi

  sed -e 's/[[:space:]]*$//' "$name.txt.new" | head -n "$LINES" > "$name.txt"
  rm -f "$name.txt.new"
  echo "atualizado: $name.txt"
done

[ $skipped -gt 0 ] && echo "$skipped ferramenta(s) puladas." >&2
exit 0
