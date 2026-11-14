"""로컬 전달 (`QUEUE_MODE=inline`, architecture 11.2): 큐 없이 같은 프로세스에서 분석한다.

응답을 보낸 뒤 실행되는 백그라운드 작업으로 넣는다. 워커 로직은 운영과 같고 전달 경로만 다르다.
"""

from typing import Any

from fastapi import BackgroundTasks

from backend.db.models import Material
from backend.services.analysis import analyze_material


def schedule(tasks: BackgroundTasks, state: Any, material: Material) -> None:
    """`state`는 앱 상태(세션 팩토리, 보관소, LLM 설정, OCR 생성 함수)."""
    tasks.add_task(
        analyze_material,
        state.session_factory,
        state.storage,
        material.id,
        material.analysis_attempt,
        llm_settings=state.llm_settings,
        ocr_factory=state.ocr_factory,
    )
