"""Generate deterministic TypeScript contracts from the application's OpenAPI schema.

Run with the backend environment: uv run python ../../scripts/generate_api_types.py.
No server, database connection, application lifespan, or external API is started.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "packages/api-types/index.ts"
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}
ANNOTATIONS = {
    "title",
    "description",
    "default",
    "example",
    "examples",
    "deprecated",
    "readOnly",
    "writeOnly",
    "$id",
    "$schema",
    "$comment",
    "discriminator",
    "xml",
    "externalDocs",
}
CONSTRAINTS = {
    "format",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minLength",
    "maxLength",
    "pattern",
    "minItems",
    "maxItems",
    "uniqueItems",
    "minProperties",
    "maxProperties",
}
STRUCTURE = {
    "$ref",
    "type",
    "enum",
    "const",
    "anyOf",
    "oneOf",
    "allOf",
    "nullable",
    "items",
    "properties",
    "required",
    "additionalProperties",
}


def quoted(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def union(types: list[str], operator: str = " | ") -> str:
    values = list(dict.fromkeys(types))
    if not values:
        raise ValueError("a type union must contain at least one value")
    return (
        operator.join(f"({item})" for item in values) if len(values) > 1 else values[0]
    )


def literal(value: Any) -> str:
    if value is not None and not isinstance(value, str | bool | int | float):
        raise ValueError(
            f"unsupported non-primitive schema literal: {type(value).__name__}"
        )
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def schema_type(schema: Any) -> str:
    if isinstance(schema, bool):
        return "unknown" if schema else "never"
    if not isinstance(schema, Mapping):
        raise TypeError("a schema must be an object or boolean")
    unsupported = set(schema) - ANNOTATIONS - CONSTRAINTS - STRUCTURE
    if unsupported:
        raise ValueError(
            f"unsupported schema keywords: {', '.join(sorted(unsupported))}"
        )
    if "nullable" in schema:
        result = schema_type({k: v for k, v in schema.items() if k != "nullable"})
        return union([result, "null"]) if schema["nullable"] else result
    if "$ref" in schema:
        prefix = "#/components/schemas/"
        reference = schema["$ref"]
        if not isinstance(reference, str) or not reference.startswith(prefix):
            raise ValueError(f"unsupported schema reference: {reference}")
        name = reference[len(prefix) :].replace("~1", "/").replace("~0", "~")
        result = f"Schemas[{quoted(name)}]"
        siblings = {
            k: v for k, v in schema.items() if k != "$ref" and k not in ANNOTATIONS
        }
        return union([result, schema_type(siblings)], " & ") if siblings else result
    if "const" in schema:
        return literal(schema["const"])
    if "enum" in schema:
        return (
            union([literal(value) for value in schema["enum"]])
            if schema["enum"]
            else "never"
        )
    for keyword, operator in (("anyOf", " | "), ("oneOf", " | "), ("allOf", " & ")):
        if keyword in schema:
            variants = schema[keyword]
            if not isinstance(variants, list) or not variants:
                raise ValueError(f"{keyword} must contain at least one schema")
            combined = union([schema_type(item) for item in variants], operator)
            siblings = {
                k: v for k, v in schema.items() if k != keyword and k in STRUCTURE
            }
            return (
                union([combined, schema_type(siblings)], " & ")
                if siblings
                else combined
            )
    kind = schema.get("type")
    if isinstance(kind, list):
        return union([schema_type(dict(schema, type=item)) for item in kind])
    if kind in ("string", "number", "boolean", "null"):
        return kind
    if kind == "integer":
        return "number"
    if kind == "array":
        if "items" not in schema:
            raise ValueError("array schema must declare items")
        return f"Array<{schema_type(schema['items'])}>"
    if kind == "object" or "properties" in schema or "additionalProperties" in schema:
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        if required - properties.keys():
            raise ValueError("required properties must be declared in properties")
        fields = [
            f"{quoted(name)}{'' if name in required else '?'}: {schema_type(value)};"
            for name, value in sorted(properties.items())
        ]
        extra = schema.get("additionalProperties")
        if isinstance(extra, Mapping):
            if properties:
                raise ValueError(
                    "named properties with typed additionalProperties need an explicit model"
                )
            return f"Record<string, {schema_type(extra)}>"
        if not properties:
            return (
                "Record<string, never>" if extra is False else "Record<string, unknown>"
            )
        result = "{ " + " ".join(fields) + " }"
        return result + " & Record<string, unknown>" if extra is True else result
    if kind is None and not set(schema) - ANNOTATIONS - CONSTRAINTS:
        return "unknown"  # OpenAPI explicitly leaves this value unconstrained.
    raise ValueError(f"unsupported schema type: {kind!r}")


def resolve_object(value: dict[str, Any], document: dict[str, Any]) -> dict[str, Any]:
    if "$ref" not in value:
        return value
    reference = value["$ref"]
    if not reference.startswith("#/"):
        raise ValueError(f"external references are not supported: {reference}")
    target: Any = document
    for part in reference[2:].split("/"):
        target = target[part.replace("~1", "/").replace("~0", "~")]
    if not isinstance(target, dict) or "$ref" in target:
        raise ValueError(f"invalid or chained OpenAPI reference: {reference}")
    return target


def content_type(content: dict[str, Any]) -> str:
    if not content:
        return "void"
    return union(
        [schema_type(value.get("schema", {})) for _, value in sorted(content.items())]
    )


def operation_type(
    operation: dict[str, Any],
    common_parameters: list[dict[str, Any]],
    document: dict[str, Any],
) -> str:
    parameters: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in common_parameters + operation.get("parameters", []):
        parameter = resolve_object(raw, document)
        if parameter["in"] not in {"path", "query", "header", "cookie"}:
            raise ValueError(f"unsupported parameter location: {parameter['in']}")
        parameters[(parameter["in"], parameter["name"])] = parameter
    groups = []
    for location in ("path", "query", "header", "cookie"):
        entries = [
            value
            for (place, _), value in sorted(parameters.items())
            if place == location
        ]
        if entries:
            fields = [
                f"{quoted(item['name'])}{'' if item.get('required') else '?'}: "
                f"{schema_type(item['schema'])};"
                for item in entries
            ]
            optional = "" if any(item.get("required") for item in entries) else "?"
            groups.append(f"{location}{optional}: {{ {' '.join(fields)} }};")
    fields = [
        f"parameters: {{ {' '.join(groups)} }};" if groups else "parameters?: never;"
    ]
    if "requestBody" in operation:
        body = resolve_object(operation["requestBody"], document)
        fields.append(
            f"requestBody{'' if body.get('required') else '?'}: "
            f"{content_type(body.get('content', {}))};"
        )
    else:
        fields.append("requestBody?: never;")
    responses = []
    for status, raw in sorted(operation.get("responses", {}).items()):
        response = resolve_object(raw, document)
        responses.append(
            f"{quoted(status)}: {content_type(response.get('content', {}))};"
        )
    fields.append(f"responses: {{ {' '.join(responses)} }};")
    return "{ " + " ".join(fields) + " }"


def generate(document: dict[str, Any]) -> str:
    lines = [
        "// Generated by scripts/generate_api_types.py. Do not edit by hand.",
        "// JSON validation constraints and string formats are enforced by the backend at runtime.",
        "// Paths contains request body and response body types directly, keyed by HTTP status.",
        "",
        "export type Schemas = {",
    ]
    for name, schema in sorted(
        document.get("components", {}).get("schemas", {}).items()
    ):
        lines.append(f"  {quoted(name)}: {schema_type(schema)};")
    lines += ["};", "", "export type Paths = {"]
    for path, path_item in sorted(document.get("paths", {}).items()):
        path_item = resolve_object(path_item, document)
        lines.append(f"  {quoted(path)}: {{")
        for method, operation in sorted(path_item.items()):
            if method not in HTTP_METHODS:
                continue
            rendered = operation_type(
                operation, path_item.get("parameters", []), document
            )
            lines.append(f"    {quoted(method)}: {rendered};")
        lines.append("  };")
    lines += ["};", ""]
    return "\n".join(lines)


def load_openapi() -> dict[str, Any]:
    # Importing backend.main creates an app object but does not enter its lifespan.
    # Force service boundaries to inert local settings even when a personal .env exists.
    isolated = {
        "DATABASE_URL": "postgresql+asyncpg://schema:schema@127.0.0.1:1/schema",
        "FIREBASE_PROJECT_ID": "openapi-types",
        "GCS_BUCKET": "",
        "GCS_SIGNER_SERVICE_ACCOUNT": "",
        "GCS_EMULATOR_URL": "",
        "GCS_EMULATOR_PUBLIC_URL": "",
        "QUEUE_MODE": "inline",
        "OPENAI_API_KEY": "",
        "CORS_ORIGINS": "",
    }
    previous = {name: os.environ.get(name) for name in isolated}
    os.environ.update(isolated)
    sys.path.insert(0, str(ROOT / "apps/backend/src"))
    try:
        from backend.main import app

        return app.openapi()
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="fail if committed types are stale"
    )
    parser.add_argument(
        "--output", type=Path, default=OUTPUT, help="output TypeScript file"
    )
    args = parser.parse_args()
    try:
        generated = generate(load_openapi())
    except (ValueError, TypeError, KeyError) as error:
        print(f"Cannot generate API types: {error}", file=sys.stderr)
        return 1
    if args.check:
        if (
            not args.output.exists()
            or args.output.read_text(encoding="utf-8") != generated
        ):
            print(
                "API types are missing or stale. Run scripts/generate_api_types.py.",
                file=sys.stderr,
            )
            return 1
        print("API types are up to date.")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(generated, encoding="utf-8", newline="\n")
    display_path = (
        args.output.relative_to(ROOT)
        if args.output.is_relative_to(ROOT)
        else args.output
    )
    print(f"Generated API types: {display_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
