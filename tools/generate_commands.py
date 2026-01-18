#!/usr/bin/env python3
import json
import os
import re
import subprocess
from collections import deque
from typing import Dict, List, Any, Tuple, Set

DI2SE_ROOT = os.path.abspath(os.environ.get("DI2SE_ROOT", "."))
OUT_FILE = os.environ.get("OUT_FILE", "commands.json")
MAX_DEPTH = int(os.environ.get("MAX_DEPTH", "10"))

# Each line is a seed command like:
#   --help
#   --help player
#   help inventory items
HELP_SEEDS_RAW = os.environ.get("HELP_SEEDS", "").strip()

SUBCOMMANDS_HEADER_RE = re.compile(r"^\s*Subcommands:\s*$", re.IGNORECASE)

def di2save_run(argv: List[str], cwd: str) -> str:
    p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True)
    return (p.stdout or "") + "\n" + (p.stderr or "")

def run_help_tokens(path: List[str]) -> str:
    # Run from bin/ so bin/data/* is found
    bin_dir = os.path.join(DI2SE_ROOT, "bin")
    cmd = ["./di2save", "--help"] + path
    return di2save_run(cmd, cwd=bin_dir)

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

def parse_seed_line(line: str) -> Tuple[str, List[str]]:
    """
    Returns (kind, tokens)
    kind:
      - "helpflag": for '--help' seeds (tokens are the path after --help)
      - "command":  for normal command seeds, e.g. 'help inventory items'
    """
    parts = line.strip().split()
    if not parts:
        return ("", [])
    if parts[0] == "--help":
        return ("helpflag", parts[1:])
    return ("command", parts)

def crawl_from_seeds() -> Dict[str, Dict[str, Any]]:
    registry: Dict[str, Dict[str, Any]] = {}
    visited_help_paths: Set[Tuple[str, ...]] = set()

    q = deque()

    # Always include root help crawl even if seeds omitted
    q.append( ("helpflag", []) )

    # Add user-provided seeds
    if HELP_SEEDS_RAW:
        for line in HELP_SEEDS_RAW.splitlines():
            line = line.strip()
            if not line:
                continue
            kind, toks = parse_seed_line(line)
            if kind:
                q.append((kind, toks))

    while q:
        kind, toks = q.popleft()

        if kind == "helpflag":
            # This seed says: run ./di2save --help <toks> and parse Subcommands
            path = toks
            tpath = tuple(path)
            if tpath in visited_help_paths:
                continue
            visited_help_paths.add(tpath)

            depth = len(path)
            if depth > MAX_DEPTH:
                continue

            # Run help for this path and discover subcommands
            help_text = run_help_tokens(path)
            subs = parse_subcommands(help_text)

            # Queue deeper help paths
            for s in subs:
                q.append(("helpflag", path + [s]))

            # Also add the help path itself as an invokable command
            # e.g. player.inventory.ls will be added when helpflag reaches that leaf
            if path:
                dotted = ".".join(path)
                registry[dotted] = {"argv": path}

        elif kind == "command":
            # Add explicit non-flag command seeds to registry as-is
            # e.g. help.inventory.items => argv ["help","inventory","items"]
            dotted = ".".join(toks)
            registry[dotted] = {"argv": toks}

        else:
            continue

    return registry

def main():
    reg = crawl_from_seeds()
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(reg, f, indent=2, sort_keys=True)
    print(f"Wrote {len(reg)} commands to {OUT_FILE}")

if __name__ == "__main__":
    main()
