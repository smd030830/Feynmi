# Feynmi API types

`index.ts` is generated from the current FastAPI OpenAPI document. It exports:

- `Schemas`: component models, for example `Schemas["ProjectResponse"]`.
- `Paths`: path/method contracts. `requestBody` is the body type and `responses` maps status codes directly to response body types. A response without a body is `void`.

From `apps/backend`, run:

```sh
uv run python ../../scripts/generate_api_types.py
uv run python ../../scripts/generate_api_types.py --check
```

Generation does not start a server or application lifespan and uses isolated local settings. No database, Firebase account, storage bucket, or AI key is needed. It uses existing backend dependencies and the Python standard library.

Unconstrained OpenAPI values are `unknown`, not `any`. Unsupported schema constructs fail generation instead of silently weakening the contract. UUID/date/time/binary string formats and numeric/string constraints remain runtime validation rules. An endpoint described only as `dict[str, Any]` can only generate an unknown-valued dictionary; define a response model in the backend to generate its full shape.
