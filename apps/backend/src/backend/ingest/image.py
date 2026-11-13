"""이미지 열기: PNG/JPG 업로드 파일과 PDF·PPTX 속 그림을 안전하게 연다."""

import io
import logging
import warnings

from PIL import Image

from backend.domain.enums import FailureCode
from backend.ingest.base import IngestError, check_size

logger = logging.getLogger(__name__)

_PNG = b"\x89PNG\r\n\x1a\n"
_JPEG = b"\xff\xd8\xff"


def decode_image(data: bytes) -> Image.Image:
    """그림 바이트를 끝까지 읽어 연다. 너무 큰(압축 폭탄) 그림은 DecompressionBombError."""
    with warnings.catch_warnings():
        # Pillow는 약 9천만 화소부터 경고만 낸다. 경고도 오류로 다뤄 메모리를 보호한다.
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        image = Image.open(io.BytesIO(data))
        image.load()
    return image


def open_image_file(data: bytes) -> Image.Image:
    """PNG/JPG 업로드 파일 하나 = 1쪽. 확장자보다 실제 내용(앞 바이트)을 믿는다."""
    check_size(data)
    if not (data.startswith(_PNG) or data.startswith(_JPEG)):
        raise IngestError(FailureCode.UNSUPPORTED_FORMAT, "not a PNG/JPEG image")
    try:
        return decode_image(data)
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise IngestError(FailureCode.FILE_TOO_LARGE, "image has too many pixels") from exc
    except Exception as exc:
        raise IngestError(FailureCode.CORRUPTED_FILE, "unreadable image") from exc


def try_decode(data: bytes, where: str) -> Image.Image | None:
    """자료 속 그림은 못 열어도 자료 전체를 실패시키지 않고 건너뛴다 (EMF, JBIG2 등)."""
    try:
        return decode_image(data)
    except Exception:
        logger.info("skip unreadable image in %s", where)
        return None
