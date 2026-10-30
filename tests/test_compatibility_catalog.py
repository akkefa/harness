"""Keep docs/compatibility-cases.json and @pytest.mark.upstream tests in step.

Every Python test that claims an upstream origin must be listed in the catalog under
that origin, and every catalog case must point at tests that exist and carry the mark.
"""

from __future__ import annotations

import ast
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CLASSIFICATIONS = {"ported", "adapted", "not-applicable"}
SOURCE = re.compile(r"(?P<path>packages/[a-z0-9-]+/[a-z0-9-]+/\S+\.spec\.ts)::(?P<title>.+)")


def _is_upstream_mark(node: ast.expr) -> str | None:
    if not (isinstance(node, ast.Call) and node.args):
        return None
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr == "upstream"):
        return None
    mark = func.value
    if not (isinstance(mark, ast.Attribute) and mark.attr == "mark"):
        return None
    if not (isinstance(mark.value, ast.Name) and mark.value.id == "pytest"):
        return None
    first = node.args[0]
    return first.value if isinstance(first, ast.Constant) and isinstance(first.value, str) else ""


def upstream_marks(tests_root: Path) -> dict[str, str]:
    """Map each marked test node id to the upstream source its mark names."""
    marks: dict[str, str] = {}
    for path in sorted(tests_root.rglob("test_*.py")):
        relative = path.relative_to(tests_root.parent).as_posix()
        tree = ast.parse(path.read_text())
        for node in tree.body:
            members: list[tuple[str, ast.AST]] = (
                [(node.name, node)]
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
                else []
            )
            if isinstance(node, ast.ClassDef):
                members = [
                    (f"{node.name}::{child.name}", child)
                    for child in node.body
                    if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef)
                ]
            for name, member in members:
                assert isinstance(member, ast.FunctionDef | ast.AsyncFunctionDef)
                for decorator in member.decorator_list:
                    source = _is_upstream_mark(decorator)
                    if source is not None:
                        marks[f"{relative}::{name}"] = source
    return marks


def catalog_problems(catalog: dict[str, Any], marks: dict[str, str], mapped: set[str]) -> list[str]:
    problems: list[str] = []
    cases: list[dict[str, Any]] = catalog["cases"]
    files = {entry["path"]: entry for entry in catalog["source_files"]}
    for case_id, count in Counter(case["id"] for case in cases).items():
        if count > 1:
            problems.append(f"duplicate case id {case_id}")
    if len(files) != len(catalog["source_files"]):
        problems.append("duplicate source file")
    for entry in catalog["source_files"]:
        if not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
            problems.append(f"bad sha256 for {entry['path']}")
    used_files: set[str] = set()
    claimed: set[str] = set()
    for case in cases:
        match = SOURCE.fullmatch(case["source"])
        if match is None:
            problems.append(f"{case['id']}: source must be 'packages/.../x.spec.ts::title'")
            continue
        spec = match["path"]
        used_files.add(spec)
        if not any(spec.startswith(package + "/") for package in mapped):
            problems.append(f"{case['id']}: {spec} is outside every mapped package")
        if spec not in files:
            problems.append(f"{case['id']}: {spec} missing from source_files")
        if case["classification"] not in CLASSIFICATIONS:
            problems.append(f"{case['id']}: unknown classification {case['classification']}")
        if case["classification"] != "not-applicable" and not case["python_tests"]:
            problems.append(f"{case['id']}: no Python tests")
        for test in case["python_tests"]:
            claimed.add(test)
            if marks.get(test) != case["source"]:
                problems.append(f"{case['id']}: {test} lacks the matching upstream mark")
    for test, source in marks.items():
        if test not in claimed:
            problems.append(f"{test} is marked upstream({source!r}) but not catalogued")
    for path in files.keys() - used_files:
        problems.append(f"source file {path} has no cases")
    return problems


def test_catalog_matches_marked_tests() -> None:
    catalog = json.loads((ROOT / "docs" / "compatibility-cases.json").read_text())
    upstream_map = json.loads((ROOT / "docs" / "upstream.json").read_text())
    assert catalog["upstream_commit"] == upstream_map["upstream"]["commit"]
    mapped = {package["upstream"] for package in upstream_map["packages"]}
    assert catalog_problems(catalog, upstream_marks(ROOT / "tests"), mapped) == []


SPEC = "packages/core/session/tests/surface.spec.ts"
GOOD: dict[str, Any] = {
    "source_files": [{"path": SPEC, "sha256": "0" * 64}],
    "cases": [
        {
            "id": "session-surface-1",
            "source": f"{SPEC}::replaces a range",
            "classification": "ported",
            "python_tests": ["tests/test_x.py::test_replace"],
        }
    ],
}
MARKS = {"tests/test_x.py::test_replace": f"{SPEC}::replaces a range"}
MAPPED = {"packages/core/session"}


def test_checker_accepts_a_consistent_catalog() -> None:
    assert catalog_problems(GOOD, MARKS, MAPPED) == []


def test_checker_rejects_an_uncatalogued_mark() -> None:
    extra = {**MARKS, "tests/test_x.py::test_other": f"{SPEC}::other"}
    assert any("not catalogued" in p for p in catalog_problems(GOOD, extra, MAPPED))


def test_checker_rejects_a_case_without_its_mark() -> None:
    assert any("lacks the matching" in p for p in catalog_problems(GOOD, {}, MAPPED))


def test_checker_rejects_an_unmapped_source() -> None:
    assert any("outside every mapped" in p for p in catalog_problems(GOOD, MARKS, set()))


def test_marks_are_found_in_functions_and_classes(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_sample.py").write_text(
        "import pytest\n\n"
        f"@pytest.mark.upstream('{SPEC}::a')\n"
        "def test_a() -> None: ...\n\n"
        "class TestGroup:\n"
        f"    @pytest.mark.upstream('{SPEC}::b')\n"
        "    async def test_b(self) -> None: ...\n"
    )
    assert upstream_marks(tests) == {
        "tests/test_sample.py::test_a": f"{SPEC}::a",
        "tests/test_sample.py::TestGroup::test_b": f"{SPEC}::b",
    }
