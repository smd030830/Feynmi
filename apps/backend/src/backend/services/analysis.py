"""자료 분석 작업 (architecture 7.1 워커의 `extracting` 단계).

원본 → 쪽별 글자(OCR 포함) → 청크 → 임베딩 → chunks 저장
→ `generating_concepts` 개념 추출(FM-022) → `ready`.
AI 설정(키)이 없으면 임베딩과 개념 추출을 건너뛴다(글자 추출까지만 확인하는 로컬 시연).
"""

import asyncio
import logging
import uuid
from collections.abc import Callable
from contextlib import AsyncExitStack

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.db.models import Chunk, Concept, Material, Project
from backend.domain.enums import FailureCode, MaterialStatus
from backend.ingest import HybridOcr, IngestError, has_real_pages, make_ocr, read_material
from backend.ingest.cleanup import drop_repeated_lines
from backend.ingest.ocr import ImageTextReader
from backend.llm import LLMError, LLMSettings, openai_provider
from backend.rag.chunking import split_pages
from backend.rag.store import embed_chunks, save_chunks
from backend.services.concepts import extract_concepts
from backend.services.storage import MaterialStorage

logger = logging.getLogger(__name__)

OcrFactory = Callable[[ImageTextReader | None], HybridOcr | None]


def load_llm_settings() -> LLMSettings | None:
    """키와 모델이 모두 설정됐을 때만 LLM 설정을 돌려준다."""
    try:
        return LLMSettings()  # pyright: ignore[reportCallIssue]
    except Exception:
        return None


_RUNNABLE = (
    MaterialStatus.QUEUED,
    MaterialStatus.EXTRACTING,
    MaterialStatus.GENERATING_CONCEPTS,
)


async def _set_status(
    db: AsyncSession, material: Material, status: MaterialStatus, code: FailureCode | None = None
) -> None:
    material.status = status.value
    material.failure_code = code.value if code else None
    await db.commit()


async def analyze_material(
    session_factory: async_sessionmaker[AsyncSession],
    storage: MaterialStorage,
    material_id: uuid.UUID,
    attempt: int,
    *,
    llm_settings: LLMSettings | None,
    ocr_factory: OcrFactory = make_ocr,
) -> None:
    """같은 시도(`analysis_attempt`)이고 아직 끝나지 않았을 때만 실행한다 (7.1 멱등성).

    진행 상태(`extracting` 등)에서 다시 오면 인스턴스가 도중에 끊겨 Cloud Tasks가 재전달한 경우라
    처음부터 다시 한다 (시작할 때 이전 조각과 개념을 지운다). 끝났거나(`ready`, `failed`)
    재시도로 시도 번호가 바뀐 작업은 무시한다.
    """
    async with session_factory() as db:
        material = await db.get(Material, material_id)
        if (
            material is None
            or material.analysis_attempt != attempt
            or material.status not in _RUNNABLE
        ):
            return
        user_id = await db.scalar(select(Project.user_id).where(Project.id == material.project_id))
        await _set_status(db, material, MaterialStatus.EXTRACTING)
        try:
            async with AsyncExitStack() as stack:
                provider = None
                if llm_settings is not None:
                    provider = await stack.enter_async_context(openai_provider(llm_settings))
                image_ai = provider if llm_settings and llm_settings.llm_image_text_model else None

                data = await asyncio.to_thread(storage.load, material.gcs_path)
                pages = await read_material(data, material.file_type, ocr_factory(image_ai))
                material.page_count = len(pages)
                material.page_texts = [page.text for page in pages]  # "글자 보기"는 원문 그대로
                # 조각에는 매 쪽 반복되는 머리글·바닥글을 넣지 않는다
                # (글 문서의 쪽·구역에는 머리글이 없다)
                if has_real_pages(material.file_type):
                    pages = drop_repeated_lines(pages)
                chunks = await asyncio.to_thread(split_pages, pages)

                # 재시도라면 이전 시도의 조각과 개념을 지운다 (save_chunks는 중복 저장을 거부한다).
                await db.execute(delete(Concept).where(Concept.material_id == material.id))
                await db.execute(delete(Chunk).where(Chunk.material_id == material.id))
                if provider is not None and user_id is not None:
                    embedded = await embed_chunks(chunks, provider)
                    saved = await save_chunks(
                        db, user_id=user_id, material_id=material.id, chunks=embedded
                    )
                    # 조각을 커밋한 뒤 개념을 뽑는다 (LLM을 기다리는 동안 트랜잭션을 잡지 않는다)
                    await _set_status(db, material, MaterialStatus.GENERATING_CONCEPTS)
                    await extract_concepts(
                        db,
                        provider,
                        material_id=material.id,
                        material_title=material.title,
                        chunks=saved,
                    )
            await _set_status(db, material, MaterialStatus.READY)
        except IngestError as exc:
            await db.rollback()
            logger.info("material %s failed: %s", material_id, exc.code.value)
            await _set_status(db, material, MaterialStatus.FAILED, exc.code)
        except LLMError:
            await db.rollback()
            logger.warning("material %s: LLM call failed", material_id)
            await _set_status(db, material, MaterialStatus.FAILED, FailureCode.LLM_FAILED)
        except Exception:
            await db.rollback()
            logger.exception("material %s: unexpected analysis error", material_id)
            await _set_status(db, material, MaterialStatus.FAILED, FailureCode.INTERNAL_ERROR)
