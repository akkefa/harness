"""The enforced lossless-JSON Schema subset used by tools."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from deskagents.llm import HarnessError
from deskagents.util.values import is_json_value

_TYPES = {"object", "array", "string", "number", "integer", "boolean", "null"}
_KEYS = {
    "type",
    "oneOf",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "enum",
    "const",
    "description",
    "title",
    "default",
    "examples",
}


class JsonSchemaError(HarnessError):
    def __init__(self, violations: Sequence[str]) -> None:
        self.violations = list(violations)
        super().__init__(f"unsupported JSON schema: {'; '.join(violations)}", "UNSUPPORTED_SCHEMA")


def _number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def _matches_type(kind: str, value: object) -> bool:
    return {
        "object": isinstance(value, Mapping),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "number": _number(value),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }[kind]


def check_supported_json_schema(schema: object) -> list[str]:
    violations: list[str] = []
    seen: set[int] = set()

    def visit(node: object, path: str) -> None:
        if not isinstance(node, Mapping):
            violations.append(f"{path} must be a schema object")
            return
        identity = id(node)
        if identity in seen:
            violations.append(f"{path} is circular")
            return
        seen.add(identity)
        for key in node:
            if key not in _KEYS:
                violations.append(f"{path}.{key} is not supported")
        if "default" in node and not is_json_value(node["default"]):
            violations.append(f"{path}.default must be lossless JSON")
        if "examples" in node and not is_json_value(node["examples"]):
            violations.append(f"{path}.examples must be lossless JSON")
        if "oneOf" in node:
            branches = node["oneOf"]
            if not isinstance(branches, list) or len(branches) < 2 or "type" in node:
                violations.append(f"{path}.oneOf must contain at least two branches")
            else:
                for index, branch in enumerate(branches):
                    visit(branch, f"{path}.oneOf[{index}]")
            seen.remove(identity)
            return
        kind = node.get("type")
        if kind is not None and kind not in _TYPES:
            violations.append(f"{path}.type is unsupported")
        if "properties" in node:
            properties = node["properties"]
            if kind != "object" or not isinstance(properties, Mapping):
                violations.append(f"{path}.properties requires object type")
            else:
                for name, child in properties.items():
                    visit(child, f"{path}.properties.{name}")
        if "required" in node:
            required = node["required"]
            properties = node.get("properties", {})
            if not isinstance(required, list) or not all(
                isinstance(item, str) for item in required
            ):
                violations.append(f"{path}.required must be an array of strings")
            elif any(item not in properties for item in required):
                violations.append(f"{path}.required names an undeclared property")
        if "additionalProperties" in node and (
            kind != "object" or not isinstance(node["additionalProperties"], bool)
        ):
            violations.append(f"{path}.additionalProperties requires object type")
        if "items" in node:
            if kind != "array":
                violations.append(f"{path}.items requires array type")
            else:
                visit(node["items"], f"{path}.items")
        for literal in ("enum", "const"):
            if literal in node:
                values = node[literal] if literal == "enum" else [node[literal]]
                if (
                    kind not in {"string", "number", "integer", "boolean", "null"}
                    or not isinstance(values, list)
                    or not values
                    or not all(_matches_type(kind, value) for value in values)
                ):
                    violations.append(f"{path}.{literal} is invalid for its type")
        seen.remove(identity)

    visit(schema, "schema")
    return violations


def assert_supported_json_schema(schema: object) -> None:
    violations = check_supported_json_schema(schema)
    if violations:
        raise JsonSchemaError(violations)


def assert_object_json_schema(schema: object) -> None:
    assert_supported_json_schema(schema)
    if not isinstance(schema, Mapping) or schema.get("type") != "object":
        raise JsonSchemaError(["schema must declare type object"])


def validate_json_schema_value(
    schema: Mapping[str, Any], value: object, path: str = ""
) -> list[str]:
    violations: list[str] = []
    label = path or "value"
    if "oneOf" in schema:
        matches = [
            not validate_json_schema_value(branch, value, path) for branch in schema["oneOf"]
        ]
        if sum(matches) != 1:
            violations.append(f"{label} must match exactly one oneOf branch")
        return violations
    kind = schema.get("type")
    if kind is not None and not _matches_type(kind, value):
        return [f"{label} must be {kind}"]
    if "enum" in schema and value not in schema["enum"]:
        violations.append(f"{label} must be one of the declared enum values")
    if "const" in schema and value != schema["const"]:
        violations.append(f"{label} must equal const")
    if kind == "object" and isinstance(value, Mapping):
        properties = schema.get("properties", {})
        for required in schema.get("required", ()):
            if required not in value:
                violations.append(f"{label}.{required} is required")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    violations.append(f"{label}.{key} is not allowed")
        for key, child in properties.items():
            if key in value:
                violations.extend(validate_json_schema_value(child, value[key], f"{label}.{key}"))
    if kind == "array" and isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            violations.extend(
                validate_json_schema_value(schema["items"], item, f"{label}[{index}]")
            )
    return violations
