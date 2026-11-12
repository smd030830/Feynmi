"""PPTX에서 슬라이드별 텍스트를 추출한다 (python-pptx, PRD 9.1).

슬라이드 본문의 텍스트 상자·자리 표시자·표·그룹 안의 텍스트를 도형 순서대로 모은다.
이미지, 차트, 발표자 노트는 추출하지 않는다.
"""

from collections.abc import Iterable, Iterator
from io import BytesIO

from pptx import Presentation
from pptx.shapes.autoshape import Shape
from pptx.shapes.base import BaseShape
from pptx.shapes.graphfrm import GraphicFrame
from pptx.shapes.group import GroupShape

from backend.domain.enums import FailureCode
from backend.ingest.base import (
    IngestError,
    check_page_count,
    check_size,
    ensure_extractable,
    normalize_text,
)
from backend.rag.chunking import PageText

_ZIP_HEADER = b"PK\x03\x04"  # 구형 .ppt(OLE)는 여기서 걸러진다 (FR-1.1)


def extract_pptx_pages(data: bytes) -> list[PageText]:
    """모든 슬라이드를 1부터 번호 붙여 반환한다. 텍스트가 없는 슬라이드도 포함한다.

    반환 길이가 곧 슬라이드 수(`materials.page_count`)다.
    """
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
        pages = [
            PageText(number, normalize_text("\n".join(_texts(slide.shapes))))
            for number, slide in enumerate(slides, start=1)
        ]
    except IngestError:
        raise
    except Exception as exc:
        raise IngestError(FailureCode.CORRUPTED_FILE, "unreadable slide") from exc
    return ensure_extractable(pages)


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
