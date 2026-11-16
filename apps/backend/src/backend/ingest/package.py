"""ZIP 기반 문서(DOCX, HWPX) 공통 검사."""

import zipfile
from io import BytesIO

from backend.domain.enums import FailureCode
from backend.ingest.base import IngestError, check_size

_ZIP_HEADER = b"PK\x03\x04"
# 압축을 풀었을 때 크기 상한 (압축 폭탄 방지). 업로드 상한 50MB 문서의 여유분을 둔다
MAX_UNZIPPED_BYTES = 300 * 1024 * 1024


def open_package(data: bytes, required: str, kind: str) -> zipfile.ZipFile:
    """ZIP을 열고 형식을 가리는 필수 부분(`required`)이 있는지 확인한다.

    ZIP이 아니거나 필수 부분이 없으면 다른 형식(UNSUPPORTED_FORMAT), 깨졌으면 CORRUPTED_FILE.
    """
    check_size(data)
    if not data.startswith(_ZIP_HEADER):
        raise IngestError(FailureCode.UNSUPPORTED_FORMAT, f"not a {kind} package")
    try:
        package = zipfile.ZipFile(BytesIO(data))
        infos = package.infolist()
    except zipfile.BadZipFile as exc:
        raise IngestError(FailureCode.CORRUPTED_FILE, f"unreadable {kind}") from exc
    if required not in {info.filename for info in infos}:
        raise IngestError(FailureCode.UNSUPPORTED_FORMAT, f"not a {kind} file")
    if sum(info.file_size for info in infos) > MAX_UNZIPPED_BYTES:
        raise IngestError(FailureCode.FILE_TOO_LARGE, f"{kind} expands too much")
    return package


def read_part(package: zipfile.ZipFile, name: str, kind: str) -> bytes:
    try:
        return package.read(name)
    except Exception as exc:  # 깨진 압축, 암호 걸린 항목 등
        raise IngestError(FailureCode.CORRUPTED_FILE, f"unreadable {kind} part") from exc
