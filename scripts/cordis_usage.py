"""Inventory the Cordis APIs that mapped upstream packages use, at the pin.

Usage:
    python scripts/cordis_usage.py [--upstream PATH] [--json]

Reads each mapped package's TypeScript sources (tests excluded) from the pinned
commit through git, and reports which Cordis features appear and in which packages,
with the earliest milestone that needs them. docs/cordis-alignment.md is written from
this report; re-run it whenever the pin moves.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

from upstream_changes import default_upstream, git, load_map

# Feature name -> pattern over TypeScript source. Group 1, when present, refines the key.
FEATURES: dict[str, str] = {
    "ctx.on/once": r"\bctx\.(?:on|once)\(",
    "ctx.emit": r"\bctx\.emit\(",
    "ctx.parallel": r"\bctx\.parallel\(",
    "ctx.serial": r"\bctx\.serial\(",
    "ctx.bail": r"\bctx\.bail\(",
    "ctx.waterfall": r"\bctx\.waterfall\(",
    "ctx.events.dispatch": r"\bctx\.events\.dispatch\(",
    "ctx.effect": r"\bctx\.effect\(",
    "ctx.inject": r"\bctx\.inject\(",
    "ctx.plugin": r"\bctx\.plugin\(",
    "ctx.get": r"\bctx\.get\(",
    "ctx.provide": r"\bctx\.provide\(",
    "ctx.extend": r"\bctx\.extend\(",
    "ctx.isolate / Context.isolate": r"\b(?:ctx|Context)\.isolate\b",
    "ctx.logger": r"\bctx\.logger\b",
    "ctx.root.loader": r"\bctx\.root\.loader\b",
    "ctx.reflect.store": r"\bctx\.reflect\.store\b",
    "fiber.assertActive": r"\bfiber\.assertActive\(",
    "fiber.entry": r"\bfiber\.entry\b",
    "fiber.state / FiberState": r"\b(?:fiber\.state|FiberState\.)",
    "fiber.uid": r"\bfiber\.uid\b",
    "fiber.await": r"\bfiber\.await\(",
    "fiber.effectiveConfig": r"\bfiber\.effectiveConfig\b",
    "internal/status": r"'internal/status'",
    "internal/plugin": r"'internal/plugin'",
    "Service subclass": r"\bextends Service\b",
    "[Service.init]": r"\[Service\.init\]",
    "[Service.check]": r"\[Service\.check\]",
    "getTraceable / symbols": r"\b(?:getTraceable|symbols\.[a-z]+)\b",
    "Volatile (cosmokit)": r"\b(?:Volatile|isVolatile)\b",
    "resolveConfig (cordis import)": (
        r"import \{[^}]*\bresolveConfig\b[^}]*\} from '@deepseek-ai/cordis'"
    ),
    "loader / include runtime import": (
        r"import \{[^}]+\} from '@deepseek-ai/cordis-plugin-(?:loader|include)'"
    ),
    "schemastery config schema": r"from '@deepseek-ai/schemastery'",
}
MILESTONE_ORDER = ["0.1", "0.2", "0.3", "0.4", "0.5"]


def package_sources(upstream: Path, pin: str, package: str) -> list[str]:
    listing = git(upstream, "ls-tree", "-r", "--name-only", pin, "--", f"{package}/src")
    texts = []
    for path in listing.splitlines():
        if path.endswith(".ts") and not path.endswith((".spec.ts", ".d.ts")):
            blob = subprocess.run(
                ["git", "-C", str(upstream), "show", f"{pin}:{path}"],
                check=True,
                capture_output=True,
                text=True,
            )
            texts.append(blob.stdout)
    return texts


def inventory(upstream: Path) -> dict[str, Any]:
    data = load_map()
    pin = data["upstream"]["commit"]
    compiled = {name: re.compile(pattern) for name, pattern in FEATURES.items()}
    users: dict[str, dict[str, str]] = defaultdict(dict)
    for package in data["packages"]:
        texts = package_sources(upstream, pin, package["upstream"])
        for name, pattern in compiled.items():
            if any(pattern.search(text) for text in texts):
                short = package["upstream"].removeprefix("packages/")
                users[name][short] = package["milestone"]
    features = {}
    for name in FEATURES:
        packages = users.get(name, {})
        milestones = sorted(set(packages.values()), key=MILESTONE_ORDER.index)
        features[name] = {
            "packages": sorted(packages),
            "first_milestone": milestones[0] if milestones else None,
        }
    return {"pin": pin, "features": features}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--upstream", type=Path, default=default_upstream())
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = inventory(args.upstream)
    if args.json:
        print(json.dumps(report, indent=2))
        return
    print(f"Cordis usage in mapped packages at {report['pin'][:7]}")
    for name, entry in report["features"].items():
        count = len(entry["packages"])
        first = entry["first_milestone"] or "-"
        shown = ", ".join(entry["packages"][:5]) + (f" +{count - 5}" if count > 5 else "")
        print(f"{name:34} {count:3} pkgs  first {first:4} {shown}")


if __name__ == "__main__":
    main()
