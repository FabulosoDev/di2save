#!/usr/bin/env python3
import json
import os
import re
import subprocess
from typing import Dict, List, Any

# DI2SE_ROOT is the directory that contains ./bin/di2save and ./bin/data/...
DI2SE_ROOT = os.path.abspath(os.environ.get("DI2SE_ROOT", "."))
OUT_FILE = os.environ.get("OUT_FILE", "commands.json")
MAX_DEPTH = int(os.environ.get("MAX_DEPTH", "8"))

SUBCOMMANDS_HEADER_RE = re.compile(r"^\s*Subcommands:\s*$", re.IGNORECASE)

def run_help(path: List[str]) -> str:
    # Run from the bin/ dir so relative data/ paths resolve (your package has bin/data/*)
    bin_dir = os.path.join(DI2SE_ROOT, "bin")
    cmd = ["./di2save", "--help"] + path
    p = subprocess.run(cmd, cwd=bin_dir, capture_output=True, text=True)
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

    # de-dup preserving order
    seen = set()
    out = []
    for s in subs:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out

def crawl() -> Dict[str, Dict[str, Any]]:
    registry: Dict[str, Dict[str, Any]] = {}

    def rec(cmd_path: List[str], depth: int):
        if depth > MAX_DEPTH:
            return
        if cmd_path:
            dotted = ".".join(cmd_path)
            registry[dotted] = {"argv": cmd_path}

        help_text = run_help(cmd_path)
        for s in parse_subcommands(help_text):
            rec(cmd_path + [s], depth + 1)

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
