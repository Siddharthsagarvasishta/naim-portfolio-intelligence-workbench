#!/usr/bin/env python3
"""Generate dependency-free TypeScript wire types from the nAIM OpenAPI contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = REPOSITORY_ROOT / "outputs" / "contracts" / "openapi.json"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "app" / "generated-api-types.ts"
HTTP_METHODS = ("get", "post", "put", "patch", "delete", "options", "head", "trace")
PARAMETER_LOCATIONS = ("query", "header", "path", "cookie")


def _quoted(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _literal(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return _quoted(value)
    if isinstance(value, (int, float)):
        return json.dumps(value)
    return "JsonValue"


def _indent(value: str, spaces: int = 2) -> str:
    prefix = " " * spaces
    return "\n".join(prefix + line if line else line for line in value.splitlines())


def _union(values: list[str]) -> str:
    unique: list[str] = []
    for value in values:
        if value not in unique:
            unique.append(value)
    if not unique:
        return "never"
    if len(unique) == 1:
        return unique[0]
    return " | ".join(f"({value})" if " & " in value else value for value in unique)


def _intersection(values: list[str]) -> str:
    unique: list[str] = []
    for value in values:
        if value not in unique:
            unique.append(value)
    if not unique:
        return "JsonValue"
    if len(unique) == 1:
        return unique[0]
    return " & ".join(f"({value})" if " | " in value else value for value in unique)


def _reference_type(reference: str) -> str:
    prefix = "#/components/schemas/"
    if not reference.startswith(prefix):
        return "JsonValue"
    name = reference.removeprefix(prefix).replace("~1", "/").replace("~0", "~")
    return f"components[\"schemas\"][{_quoted(name)}]"


def schema_to_typescript(schema: Any) -> str:
    """Translate the JSON Schema subset emitted by FastAPI into wire-safe TypeScript."""

    if schema is True:
        return "JsonValue"
    if schema is False:
        return "never"
    if not isinstance(schema, dict) or not schema:
        return "JsonValue"
    if "$ref" in schema:
        return _reference_type(str(schema["$ref"]))
    if "const" in schema:
        return _literal(schema["const"])
    if isinstance(schema.get("enum"), list):
        return _union([_literal(value) for value in schema["enum"]])
    if isinstance(schema.get("allOf"), list):
        return _intersection([schema_to_typescript(item) for item in schema["allOf"]])
    for composition in ("oneOf", "anyOf"):
        if isinstance(schema.get(composition), list):
            return _union([schema_to_typescript(item) for item in schema[composition]])

    declared_type = schema.get("type")
    if isinstance(declared_type, list):
        return _union(
            [schema_to_typescript({**schema, "type": item}) for item in declared_type]
        )
    if declared_type == "null":
        return "null"
    if declared_type == "boolean":
        return "boolean"
    if declared_type in {"integer", "number"}:
        return "number"
    if declared_type == "string":
        return "string"
    if declared_type == "array":
        item_type = schema_to_typescript(schema.get("items", {}))
        return f"Array<{item_type}>"

    properties = schema.get("properties")
    additional = schema.get("additionalProperties", None)
    if declared_type == "object" or isinstance(properties, dict) or additional is not None:
        if not properties:
            if additional is False:
                return "Record<string, never>"
            if isinstance(additional, dict):
                return f"Record<string, {schema_to_typescript(additional)}>"
            return "JsonObject"

        required = set(schema.get("required", []))
        lines = ["{"]
        if additional is not False:
            additional_type = (
                schema_to_typescript(additional) if isinstance(additional, dict) else "JsonValue"
            )
            lines.append(f"  [key: string]: {additional_type} | undefined;")
        for name in sorted(properties):
            optional = "" if name in required else "?"
            field_type = schema_to_typescript(properties[name])
            if "\n" in field_type:
                lines.append(f"  {_quoted(name)}{optional}:")
                lines.append(_indent(field_type, 4) + ";")
            else:
                lines.append(f"  {_quoted(name)}{optional}: {field_type};")
        lines.append("}")
        return "\n".join(lines)

    return "JsonValue"


def _content_type(content: Any) -> str:
    if not isinstance(content, dict) or not content:
        return "never"
    lines = ["{"]
    for media_type, media in sorted(content.items()):
        schema = media.get("schema", {}) if isinstance(media, dict) else {}
        rendered = schema_to_typescript(schema)
        if "\n" in rendered:
            lines.append(f"  {_quoted(media_type)}:")
            lines.append(_indent(rendered, 4) + ";")
        else:
            lines.append(f"  {_quoted(media_type)}: {rendered};")
    lines.append("}")
    return "\n".join(lines)


def _parameter_type(parameter: dict[str, Any]) -> str:
    if isinstance(parameter.get("schema"), dict):
        return schema_to_typescript(parameter["schema"])
    content = parameter.get("content")
    if isinstance(content, dict) and content:
        first_media = content[sorted(content)[0]]
        if isinstance(first_media, dict):
            return schema_to_typescript(first_media.get("schema", {}))
    return "JsonValue"


def _render_parameters(parameters: list[Any]) -> str:
    resolved: dict[tuple[str, str], dict[str, Any]] = {}
    for parameter in parameters:
        if not isinstance(parameter, dict) or "$ref" in parameter:
            continue
        location = str(parameter.get("in", ""))
        name = str(parameter.get("name", ""))
        if location in PARAMETER_LOCATIONS and name:
            resolved[(location, name)] = parameter

    lines = ["{"]
    for location in PARAMETER_LOCATIONS:
        entries = [
            (name, parameter)
            for (candidate, name), parameter in resolved.items()
            if candidate == location
        ]
        if not entries:
            lines.append(f"  {location}?: never;")
            continue
        lines.append(f"  {location}:")
        lines.append("    {")
        for name, parameter in sorted(entries):
            optional = "" if parameter.get("required") else "?"
            rendered = _parameter_type(parameter)
            if "\n" in rendered:
                lines.append(f"      {_quoted(name)}{optional}:")
                lines.append(_indent(rendered, 8) + ";")
            else:
                lines.append(f"      {_quoted(name)}{optional}: {rendered};")
        lines.append("    };")
    lines.append("}")
    return "\n".join(lines)


def _render_request_body(request_body: Any) -> tuple[str, bool]:
    if not isinstance(request_body, dict):
        return "never", False
    if "$ref" in request_body:
        return "JsonObject", bool(request_body.get("required"))
    content = _content_type(request_body.get("content", {}))
    return "{\n" + _indent("content:\n" + _indent(content, 2) + ";", 2) + "\n}", bool(
        request_body.get("required")
    )


def _render_responses(responses: Any) -> str:
    if not isinstance(responses, dict) or not responses:
        return "Record<string, never>"
    lines = ["{"]
    for status, response in sorted(responses.items(), key=lambda item: str(item[0])):
        lines.append(f"  {_quoted(str(status))}:")
        if not isinstance(response, dict):
            lines.append("    { content?: never };")
            continue
        if "$ref" in response:
            lines.append("    JsonObject;")
            continue
        content = response.get("content")
        if not isinstance(content, dict) or not content:
            lines.append("    { content?: never };")
            continue
        lines.append("    {")
        lines.append("      content:")
        lines.append(_indent(_content_type(content), 8) + ";")
        lines.append("    };")
    lines.append("}")
    return "\n".join(lines)


def _operation_identifier(operation: dict[str, Any], method: str, path: str) -> str:
    operation_id = operation.get("operationId")
    if operation_id:
        return str(operation_id)
    fallback = re.sub(r"[^A-Za-z0-9_]+", "_", f"{method}_{path}").strip("_")
    return fallback or f"{method}_root"


def _render_operation(
    operation: dict[str, Any], path_parameters: list[Any], method: str, path: str
) -> str:
    operation_parameters = operation.get("parameters", [])
    parameters = [
        *path_parameters,
        *(operation_parameters if isinstance(operation_parameters, list) else []),
    ]
    body_type, body_required = _render_request_body(operation.get("requestBody"))
    lines = ["{"]
    lines.append("  parameters:")
    lines.append(_indent(_render_parameters(parameters), 4) + ";")
    if body_type == "never":
        lines.append("  requestBody?: never;")
    else:
        optional = "" if body_required else "?"
        lines.append(f"  requestBody{optional}:")
        lines.append(_indent(body_type, 4) + ";")
    lines.append("  responses:")
    lines.append(_indent(_render_responses(operation.get("responses", {})), 4) + ";")
    if operation.get("security"):
        lines.append("  authenticated: true;")
    else:
        lines.append("  authenticated: false;")
    lines.append(f"  method: {_quoted(method.upper())};")
    lines.append(f"  path: {_quoted(path)};")
    lines.append("}")
    return "\n".join(lines)


def render_contract(contract: dict[str, Any]) -> str:
    """Render a deterministic TypeScript contract from parsed OpenAPI JSON."""

    canonical = (json.dumps(contract, indent=2, sort_keys=True) + "\n").encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    paths = contract.get("paths", {})
    schemas = contract.get("components", {}).get("schemas", {})

    operations: dict[str, tuple[dict[str, Any], list[Any], str, str]] = {}
    path_methods: dict[str, list[tuple[str, str]]] = {}
    for path, path_item in sorted(paths.items()):
        if not isinstance(path_item, dict):
            continue
        path_parameters = path_item.get("parameters", [])
        if not isinstance(path_parameters, list):
            path_parameters = []
        methods: list[tuple[str, str]] = []
        for method in HTTP_METHODS:
            operation = path_item.get(method)
            if not isinstance(operation, dict):
                continue
            operation_id = _operation_identifier(operation, method, path)
            if operation_id in operations:
                raise ValueError(f"duplicate OpenAPI operationId: {operation_id}")
            operations[operation_id] = (operation, path_parameters, method, path)
            methods.append((method, operation_id))
        path_methods[path] = methods

    lines = [
        "/**",
        " * GENERATED FILE — DO NOT EDIT.",
        " * Source: outputs/contracts/openapi.json",
        f" * OpenAPI SHA-256: {digest}",
        " * Refresh: npm run contracts:generate",
        " */",
        "",
        "export type JsonPrimitive = string | number | boolean | null;",
        "export type JsonValue = JsonPrimitive | JsonObject | Array<JsonValue>;",
        "export interface JsonObject { [key: string]: JsonValue | undefined }",
        "",
        f"export const OPENAPI_SHA256 = {_quoted(digest)} as const;",
        f"export const OPENAPI_PATH_COUNT = {len(path_methods)} as const;",
        f"export const OPENAPI_OPERATION_COUNT = {len(operations)} as const;",
        "",
        "export interface components {",
        "  schemas: {",
    ]
    for name, schema in sorted(schemas.items()):
        rendered = schema_to_typescript(schema)
        lines.append(f"    {_quoted(name)}:")
        lines.append(_indent(rendered, 6) + ";")
    lines.extend(["  };", "}", ""])

    for name in sorted(schemas):
        if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", name):
            lines.append(f"export type {name} = components[\"schemas\"][{_quoted(name)}];")
    lines.extend(["", "export interface operations {"])
    for operation_id in sorted(operations):
        operation, path_parameters, method, path = operations[operation_id]
        rendered = _render_operation(operation, path_parameters, method, path)
        lines.append(f"  {_quoted(operation_id)}:")
        lines.append(_indent(rendered, 4) + ";")
    lines.extend(["}", "", "export interface paths {"])
    for path, methods in path_methods.items():
        lines.append(f"  {_quoted(path)}:")
        lines.append("    {")
        for method, operation_id in methods:
            lines.append(f"      {method}: operations[{_quoted(operation_id)}];")
        lines.append("    };")
    lines.extend(
        [
            "}",
            "",
            "export type HttpMethod =",
            '  | "get"',
            '  | "post"',
            '  | "put"',
            '  | "patch"',
            '  | "delete"',
            '  | "options"',
            '  | "head"',
            '  | "trace";',
            "export type ApiPath = keyof paths;",
            "export type ApiMethod<P extends ApiPath> = Extract<keyof paths[P], HttpMethod>;",
            "export type OperationFor<",
            "  P extends ApiPath,",
            "  M extends ApiMethod<P>,",
            "> = paths[P][M];",
            "",
            "type ContentValue<C> = C extends Record<string, unknown>",
            '  ? "application/json" extends keyof C',
            '    ? C["application/json"]',
            "    : C[keyof C]",
            "  : never;",
            "type ResponsesOf<T> = T extends { responses: infer R } ? R : never;",
            "",
            "export type RequestBodyFor<",
            "  P extends ApiPath,",
            "  M extends ApiMethod<P>,",
            "> = OperationFor<P, M> extends { requestBody?: infer B }",
            "  ? NonNullable<B> extends { content: infer C }",
            "    ? ContentValue<C>",
            "    : never",
            "  : never;",
            "",
            "export type ResponseStatusFor<",
            "  P extends ApiPath,",
            "  M extends ApiMethod<P>,",
            "> = keyof ResponsesOf<OperationFor<P, M>>;",
            "",
            "export type ResponseBodyFor<",
            "  P extends ApiPath,",
            "  M extends ApiMethod<P>,",
            "  S extends ResponseStatusFor<P, M>,",
            "> = ResponsesOf<OperationFor<P, M>>[S] extends { content: infer C }",
            "  ? ContentValue<C>",
            "  : never;",
            "",
        ]
    )
    return "\n".join(lines)


def generate(contract_path: Path = DEFAULT_CONTRACT, output_path: Path = DEFAULT_OUTPUT) -> str:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    rendered = render_contract(contract)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")
    return rendered


def check(contract_path: Path = DEFAULT_CONTRACT, output_path: Path = DEFAULT_OUTPUT) -> str:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    rendered = render_contract(contract)
    if not output_path.is_file() or output_path.read_text(encoding="utf-8") != rendered:
        raise ValueError(
            "Generated TypeScript API contract drift: run "
            f"{Path(__file__).name} to refresh {output_path}"
        )
    return rendered


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="fail on drift without writing")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        rendered = (
            check(args.contract, args.output)
            if args.check
            else generate(args.contract, args.output)
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"contract generation failed: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "contract": str(args.contract),
                "output": str(args.output),
                "check": args.check,
                "bytes": len(rendered.encode("utf-8")),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
