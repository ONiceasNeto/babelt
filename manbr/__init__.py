"""manbr — tradução de saída de terminal para pt-BR.

Fase 1: apenas mascaramento de tokens críticos e validação da tradução.
"""

from manbr.headers import apply_headers, translate_header
from manbr.mask import MaskResult, mask, restore
from manbr.normalize import normalize
from manbr.segment import Segment, SegmentKind, reassemble, segment
from manbr.validate import ValidationResult, validate

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
