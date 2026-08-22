"""babelt — tradução de saída de terminal para pt-BR, offline.

O nome não fixa o par de idiomas de propósito: hoje só existe en→pt-BR, e a
estrutura (``headers.txt``, ``glossary.txt``, ``literals.txt``,
``function_words.txt``) é por idioma, não global.
"""

from babelt.headers import apply_headers, translate_header
from babelt.mask import MaskResult, mask, restore
from babelt.normalize import normalize
from babelt.segment import Segment, SegmentKind, reassemble, segment
from babelt.validate import ValidationResult, validate

__all__ = [
    "MaskResult",
    "Segment",
    "SegmentKind",
    "ValidationResult",
    "apply_headers",
    "mask",
    "normalize",
    "reassemble",
    "restore",
    "segment",
    "translate_header",
    "validate",
]
