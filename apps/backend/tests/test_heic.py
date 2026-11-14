"""HEIC(아이폰 사진): 원본을 메모리에서 디코딩해 PNG/JPG와 같은 OCR 경로로 보낸다.

test_minseok2 실험 추가 (PRD 미반영).
"""

import io

import pytest
from PIL import Image
from test_read_material import FakeEngine, image_bytes, ocr

from backend.domain.enums import FailureCode, FileType
from backend.ingest import IngestError, extract_pages, read_material
from backend.ingest.image import open_image_file
from backend.ingest.ocr import prepare
from backend.services.materials import _file_type  # pyright: ignore[reportPrivateUsage]


def heic(image: Image.Image, **options: object) -> bytes:
    out = io.BytesIO()
    image.save(out, format="HEIF", **options)
    return out.getvalue()


def test_heic_extensions_map_to_one_type() -> None:
    assert _file_type("칠판.HEIC") == (FileType.HEIC, "heic")
    assert _file_type("화면.heif") == (FileType.HEIC, "heif")


async def test_heic_goes_through_the_image_ocr_path() -> None:
    engine = FakeEngine("운영체제 3장: 프로세스")
    data = heic(Image.new("RGB", (400, 200), "gray"))
    pages = await read_material(data, "heic", ocr(engine))
    assert [(p.number, p.text) for p in pages] == [(1, "운영체제 3장: 프로세스")]
    assert len(engine.sizes) == 1


def test_rotated_photo_is_upright_and_not_rotated_twice() -> None:
    # 아이폰 세로 사진: 가로로 저장하고 "오른쪽으로 90도 돌려 보라"(EXIF 6)를 붙인다
    exif = Image.Exif()
    exif[0x0112] = 6
    opened = open_image_file(heic(Image.new("RGB", (400, 200), "white"), exif=exif.tobytes()))
    assert opened.size == (200, 400)  # 열 때 이미 세로로 섰다
    assert opened.getexif().get(0x0112) == 1
    assert opened.info.get("original_orientation") == 6
    width, height = prepare(opened).size  # OCR 전처리의 exif_transpose가 다시 돌리지 않는다
    assert height > width


def test_multi_image_heic_reads_the_primary_image() -> None:
    first = Image.new("RGB", (64, 64), "white")
    primary = Image.new("RGB", (64, 64), (80, 80, 80))
    data = heic(first, save_all=True, append_images=[primary], primary_index=1)
    assert open_image_file(data).convert("RGB").getpixel((5, 5)) == (80, 80, 80)


async def test_jpeg_content_named_heic_is_still_read() -> None:
    # 확장자와 내용이 달라도 지원하는 그림이면 읽는다 (PNG/JPG와 같은 정책)
    pages = await read_material(image_bytes((400, 200), "JPEG", "gray"), "heic", ocr(FakeEngine()))
    assert pages[0].text == "그림 속 글자"


@pytest.mark.parametrize(
    ("data", "code"),
    [
        ("이건 사진이 아니다".encode(), FailureCode.UNSUPPORTED_FORMAT),
        (heic(Image.new("RGB", (400, 200), "gray"))[:300], FailureCode.CORRUPTED_FILE),
    ],
)
async def test_heic_failures(data: bytes, code: FailureCode) -> None:
    with pytest.raises(IngestError) as error:
        await read_material(data, "heic", ocr(FakeEngine()))
    assert error.value.code == code


def test_heic_pixel_bomb_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    data = heic(Image.new("RGB", (400, 200), "gray"))
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)  # 이 크기면 경고, 두 배면 오류
    with pytest.raises(IngestError) as error:
        open_image_file(data)
    assert error.value.code == FailureCode.FILE_TOO_LARGE


def test_heic_needs_ocr_like_other_images() -> None:
    with pytest.raises(IngestError) as error:
        extract_pages(heic(Image.new("RGB", (64, 64), "gray")), "heic")
    assert error.value.code == FailureCode.INTERNAL_ERROR
