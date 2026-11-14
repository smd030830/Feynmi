"""HWPX(한글 2014 이후의 XML 형식)에서 쪽별 텍스트를 추출한다.

ZIP 안의 Contents/section*.xml에 문단(p) → 글자 묶음(run) → 글자(t)가 들어 있다.
문단의 쪽 나누기(pageBreak="1")에서 쪽을 나누고, 표는 한 행을 한 줄(" | "로 칸 구분)로 만든다.
그림은 Contents/content.hpf의 목록으로 BinData/ 안의 파일을 찾는다.
"""

import re
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterator
from typing import Any

from PIL import Image

from backend.domain.enums import FailureCode
from backend.ingest.base import IngestError, RawPage, check_page_count, normalize_text
from backend.ingest.image import try_decode
from backend.ingest.package import open_package, read_part

_FIRST_SECTION = "Contents/section0.xml"
_MANIFEST = "Contents/content.hpf"
_SECTION = re.compile(r"Contents/section(\d+)\.xml")


def _local(tag: Any) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


class _Page:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.images: list[str] = []  # ZIP 안 그림 경로


def hwpx_raw_pages(data: bytes) -> list[RawPage]:
    package = open_package(data, _FIRST_SECTION, "HWPX")
    try:
        sections = sorted(
            (int(m.group(1)), name)
            for name in package.namelist()
            if (m := _SECTION.fullmatch(name))
        )
        images = _image_paths(package)
        pages = [_Page()]
        for _, name in sections:
            root = _parse(read_part(package, name, "HWPX"))
            for paragraph in root:
                if _local(paragraph.tag) == "p":
                    _paragraph(paragraph, pages, images)
        while len(pages) > 1 and not pages[-1].lines and not pages[-1].images:
            pages.pop()
        check_page_count(len(pages))
        return [
            RawPage(number, normalize_text("\n".join(page.lines)), _loader(package, page.images))
            for number, page in enumerate(pages, start=1)
        ]
    except IngestError:
        raise
    except Exception as exc:
        raise IngestError(FailureCode.CORRUPTED_FILE, "unreadable HWPX") from exc


def _parse(xml: bytes) -> ET.Element:
    try:
        return ET.fromstring(xml)
    except ET.ParseError as exc:
        raise IngestError(FailureCode.CORRUPTED_FILE, "broken HWPX section") from exc


def _image_paths(package: zipfile.ZipFile) -> dict[str, str]:
    """그림 id → ZIP 안 경로 (content.hpf의 item 목록)."""
    if _MANIFEST not in package.namelist():
        return {}
    root = _parse(read_part(package, _MANIFEST, "HWPX"))
    return {
        item.get("id", ""): item.get("href", "")
        for item in root.iter()
        if _local(item.tag) == "item" and item.get("href", "").startswith("BinData/")
    }


def _paragraph(paragraph: ET.Element, pages: list[_Page], images: dict[str, str]) -> None:
    if paragraph.get("pageBreak") == "1" and (pages[-1].lines or pages[-1].images):
        pages.append(_Page())
    text = "".join(_texts(paragraph, pages, images))
    if text.strip():
        pages[-1].lines.append(text)


def _texts(node: ET.Element, pages: list[_Page], images: dict[str, str]) -> Iterator[str]:
    """문단 안 글자를 순서대로 낸다. 표·그림을 만나면 따로 처리한다."""
    for child in node:
        name = _local(child.tag)
        if name == "t":
            yield child.text or ""
            for inner in child:
                inner_name = _local(inner.tag)
                if inner_name == "tab":
                    yield "\t"
                elif inner_name == "lineBreak":
                    yield "\n"
                yield inner.tail or ""
        elif name == "tbl":
            pages[-1].lines.extend(_table_rows(child))
        elif name == "img":
            path = images.get(child.get("binaryItemIDRef", ""))
            if path:
                pages[-1].images.append(path)
        elif name != "p":  # 글상자 안 문단 등은 아래로 내려가며 읽는다
            yield from _texts(child, pages, images)
        else:
            nested = "".join(_texts(child, pages, images))
            if nested.strip():
                pages[-1].lines.append(nested)


def _table_rows(table: ET.Element) -> Iterator[str]:
    for row in (el for el in table.iter() if _local(el.tag) == "tr"):
        cells = []
        for cell in (el for el in row if _local(el.tag) == "tc"):
            words = ["".join(t.itertext()) for t in cell.iter() if _local(t.tag) == "t"]
            cells.append(" ".join(w.strip() for w in words if w.strip()))
        if any(cells):
            yield " | ".join(cells)


def _loader(package: zipfile.ZipFile, paths: list[str]):  # noqa: ANN202 - RawPage.images
    def load() -> Iterator[Image.Image]:
        for path in paths:
            try:
                blob = package.read(path)
            except Exception:
                continue
            image = try_decode(blob, f"HWPX {path}")
            if image is not None:
                yield image

    return load
