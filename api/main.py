import json
import os
import subprocess
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

# ---- Config ----
DI2SE_BIN_DIR = os.environ.get("DI2SE_BIN_DIR", "/opt/di2se/bin")
DI2SAVE_CMD = os.environ.get("DI2SAVE_BIN", "./di2save")  # run from DI2SE_BIN_DIR
COMMANDS_FILE = os.environ.get("COMMANDS_FILE", "/app/commands.json")
SAVE_DIR = os.environ.get("SAVE_DIR", "/data")
CMD_TIMEOUT_SEC = int(os.environ.get("CMD_TIMEOUT_SEC", "60"))
MAX_OUTPUT_CHARS = int(os.environ.get("MAX_OUTPUT_CHARS", "400000"))  # ~400k chars

def load_commands() -> Dict[str, Any]:
    try:
        with open(COMMANDS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("commands.json must be a JSON object")
        return data
    except FileNotFoundError:
        raise RuntimeError(f"Commands file not found: {COMMANDS_FILE}")

COMMANDS: Dict[str, Any] = load_commands()

def safe_join_under(base_dir: str, relative_path: str) -> str:
    base_abs = os.path.abspath(base_dir)
    candidate = os.path.abspath(os.path.join(base_abs, relative_path))
    # must be under base_abs
    if candidate == base_abs:
        return candidate
    if not candidate.startswith(base_abs + os.sep):
        raise HTTPException(400, "Invalid file path (must be under SAVE_DIR)")
    return candidate

def clamp_output(s: str) -> str:
    if s is None:
        return ""
    if len(s) <= MAX_OUTPUT_CHARS:
        return s
    return s[:MAX_OUTPUT_CHARS] + f"\n\n[output truncated to {MAX_OUTPUT_CHARS} chars]\n"

# ---- FastAPI app ----
app = FastAPI(
    title="di2save API",
    description="REST wrapper around the di2save CLI (Dead Island 2 Save Editor).",
    version="1.0.0",
)

class RunRequest(BaseModel):
    # file is OPTIONAL now. If omitted, we do not append --file.
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

class RunResponse(BaseModel):
    cmd: List[str]
    exit_code: int
    stdout: str
    stderr: str

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.get("/commands")
def list_commands():
    """
    Returns the baked-in (or mounted override) commands.json mapping.
    """
    return COMMANDS

@app.post("/run/{command_path}", response_model=RunResponse)
def run_command(command_path: str, req: RunRequest):
    spec = COMMANDS.get(command_path)
    if not spec or "argv" not in spec or not isinstance(spec["argv"], list):
        raise HTTPException(404, f"Unknown command: {command_path}")

    cmd: List[str] = [DI2SAVE_CMD] + list(spec["argv"])

    # Only append --file if provided
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

    return RunResponse(
        cmd=cmd,
        exit_code=p.returncode,
        stdout=clamp_output(p.stdout or ""),
        stderr=clamp_output(p.stderr or ""),
    )

# ---- Scalar API Reference UI ----
# This serves a Scalar UI that reads FastAPI's /openapi.json.
# Uses a CDN script; no extra Python deps required.
@app.get("/docs", include_in_schema=False)
def scalar_docs():
    html = f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>di2save API Docs</title>
    <style>
      html, body {{
        margin: 0;
        padding: 0;
        height: 100%;
      }}
      #app {{
        height: 100vh;
      }}
    </style>
  </head>
  <body>
    <div id="app"></div>
    <script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference"></script>
    <script>
      ScalarApiReference.render(document.getElementById('app'), {{
        spec: {{
          url: '/openapi.json'
        }},
        theme: 'default'
      }});
    </script>
  </body>
</html>
"""
    return HTMLResponse(html)
