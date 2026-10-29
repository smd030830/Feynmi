"""Firebase ID 토큰 검증 (architecture.md 5.2-1).

Firebase가 공개하는 인증서로 서명, 만료, 대상(aud), 발급자(iss)를 직접 검증한다.
Admin SDK의 `verify_id_token`과 같은 검사이고, 서비스 계정 같은 자격 증명이 필요 없다.
동기 함수이므로 호출하는 쪽이 스레드풀에서 실행한다.
"""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import requests
from google.auth import jwt
from google.auth.exceptions import GoogleAuthError

from backend.domain.enums import SignInProvider
from backend.errors import AppError

CERTS_URL = (
    "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com"
)
ISSUER_PREFIX = "https://securetoken.google.com/"
DEFAULT_CERTS_TTL_SECONDS = 3600
FETCH_TIMEOUT_SECONDS = 5


@dataclass(frozen=True)
class VerifiedToken:
    uid: str
    email: str
    email_verified: bool
    sign_in_provider: SignInProvider
    auth_time: datetime


# 테스트에서 Firebase 없이 바꿔 끼울 수 있게 함수 타입으로 둔다.
TokenVerifier = Callable[[str], VerifiedToken]

# (kid → 인증서 PEM, 캐시 유지 시간(초))
CertsFetcher = Callable[[], tuple[dict[str, str], int]]


def fetch_certs() -> tuple[dict[str, str], int]:
    response = requests.get(CERTS_URL, timeout=FETCH_TIMEOUT_SECONDS)
    response.raise_for_status()
    ttl = DEFAULT_CERTS_TTL_SECONDS
    for directive in response.headers.get("Cache-Control", "").split(","):
        name, _, value = directive.strip().partition("=")
        if name == "max-age" and value.isdigit():
            ttl = int(value)
    return response.json(), ttl


class CertsCache:
    """요청마다 인증서를 받지 않도록 Cache-Control 기간만큼 보관한다."""

    def __init__(self, fetch: CertsFetcher) -> None:
        self._fetch = fetch
        self._lock = threading.Lock()
        self._certs: dict[str, str] = {}
        self._expires_at = 0.0

    def get(self, *, force: bool = False) -> dict[str, str]:
        with self._lock:
            if force or time.monotonic() >= self._expires_at:
                self._certs, ttl = self._fetch()
                self._expires_at = time.monotonic() + ttl
            return self._certs


def _unauthenticated(message: str) -> AppError:
    return AppError(401, "unauthenticated", message)


def make_token_verifier(project_id: str, fetch: CertsFetcher = fetch_certs) -> TokenVerifier:
    cache = CertsCache(fetch)

    def decode(token: str, certs: dict[str, str]) -> dict[str, Any]:
        # 서명, 만료, 발급 시각, 대상(aud = 프로젝트 ID)을 확인한다.
        return jwt.decode(token, certs=certs, audience=project_id)

    def verify(token: str) -> VerifiedToken:
        try:
            try:
                claims = decode(token, cache.get())
            except ValueError as exc:
                # 인증서가 교체된 직후라면 캐시에 없는 kid일 수 있으니 한 번만 다시 받아 본다.
                if "not found" not in str(exc):
                    raise
                claims = decode(token, cache.get(force=True))
        except (ValueError, GoogleAuthError) as exc:
            # 형식 오류, 서명·대상 불일치, 만료. 인증서를 받지 못한 장애는 그대로 올려 500이 된다.
            raise _unauthenticated(f"invalid id token: {exc}") from exc
        if claims.get("iss") != f"{ISSUER_PREFIX}{project_id}":
            raise _unauthenticated("invalid token issuer")
        return _to_verified_token(claims)

    return verify


def _to_verified_token(claims: dict[str, Any]) -> VerifiedToken:
    uid = claims.get("sub")
    email = claims.get("email")
    firebase = claims.get("firebase") or {}
    try:
        provider = SignInProvider(firebase.get("sign_in_provider"))
    except ValueError:
        # 지원하는 로그인 수단은 이메일/비밀번호와 구글뿐이다 (PRD FR-4.1).
        raise _unauthenticated("unsupported sign-in provider") from None
    if not uid or not isinstance(uid, str) or len(uid) > 128:
        raise _unauthenticated("token has no subject")
    if not email:
        raise _unauthenticated("token has no email")
    auth_time = claims.get("auth_time")
    if not isinstance(auth_time, int):
        raise _unauthenticated("token has no auth_time")
    return VerifiedToken(
        uid=uid,
        email=email,
        email_verified=bool(claims.get("email_verified")),
        sign_in_provider=provider,
        auth_time=datetime.fromtimestamp(auth_time, UTC),
    )
