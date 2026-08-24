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

# Tudo o que o instalador fala vai para stderr, `say` inclusive. Antes `say`
# ia para stdout e `warn` para stderr, e as linhas se cruzavam na tela porque
# os dois fluxos não sincronizam: o aviso de PATH aparecia separado da
# sugestão que ele introduz. Um instalador não produz dado em stdout — tudo
# aqui é conversa —, e é o mesmo contrato que o babelt cumpre: stdout é
# resultado, stderr é recado.
say()  { printf '\033[1;34m::\033[0m %s\n' "$*" >&2; }
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
    for c in python3.14 python3.13 python3.12 python3.11 python3; do
        command -v "$c" >/dev/null 2>&1 || continue
        "$c" -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, $MIN_PY) else 1)" \
            2>/dev/null && { echo "$c"; return 0; }
    done
    return 1
}

# shellcheck disable=SC2088  # o ~ sai literal na linha que o usuário copia e
#                             # expande quando *ele* a executa, não aqui
hint_path() {
    case ":$PATH:" in *":$BINDIR:"*) return 0 ;; esac
    warn "$BINDIR não está no PATH. Adicione:"

    # O arquivo depende do shell, e errar aqui é pior que não dizer nada: a
    # instrução parece resolver, o usuário reabre o terminal e o comando
    # continua sem existir.
    #
    # `sh` cai em ~/.profile, e não em ~/.bashrc. Não é caso de borda: um
    # `useradd -m` sem `-s` cria a conta com /bin/sh, e no Alpine o shell do
    # sistema inteiro é ash. Os três leem ~/.profile no login; nenhum lê
    # ~/.bashrc.
    #
    # Shell desconhecido também vai para ~/.profile: é o arquivo que a maior
    # parte dos shells POSIX lê, e o palpite é dito como palpite.
    #
    # A sugestão vai para stderr junto com o aviso: em stdout ela aparecia
    # deslocada do `warn` que a introduz, porque os dois fluxos não sincronizam.
    shell_name="$(basename "${SHELL:-}")"
    case "$shell_name" in
        fish)
            printf '\n    fish_add_path %s\n\n' "$BINDIR" >&2
            return 0
            ;;
        bash) file="~/.bashrc" ;;
        zsh)  file="~/.zshrc" ;;
        sh|dash|ash) file="~/.profile" ;;
        *)    file="~/.profile" ;;
    esac

    # shellcheck disable=SC2016  # $PATH tem que sair literal na sugestão
    printf '\n    echo '\''export PATH="%s:$PATH"'\'' >> %s\n\n' \
        "$BINDIR" "$file" >&2

    case "$shell_name" in
        bash|zsh|sh|dash|ash) ;;
        "")  warn "Não consegui identificar seu shell (\$SHELL está vazio);"
             warn "~/.profile é o palpite conservador." ;;
        *)   warn "Não conheço o shell \`$shell_name\`; ~/.profile é o palpite"
             warn "conservador. Se ele não for lido, use o rc do seu shell." ;;
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
   Procurei por: python3.14, python3.13, python3.12, python3.$MIN_PY, python3."
say "Python: $PY ($("$PY" -V 2>&1))"

# `import venv` é a checagem errada em Debian e derivados: o módulo `venv` vem
# na stdlib de `python3` e importa, mas o que o pacote `python3-venv` carrega é
# o `ensurepip`, e é ele que falta. A guarda passava, `python3 -m venv` criava
# meio ambiente e o erro vinha do Python, já com o venv quebrado no disco.
if ! "$PY" -c 'import ensurepip' 2>/dev/null; then
    die "O Python encontrado não tem \`ensurepip\`, e sem ele \`venv\` não
   consegue montar um ambiente utilizável.
   Debian/Ubuntu/Mint: sudo apt install python3-venv
   Fedora:             sudo dnf install python3-pip
   Arch:               já vem com o pacote python"
fi

say "Criando ambiente em $VENV"
mkdir -p "$PREFIX" "$BINDIR"
rm -rf "$VENV"
# Um venv que falhou no meio não pode ficar no disco: a próxima execução o
# encontraria e o `[ -x "$VENV/bin/babelt" ]` lá embaixo daria um erro que não
# aponta para a causa.
if ! "$PY" -m venv "$VENV"; then
    rm -rf "$VENV"
    die "Falha ao criar o ambiente em $VENV. O diretório parcial foi removido."
fi

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
