"""분석 작업 전달 (architecture 7.1, 10, 11).

- `QUEUE_MODE=inline`(로컬): 큐 없이 같은 프로세스에서 분석 함수를 백그라운드로 실행한다
  (API 계층에서 처리).
- `QUEUE_MODE=cloud_tasks`(운영): Cloud Tasks `analysis` 큐에 작업을 넣고,
  큐가 OIDC 토큰을 붙여 `POST /api/v1/internal/tasks/analyze-material`을 부른다.
워커 로직은 두 경우 모두 `services.analysis.analyze_material`로 같다.
"""

import uuid
from typing import Protocol

from backend.config import Settings

WORKER_PATH = "/api/v1/internal/tasks/analyze-material"


class AnalysisQueue(Protocol):
    def enqueue(self, material_id: uuid.UUID, attempt: int) -> None: ...


def make_queue(settings: Settings) -> AnalysisQueue | None:
    """inline이면 None (API가 같은 프로세스에서 실행한다)."""
    from backend.queue.cloud_tasks import CloudTasksQueue

    return CloudTasksQueue(settings) if settings.queue_mode == "cloud_tasks" else None
