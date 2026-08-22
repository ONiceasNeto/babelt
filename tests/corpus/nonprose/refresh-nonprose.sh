#!/usr/bin/env bash
# Regenera o corpus de saída que NÃO é prosa.
#
# Existe porque a fase 6 descobriu que `ls | babelt` traduzia nomes de arquivo
# ("Labs" -> "Laboratórios"). O projeto sempre assumiu entrada em prosa
# inglesa, e nada media o que acontece quando a premissa é falsa. Sem este
# corpus, a guarda de prosa seria calibrada contra duas populações que já
# eram prosa — e não separaria nada.
#
#     ./refresh-nonprose.sh          # regenera tudo
#     ./refresh-nonprose.sh ls ps    # regenera só esses
#
# O conteúdo é da máquina que rodou o script: nomes de arquivo, PIDs e
# interfaces mudam. Isso não importa — o que se mede é a *forma*, e a forma
# de `ps aux` é a mesma em qualquer lugar.
set -uo pipefail

cd "$(dirname "$0")"

LINES=${BABELT_CORPUS_LINES:-60}

run() {
  local name=$1; shift
  if [ ${#want[@]} -gt 0 ]; then
    local found=0
    for w in "${want[@]}"; do [ "$w" = "$name" ] && found=1; done
    [ $found -eq 1 ] || return 0
  fi
  if ! "$@" > "$name.txt.new" 2>/dev/null; then
    echo "aviso: $name indisponível, mantendo $name.txt" >&2
    rm -f "$name.txt.new"
    return 0
  fi
  sed -e 's/[[:space:]]*$//' "$name.txt.new" | head -n "$LINES" > "$name.txt"
  rm -f "$name.txt.new"
  echo "atualizado: $name.txt"
}

want=("$@")

run ls        ls /usr/share
run ls-la     ls -la /etc
run ps-aux    ps aux
run df-h      df -h
run ip-a      ip -o a
run journal   journalctl -n 40 --no-pager
