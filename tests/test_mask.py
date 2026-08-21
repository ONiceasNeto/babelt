"""Testes de mask/restore.

O invariante que importa é o round-trip: qualquer que seja o texto, mascarar
e restaurar tem que devolver os mesmos bytes. Tudo o mais (quais tokens são
capturados, quais falsos positivos são evitados) é qualidade de tradução, não
correção — mas é testado aqui porque a qualidade é o motivo do módulo existir.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from manbr.mask import CLOSE, EXTENSIONS, OPEN, mask, restore

CORPUS_DIR = Path(__file__).parent / "corpus"

# Casos que devem virar exatamente um placeholder cobrindo o texto inteiro.
SINGLE_TOKEN: list[str] = [
    "-sS",
    "-o",
    "-T4",
    "--script-args=http-*",
    "--verbose",
    "--exclude-dir=GLOB",
    "/etc/services",
    "/var/log/",
    "`ss -tulpn`",
    "<interface>",
    "$HOME",
    "${PATH}",
]

NOT_MASKED: list[str] = [
    "well-known",
    "port 1-1024",
    "read-only",
    "1/2",
    "e.g.",
    "i.e.",
    "and/or",
    "n/a",
    "a / b",
    "/",
    "- item de lista",
    "um travessão - assim",
    "Esta linha não tem nenhum token protegido.",
    "",
]

ROUND_TRIP_CASES: list[str] = [
    *SINGLE_TOKEN,
    *NOT_MASKED,
    "-o output.txt",
    "./run.sh",
    "../bin/tool",
    "/home/user/.bashrc",
    "~/.ssh/config",
    "scanme.nmap.org",
    "backup.tar.gz",
    "arquivo em ~/ e nada mais",
    "$HOME",
    "${PATH}",
    "`ss -tulpn`",
    "<interface>",
    "<file>",
    "Use --verbose com /etc/services e $HOME, e.g. read-only.",
    "veja /dev/null.",
    f"texto com {OPEN} e {CLOSE} dentro",
    f"{OPEN}0{CLOSE}",
    f"{OPEN}{OPEN}0{CLOSE}{CLOSE}",
    f"{OPEN}",
    f"{CLOSE}{CLOSE}",
    "linha um\nlinha dois com -v\n",
    "   indentado com --flag   ",
]


def masked_tokens(text: str) -> list[str]:
    """Os literais capturados, na ordem em que aparecem."""
    result = mask(text)
    return [result.tokens[i] for i in sorted(result.tokens)]


# --------------------------------------------------------------------------
# Round-trip
# --------------------------------------------------------------------------


@pytest.mark.parametrize("text", ROUND_TRIP_CASES)
def test_round_trip(text: str) -> None:
    result = mask(text)
    assert restore(result.text, result.tokens) == text


def test_round_trip_de_texto_composto() -> None:
    text = "\n".join(ROUND_TRIP_CASES)
    result = mask(text)
    assert restore(result.text, result.tokens) == text


# --------------------------------------------------------------------------
# Padrões que devem ser capturados
# --------------------------------------------------------------------------


@pytest.mark.parametrize("text", SINGLE_TOKEN)
def test_token_unico_cobre_o_texto_inteiro(text: str) -> None:
    result = mask(text)
    assert result.text == f"{OPEN}0{CLOSE}"
    assert result.tokens == {0: text}


def test_flag_curta_composta() -> None:
    assert masked_tokens("nmap -sS -T4 alvo") == ["-sS", "-T4"]


def test_flag_longa_com_valor() -> None:
    assert masked_tokens("--script-args=http-*") == ["--script-args=http-*"]


def test_flag_curta_com_argumento_separado() -> None:
    assert masked_tokens("-o output.txt") == ["-o", "output.txt"]


@pytest.mark.parametrize(
    "text",
    [
        "/etc/services",
        "/var/log/",
        "./run.sh",
        "../bin/tool",
        "/home/user/.bashrc",
        "~/.ssh/config",
        "~/.ssh/id_ed25519",
        "~/",
    ],
)
def test_caminhos(text: str) -> None:
    assert masked_tokens(text) == [text]


def test_til_entra_no_placeholder() -> None:
    """Um ~ exposto vira um caminho errado se a tradução o perder."""
    assert mask("veja ~/.ssh/config").text == f"veja {OPEN}0{CLOSE}"


def test_til_solto_nao_e_caminho() -> None:
    assert mask("aproximadamente ~ isso").tokens == {}


def test_caminho_nao_engole_ponto_final_da_frase() -> None:
    assert masked_tokens("veja /dev/null.") == ["/dev/null"]
    assert mask("veja /dev/null.").text == f"veja {OPEN}0{CLOSE}."


@pytest.mark.parametrize("text", ["$HOME", "${PATH}", "$API_URL"])
def test_variaveis(text: str) -> None:
    assert masked_tokens(text) == [text]


@pytest.mark.parametrize("text", ["<interface>", "<file>", "<port-range>"])
def test_blocos_angulares(text: str) -> None:
    assert masked_tokens(text) == [text]


def test_crase_vira_um_unico_placeholder() -> None:
    """Uma crase contendo flags é um token só, não um por flag."""
    result = mask("Rode `ss -tulpn` para ver.")
    assert result.tokens == {0: "`ss -tulpn`"}
    assert result.text == f"Rode {OPEN}0{CLOSE} para ver."


def test_crase_tem_precedencia_sobre_caminho() -> None:
    assert masked_tokens("`cat /etc/passwd`") == ["`cat /etc/passwd`"]


def test_crase_nao_atravessa_linha() -> None:
    """Uma crase sem par não pode engolir o resto do texto."""
    result = mask("`aberta\n--flag")
    assert "--flag" in result.tokens.values()


def test_nomes_com_ponto() -> None:
    assert masked_tokens("baixe example.com e output.txt") == [
        "example.com",
        "output.txt",
    ]


@pytest.mark.parametrize("text", ["scanme.nmap.org", "backup.tar.gz", "a.b.c.info"])
def test_nome_com_varios_rotulos_e_um_placeholder_so(text: str) -> None:
    """Mascarar só 'scanme.nmap' deixaria '.org' exposto à tradução."""
    assert masked_tokens(text) == [text]


@pytest.mark.parametrize("text", ["versão 1.2.3 aqui", "a frase termina.Assim"])
def test_nome_com_ponto_nao_pega_numero_nem_frase_colada(text: str) -> None:
    assert mask(text).tokens == {}


# --------------------------------------------------------------------------
# Falsos positivos
# --------------------------------------------------------------------------


@pytest.mark.parametrize("text", NOT_MASKED)
def test_nao_mascarado(text: str) -> None:
    result = mask(text)
    assert result.tokens == {}
    assert result.text == text


def test_hifen_de_palavra_composta_em_frase() -> None:
    text = "Portas well-known são read-only no intervalo 1-1024."
    assert mask(text).tokens == {}


def test_abreviacoes_latinas_em_frase() -> None:
    text = "Use, e.g., o modo padrão; i.e. sem argumentos."
    assert mask(text).tokens == {}


# --------------------------------------------------------------------------
# Escape das chaves
# --------------------------------------------------------------------------


def test_chaves_do_texto_sao_escapadas() -> None:
    result = mask(f"a {OPEN} b {CLOSE} c")
    assert result.text == f"a {OPEN}{OPEN} b {CLOSE}{CLOSE} c"
    assert result.tokens == {}


def test_placeholder_falso_no_texto_de_entrada() -> None:
    """Texto que já contém ⟦0⟧ não pode ser confundido com um placeholder."""
    text = f"literal {OPEN}0{CLOSE} aqui"
    result = mask(text)
    assert result.tokens == {}
    assert result.text != text
    assert restore(result.text, result.tokens) == text


def test_placeholder_falso_convive_com_token_real() -> None:
    text = f"{OPEN}0{CLOSE} e --flag"
    result = mask(text)
    assert result.tokens == {0: "--flag"}
    assert restore(result.text, result.tokens) == text


# --------------------------------------------------------------------------
# Detalhes da API
# --------------------------------------------------------------------------


def test_indices_sequenciais_na_ordem_de_aparicao() -> None:
    result = mask("-a /tmp/x $VAR")
    assert result.tokens == {0: "-a", 1: "/tmp/x", 2: "$VAR"}


def test_literais_repetidos_recebem_indices_distintos() -> None:
    result = mask("-v e -v de novo")
    assert result.tokens == {0: "-v", 1: "-v"}
    assert restore(result.text, result.tokens) == "-v e -v de novo"


def test_restore_deixa_placeholder_desconhecido_intacto() -> None:
    """restore não inventa nada; validate é quem rejeita."""
    assert restore(f"x {OPEN}7{CLOSE}", {}) == f"x {OPEN}7{CLOSE}"


def test_restore_aceita_reordenacao() -> None:
    result = mask("copie -r /tmp")
    reordered = f"{OPEN}1{CLOSE} recursivamente com {OPEN}0{CLOSE}"
    assert restore(reordered, result.tokens) == "/tmp recursivamente com -r"


def test_mask_result_e_imutavel() -> None:
    result = mask("-v")
    with pytest.raises(AttributeError):
        result.text = "outro"  # type: ignore[misc]


# --------------------------------------------------------------------------
# Corpus
# --------------------------------------------------------------------------


def corpus_files() -> list[Path]:
    return sorted(CORPUS_DIR.glob("*.txt"))


def test_corpus_esta_presente() -> None:
    names = {path.stem for path in corpus_files()}
    expected = {
        "ss", "ip", "tar", "find", "grep", "awk", "sed", "systemctl",
        "journalctl", "rsync", "ssh", "curl", "git-log", "dd", "lsblk",
        "mount", "iptables", "nmap", "chmod", "ps",
    }
    assert expected <= names


@pytest.mark.parametrize("path", corpus_files(), ids=lambda p: p.stem)
def test_corpus_round_trip(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    result = mask(text)
    assert restore(result.text, result.tokens) == text


@pytest.mark.parametrize("path", corpus_files(), ids=lambda p: p.stem)
def test_corpus_round_trip_linha_a_linha(path: Path) -> None:
    """mask opera sobre texto segmentado; a unidade real é a linha."""
    for line in path.read_text(encoding="utf-8").splitlines():
        result = mask(line)
        assert restore(result.text, result.tokens) == line


@pytest.mark.parametrize("path", corpus_files(), ids=lambda p: p.stem)
def test_corpus_captura_algum_token(path: Path) -> None:
    """Um corpus de man page sem nenhum token protegido não testa nada."""
    assert mask(path.read_text(encoding="utf-8")).tokens


# --------------------------------------------------------------------------
# Fase 1.1 — falsos negativos fechados
# --------------------------------------------------------------------------


class TestFimDeOpcoes:
    """`--` isolado muda o que o comando faz; perdê-lo é corromper sintaxe."""

    @pytest.mark.parametrize(
        "text",
        ["--", "use -- para terminar", "cmd -- -arquivo-com-hifen", "cmd --"],
    )
    def test_hifen_duplo_isolado_e_mascarado(self, text: str) -> None:
        assert "--" in mask(text).tokens.values()

    def test_hifen_duplo_sozinho_vira_placeholder_unico(self) -> None:
        assert mask("--").text == f"{OPEN}0{CLOSE}"

    def test_nao_confunde_com_flag_longa(self) -> None:
        assert masked_tokens("--verbose") == ["--verbose"]
        assert masked_tokens("-- --verbose") == ["--", "--verbose"]

    def test_regua_de_hifens_nao_e_mascarada(self) -> None:
        """---- é decoração de página, não fim de opções."""
        assert mask("----").tokens == {}
        assert mask("--------").tokens == {}

    def test_round_trip(self) -> None:
        text = "tar -x -- ./-arquivo"
        result = mask(text)
        assert restore(result.text, result.tokens) == text


class TestFlagsComAlternativas:
    """-sS/sT/sA é um token só: mascarar só -sS deixa /sT/sA exposto."""

    @pytest.mark.parametrize(
        "text",
        [
            "-sS/sT/sA/sW/sM",
            "-PS/PA/PU/PY",
            "-R/-r",
            "-n/-R",
            "-I/usr/include",
        ],
    )
    def test_alternativas_num_placeholder_unico(self, text: str) -> None:
        assert masked_tokens(text) == [text]

    def test_para_no_delimitador(self) -> None:
        assert masked_tokens("-sS/sT/sA/sW/sM: TCP SYN scans") == [
            "-sS/sT/sA/sW/sM"
        ]

    def test_valor_colado_da_tar(self) -> None:
        """A tar documenta -g/tmp/snar.db, com o valor colado na flag."""
        assert masked_tokens("como em -g/tmp/snar.db.") == ["-g/tmp/snar.db"]

    def test_nao_atravessa_espaco(self) -> None:
        assert masked_tokens("-o /tmp/saida") == ["-o", "/tmp/saida"]

    def test_alternativa_exige_letra(self) -> None:
        """-x/2 não é uma alternativa de flag; o /2 fica de fora."""
        assert masked_tokens("-x/2") == ["-x"]


class TestEnderecosIP:
    @pytest.mark.parametrize(
        "text",
        [
            "10.0.0.1",
            "192.168.0.0/24",
            "127.0.0.1",
            "::1",
            "::",
            "fe80::/10",
            "2001:db8::1",
            "fe80::3",
            "2001:0db8:0000:0000:0000:ff00:0042:8329",
        ],
    )
    def test_ip_e_mascarado(self, text: str) -> None:
        assert masked_tokens(text) == [text]

    def test_cidr_entra_no_placeholder(self) -> None:
        """Precedência acima de caminhos, senão o /24 ficaria exposto."""
        assert mask("rede 192.168.0.0/24 aqui").text == f"rede {OPEN}0{CLOSE} aqui"

    @pytest.mark.parametrize(
        "text",
        [
            "18:17:16",
            "2012-10-30 18:17:16",
            "aa:bb:cc:dd:ee:ff",
            "versão 1.2.3",
            "U:53,111,T:21-25,80",
            "das 9:00 às 18:00",
        ],
    )
    def test_nao_e_ip(self, text: str) -> None:
        assert mask(text).tokens == {}


class TestVariaveisEspeciais:
    @pytest.mark.parametrize("text", ["$1", "$3", "$@", "$$", "$?", "$*", "$#"])
    def test_variavel_especial(self, text: str) -> None:
        assert masked_tokens(text) == [text]

    def test_campos_do_awk(self) -> None:
        assert masked_tokens("awk '{ print $1, $3 }'") == ["$1", "$3"]

    def test_pid_do_shell(self) -> None:
        assert masked_tokens("ps -p $$ -o comm=") == ["-p", "$$", "-o", "comm="]

    @pytest.mark.parametrize(
        "text",
        ["$HOME/.secret", "$PREFIX/bin/tool", "${DIR}/sub/", "$HOME/.ssh/config"],
    )
    def test_variavel_absorve_o_caminho_seguinte(self, text: str) -> None:
        """O lookbehind do padrão de caminho barra o / colado no E de $HOME.

        Sem absorver o sufixo aqui, /.secret ficava exposto à tradução — o
        mesmo mascaramento pela metade de ~/.ssh/config na fase 1.
        """
        assert masked_tokens(text) == [text]

    def test_variavel_nao_engole_ponto_final(self) -> None:
        assert masked_tokens("veja $HOME/.secret.") == ["$HOME/.secret"]

    @pytest.mark.parametrize("text", ["US$100", "R$5", "custa US$100 hoje"])
    def test_dinheiro_nao_e_variavel(self, text: str) -> None:
        """Um $ colado numa letra é moeda. Mascarar $100 partiria US$100."""
        assert mask(text).tokens == {}


class TestBlocosAngularesRicos:
    @pytest.mark.parametrize(
        "text",
        [
            "<n1=v1,[n2=v2,...]>",
            "<host1[,host2][,host3],...>",
            "<user:password>",
            "<header/@file>",
            "<0-5>",
            "<https://www.gnu.org/software/sed/>",
            "<bug-sed@gnu.org>",
        ],
    )
    def test_bloco_angular_com_pontuacao(self, text: str) -> None:
        assert masked_tokens(text) == [text]

    def test_espaco_interrompe(self) -> None:
        """Sem essa regra, uma comparação em prosa viraria placeholder."""
        assert mask("se a < b > c então").tokens == {}

    def test_flag_com_argumento_angular(self) -> None:
        assert masked_tokens("-T<0-5>") == ["-T", "<0-5>"]


class TestExpressaoSed:
    @pytest.mark.parametrize(
        "text",
        [
            "s/regexp/replacement/",
            "s/a/b/g",
            "s/^#Permit.*/Permit no/",
            "s/[0-9]{1,3}/<ip>/g",
            "y/abc/def/",
        ],
    )
    def test_expressao_sed(self, text: str) -> None:
        assert masked_tokens(text) == [text]

    def test_dentro_de_um_comando(self) -> None:
        """Entre aspas, o literal citado cobre a expressão inteira."""
        assert masked_tokens("sed -i 's/^#A.*/B no/' /etc/ssh/sshd_config") == [
            "-i",
            "'s/^#A.*/B no/'",
            "/etc/ssh/sshd_config",
        ]

    def test_sem_aspas_o_padrao_sed_e_quem_pega(self) -> None:
        assert masked_tokens("sed -i s/^#A.*/Bno/ /etc/fstab") == [
            "-i",
            "s/^#A.*/Bno/",
            "/etc/fstab",
        ]

    @pytest.mark.parametrize(
        "text",
        [
            "refs/heads/, refs/tags/ e refs/remotes/",
            "/sys/module/fuse",
            "the options/flags list",
            "veja /usr/share/doc/",
        ],
    )
    def test_nao_confunde_caminho_com_expressao_sed(self, text: str) -> None:
        """O s de /sys e o de refs/ vêm depois de \\w ou /; o lookbehind barra."""
        for token in masked_tokens(text):
            assert not token.startswith("s/")


# --------------------------------------------------------------------------
# Fase 1.2 — parciais fechados, URLs, chave=valor, extensões
# --------------------------------------------------------------------------


class TestURLs:
    """Uma URL é feita de palavras em inglês — o que o NMT mais gosta de traduzir."""

    @pytest.mark.parametrize(
        "text",
        [
            "https://download.samba.org/pub/rsync/rsync.1",
            "http://site.{one,two,three}.com",
            "http://example.com/archive[1996-1999]/vol[1-4]/part{a,b,c}.html",
            "protocol://",
            "rsync://",
            "ftp://ftp.example.com/pub",
            "git://git.kernel.org/pub/scm",
            "ssh://user@host:22/path",
            "http://[fe80::3%25eth0]/",
        ],
    )
    def test_url_inteira_num_placeholder(self, text: str) -> None:
        assert masked_tokens(text) == [text]

    def test_esquema_entra_no_placeholder(self) -> None:
        """Mascarar só o host deixaria https:// exposto — falha pela metade."""
        result = mask("veja https://gnu.org/x aqui")
        assert result.tokens == {0: "https://gnu.org/x"}

    def test_devolve_a_pontuacao_final(self) -> None:
        assert masked_tokens("baixe de https://a.org/b.") == ["https://a.org/b"]

    def test_para_nas_aspas(self) -> None:
        """Sem aspas em volta, a URL para onde a linha para."""
        assert masked_tokens("veja http://example.com/x aqui") == [
            "http://example.com/x"
        ]

    def test_url_entre_aspas_vira_um_token_com_as_aspas(self) -> None:
        """A partir da fase 2.1 a citação inteira é o literal, como na crase."""
        assert masked_tokens('"http://example.com/x"') == [
            '"http://example.com/x"'
        ]

    def test_url_entre_angulares_e_um_token_so(self) -> None:
        text = "<https://www.gnu.org/software/sed/>"
        assert masked_tokens(text) == [text]


class TestChaveValor:
    @pytest.mark.parametrize(
        "text",
        [
            "conv=CONVS",
            "oflag=sync",
            "c=1",
            "K=1024",
            "MB=1000*1000",
            "xM=M",
            "PARTUUID=uuid",
            "Storage=",
            "time=TIME",
            "pid=",
            "if=/dev/zero",
        ],
    )
    def test_operando_chave_valor(self, text: str) -> None:
        assert masked_tokens(text) == [text]

    def test_para_na_virgula(self) -> None:
        assert masked_tokens("c=1, w=2, b=512") == ["c=1", "w=2", "b=512"]

    def test_devolve_pontuacao_e_parenteses(self) -> None:
        assert masked_tokens("(time=TIME), e (ucmd=CMD).") == [
            "time=TIME",
            "ucmd=CMD",
        ]

    @pytest.mark.parametrize(
        "text",
        [
            "a = b",
            "o resultado = 4 aqui",
            "se x = y então",
        ],
    )
    def test_igual_com_espaco_e_prosa(self, text: str) -> None:
        """O = precisa estar colado no nome; é isso que segura a prosa."""
        assert mask(text).tokens == {}

    def test_flag_longa_tem_precedencia(self) -> None:
        """--flag=valor é da regra 6, não da chave=valor."""
        assert masked_tokens("--reference=RFILE") == ["--reference=RFILE"]
        assert masked_tokens("--file=script-file") == ["--file=script-file"]

    def test_nome_com_ponto(self) -> None:
        assert masked_tokens("log.excludeDecoration=true") == [
            "log.excludeDecoration=true"
        ]


class TestExtensoesPorLista:
    def test_sufixo_longo_de_unit(self) -> None:
        """.service tem 7 letras e caía fora do antigo [a-z]{2,6}."""
        assert masked_tokens("systemd-initctl.service") == ["systemd-initctl.service"]
        assert masked_tokens("proc-sys.automount") == ["proc-sys.automount"]

    @pytest.mark.parametrize(
        "text",
        ["a.timer", "a.socket", "a.device", "a.path", "a.mount", "a.target"],
    )
    def test_sufixos_curtos_continuam(self, text: str) -> None:
        assert masked_tokens(text) == [text]

    @pytest.mark.parametrize(
        "text", ["example.com", "www.gnu.org", "knuth.cwi.nl", "gpl.html"]
    )
    def test_dominios_continuam(self, text: str) -> None:
        assert masked_tokens(text) == [text]

    @pytest.mark.parametrize("text", ["e.g.", "i.e.", "versão 1.2.3", "obj.getName"])
    def test_prosa_continua_fora(self, text: str) -> None:
        assert mask(text).tokens == {}

    def test_lista_nao_tem_extensao_de_uma_letra(self) -> None:
        """É essa regra que mantém 'e.g.' e 'i.e.' fora, agora que o limite
        inferior do {2,6} não existe mais."""
        assert all(len(extension) >= 2 for extension in EXTENSIONS)

    def test_lista_carregada_do_arquivo(self) -> None:
        assert "service" in EXTENSIONS
        assert "automount" in EXTENSIONS
        assert len(EXTENSIONS) > 50


class TestHostCaminho:
    @pytest.mark.parametrize(
        "text", ["knuth.cwi.nl:/dir", "foo:src/bar/", "host:/etc/fstab"]
    )
    def test_host_dois_pontos_caminho(self, text: str) -> None:
        assert masked_tokens(text) == [text]

    def test_dois_pontos_nao_fica_exposto(self) -> None:
        result = mask("como knuth.cwi.nl:/dir.")
        assert result.text == f"como {OPEN}0{CLOSE}."

    @pytest.mark.parametrize(
        "text", ["U:53,111", "18:17:16", "Nota:veja isso", "HOST:SRC..."]
    )
    def test_exige_barra_depois_dos_dois_pontos(self, text: str) -> None:
        for token in masked_tokens(text):
            assert ":" not in token


class TestGrupoColadoNaFlagOuCaminho:
    def test_expansao_de_chaves_no_caminho(self) -> None:
        text = "/dev/disk/by-{label,uuid,id,partuuid,partlabel}"
        assert masked_tokens(text) == [text]

    def test_grupo_colchetado_na_flag(self) -> None:
        assert masked_tokens("-i[SUFFIX]") == ["-i[SUFFIX]"]

    def test_grupo_sem_fechar_da_ip(self) -> None:
        text = "-c[color][={always|auto|never}"
        assert masked_tokens(text) == [text]

    def test_grupo_com_espaco_nao_e_absorvido(self) -> None:
        """-PO[protocol list] viraria -PO[protocol, expondo ' list]'."""
        assert masked_tokens("-PO[protocol list]") == ["-PO"]

    def test_colchete_de_sinopse_nao_e_absorvido(self) -> None:
        assert masked_tokens("mount [-fnrsvw] [-t fstype]") == ["-fnrsvw", "-t"]


class TestValorAngularNaFlagLonga:
    def test_valor_com_espaco_dentro_de_angulares(self) -> None:
        """--script-help=<Lua scripts> parava no espaço e expunha ' scripts>'."""
        text = "--script-help=<Lua scripts>"
        assert masked_tokens(text) == [text]

    def test_valor_normal_continua(self) -> None:
        assert masked_tokens("--script-args=http-*") == ["--script-args=http-*"]

    def test_nao_atravessa_a_linha(self) -> None:
        """Sem par na mesma linha, o valor cai no ramo \\S+ e para no fim dela."""
        for token in masked_tokens("--opt=<a\nb>"):
            assert "\n" not in token


class TestGlob:
    @pytest.mark.parametrize("text", ["*.c", "*.log", "*.tar-gz"])
    def test_glob_de_extensao(self, text: str) -> None:
        assert masked_tokens(text) == [text]

    def test_glob_nao_consulta_a_lista(self) -> None:
        """*.c tem extensão de uma letra, que a lista proíbe de propósito."""
        assert masked_tokens("(*.c)") == ["*.c"]


class TestAjustesFinaisDaFase12:
    def test_sigilo_percent_da_curl(self) -> None:
        """--variable %name=content: sem o %, o sigilo ficava exposto."""
        assert masked_tokens("--variable %name=content") == [
            "--variable",
            "%name=content",
        ]

    def test_pacote_de_flags_comecando_com_digito(self) -> None:
        text = "-46AaCfGgKkMNnqsTtVvXxYy"
        assert masked_tokens(text) == [text]

    @pytest.mark.parametrize(
        "text", ["a NUM of -1 is", "port 1-1024", "2012-10-30", "1-10"]
    )
    def test_numero_negativo_em_prosa_nao_e_flag(self, text: str) -> None:
        """Um flag que comece com dígito precisa conter ao menos uma letra."""
        assert mask(text).tokens == {}

    @pytest.mark.parametrize("text", ["./", "../"])
    def test_prefixo_relativo_sozinho(self, text: str) -> None:
        assert masked_tokens(text) == [text]

    def test_ponto_final_seguido_de_caminho(self) -> None:
        assert masked_tokens("fim. /usr") == ["/usr"]
