"""Firebase ID 토큰 검증 (architecture.md 5.2-1).

Admin SDK의 `verify_id_token`은 동기 함수라서 호출하는 쪽이 스레드풀에서 실행한다.
프로젝트 ID는 설정에서 받는다. Admin SDK는 검증할 때도 ADC(기본 자격 증명)를 찾으므로,
로컬에서는 `gcloud auth application-default login`이나 `GOOGLE_APPLICATION_CREDENTIALS`가 필요하다
(architecture.md 11.2). 자격 증명이 없으면 요청이 500으로 실패한다.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import firebase_admin
from firebase_admin import auth

from backend.domain.enums import SignInProvider
from backend.errors import AppError


@dataclass(frozen=True)
class VerifiedToken:
    uid: str
    email: str
    email_verified: bool
    sign_in_provider: SignInProvider
    auth_time: datetime


# 테스트에서 Firebase 없이 바꿔 끼울 수 있게 함수 타입으로 둔다.
TokenVerifier = Callable[[str], VerifiedToken]


def _unauthenticated(message: str) -> AppError:
    return AppError(401, "unauthenticated", message)


def make_token_verifier(project_id: str) -> TokenVerifier:
    try:
        app = firebase_admin.get_app(project_id)
    except ValueError:
        app = firebase_admin.initialize_app(options={"projectId": project_id}, name=project_id)

    def verify(token: str) -> VerifiedToken:
        try:
            claims = auth.verify_id_token(token, app=app)
        except (ValueError, auth.InvalidIdTokenError) as exc:
            # 형식 오류, 서명·발급자·대상 불일치, 만료. 인증서 조회 실패 같은 장애는
            # 그대로 올려 500이 된다.
            raise _unauthenticated(f"invalid id token: {exc}") from exc
        return _to_verified_token(claims)

    return verify


def _to_verified_token(claims: dict) -> VerifiedToken:
    email = claims.get("email")
    firebase = claims.get("firebase") or {}
    try:
        provider = SignInProvider(firebase.get("sign_in_provider"))
    except ValueError:
        # 지원하는 로그인 수단은 이메일/비밀번호와 구글뿐이다 (PRD FR-4.1).
        raise _unauthenticated("unsupported sign-in provider") from None
    if not email:
        raise _unauthenticated("token has no email")
    return VerifiedToken(
        uid=claims["uid"],
        email=email,
        email_verified=bool(claims.get("email_verified")),
        sign_in_provider=provider,
        auth_time=datetime.fromtimestamp(claims["auth_time"], UTC),
    )
