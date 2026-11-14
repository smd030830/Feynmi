"""이미지 열기: PNG/JPG/HEIC 업로드 파일과 문서·슬라이드 속 그림을 안전하게 연다.

HEIC(아이폰 기본 사진 형식)는 pillow-heif를 Pillow 플러그인으로 등록해 다른 그림과 똑같이 연다.
- 원본 HEIC는 저장소에 그대로 두고, 분석할 때 메모리에서만 디코딩한다.
  JPG나 PDF로 바꿔 다시 저장하지 않는다.
- 열 때 pillow-heif가 회전 정보를 적용하고 EXIF 방향을 1로 되돌린다. 그래서 OCR 전처리의
  exif_transpose()가 한 번 더 돌리지 않는다 (원래 값은 info["original_orientation"]).
- 여러 장이 든 HEIC는 대표 이미지(primary)가 열린다. 업로드 그림 1개 = 1쪽 규칙을 지킨다.
- 내장 미리보기(썸네일)는 쓰지 않는다 (OCR은 원본 해상도로).
"""

import io
import logging
import warnings

import pillow_heif
from PIL import Image

from backend.domain.enums import FailureCode
from backend.ingest.base import IngestError, check_size

logger = logging.getLogger(__name__)

pillow_heif.register_heif_opener(thumbnails=False)

_PNG = b"\x89PNG\r\n\x1a\n"
_JPEG = b"\xff\xd8\xff"
# HEIF 파일은 4바이트 뒤에 "ftyp" + 브랜드가 온다 (pillow-heif 플러그인이 받는 브랜드와 같음)
_HEIF_BRANDS = {
    b"heic",
    b"heix",
    b"heim",
    b"heis",
    b"hevc",
    b"hevx",
    b"hevm",
    b"hevs",
    b"mif1",
    b"msf1",
}


def _is_heif(data: bytes) -> bool:
    return data[4:8] == b"ftyp" and data[8:12] in _HEIF_BRANDS


def decode_image(data: bytes) -> Image.Image:
    """그림 바이트를 끝까지 읽어 연다. 너무 큰(압축 폭탄) 그림은 DecompressionBombError."""
    with warnings.catch_warnings():
        # Pillow는 약 9천만 화소부터 경고만 낸다. 경고도 오류로 다뤄 메모리를 보호한다.
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        image = Image.open(io.BytesIO(data))
        image.load()
    return image


def open_image_file(data: bytes) -> Image.Image:
    """PNG/JPG/HEIC 업로드 파일 하나 = 1쪽. 확장자보다 실제 내용(앞 바이트)을 믿는다.

    확장자와 내용이 달라도(예: JPG 내용의 .heic) 지원하는 그림이면 그대로 읽는다.
    """
    check_size(data)
    if not (data.startswith(_PNG) or data.startswith(_JPEG) or _is_heif(data)):
        raise IngestError(FailureCode.UNSUPPORTED_FORMAT, "not a PNG/JPEG/HEIC image")
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
