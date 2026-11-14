import threading

from backend.auth.firebase import VerifiedToken
from backend.errors import AppError


class FakeCloud:
    def __init__(self) -> None:
        self.deleted: set[str] = set()
        self.revoked: list[str] = []
        self.files: dict[str, tuple[str, bytes]] = {}
        self.fail_deletion = False
        self.calls: list[str] = []
        self.uploaded: list[str] = []
        self.fail_upload = False
        self.fail_read_url = False
        self.upload_started: threading.Event | None = None
        self.upload_release: threading.Event | None = None

    def check_user(self, token: VerifiedToken) -> None:
        if token.uid in self.deleted:
            raise AppError(401, "unauthenticated")

    def revoke(self, uid: str) -> None:
        self.revoked.append(uid)

    def delete_user(self, uid: str) -> None:
        self.calls.append("firebase")
        if self.fail_deletion:
            raise RuntimeError("fake upstream outage")
        self.deleted.add(uid)

    def delete_files(self, prefix: str) -> None:
        self.calls.append("storage")
        for path in list(self.files):
            if path.startswith(prefix):
                del self.files[path]

    def upload_avatar(self, path: str, content_type: str, data: bytes) -> None:
        self.uploaded.append(path)
        if self.upload_started is not None:
            self.upload_started.set()
        if self.upload_release is not None and not self.upload_release.wait(10):
            raise RuntimeError("test upload wait timed out")
        self.files[path] = (content_type, data)
        if self.fail_upload:
            raise RuntimeError("fake upload response failure after write")

    def read_url(self, path: str) -> str:
        if self.fail_read_url:
            raise RuntimeError("fake signing failure")
        return f"https://example.invalid/{path}"

    def delete_file(self, path: str) -> None:
        self.files.pop(path, None)
