"""ID 토큰 검증을 실제 RSA 서명으로 확인한다. Firebase 인증서 조회는 가짜로 바꾼다."""

import time
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from google.auth import crypt, jwt

from backend.auth.firebase import CertsCache, TokenVerifier, make_token_verifier
from backend.domain.enums import SignInProvider
from backend.errors import AppError

PROJECT = "feynmi-test"


def make_key(kid: str) -> tuple[crypt.RSASigner, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return crypt.RSASigner.from_string(private_pem, kid), public_pem.decode()


SIGNER, PUBLIC = make_key("k1")


def claims(**overrides: Any) -> dict[str, Any]:
    now = int(time.time())
    base = {
        "iss": f"https://securetoken.google.com/{PROJECT}",
        "aud": PROJECT,
        "sub": "uid-1",
        "iat": now,
        "exp": now + 3600,
        "auth_time": now,
        "email": "a@example.com",
        "email_verified": True,
        "firebase": {"sign_in_provider": "password"},
    }
    return base | overrides


def sign(payload: dict[str, Any], signer: crypt.RSASigner = SIGNER) -> str:
    return jwt.encode(signer, payload).decode()


def verifier() -> TokenVerifier:
    return make_token_verifier(PROJECT, lambda: ({"k1": PUBLIC}, 60))


def test_valid_token_is_accepted() -> None:
    token = verifier()(sign(claims()))
    assert token.uid == "uid-1"
    assert token.email == "a@example.com"
    assert token.email_verified is True
    assert token.sign_in_provider is SignInProvider.PASSWORD


@pytest.mark.parametrize(
    "overrides",
    [
        {"aud": "other-project"},
        {"iss": "https://securetoken.google.com/other-project"},
        {"exp": int(time.time()) - 3600, "iat": int(time.time()) - 7200},
        {"sub": ""},
        {"email": None},
        {"firebase": {"sign_in_provider": "anonymous"}},
        {"firebase": {}},
    ],
)
def test_invalid_claims_are_unauthenticated(overrides: dict[str, Any]) -> None:
    with pytest.raises(AppError) as exc:
        verifier()(sign(claims(**overrides)))
    assert exc.value.status_code == 401
    assert exc.value.code == "unauthenticated"


def test_signature_from_another_key_is_rejected() -> None:
    other_signer, _ = make_key("k1")
    with pytest.raises(AppError) as exc:
        verifier()(sign(claims(), other_signer))
    assert exc.value.code == "unauthenticated"


@pytest.mark.parametrize("token", ["", "garbage", "a.b.c"])
def test_malformed_token_is_unauthenticated(token: str) -> None:
    with pytest.raises(AppError) as exc:
        verifier()(token)
    assert exc.value.code == "unauthenticated"


def test_unknown_kid_refetches_certs() -> None:
    new_signer, new_public = make_key("k2")
    calls = 0

    def fetch() -> tuple[dict[str, str], int]:
        nonlocal calls
        calls += 1
        # 첫 조회에는 새 키가 아직 없고, 다시 받으면 들어 있다 (인증서 교체 직후).
        return ({"k1": PUBLIC} if calls == 1 else {"k1": PUBLIC, "k2": new_public}), 60

    verify = make_token_verifier(PROJECT, fetch)
    assert verify(sign(claims(), new_signer)).uid == "uid-1"
    assert calls == 2

    with pytest.raises(AppError):
        verify(sign(claims(), make_key("k3")[0]))
    assert calls == 3  # 없는 kid는 요청마다 한 번씩만 다시 받는다


def test_certs_are_cached_between_requests() -> None:
    calls = 0

    def fetch() -> tuple[dict[str, str], int]:
        nonlocal calls
        calls += 1
        return {"k1": PUBLIC}, 60

    verify = make_token_verifier(PROJECT, fetch)
    for _ in range(3):
        verify(sign(claims()))
    assert calls == 1


def test_certs_cache_expires() -> None:
    calls = 0

    def fetch() -> tuple[dict[str, str], int]:
        nonlocal calls
        calls += 1
        return {}, 0

    cache = CertsCache(fetch)
    cache.get()
    cache.get()
    assert calls == 2
