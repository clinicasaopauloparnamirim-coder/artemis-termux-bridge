#!/usr/bin/env python3
"""Authenticated GitHub issue bridge for the owner's ARTEMIS Termux environment."""
from __future__ import annotations
import json, os, platform, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

OWNER = os.environ.get("ARTEMIS_BRIDGE_OWNER", "clinicasaopauloparnamirim-coder")
QUEUE_REPO = os.environ.get("ARTEMIS_BRIDGE_QUEUE", "artemis-termux-bridge-queue")
ISSUE = os.environ.get("ARTEMIS_BRIDGE_ISSUE", "1")
API_ROOT = f"repos/{OWNER}/{QUEUE_REPO}/issues/{ISSUE}"
CMD_OPEN = "<!-- TERMUX_BRIDGE_CMD -->"
CMD_CLOSE = "<!-- /TERMUX_BRIDGE_CMD -->"
POLL_SECONDS = 4
MAX_TIMEOUT = 180
MAX_OUTPUT_CHARS = 12000
STATE_DIR = Path.home() / ".config" / "artemis-termux-bridge"
STATE_FILE = STATE_DIR / "state.json"
DEFAULT_CWD = Path("/root/artemis")
WORKDIR = Path(os.environ.get("ARTEMIS_BRIDGE_CWD", str(DEFAULT_CWD if DEFAULT_CWD.exists() else Path.home())))

def run_gh(args: list[str], timeout: int = 45) -> str:
    proc = subprocess.run(["gh", *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "gh command failed").strip()[:1200])
    return proc.stdout

def get_comments() -> list[dict[str, Any]]:
    raw = run_gh(["api", "--paginate", "--slurp", f"{API_ROOT}/comments?per_page=100"])
    parsed = json.loads(raw or "[]")
    if not isinstance(parsed, list):
        return []
    if parsed and all(isinstance(page, list) for page in parsed):
        comments = [item for page in parsed for item in page]
    else:
        comments = parsed
    return sorted([c for c in comments if isinstance(c, dict) and str(c.get("id", "")).isdigit()], key=lambda c: int(c["id"]))

def post_comment(body: str) -> None:
    run_gh(["api", "--method", "POST", f"{API_ROOT}/comments", "--raw-field", "body=" + body])

def load_state() -> dict[str, Any]:
    try:
        val = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return val if isinstance(val, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}

def save_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    tmp.replace(STATE_FILE)
    try:
        STATE_FILE.chmod(0o600)
    except OSError:
        pass

def parse_command(body: str) -> dict[str, Any] | None:
    start = body.find(CMD_OPEN)
    if start < 0:
        return None
    start += len(CMD_OPEN)
    end = body.find(CMD_CLOSE, start)
    if end < 0:
        return None
    try:
        data = json.loads(body[start:end].strip())
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("cmd"), str):
        return None
    cmd = data["cmd"].strip()
    if not cmd or len(cmd) > 10000:
        return None
    try:
        timeout = int(data.get("timeout", 90))
    except (TypeError, ValueError):
        timeout = 90
    timeout = max(1, min(timeout, MAX_TIMEOUT))
    label = str(data.get("label", "ChatGPT command")).replace("\n", " ")[:100]
    return {"cmd": cmd, "timeout": timeout, "label": label}

def safe_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return value[-MAX_OUTPUT_CHARS:]

def execute_command(command: dict[str, Any]) -> tuple[int, str]:
    cmd = command["cmd"]
    if cmd == "__STOP_BRIDGE__":
        return 0, "Remote stop requested. The bridge will exit after posting this result."
    if cmd == "__BRIDGE_STATUS__":
        return 0, json.dumps({"python": sys.version.split()[0], "platform": platform.platform(), "cwd": str(WORKDIR), "artemis_dir_exists": Path("/root/artemis").exists(), "time_utc": datetime.now(timezone.utc).isoformat()}, indent=2)
    print(f"[{datetime.now().isoformat(timespec='seconds')}] Received: {command['label']}")
    print("$ " + cmd[:500], flush=True)
    try:
        proc = subprocess.run(["bash", "-lc", cmd], cwd=str(WORKDIR), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=command["timeout"], check=False)
        return proc.returncode, safe_output(proc.stdout)
    except subprocess.TimeoutExpired as exc:
        out = safe_output(exc.stdout)
        return 124, (out + "\n[bridge] Command timed out after " + str(command["timeout"]) + " seconds.")[-MAX_OUTPUT_CHARS:]
    except Exception as exc:
        return 125, f"{type(exc).__name__}: {exc}"

def result_body(comment_id: int, command: dict[str, Any], code: int, output: str) -> str:
    status = "SUCCESS" if code == 0 else "ERROR"
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return ("<!-- TERMUX_BRIDGE_RESULT -->\n" f"## Termux bridge result: {status}\n\n" f"- Command comment ID: {comment_id}\n" f"- Label: {command['label']}\n" f"- Exit code: {code}\n" f"- UTC: {now}\n\n" "<details><summary>Command output</summary>\n\n<pre>\n" + output.replace("<", "&lt;") + "\n</pre>\n\n</details>")

def shutil_which(name: str) -> str | None:
    for path in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(path) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None

def main() -> int:
    if not shutil_which("gh"):
        print("ERROR: GitHub CLI (gh) is required.", file=sys.stderr)
        return 2
    try:
        login = run_gh(["api", "user", "--jq", ".login"]).strip()
        if login != OWNER:
            print(f"ERROR: authenticated as {login}, expected {OWNER}.", file=sys.stderr)
            return 2
        run_gh(["api", f"repos/{OWNER}/{QUEUE_REPO}/issues/{ISSUE}"])
    except Exception as exc:
        print(f"ERROR: cannot access private queue: {exc}", file=sys.stderr)
        return 2

    state = load_state()
    comments = get_comments()
    if "last_seen_id" not in state:
        state["last_seen_id"] = max((int(c["id"]) for c in comments), default=0)
        save_state(state)
        post_comment("<!-- TERMUX_BRIDGE_STATUS -->\n## TERMUX BRIDGE ONLINE\n\n" f"- Authenticated GitHub account: {OWNER}\n" f"- Working directory: {WORKDIR}\n" f"- ARTEMIS directory exists: {Path('/root/artemis').exists()}\n" f"- Python: {sys.version.split()[0]}\n" f"- Platform: {platform.platform()}\n" f"- Started (UTC): {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n\nThe bridge is polling for owner-authored commands.")
        print("TERMUX BRIDGE ONLINE. Waiting for commands from ChatGPT.")
        print(f"Private queue: https://github.com/{OWNER}/{QUEUE_REPO}/issues/{ISSUE}")
        print(f"Working directory: {WORKDIR}")
        print("Leave this Termux session running. Press Ctrl+C to stop.", flush=True)

    while True:
        try:
            comments = get_comments()
            cursor = int(state.get("last_seen_id", 0))
            for comment in comments:
                comment_id = int(comment["id"])
                if comment_id <= cursor:
                    continue
                cursor = comment_id
                state["last_seen_id"] = cursor
                save_state(state)
                author = (comment.get("user") or {}).get("login", "")
                if author != OWNER:
                    continue
                command = parse_command(str(comment.get("body") or ""))
                if command is None:
                    continue
                code, output = execute_command(command)
                try:
                    post_comment(result_body(comment_id, command, code, output or "(no output)"))
                    print(f"Result posted for command {comment_id}; exit={code}.", flush=True)
                except Exception as exc:
                    print(f"ERROR posting result for command {comment_id}: {exc}", file=sys.stderr, flush=True)
                if command["cmd"] == "__STOP_BRIDGE__":
                    return 0
        except KeyboardInterrupt:
            print("\nBridge stopped by Ctrl+C.")
            return 0
        except Exception as exc:
            print(f"[bridge poll error] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    raise SystemExit(main())
