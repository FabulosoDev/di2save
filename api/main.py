import json
import os
import subprocess
from typing import List, Dict, Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="di2save REST API")

DI2SE_BIN_DIR = os.environ.get("DI2SE_BIN_DIR", "/opt/di2se/bin")
DI2SAVE_CMD = os.environ.get("DI2SAVE_BIN", "./di2save")
COMMANDS_FILE = os.environ.get("COMMANDS_FILE", "/app/commands.json")
SAVE_DIR = os.environ.get("SAVE_DIR", "/data")

def load_commands() -> Dict[str, Any]:
    try:
        with open(COMMANDS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("commands.json must be a JSON object")
        return data
    except FileNotFoundError:
        raise RuntimeError(f"commands file not found: {COMMANDS_FILE}")

COMMANDS = load_commands()

def safe_join_under(base_dir: str, relative_path: str) -> str:
    base_abs = os.path.abspath(base_dir)
    candidate = os.path.abspath(os.path.join(base_abs, relative_path))
    if candidate == base_abs:
        return candidate
    if not candidate.startswith(base_abs + os.sep):
        raise HTTPException(400, "Invalid file path (must be under SAVE_DIR)")
    return candidate

class RunRequest(BaseModel):
    file: str = Field(..., description="Save file path relative to SAVE_DIR")
    extra: List[str] = Field(default_factory=list, description="Extra CLI tokens appended after --file <path>")

@app.get("/commands")
def list_commands():
    return COMMANDS

@app.post("/run/{command_path}")
def run_command(command_path: str, req: RunRequest):
    spec = COMMANDS.get(command_path)
    if not spec or "argv" not in spec:
        raise HTTPException(404, f"Unknown command: {command_path}")

    file_path = safe_join_under(SAVE_DIR, req.file)
    if not os.path.exists(file_path):
        raise HTTPException(404, "Save file not found")

    cmd = [DI2SAVE_CMD] + spec["argv"] + ["--file", file_path] + (req.extra or [])

    try:
        p = subprocess.run(
            cmd,
            cwd=DI2SE_BIN_DIR,          # important for bin/data/*
            capture_output=True,
            text=True,
            timeout=60
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Command timed out")

    return {
        "cmd": cmd,
        "exit_code": p.returncode,
        "stdout": p.stdout,
        "stderr": p.stderr,
    }

@app.get("/healthz")
def healthz():
    return {"ok": True}
