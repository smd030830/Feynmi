# Feynmi backend

```bash
uv sync
cp .env.example .env
uv run uvicorn backend.main:app --reload   # http://localhost:8000/docs
uv run ruff check . && uv run ruff format --check .
uv run pyright
uv run pytest
```
