"""Parser and conversion capability discovery exposed by ``/healthz``."""
from dataclasses import asdict, dataclass
from importlib.util import find_spec
from shutil import which


_FALLBACK_LIMITATIONS = (
    "当前使用基础解析：不含 OCR、版面还原或表格结构识别。",
    "扫描版 PDF 只能提取嵌入图片，图片仍会交给视觉模型生成描述。",
)


@dataclass(frozen=True)
class Capabilities:
    """Runtime capabilities plus the parser selected at startup."""

    mineru: bool
    libreoffice: bool
    parser: str
    parser_degraded: bool
    parser_limitations: tuple[str, ...]

    def public(self) -> dict[str, object]:
        return asdict(self)


def detect_capabilities() -> Capabilities:
    """Prefer MinerU when present and otherwise keep ingestion usable."""
    mineru = find_spec("mineru") is not None or which("mineru") is not None
    libreoffice = which("libreoffice") is not None or which("soffice") is not None
    return Capabilities(
        mineru=mineru,
        libreoffice=libreoffice,
        parser="mineru" if mineru else "python",
        parser_degraded=not mineru,
        parser_limitations=() if mineru else _FALLBACK_LIMITATIONS,
    )
