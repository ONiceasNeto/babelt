#!/usr/bin/env bash
# Instalador do babelt.
#
#   ./install.sh              instala a partir deste clone
#   ./install.sh --no-model   instala sem baixar o modelo (230 MB)
#   ./install.sh --uninstall  remove tudo
#
# Cria um venv isolado em ~/.local/share/babelt/venv e um symlink em
# ~/.local/bin/babelt. O usuário nunca precisa ativar nada.

set -euo pipefail

PREFIX="${XDG_DATA_HOME:-$HOME/.local/share}/babelt"
VENV="$PREFIX/venv"
BINDIR="$HOME/.local/bin"
CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/babelt"
BIN="$BINDIR/babelt"
MIN_PY=11

say()  { printf '\033[1;34m::\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31mxx\033[0m %s\n' "$*" >&2; exit 1; }

uninstall() {
    say "Removendo $BIN"
    rm -f "$BIN"
    say "Removendo $VENV"
    rm -rf "$VENV"
    if [ -d "$PREFIX/models" ]; then
        # Sem terminal não há a quem perguntar, e apagar 230 MB por conta
        # própria é a escolha errada de default. `read` sem tty também
        # falharia, e com `set -e` levaria o script junto.
        if [ -t 0 ]; then
            printf 'Apagar o modelo em %s/models? [s/N] ' "$PREFIX"
            read -r r || r=""
        else
            r=""
            say "Sem terminal; mantendo o modelo."
        fi
        case "$r" in [sS]*) rm -rf "$PREFIX/models"; say "Modelo removido." ;;
                     *)     say "Modelo mantido em $PREFIX/models." ;;
        esac
    fi
    # O cache de tradução é derivado: sem o modelo e sem o binário ele não
    # serve para nada, e `doctor` reclamaria dele como órfão.
    if [ -d "$CACHE" ]; then
        say "Removendo o cache em $CACHE"
        rm -rf "$CACHE"
    fi
    rmdir "$PREFIX" 2>/dev/null || true
    say "Pronto."
    exit 0
}

find_python() {
    for c in python3.13 python3.12 python3.11 python3; do
        command -v "$c" >/dev/null 2>&1 || continue
        "$c" -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, $MIN_PY) else 1)" \
            2>/dev/null && { echo "$c"; return 0; }
    done
    return 1
}

hint_path() {
    case ":$PATH:" in *":$BINDIR:"*) return 0 ;; esac
    warn "$BINDIR não está no PATH. Adicione:"
    # shellcheck disable=SC2016  # $PATH tem que sair literal na sugestão
    case "$(basename "${SHELL:-sh}")" in
        fish) printf '\n    fish_add_path %s\n\n' "$BINDIR" ;;
        zsh)  printf '\n    echo '\''export PATH="%s:$PATH"'\'' >> ~/.zshrc\n\n' "$BINDIR" ;;
        *)    printf '\n    echo '\''export PATH="%s:$PATH"'\'' >> ~/.bashrc\n\n' "$BINDIR" ;;
    esac
}

WITH_MODEL=1
for a in "$@"; do
    case "$a" in
        --no-model)  WITH_MODEL=0 ;;
        --uninstall) uninstall ;;
        -h|--help)   sed -n '2,9p' "$0" | sed -e 's/^# \{0,1\}//'; exit 0 ;;
        *)           die "Opção desconhecida: $a" ;;
    esac
done

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$SRC/pyproject.toml" ] || die "pyproject.toml não encontrado em $SRC."

PY="$(find_python)" || die "Nenhum Python >= 3.$MIN_PY encontrado no PATH.
   Debian/Ubuntu/Mint: sudo apt install python3 python3-venv
   Fedora:             sudo dnf install python3
   Arch:               sudo pacman -S python
   Procurei por: python3.13, python3.12, python3.$MIN_PY, python3."
say "Python: $PY ($("$PY" -V 2>&1))"

if ! "$PY" -c 'import venv' 2>/dev/null; then
    die "Módulo venv ausente. No Debian/Ubuntu/Mint: sudo apt install python3-venv"
fi

say "Criando ambiente em $VENV"
mkdir -p "$PREFIX" "$BINDIR"
rm -rf "$VENV"
"$PY" -m venv "$VENV"

say "Instalando babelt e dependências"
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet "$SRC"

[ -x "$VENV/bin/babelt" ] || die "Instalação não gerou $VENV/bin/babelt."

say "Ligando $BIN"
ln -sfn "$VENV/bin/babelt" "$BIN"

if [ "$WITH_MODEL" -eq 1 ]; then
    # Espelha ensure_model() em babelt/__main__.py: ModelError é falha
    # prevista — rede, hash divergente, build sem URL — e não merece
    # traceback. O download em si já é idempotente e já checa is_installed.
    if ! "$VENV/bin/python" - <<'EOF'
from babelt.model import ModelError, download, is_installed, model_path
import sys

# A mensagem depende de haver o que baixar: anunciar "230 MB" numa
# reinstalação que não vai baixar nada é ruído.
if not is_installed(model_path()):
    print("babelt: baixando o modelo (~230 MB, uma vez só)", file=sys.stderr)

try:
    download(progress=True)
except ModelError as error:
    print(f"babelt: {error}", file=sys.stderr)
    sys.exit(1)
EOF
    then
        warn "Download do modelo falhou. O babelt está instalado e funciona"
        warn "sem traduzir; rode \`babelt ls\` mais tarde para tentar de novo."
    fi
else
    say "Modelo não baixado (--no-model). Será baixado no primeiro uso."
fi

hint_path
say "Instalado. Teste com:  babelt ls"
