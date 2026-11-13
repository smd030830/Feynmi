"""PPTX에서 슬라이드별 텍스트를 추출한다 (python-pptx, PRD 9.1).

슬라이드 본문의 텍스트 상자·자리 표시자·표·그룹 안의 텍스트를 도형 순서대로 모은다.
OCR을 쓸 때는 슬라이드의 그림(그룹 안 포함)도 내놓는다. 차트와 발표자 노트는 추출하지 않는다.
"""

from collections.abc import Iterable, Iterator
from functools import partial
from io import BytesIO

from PIL import Image
from pptx import Presentation
from pptx.shapes.autoshape import Shape
from pptx.shapes.base import BaseShape
from pptx.shapes.graphfrm import GraphicFrame
from pptx.shapes.group import GroupShape
from pptx.shapes.picture import Picture

from backend.domain.enums import FailureCode
from backend.ingest.base import (
    IngestError,
    RawPage,
    check_page_count,
    check_size,
    ensure_extractable,
    normalize_text,
)
from backend.ingest.image import try_decode
from backend.rag.chunking import PageText

_ZIP_HEADER = b"PK\x03\x04"  # 구형 .ppt(OLE)는 여기서 걸러진다 (FR-1.1)


def pptx_raw_pages(data: bytes) -> list[RawPage]:
    """모든 슬라이드를 1부터 번호 붙여 반환한다. 텍스트가 없는 슬라이드도 포함한다."""
    check_size(data)
    if not data.startswith(_ZIP_HEADER):
        raise IngestError(FailureCode.UNSUPPORTED_FORMAT, "not a PPTX package")
    try:
        presentation = Presentation(BytesIO(data))
    except ValueError as exc:  # 정상 OOXML이지만 PowerPoint가 아님(예: .docx)
        raise IngestError(FailureCode.UNSUPPORTED_FORMAT, "not a PowerPoint file") from exc
    except Exception as exc:  # 깨진 압축/XML 등
        raise IngestError(FailureCode.CORRUPTED_FILE, "unreadable PPTX") from exc

    try:
        slides = list(presentation.slides)
        check_page_count(len(slides))
        return [
            RawPage(
                number,
                normalize_text("\n".join(_texts(slide.shapes))),
                partial(_pictures, slide.shapes, number),
            )
            for number, slide in enumerate(slides, start=1)
        ]
    except IngestError:
        raise
    except Exception as exc:
        raise IngestError(FailureCode.CORRUPTED_FILE, "unreadable slide") from exc


def extract_pptx_pages(data: bytes) -> list[PageText]:
    """OCR 없이 글자만 뽑는다. 반환 길이가 곧 슬라이드 수(`materials.page_count`)다."""
    return ensure_extractable([PageText(p.number, p.text) for p in pptx_raw_pages(data)])


def _pictures(shapes: Iterable[BaseShape], number: int) -> Iterator[Image.Image]:
    for shape in shapes:
        if isinstance(shape, GroupShape):
            yield from _pictures(shape.shapes, number)
        elif isinstance(shape, Picture):
            try:
                blob = shape.image.blob
            except Exception:  # 연결만 된(외부) 그림 등
                continue
            image = try_decode(blob, f"slide {number}")
            if image is not None:
                yield image


def _texts(shapes: Iterable[BaseShape]) -> Iterator[str]:
    for shape in shapes:
        if isinstance(shape, GroupShape):
            yield from _texts(shape.shapes)
        elif isinstance(shape, GraphicFrame) and shape.has_table:
            for row in shape.table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                if any(cells):
                    yield " | ".join(cells)
        elif isinstance(shape, Shape) and shape.has_text_frame:
            # python-pptx는 줄바꿈(<a:br>)을 세로 탭으로 돌려준다.
            text = shape.text_frame.text.replace("\v", "\n")
            if text.strip():
                yield text
