import json
import os
import subprocess
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse, HTMLResponse
from pydantic import BaseModel, Field

DI2SE_BIN_DIR = os.environ.get("DI2SE_BIN_DIR", "/opt/di2se/bin")
DI2SAVE_CMD = os.environ.get("DI2SAVE_BIN", "./di2save")
COMMANDS_FILE = os.environ.get("COMMANDS_FILE", "/app/commands.json")
SAVE_DIR = os.environ.get("SAVE_DIR", "/data")
CMD_TIMEOUT_SEC = int(os.environ.get("CMD_TIMEOUT_SEC", "60"))

def load_commands() -> Dict[str, Any]:
    with open(COMMANDS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise RuntimeError("commands.json must be an object")
    return data

COMMANDS = load_commands()

def safe_join_under(base_dir: str, relative_path: str) -> str:
    base_abs = os.path.abspath(base_dir)
    candidate = os.path.abspath(os.path.join(base_abs, relative_path))
    if candidate == base_abs:
        return candidate
    if not candidate.startswith(base_abs + os.sep):
        raise HTTPException(400, "Invalid file path (must be under SAVE_DIR)")
    return candidate

app = FastAPI(
    title="di2save API",
    description="REST wrapper around the di2save CLI (Dead Island 2 Save Editor).",
    version="1.0.0",
)

class RunRequest(BaseModel):
    file: Optional[str] = Field(
        default=None,
        description="Save file path relative to SAVE_DIR (omit for pure help/info commands).",
        examples=["DeadIsland2SaveGame.sav"],
    )
    extra: List[str] = Field(
        default_factory=list,
        description="Extra CLI tokens appended after the base command (and after --file if file is provided).",
        examples=[["max-xp"]],
    )

def run_cli(command_path: str, req: RunRequest):
    spec = COMMANDS.get(command_path)
    if not spec or "argv" not in spec or not isinstance(spec["argv"], list):
        raise HTTPException(404, f"Unknown command: {command_path}")

    cmd: List[str] = [DI2SAVE_CMD] + list(spec["argv"])

    if req.file:
        file_path = safe_join_under(SAVE_DIR, req.file)
        if not os.path.exists(file_path):
            raise HTTPException(404, "Save file not found")
        cmd += ["--file", file_path]

    if req.extra:
        cmd += list(req.extra)

    try:
        p = subprocess.run(
            cmd,
            cwd=DI2SE_BIN_DIR,  # important so ./data resolves
            capture_output=True,
            text=True,
            timeout=CMD_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Command timed out")

    return cmd, p

@app.get("/healthz", summary="Health check")
def healthz():
    return {"ok": True}

@app.get("/commands", summary="List available commands from commands.json")
def list_commands():
    return COMMANDS

@app.post(
    "/run/{command_path}",
    summary="Run a command and return JSON (stdout/stderr as strings)",
)
def run_json(command_path: str, req: RunRequest):
    cmd, p = run_cli(command_path, req)
    return {
        "cmd": cmd,
        "exit_code": p.returncode,
        "stdout": p.stdout,
        "stderr": p.stderr,
    }

@app.post(
    "/run-text/{command_path}",
    response_class=PlainTextResponse,
    summary="Run a command and return stdout as text/plain (real newlines)",
    responses={
        200: {"content": {"text/plain": {"example": "A save editor for the Dead Island 2 game.\n\nUsage: ...\n"}}}
    },
)
def run_text(command_path: str, req: RunRequest):
    _, p = run_cli(command_path, req)
    return p.stdout or ""

# Scalar API Reference UI (reads /openapi.json which now includes run-text)
@app.get("/docs", include_in_schema=False)
def scalar_docs():
    html = """<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>di2save API Docs</title>
    <style>
      html, body { margin: 0; padding: 0; height: 100%; }
      #app { height: 100vh; }
    </style>
  </head>
  <body>
    <div id="app"></div>
    <script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference"></script>
    <script>
      ScalarApiReference.render(document.getElementById('app'), {
        spec: { url: '/openapi.json' },
        theme: 'default'
      });
    </script>
  </body>
</html>"""
    return HTMLResponse(html)
