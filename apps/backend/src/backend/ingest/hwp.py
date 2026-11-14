"""HWP(한글 5.x 바이너리)에서 쪽별 텍스트를 추출한다.

한컴이 공개한 "한글 문서 파일 형식 5.0" 규격대로 읽는다.
- 파일은 OLE 복합 문서이고, 본문은 BodyText/Section0, Section1 … 스트림에 있다.
- FileHeader의 속성 비트: 0 = 압축(raw deflate), 1 = 암호, 2 = 배포용 문서.
- 본문 스트림은 레코드의 연속이다. 머리 4바이트 = 태그(10비트) | 수준(10비트) | 크기(12비트).
- 문단 머리(PARA_HEADER)의 나누기 종류에 쪽 나누기 비트가 있고,
  문단 글자(PARA_TEXT)는 UTF-16LE에 제어 문자가 섞여 있다.
- 그림 개체(SHAPE_COMPONENT_PICTURE)가 BinData/BINxxxx.* 스트림 번호를 가리킨다.
암호·배포용 문서는 열 수 없어 CORRUPTED_FILE(암호 걸린 PDF와 같은 처리)로 본다.
"""

import struct
import zlib
from collections.abc import Iterator
from io import BytesIO

import olefile
from PIL import Image

from backend.domain.enums import FailureCode
from backend.ingest.base import IngestError, PageParts, RawPage, check_page_count, check_size
from backend.ingest.image import try_decode

_OLE_HEADER = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_SIGNATURE = b"HWP Document File"
_COMPRESSED, _PASSWORD, _DISTRIBUTION = 0x1, 0x2, 0x4
# 압축을 풀었을 때 스트림 하나의 크기 상한 (압축 폭탄 방지)
_MAX_STREAM_BYTES = 200 * 1024 * 1024

_HWPTAG_BEGIN = 0x10
PARA_HEADER = _HWPTAG_BEGIN + 50
PARA_TEXT = _HWPTAG_BEGIN + 51
SHAPE_COMPONENT_PICTURE = _HWPTAG_BEGIN + 69
_PAGE_BREAK = 0x04 | 0x01  # 쪽 나누기 | 구역 나누기

# 문단 글자 속 제어 문자: 확장·인라인 제어는 8글자(16바이트)를 차지한다
_WIDE_CONTROLS = {1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23}
_TAB, _LINE_BREAK, _HYPHEN = 9, 10, 24
_SPACES = {30, 31}  # 묶음 빈칸, 고정폭 빈칸


def records(stream: bytes) -> Iterator[tuple[int, int, bytes]]:
    """(태그, 수준, 내용)을 차례로 낸다. 끝이 잘린 레코드는 버린다."""
    pos = 0
    while pos + 4 <= len(stream):
        (header,) = struct.unpack_from("<I", stream, pos)
        pos += 4
        tag, level, size = header & 0x3FF, (header >> 10) & 0x3FF, header >> 20
        if size == 0xFFF:
            if pos + 4 > len(stream):
                return
            (size,) = struct.unpack_from("<I", stream, pos)
            pos += 4
        if pos + size > len(stream):
            return
        yield tag, level, stream[pos : pos + size]
        pos += size


def para_text(payload: bytes) -> str:
    """PARA_TEXT의 UTF-16LE에서 제어 문자를 걷어 내고 글자만 남긴다."""
    units = struct.unpack(f"<{len(payload) // 2}H", payload[: len(payload) // 2 * 2])
    kept: list[int] = []
    i = 0
    while i < len(units):
        unit = units[i]
        if unit >= 32:
            kept.append(unit)
            i += 1
            continue
        if unit in _WIDE_CONTROLS:
            if unit == _TAB:
                kept.append(ord("\t"))
            i += 8
            continue
        if unit == _LINE_BREAK:
            kept.append(ord("\n"))
        elif unit == _HYPHEN:
            kept.append(ord("-"))
        elif unit in _SPACES:
            kept.append(ord(" "))
        i += 1  # 13(문단 끝) 등 나머지 한 글자 제어는 버린다
    return struct.pack(f"<{len(kept)}H", *kept).decode("utf-16-le", errors="replace")


def _inflate(data: bytes) -> bytes:
    inflater = zlib.decompressobj(-15)
    out = inflater.decompress(data, _MAX_STREAM_BYTES)
    if inflater.unconsumed_tail:
        raise IngestError(FailureCode.FILE_TOO_LARGE, "HWP section expands too much")
    return out


def hwp_raw_pages(data: bytes) -> list[RawPage]:
    check_size(data)
    if not data.startswith(_OLE_HEADER):
        raise IngestError(FailureCode.UNSUPPORTED_FORMAT, "not an HWP 5 file")
    try:
        ole = olefile.OleFileIO(BytesIO(data))
    except Exception as exc:
        raise IngestError(FailureCode.CORRUPTED_FILE, "unreadable HWP") from exc
    if not ole.exists("FileHeader"):  # 다른 OLE 문서 (.doc, .ppt, .xls)
        raise IngestError(FailureCode.UNSUPPORTED_FORMAT, "not an HWP file")
    try:
        header = ole.openstream("FileHeader").read()
        if not header.startswith(_SIGNATURE):
            raise IngestError(FailureCode.UNSUPPORTED_FORMAT, "not an HWP file")
        (flags,) = struct.unpack_from("<I", header, 36)
        if flags & (_PASSWORD | _DISTRIBUTION):
            raise IngestError(FailureCode.CORRUPTED_FILE, "password or distribution HWP")
        compressed = bool(flags & _COMPRESSED)
        pages = _read_sections(ole, compressed)
        bin_streams = _bin_streams(ole)
    except IngestError:
        raise
    except Exception as exc:
        raise IngestError(FailureCode.CORRUPTED_FILE, "unreadable HWP body") from exc
    check_page_count(len(pages))
    return [
        page.raw_page(number, _loader(ole, compressed, [bin_streams.get(i) for i in page.images]))
        for number, page in enumerate(pages, start=1)
    ]


def _section_names(ole: olefile.OleFileIO) -> list[str]:
    names = [
        "/".join(entry)
        for entry in ole.listdir()
        if len(entry) == 2 and entry[0] == "BodyText" and entry[1].startswith("Section")
    ]
    return sorted(names, key=lambda name: int(name.removeprefix("BodyText/Section") or 0))


def _read_sections(ole: olefile.OleFileIO, compressed: bool) -> list[PageParts[int]]:
    # 그림 개체 레코드는 그 문단의 글자(PARA_TEXT) 뒤에 나온다.
    # 그래서 순서대로 담으면 그림 자리가 문단 바로 뒤가 된다
    pages: list[PageParts[int]] = [PageParts()]
    for name in _section_names(ole):
        raw = ole.openstream(name).read()
        stream = _inflate(raw) if compressed else raw
        for tag, level, payload in records(stream):
            if tag == PARA_HEADER and level == 0 and len(payload) >= 12:
                if payload[11] & _PAGE_BREAK and not pages[-1].empty:
                    pages.append(PageParts())
            elif tag == PARA_TEXT:
                pages[-1].line(para_text(payload))
            elif tag == SHAPE_COMPONENT_PICTURE and len(payload) >= 73:
                (bin_id,) = struct.unpack_from("<H", payload, 71)
                pages[-1].image(bin_id)
    while len(pages) > 1 and pages[-1].empty:
        pages.pop()
    return pages


def _bin_streams(ole: olefile.OleFileIO) -> dict[int, str]:
    """그림 번호 → 스트림 이름 (BinData/BIN0001.png → 1)."""
    found: dict[int, str] = {}
    for entry in ole.listdir():
        if len(entry) == 2 and entry[0] == "BinData" and entry[1].upper().startswith("BIN"):
            try:
                found[int(entry[1][3:7], 16)] = "/".join(entry)
            except ValueError:
                continue
    return found


def _loader(ole: olefile.OleFileIO, compressed: bool, names: list[str | None]):  # noqa: ANN202
    def load() -> Iterator[Image.Image | None]:
        for name in names:
            if name is None:  # 없는 그림은 None으로 자리만 지킨다
                yield None
                continue
            try:
                raw = ole.openstream(name).read()
                # 그림은 이미 압축된 형식(PNG/JPG)이라 한글이 다시 압축하지 않는 경우가 많다
                already_image = raw.startswith((b"\x89PNG", b"\xff\xd8"))
                blob = _inflate(raw) if compressed and not already_image else raw
            except Exception:
                yield None
                continue
            yield try_decode(blob, f"HWP {name}")

    return load
