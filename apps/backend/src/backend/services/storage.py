"""원본 자료 보관소.

architecture 7.1은 비공개 Cloud Storage 버킷을 쓴다. 이 구현은 로컬 개발·시연용으로 같은 객체 경로를
로컬 폴더에 둔다. GCS 구현으로 바꿀 때는 같은 save/load 모양을 맞추면 된다.
"""

import uuid
from pathlib import Path
from typing import Protocol


class MaterialStorage(Protocol):
    def save(self, key: str, data: bytes) -> None: ...

    def load(self, key: str) -> bytes: ...


def material_key(
    user_id: uuid.UUID, project_id: uuid.UUID, material_id: uuid.UUID, ext: str
) -> str:
    """architecture 7.1 객체 경로. 모두 서버가 정한 값이라 경로 조작이 끼어들 수 없다."""
    return f"users/{user_id}/projects/{project_id}/materials/{material_id}/original.{ext}"


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise ValueError("storage key escapes the storage root")
        return path

    def save(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def load(self, key: str) -> bytes:
        return self._path(key).read_bytes()
