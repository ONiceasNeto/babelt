#!/usr/bin/env bash
# Regenera o corpus a partir das man pages locais.
#
# O corpus versionado foi gerado por este script (Ubuntu 24.04). Rode-o de
# novo para atualizar, ou noutra distro para pegar variações de formatação —
# o teste de round-trip vale para qualquer entrada, então trocar o corpus não
# quebra nada; só muda o que está sendo exercitado.
#
#     ./refresh.sh            # regenera tudo que estiver disponível
#     ./refresh.sh tar find   # regenera só esses
#
# Páginas ausentes são puladas com aviso — o corpus antigo é preservado.
set -uo pipefail

cd "$(dirname "$0")"

# nome_do_arquivo:página_de_man
PAGES=(
  ss:ss ip:ip tar:tar find:find grep:grep awk:awk sed:sed
  systemctl:systemctl journalctl:journalctl rsync:rsync ssh:ssh
  curl:curl git-log:git-log dd:dd lsblk:lsblk mount:mount
  iptables:iptables nmap:nmap chmod:chmod ps:ps
)

# Quantas linhas guardar por página. O suficiente para pegar SYNOPSIS,
# DESCRIPTION e uma boa parte das OPTIONS.
LINES=${MANBR_CORPUS_LINES:-160}

want=("$@")

skipped=0
for entry in "${PAGES[@]}"; do
  name=${entry%%:*}
  page=${entry##*:}

  if [ ${#want[@]} -gt 0 ]; then
    found=0
    for w in "${want[@]}"; do [ "$w" = "$name" ] && found=1; done
    [ $found -eq 1 ] || continue
  fi

  # col -bx tira o overstrike (negrito por backspace) e expande tabs, senão o
  # corpus fica cheio de \b e a comparação de round-trip testa a coisa errada.
  if ! MANWIDTH=78 man "$page" 2>/dev/null | col -bx > "$name.txt.new"; then
    echo "aviso: man $page indisponível, mantendo $name.txt" >&2
    rm -f "$name.txt.new"
    skipped=$((skipped + 1))
    continue
  fi

  if [ ! -s "$name.txt.new" ]; then
    echo "aviso: man $page veio vazio, mantendo $name.txt" >&2
    rm -f "$name.txt.new"
    skipped=$((skipped + 1))
    continue
  fi

  # Descarta o cabeçalho/rodapé de paginação e limita o tamanho.
  sed -e 's/[[:space:]]*$//' "$name.txt.new" | head -n "$LINES" > "$name.txt"
  rm -f "$name.txt.new"
  echo "atualizado: $name.txt"
done

[ $skipped -gt 0 ] && echo "$skipped página(s) puladas." >&2
exit 0
