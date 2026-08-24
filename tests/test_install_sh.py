"""Testes de `install.sh`.

O instalador não é Python, mas quebra do mesmo jeito e quebra pior: um erro
aqui acontece antes de o usuário ter o programa, e ele não tem como
diagnosticar. Os testes rodam as funções do script isoladamente, em `bash`,
sem instalar nada.

O que se testa é a **decisão**, não o efeito: se `hint_path` nomeia o arquivo
certo para cada shell. Que a linha sugerida de fato funcione depois de um
login novo foi verificado em container, com `useradd -s` e login interativo
de verdade — não dá para reproduzir isso numa suíte de unidade.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

INSTALL_SH = Path(__file__).parent.parent / "install.sh"

#: Corpo de `hint_path`, extraído do script. Extrair em vez de rodar o
#: instalador inteiro: a função decide sozinha e o resto do script cria venv,
#: baixa 230 MB e escreve no disco do usuário.
_HINT_PATH_RE = re.compile(r"^hint_path\(\) \{.*?^\}", re.MULTILINE | re.DOTALL)


def hint_path_source() -> str:
    body = _HINT_PATH_RE.search(INSTALL_SH.read_text(encoding="utf-8"))
    assert body is not None, "hint_path não encontrada em install.sh"
    return body.group(0)


def run_hint_path(shell: str, *, home: Path, path: str = "/usr/bin:/bin") -> str:
    """Roda `hint_path` com `$SHELL` dado e devolve o que ela escreveu."""
    script = f"""
    BINDIR="$HOME/.local/bin"
    warn() {{ printf '!! %s\\n' "$*" >&2; }}
    {hint_path_source()}
    hint_path
    """
    result = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        env={"HOME": str(home), "SHELL": shell, "PATH": path},
        check=False,
    )
    return result.stdout + result.stderr


pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None, reason="bash não disponível"
)


class TestHintPath:
    """O arquivo de rc certo para cada shell.

    Todo shell que não fosse fish nem zsh caía no ramo do bash e mandava
    escrever em `~/.bashrc`. Isso está errado para `sh`, e não é caso de
    borda: `useradd -m` sem `-s` cria a conta com `/bin/sh`, e no Alpine o
    shell do sistema inteiro é `ash`. Nenhum dos três lê `~/.bashrc`, então a
    instrução parecia resolver, o usuário reabria o terminal e o comando
    continuava sem existir.
    """

    @pytest.mark.parametrize(
        ("shell", "expected"),
        [
            ("/bin/sh", "~/.profile"),
            ("/bin/dash", "~/.profile"),
            ("/bin/ash", "~/.profile"),
            ("/bin/bash", "~/.bashrc"),
            ("/bin/zsh", "~/.zshrc"),
        ],
    )
    def test_arquivo_por_shell(self, shell: str, expected: str, tmp_path: Path) -> None:
        assert f">> {expected}" in run_hint_path(shell, home=tmp_path)

    def test_sh_nao_manda_escrever_no_bashrc(self, tmp_path: Path) -> None:
        """O defeito, dito pelo nome. `dash` não lê `~/.bashrc`."""
        assert ".bashrc" not in run_hint_path("/bin/sh", home=tmp_path)

    def test_fish_usa_o_comando_proprio(self, tmp_path: Path) -> None:
        """fish não tem `export`, e escrever no rc dele à mão é o caminho errado."""
        out = run_hint_path("/usr/bin/fish", home=tmp_path)
        assert "fish_add_path" in out
        assert "export PATH" not in out

    def test_shell_desconhecido_cai_no_profile_e_avisa(self, tmp_path: Path) -> None:
        """Palpite dito como palpite vale mais que palpite silencioso."""
        out = run_hint_path("/bin/tcsh", home=tmp_path)
        assert ">> ~/.profile" in out
        assert "tcsh" in out
        assert "palpite" in out

    def test_shell_vazio_cai_no_profile_e_avisa(self, tmp_path: Path) -> None:
        out = run_hint_path("", home=tmp_path)
        assert ">> ~/.profile" in out
        assert "palpite" in out

    def test_o_til_sai_literal(self, tmp_path: Path) -> None:
        """A linha é para copiar e colar: o `~` expande na mão do usuário.

        Se `hint_path` expandisse o til, a sugestão traria o home de quem
        rodou o instalador — que numa instalação via `sudo` é o do root.
        """
        out = run_hint_path("/bin/bash", home=tmp_path)
        assert ">> ~/.bashrc" in out
        assert str(tmp_path / ".bashrc") not in out

    def test_bindir_sai_expandido(self, tmp_path: Path) -> None:
        """O caminho do binário, ao contrário, precisa ser o real."""
        out = run_hint_path("/bin/bash", home=tmp_path)
        assert str(tmp_path / ".local" / "bin") in out

    def test_cala_quando_ja_esta_no_path(self, tmp_path: Path) -> None:
        bindir = tmp_path / ".local" / "bin"
        out = run_hint_path("/bin/sh", home=tmp_path, path=f"{bindir}:/usr/bin")
        assert out.strip() == ""
