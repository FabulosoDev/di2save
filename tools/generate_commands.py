#!/usr/bin/env python3
import json
import os
import re
import subprocess
from typing import Dict, List, Any

# Root directory that contains ./bin/di2save and ./data/...
DI2SE_ROOT = os.environ.get("DI2SE_ROOT", ".")
DI2SAVE_REL = os.environ.get("DI2SAVE_REL", "bin/di2save")

OUT_FILE = os.environ.get("OUT_FILE", "commands.json")
MAX_DEPTH = int(os.environ.get("MAX_DEPTH", "8"))

SUBCOMMANDS_HEADER_RE = re.compile(r"^\s*Subcommands:\s*$", re.IGNORECASE)

def run_help(path: List[str]) -> str:
    exe = os.path.join(DI2SE_ROOT, DI2SAVE_REL)
    cmd = [exe, "--help"] + path
    p = subprocess.run(cmd, cwd=DI2SE_ROOT, capture_output=True, text=True)
    return (p.stdout or "") + "\n" + (p.stderr or "")

def parse_subcommands(help_text: str) -> List[str]:
    lines = help_text.splitlines()
    subs: List[str] = []
    in_block = False

    for line in lines:
        if SUBCOMMANDS_HEADER_RE.match(line):
            in_block = True
            continue
        if in_block:
            if not line.strip():
                break
            m = re.match(r"^\s{2,}([A-Za-z0-9][A-Za-z0-9\-_]*)\b", line)
            if m:
                subs.append(m.group(1))

    seen = set()
    out = []
    for s in subs:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out

def crawl() -> Dict[str, Dict[str, Any]]:
    registry: Dict[str, Dict[str, Any]] = {}

    def rec(path: List[str], depth: int):
        if depth > MAX_DEPTH:
            return
        if path:
            dotted = ".".join(path)
            registry[dotted] = {"argv": path}

        help_text = run_help(path)
        for s in parse_subcommands(help_text):
            rec(path + [s], depth + 1)

    roots = parse_subcommands(run_help([]))
    for r in roots:
        rec([r], 1)

    return registry

def main():
    reg = crawl()
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(reg, f, indent=2, sort_keys=True)
    print(f"Wrote {len(reg)} commands to {OUT_FILE}")

if __name__ == "__main__":
    main()
