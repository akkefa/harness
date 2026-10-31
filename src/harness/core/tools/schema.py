"""Author-facing tool schema helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from harness.llm import HarnessError
from harness.util.values import snapshot_json_value

from .json_schema import (
    assert_supported_json_schema,
    validate_json_schema_value,
)


class ToolArgsError(HarnessError):
    def __init__(self, violations: list[str]) -> None:
        self.violations = violations
        super().__init__(f"invalid arguments: {'; '.join(violations)}", "INVALID_ARGS")


def value_schema_spec_to_json_schema(spec: Mapping[str, Any]) -> dict[str, Any]:
    if "oneOf" in spec:
        result = {
            key: value
            for key, value in spec.items()
            if key in {"description", "title", "default", "examples"}
        }
        result["oneOf"] = [value_schema_spec_to_json_schema(branch) for branch in spec["oneOf"]]
    else:
        kind = spec.get("type")
        if kind == "json":
            result = {
                key: value
                for key, value in spec.items()
                if key in {"description", "title", "default", "examples"}
            }
        else:
            result = {key: value for key, value in spec.items() if key != "required"}
            if kind == "object" and "properties" in result:
                compiled = parameter_schema_spec_to_json_schema(result["properties"])
                result["properties"] = compiled["properties"]
                if "required" in compiled:
                    result["required"] = compiled["required"]
            if kind == "array" and "items" in result:
                result["items"] = value_schema_spec_to_json_schema(result["items"])
    assert_supported_json_schema(result)
    return result


def parameter_schema_spec_to_json_schema(
    spec: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, node in spec.items():
        if node.get("required") is True:
            required.append(name)
        properties[name] = value_schema_spec_to_json_schema(node)
    result: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        result["required"] = required
    assert_supported_json_schema(result)
    return result


def validate_args(spec: Mapping[str, Any], args: object) -> list[str]:
    return validate_json_schema_value(parameter_schema_spec_to_json_schema(spec), args)


def project_tool_schema(
    definition: Mapping[str, Any], detach_parameters: bool = True
) -> dict[str, Any]:
    parameters = (
        snapshot_json_value(definition["parameters"])
        if detach_parameters
        else definition["parameters"]
    )
    if parameters is None:
        raise ValueError(f'tool "{definition["name"]}" parameters must be lossless JSON')
    return {
        "name": definition["name"],
        "description": definition["description"],
        "parameters": parameters,
        **({"deferLoading": True} if definition.get("deferLoading") is True else {}),
    }


def define_tool(**options: Any) -> dict[str, Any]:
    parameters_spec = options["parameters"]
    parameters = parameter_schema_spec_to_json_schema(parameters_spec)
    output = options["output"]
    output_schema = value_schema_spec_to_json_schema(output["schema"])
    execute = options["execute"]

    async def checked_execute(args: object, execution: Mapping[str, Any]) -> object:
        violations = validate_json_schema_value(parameters, args)
        if violations:
            raise ToolArgsError(violations)
        return await execute(args, execution)

    definition = {
        "name": options["name"],
        "description": options["description"],
        "parameters": parameters,
        "output": {
            "schema": output_schema,
            "render": output["render"],
            **(
                {"presentationMeta": output["presentationMeta"]}
                if "presentationMeta" in output
                else {}
            ),
        },
        "execute": checked_execute,
    }
    for key in (
        "deferLoading",
        "timeoutMs",
        "isConcurrencySafe",
        "projectContent",
        "finalizeContent",
        "presentCall",
        "presentResult",
    ):
        if key in options:
            definition[key] = options[key]
    return definition
