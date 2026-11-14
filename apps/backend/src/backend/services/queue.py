"""분석 작업 전달 (architecture 7.1, 10, 11).

- `QUEUE_MODE=inline`(로컬): 큐 없이 같은 프로세스에서 분석 함수를 백그라운드로 실행한다
  (API 계층에서 처리).
- `QUEUE_MODE=cloud_tasks`(운영): Cloud Tasks `analysis` 큐에 작업을 넣고,
  큐가 OIDC 토큰을 붙여 `POST /api/v1/internal/tasks/analyze-material`을 부른다.
워커 로직은 두 경우 모두 `services.analysis.analyze_material`로 같다.
"""

import json
import uuid
from collections.abc import Callable
from typing import Protocol

from backend.config import Settings
from backend.errors import AppError

WORKER_PATH = "/api/v1/internal/tasks/analyze-material"


class AnalysisQueue(Protocol):
    def enqueue(self, material_id: uuid.UUID, attempt: int) -> None: ...


class CloudTasksQueue:
    def __init__(self, settings: Settings) -> None:
        required = {
            "TASKS_PROJECT": settings.tasks_project,
            "TASKS_LOCATION": settings.tasks_location,
            "TASKS_QUEUE": settings.tasks_queue,
            "TASKS_INVOKER_SA": settings.tasks_invoker_sa,
            "PUBLIC_BASE_URL": settings.public_base_url,
        }
        missing = [name for name, value in required.items() if not value.strip()]
        if missing:
            raise ValueError(f"QUEUE_MODE=cloud_tasks needs {', '.join(missing)}")
        self.settings = settings
        self.base_url = settings.public_base_url.strip().rstrip("/")
        self._client = None

    def enqueue(self, material_id: uuid.UUID, attempt: int) -> None:
        from google.cloud import tasks_v2
        from google.protobuf import duration_pb2

        if self._client is None:
            self._client = tasks_v2.CloudTasksClient()
        s = self.settings
        body = json.dumps({"material_id": str(material_id), "attempt": attempt}).encode()
        task = tasks_v2.Task(
            http_request=tasks_v2.HttpRequest(
                http_method=tasks_v2.HttpMethod.POST,
                url=f"{self.base_url}{WORKER_PATH}",
                headers={"Content-Type": "application/json"},
                body=body,
                oidc_token=tasks_v2.OidcToken(
                    service_account_email=s.tasks_invoker_sa, audience=self.base_url
                ),
            ),
            dispatch_deadline=duration_pb2.Duration(seconds=s.analysis_deadline_minutes * 60),
        )
        parent = self._client.queue_path(s.tasks_project, s.tasks_location, s.tasks_queue)
        self._client.create_task(parent=parent, task=task)


def make_queue(settings: Settings) -> AnalysisQueue | None:
    """inline이면 None (API가 같은 프로세스에서 실행한다)."""
    return CloudTasksQueue(settings) if settings.queue_mode == "cloud_tasks" else None


TaskTokenVerifier = Callable[[str], None]


def make_task_token_verifier(settings: Settings) -> TaskTokenVerifier:
    """Cloud Tasks가 붙인 OIDC 토큰인지 확인한다: 서명, audience, 호출 서비스 계정."""
    audience = settings.public_base_url.strip().rstrip("/")
    invoker = settings.tasks_invoker_sa.strip()

    def verify(token: str) -> None:
        from google.auth.transport import requests
        from google.oauth2 import id_token

        try:
            claims = id_token.verify_oauth2_token(token, requests.Request(), audience=audience)
        except ValueError:
            raise AppError(401, "unauthenticated", "invalid task token") from None
        if claims.get("email") != invoker or not claims.get("email_verified"):
            raise AppError(403, "forbidden", "task token from an unexpected caller")

    return verify
