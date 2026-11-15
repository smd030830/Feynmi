"""Verify first provisioning with Firebase's authenticated end-user lookup API."""

import requests

from backend.auth.firebase import VerifiedToken
from backend.errors import AppError

LOOKUP_URL = "https://identitytoolkit.googleapis.com/v1/accounts:lookup"
INVALID_SESSION = {"INVALID_ID_TOKEN", "TOKEN_EXPIRED", "USER_NOT_FOUND", "USER_DISABLED"}


def check_account(token: VerifiedToken, *, id_token: str, api_key: str) -> None:
    """Called only after local signature/issuer/audience verification; never logs credentials."""
    try:
        response = requests.post(
            LOOKUP_URL, params={"key": api_key}, json={"idToken": id_token}, timeout=5
        )
        body = response.json()
    except requests.RequestException, ValueError:
        raise AppError(
            503, "cloud_unavailable", "account lookup unavailable", retryable=True
        ) from None
    if not isinstance(body, dict):
        raise AppError(503, "cloud_unavailable", "invalid account lookup response", retryable=True)
    if response.status_code != 200:
        error = body.get("error")
        code = error.get("message") if isinstance(error, dict) else None
        if isinstance(code, str) and code in INVALID_SESSION:
            raise AppError(401, "unauthenticated", "account session no longer valid")
        raise AppError(503, "cloud_unavailable", "account lookup rejected", retryable=True)
    users = body.get("users")
    if users == []:
        raise AppError(401, "unauthenticated", "account no longer exists")
    if not isinstance(users, list) or len(users) != 1 or not isinstance(users[0], dict):
        raise AppError(503, "cloud_unavailable", "invalid account lookup response", retryable=True)
    user = users[0]
    if user.get("localId") != token.uid:
        raise AppError(401, "unauthenticated", "account identity mismatch")
    if user.get("disabled", False) is not False:
        raise AppError(401, "token_revoked", "account disabled")
    valid_since = user.get("validSince")
    if (
        not isinstance(valid_since, str)
        or len(valid_since) > 20
        or not valid_since.isascii()
        or not valid_since.isdigit()
    ):
        raise AppError(
            503, "cloud_unavailable", "invalid account revocation boundary", retryable=True
        )
    if token.auth_time.timestamp() < int(valid_since):
        raise AppError(401, "token_revoked", "account session revoked")
