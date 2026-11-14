"""Lazy official Firebase/GCS boundary. All methods run in a worker thread."""

import threading
from datetime import timedelta
from typing import Any, Protocol

from backend.auth.firebase import VerifiedToken
from backend.errors import AppError

AVATAR_LIMIT = 2 * 1024 * 1024


class AccountCloud(Protocol):
    def check_user(self, token: VerifiedToken) -> None: ...
    def revoke(self, uid: str) -> None: ...
    def delete_user(self, uid: str) -> None: ...
    def delete_files(self, prefix: str) -> None: ...
    def upload_avatar(self, path: str, content_type: str, data: bytes) -> None: ...
    def read_url(self, path: str) -> str: ...
    def delete_file(self, path: str) -> None: ...


class GoogleAccountCloud:
    _app_lock = threading.Lock()

    def __init__(self, project_id: str, bucket_name: str = "", signer_email: str = "") -> None:
        self.project_id = project_id
        self.bucket_name = bucket_name.strip()
        self.signer_email = signer_email.strip()

    def _firebase(self) -> Any:
        import firebase_admin

        name = f"feynmi-{self.project_id}"
        with self._app_lock:
            try:
                return firebase_admin.get_app(name)
            except ValueError:
                return firebase_admin.initialize_app(
                    options={"projectId": self.project_id}, name=name
                )

    def check_user(self, token: VerifiedToken) -> None:
        from firebase_admin import auth

        try:
            user = auth.get_user(token.uid, app=self._firebase())
        except auth.UserNotFoundError:
            raise AppError(401, "unauthenticated", "account no longer exists") from None
        if user.disabled or token.auth_time.timestamp() * 1000 < user.tokens_valid_after_timestamp:
            raise AppError(401, "token_revoked", "account disabled or token revoked")

    def revoke(self, uid: str) -> None:
        from firebase_admin import auth

        auth.revoke_refresh_tokens(uid, app=self._firebase())

    def delete_user(self, uid: str) -> None:
        from firebase_admin import auth

        try:
            auth.delete_user(uid, app=self._firebase())
        except auth.UserNotFoundError:
            pass

    def _bucket(self) -> Any:
        from google.cloud import storage

        name = self.bucket_name
        if not name:
            raise AppError(503, "cloud_unavailable", "GCS_BUCKET is not configured", retryable=True)
        return storage.Client(project=self.project_id).bucket(name)

    def _signed(self, blob: Any, **kwargs: Any) -> str:
        # ADC on Cloud Run can sign through IAM without exporting a private key.
        import google.auth
        from google.auth import credentials
        from google.auth.transport.requests import Request

        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        options: dict[str, Any] = {"credentials": creds}
        if not isinstance(creds, credentials.Signing):
            creds.refresh(Request())
            email = getattr(creds, "service_account_email", None)
            if not email or email == "default":
                email = self.signer_email
            if not email:
                raise AppError(503, "cloud_unavailable", "signed URL signer unavailable")
            options.update(service_account_email=email, access_token=creds.token)
        return blob.generate_signed_url(
            version="v4", expiration=timedelta(minutes=10), **options, **kwargs
        )

    def upload_avatar(self, path: str, content_type: str, data: bytes) -> None:
        self._bucket().blob(path).upload_from_string(
            data, content_type=content_type, if_generation_match=0
        )

    def read_url(self, path: str) -> str:
        return self._signed(self._bucket().blob(path), method="GET")

    def delete_file(self, path: str) -> None:
        from google.api_core.exceptions import NotFound

        try:
            self._bucket().blob(path).delete()
        except NotFound:
            pass

    def delete_files(self, prefix: str) -> None:
        for blob in self._bucket().list_blobs(prefix=prefix):
            self.delete_file(blob.name)
