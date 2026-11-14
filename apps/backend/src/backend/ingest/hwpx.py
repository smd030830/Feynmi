"""HWPX(한글 2014 이후의 XML 형식)에서 쪽별 텍스트를 추출한다.

ZIP 안의 Contents/section*.xml에 문단(p) → 글자 묶음(run) → 글자(t)가 들어 있다.
문단의 쪽 나누기(pageBreak="1")에서 쪽을 나누고, 표는 한 행을 한 줄(" | "로 칸 구분)로 만든다.
그림은 Contents/content.hpf의 목록으로 BinData/ 안의 파일을 찾고,
그림이 든 문단 바로 뒤에 자리를 둔다.
위·아래 첨자는 Contents/header.xml의 글자 모양(charPr)으로 알아내 2¹², log₂처럼 남긴다.
"""

import re
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterator
from typing import Any

from PIL import Image

from backend.domain.enums import FailureCode
from backend.ingest.base import IngestError, PageParts, RawPage, check_page_count
from backend.ingest.image import try_decode
from backend.ingest.package import open_package, read_part
from backend.ingest.script import Script, scripted

_FIRST_SECTION = "Contents/section0.xml"
_MANIFEST = "Contents/content.hpf"
_HEADER = "Contents/header.xml"
_SECTION = re.compile(r"Contents/section(\d+)\.xml")


def _local(tag: Any) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def hwpx_raw_pages(data: bytes) -> list[RawPage]:
    package = open_package(data, _FIRST_SECTION, "HWPX")
    try:
        sections = sorted(
            (int(m.group(1)), name)
            for name in package.namelist()
            if (m := _SECTION.fullmatch(name))
        )
        reader = _Reader(_image_paths(package), _char_scripts(package))
        for _, name in sections:
            root = _parse(read_part(package, name, "HWPX"))
            for paragraph in root:
                if _local(paragraph.tag) == "p":
                    reader.paragraph(paragraph)
        pages = reader.pages
        while len(pages) > 1 and pages[-1].empty:
            pages.pop()
        check_page_count(len(pages))
        return [
            page.raw_page(number, _loader(package, page.images))
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


def _char_scripts(package: zipfile.ZipFile) -> dict[str, Script]:
    """글자 모양 id → 위·아래 첨자 (header.xml의 charPr 아래 supscript/subscript)."""
    if _HEADER not in package.namelist():
        return {}
    root = _parse(read_part(package, _HEADER, "HWPX"))
    found: dict[str, Script] = {}
    for char_pr in (el for el in root.iter() if _local(el.tag) == "charPr"):
        marks = {_local(child.tag) for child in char_pr}
        if "supscript" in marks:
            found[char_pr.get("id", "")] = "super"
        elif "subscript" in marks:
            found[char_pr.get("id", "")] = "sub"
    return found


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


class _Reader:
    """한 문서를 읽는 동안의 상태: 그림 목록, 첨자 글자 모양, 쪽들."""

    def __init__(self, images: dict[str, str], scripts: dict[str, Script]) -> None:
        self.images = images
        self.scripts = scripts
        self.pages: list[PageParts[str]] = [PageParts()]  # 그림은 ZIP 안 경로로 기억한다
        self.pending: list[str] = []  # 지금 문단 안에서 만난 그림 (문단 글 줄 뒤에 둔다)

    def paragraph(self, paragraph: ET.Element) -> None:
        if paragraph.get("pageBreak") == "1" and not self.pages[-1].empty:
            self.pages.append(PageParts())
        outer, self.pending = self.pending, []
        self.pages[-1].line("".join(self.texts(paragraph)))
        for path in self.pending:
            self.pages[-1].image(path)
        self.pending = outer

    def texts(self, node: ET.Element) -> Iterator[str]:
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
            elif name == "run" and (script := self.scripts.get(child.get("charPrIDRef", ""))):
                yield scripted("".join(self.texts(child)), script)
            elif name == "tbl":
                for row in _table_rows(child):
                    self.pages[-1].line(row)
            elif name == "img":
                path = self.images.get(child.get("binaryItemIDRef", ""))
                if path:
                    self.pending.append(path)
            elif name != "p":  # 글상자 안 문단 등은 아래로 내려가며 읽는다
                yield from self.texts(child)
            else:
                self.paragraph(child)


def _table_rows(table: ET.Element) -> Iterator[str]:
    for row in (el for el in table.iter() if _local(el.tag) == "tr"):
        cells = []
        for cell in (el for el in row if _local(el.tag) == "tc"):
            words = ["".join(t.itertext()) for t in cell.iter() if _local(t.tag) == "t"]
            cells.append(" ".join(w.strip() for w in words if w.strip()))
        if any(cells):
            yield " | ".join(cells)


def _loader(package: zipfile.ZipFile, paths: list[str]):  # noqa: ANN202 - RawPage.images
    def load() -> Iterator[Image.Image | None]:
        for path in paths:
            try:
                blob = package.read(path)
            except Exception:
                yield None  # 못 연 그림은 None으로 자리만 지킨다
                continue
            yield try_decode(blob, f"HWPX {path}")

    return load
