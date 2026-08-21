"""Mascaramento de tokens críticos de sintaxe de comando.

O modelo NMT não pode ver flags, caminhos ou variáveis: ele os traduziria.
Antes de traduzir, substituímos cada token crítico por um placeholder opaco
``⟦n⟧`` e guardamos o literal original. Depois da tradução, ``restore``
recoloca os literais byte a byte.

A garantia de integridade não está aqui — está em :mod:`manbr.validate`, que
rejeita qualquer tradução que tenha perdido, duplicado ou inventado um
placeholder. Este módulo só precisa ser reversível.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

__all__ = [
    "CLOSE",
    "EXTENSIONS",
    "MAX_QUOTED_WORDS",
    "OPEN",
    "MaskResult",
    "mask",
    "restore",
]

#: U+27E6 MATHEMATICAL LEFT WHITE SQUARE BRACKET
OPEN: Final = "⟦"
#: U+27E7 MATHEMATICAL RIGHT WHITE SQUARE BRACKET
CLOSE: Final = "⟧"

# Um segmento de caminho: nunca termina em ponto, para não engolir a pontuação
# final de uma frase ("veja /dev/null." -> o ponto fica de fora).
_SEG: Final = r"\.?[\w@-](?:[\w.@-]*[\w@-])?"

# Uma alternativa de flag: o /sT de -sS/sT, o /-r de -R/-r, o /tmp/snar.db de
# -g/tmp/snar.db. Exige letra inicial para não casar a fração de "-x/2", e
# nunca termina em ponto, pela mesma razão que _SEG.
_ALT_SEG: Final = r"-?[A-Za-z](?:[\w.@-]*[\w@-])?"

# Um grupo entre chaves ou colchetes colado num caminho ou numa flag:
# /dev/disk/by-{label,uuid} e -c[color]. O ] final é opcional porque algumas
# páginas escrevem grupos sem fechar (ip(8): -c[color][={always|auto|never}).
_BRACE: Final = r"\{[^}\s]*\}"
# Grupo colchetado colado numa flag. Precisa fechar e não pode ter espaço
# dentro: sem isso, "-PO[protocol list]" viraria "-PO[protocol" e deixaria
# " list]" exposto — mascaramento pela metade. O segundo ramo cobre o grupo
# em chaves da ip(8), que a página escreve sem fechar o colchete
# (-c[color][={always|auto|never}).
_BRACKET: Final = r"\[[^\s\]]*\]|\[?=?\{[^}\s]*\}"

_EXTENSIONS_PATH: Final = Path(__file__).parent / "extensions.txt"


def _load_extensions(path: Path = _EXTENSIONS_PATH) -> tuple[str, ...]:
    """Lê a lista de extensões, ignorando comentários e linhas vazias."""
    found: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        entry = raw.split("#", 1)[0].strip()
        if entry:
            found.append(entry)
    if any(len(entry) < 2 for entry in found):
        raise ValueError(
            f"{path}: extensão de uma letra torna 'e.g.' e 'i.e.' mascaráveis"
        )
    return tuple(sorted(set(found), key=lambda e: (-len(e), e)))


#: Extensões conhecidas. Ordenadas da mais longa para a mais curta para que a
#: alternância prefira o sufixo mais específico.
EXTENSIONS: Final = _load_extensions()

_EXT_ALT: Final = "|".join(EXTENSIONS)

#: Número máximo de palavras dentro de aspas para o conteúdo ainda contar como
#: literal. Medido no corpus: das 113 citações, as de 1 a 3 palavras são
#: metacaracteres, nomes de comando e nós de texinfo ('ip address flush',
#: '(coreutils) dd invocation'); as de 4 ou mais são prosa citada
#: ("must have a tty", "copy the contents of this directory"), que precisa
#: chegar ao modelo.
MAX_QUOTED_WORDS: Final = 3


def _quoted(open_quote: str, close_quote: str, guarded: bool) -> str:
    """Literal entre aspas, com no máximo :data:`MAX_QUOTED_WORDS` palavras.

    ``guarded`` liga o lookbehind que impede o apóstrofo de prosa inglesa
    (``don't``, ``user's``) e o fechamento de aspa do groff (`` `-' ``) de
    abrirem uma citação. A aspa de abertura precisa vir depois de branco, de
    parêntese/colchete/chave, ou do começo da linha.
    """
    body = (
        rf"[^{close_quote}\n\s]+"
        rf"(?:[ \t]+[^{close_quote}\n\s]+){{0,{MAX_QUOTED_WORDS - 1}}}"
    )
    before = r"(?<![^\s([{])" if guarded else ""
    return rf"{before}{open_quote}{body}{close_quote}(?!\w)"


# Padrões protegidos, em ordem de precedência. A alternância é resolvida pelo
# `re` na ordem em que aparece, então o primeiro que casar numa dada posição
# vence — é isso que impede que um caminho dentro de crase seja mascarado
# separadamente da crase que o contém.
_PATTERNS: Final[tuple[tuple[str, str], ...]] = (
    # 1. Conteúdo em crase (inclui as crases). O limite de palavras é o mesmo
    #    das aspas, e por um motivo medido: no corpus real, as duas únicas
    #    ocorrências do padrão original eram falso positivo. O groff escreve
    #    citação como `assim', com crase de um lado e apóstrofo do outro, e a
    #    crase de fechamento seguinte estava a meia frase de distância —
    #    "`-', or the argument `" virava um placeholder de prosa.
    ("backtick", _quoted("`", "`", guarded=False)),
    # 2. Literal entre aspas, mesma precedência e mesma ideia da crase: o que
    #    a página citou, ela citou porque é para copiar como está. Fecha cinco
    #    dos sete casos que a fase 2 não conseguiu resolver por segmentação —
    #    '\n', "\{{", '[ugoa]*...', '\' e “-” são todos metacaracteres
    #    citados no meio de uma frase traduzível.
    (
        "quoted",
        "|".join(
            (
                _quoted("'", "'", guarded=True),
                _quoted('"', '"', guarded=True),
                _quoted("\u201c", "\u201d", guarded=False),
            )
        ),
    ),
    # 2. URL com esquema. Precedência alta e escopo largo de propósito: uma
    #    URL é feita de palavras em inglês (download, software, archive), que
    #    é exatamente o que o modelo traduz. O esquema entra no placeholder —
    #    mascarar só o host deixaria "https://" para fora, que é a mesma
    #    falha pela metade de ~/.ssh/config. O lookbehind final devolve a
    #    pontuação de fim de frase.
    ("url", r"\b[a-z][a-z0-9+.-]*://[^\s\"'`<>]*(?<![.,;:])"),
    # 3. Expressão sed s/// ou y///. Vem cedo porque o corpo é regex, e uma
    #    regex traduzida é lixo. Só o delimitador / é reconhecido; ver README.
    ("sedexpr", r"(?<![\w/])[sy]/[^/\n]*/[^/\n]*/[gpimIe0-9]*"),
    # 4. Blocos <placeholder>. Aceita qualquer coisa sem espaço nem <> dentro,
    #    para cobrir <n1=v1,[n2=v2,...]> e <user:password>. A proibição de
    #    espaço é o que impede casar uma comparação em prosa ("a < b > c").
    ("angle", r"<[A-Za-z0-9][^<>\s]*>"),
    # 5. Variáveis, com o caminho que as segue. $HOME/.secret é um token só:
    #    o lookbehind do padrão de caminho barra o / colado no E de $HOME, e
    #    sem isso o /.secret ficava exposto.
    #    ${...} antes de $NOME, e por último os especiais do shell ($1, $@,
    #    $$, $?). O lookbehind do último ramo existe só para não partir
    #    "US$100" ao meio; um $ colado numa letra é dinheiro, não variável.
    (
        "var",
        rf"\$(?:\{{[^}}]+\}}|[A-Za-z_]\w*)(?:/(?:{_SEG}/)*{_SEG}/?)?"
        r"|(?<![A-Za-z])\$(?:\d+|[@*#?!$])",
    ),
    # 6. Flags longas. O valor aceita um bloco <...> com espaço dentro, senão
    #    --script-help=<Lua scripts> mascarava só até o espaço e deixava
    #    " scripts>" exposto.
    ("longflag", r"(?<![\w-])--[A-Za-z][\w-]*(?:=(?:<[^>\n]*>|\S+))?"),
    # 7. -- isolado: fim de opções. Semanticamente significativo, e perdê-lo
    #    muda o que o comando faz. O lookahead evita casar --flag (já coberto
    #    acima) e a régua ---- de algumas páginas.
    ("endopts", r"(?<![\w-])--(?![\w-])"),
    # 8. Flags curtas. O lookbehind impede casar o hífen de "well-known".
    #    O sufixo /alt consome a forma -sS/sT/sA e -R/-r inteira: mascarar só
    #    -sS deixaria /sT/sA exposto. O sufixo [..] cobre -i[SUFFIX] e
    #    -c[color][={always|auto|never}.
    (
        "shortflag",
        rf"(?<![\w-])-(?=[\w-]*[A-Za-z])[A-Za-z0-9][\w-]*"
        rf"(?:/{_ALT_SEG})*(?:{_BRACKET})*",
    ),
    # 9. Endereços IP, com prefixo CIDR opcional. Precedência acima de
    #    caminhos, senão o /24 de 192.168.0.0/24 não entraria no placeholder.
    #    O ramo IPv6 exige :: ou os 8 grupos completos, para não casar hora
    #    (18:17:16) nem MAC de 6 grupos.
    (
        "ip",
        r"\b\d{1,3}(?:\.\d{1,3}){3}(?:/\d{1,2})?\b"
        r"|(?<![\w:.])(?:"
        r"(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}"
        r"|(?:[0-9A-Fa-f]{1,4}:){1,7}:(?:[0-9A-Fa-f]{1,4}(?::[0-9A-Fa-f]{1,4}){0,6})?"
        r"|::(?:[0-9A-Fa-f]{1,4}(?::[0-9A-Fa-f]{1,4}){0,7})?"
        r")(?:/\d{1,3})?(?![\w:])",
    ),
    # 10. host:caminho — knuth.cwi.nl:/dir da mount, foo:src/bar/ da rsync.
    #     Exige uma barra depois dos dois pontos, e é isso que impede casar
    #     "U:53" e "Nota:veja". Sem este padrão, o : ficava exposto entre dois
    #     placeholders.
    (
        "hostpath",
        rf"(?<![\w:])[\w][\w.@-]*:"
        rf"(?:/(?:{_SEG}/)*(?:{_SEG})?/?|(?:{_SEG}/)+(?:{_SEG})?)",
    ),
    # 11. Caminhos absolutos, relativos explícitos (./ ../) e sob o home (~/).
    #     A alternativa absoluta exige ao menos um segmento, então uma barra
    #     solta em prosa não casa. O ~ entra no placeholder: mascarar só o
    #     /.ssh/config de ~/.ssh/config deixaria o til exposto à tradução, e
    #     um til perdido muda o caminho. O sufixo {..} cobre a expansão de
    #     chaves de /dev/disk/by-{label,uuid,id}.
    (
        "path",
        r"(?<![\w/])(?:"
        rf"\.{{1,2}}/(?:(?:{_SEG}/)*{_SEG}/?)?"
        r"|"
        rf"~/(?:(?:{_SEG}/)*{_SEG}/?)?"
        r"|"
        rf"/(?:{_SEG}/)*{_SEG}/?"
        rf")(?:{_BRACE})?",
    ),
    # 12. Glob de extensão: *.log, *.c. O asterisco é a marca; não consulta a
    #     lista de extensões, porque um glob já se identifica pela forma.
    ("glob", r"(?<![\w*])\*\.[\w-]+"),
    # 13. Operando chave=valor: conv=notrunc, K=1024, PARTUUID=uuid, pid=.
    #     Vem depois das flags, que já cobrem --flag=valor pela esquerda. O =
    #     tem de estar colado no nome, e é isso que mantém o padrão longe de
    #     prosa ("a = b" não casa). O lookbehind final devolve o ponto final
    #     da frase.
    (
        "keyvalue",
        r"(?<![\w.=-])%?[A-Za-z_][\w.-]*=[^\s,;)\]}'\"]*(?<!\.)",
    ),
    # 14. Nomes com ponto que parecem arquivo, unit ou domínio. A extensão
    #     vem de extensions.txt: uma lista falha por omissão (visível), o
    #     antigo limite [a-z]{2,6} falhava por forma (.service, com 7 letras,
    #     ficava de fora sem que nada dissesse isso). Os rótulos
    #     intermediários permitem que scanme.nmap.org e backup.tar.gz virem
    #     um placeholder só: mascarar pela metade exporia o resto.
    ("dotted", rf"\b[\w-]+(?:\.[\w-]+)*\.(?:{_EXT_ALT})\b"),
)

_MASK_RE: Final = re.compile(
    "|".join(f"(?P<{name}>{pattern})" for name, pattern in _PATTERNS)
)

# Escape por duplicação: ⟦ -> ⟦⟦ e ⟧ -> ⟧⟧. Resolvido da esquerda para a
# direita, é inambíguo em relação a ⟦n⟧.
_ESCAPE_RE: Final = re.compile(f"[{OPEN}{CLOSE}]")

# Ordem da alternância importa: os pares escapados vêm antes do placeholder.
_UNMASK_RE: Final = re.compile(
    f"{OPEN}{OPEN}|{CLOSE}{CLOSE}|{OPEN}(\\d+){CLOSE}"
)


@dataclass(frozen=True)
class MaskResult:
    """Resultado de :func:`mask`."""

    #: Texto com os tokens críticos substituídos por ``⟦n⟧``.
    text: str
    #: Índice do placeholder -> literal original, exatamente como no fonte.
    tokens: dict[int, str]


def mask(text: str) -> MaskResult:
    """Substitui tokens críticos de sintaxe por placeholders opacos.

    Opera sobre texto já segmentado: não interpreta indentação nem detecta
    blocos de código (isso é de ``segment.py``, fase 2).
    """
    escaped = _ESCAPE_RE.sub(lambda m: m.group(0) * 2, text)

    tokens: dict[int, str] = {}

    def take(match: re.Match[str]) -> str:
        index = len(tokens)
        tokens[index] = match.group(0)
        return f"{OPEN}{index}{CLOSE}"

    return MaskResult(text=_MASK_RE.sub(take, escaped), tokens=tokens)


def restore(text: str, tokens: dict[int, str]) -> str:
    """Recoloca os literais e desfaz o escape das chaves.

    Um placeholder cujo índice não esteja em ``tokens`` é deixado intacto:
    detectar isso é papel de :func:`manbr.validate.validate`, que deve rodar
    antes.
    """

    def put(match: re.Match[str]) -> str:
        index = match.group(1)
        if index is None:
            # Par escapado: ⟦⟦ ou ⟧⟧ volta a ser um caractere só.
            return match.group(0)[0]
        return tokens.get(int(index), match.group(0))

    return _UNMASK_RE.sub(put, text)
