"""TXT 파일을 쪽별 텍스트로 읽는다.

한글 TXT는 UTF-8(요즘 메모장 기본) 말고도 CP949(예전 메모장 "ANSI"), UTF-16(BOM 있음)이 흔하다.
쪽 구분이 없으므로 쪽 넘김 문자(\\f)가 있을 때만 쪽을 나누고, 없으면 1쪽이다.
"""

import codecs

from backend.domain.enums import FailureCode
from backend.ingest.base import IngestError, RawPage, check_page_count, check_size, normalize_text

_BOMS = [
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
]
# BOM이 없을 때 시도하는 순서. UTF-8로 맞게 풀리면 CP949일 가능성은 거의 없다
_ENCODINGS = ("utf-8", "cp949")


def decode_text(data: bytes) -> str:
    check_size(data)
    for bom, encoding in _BOMS:
        if data.startswith(bom):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError as exc:
                raise IngestError(FailureCode.CORRUPTED_FILE, "broken text encoding") from exc
    # NUL 바이트가 있으면 글자 파일이 아니다 (이름만 .txt로 바꾼 실행 파일, 그림 등)
    if b"\x00" in data:
        raise IngestError(FailureCode.UNSUPPORTED_FORMAT, "binary file, not text")
    for encoding in _ENCODINGS:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise IngestError(FailureCode.UNSUPPORTED_FORMAT, "unknown text encoding")


def txt_raw_pages(data: bytes) -> list[RawPage]:
    parts = decode_text(data).split("\f")
    check_page_count(len(parts))
    return [
        RawPage(number, normalize_text(part), lambda: [])
        for number, part in enumerate(parts, start=1)
    ]
