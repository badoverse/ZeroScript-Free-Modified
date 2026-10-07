# SPDX-License-Identifier: GPL-3.0-or-later
# setup_claude_code.py
# ──────────────────────────────────────────────────────────────────────────
#  One-time setup for using Claude Code as the Roblox Studio agent.
#
#  Writes claude-code/.mcp.json so Claude Code starts Studio's MCP server
#  through launch_studio_mcp.py. That file holds absolute paths for THIS
#  machine - the Python running this script, and the launcher - which is why
#  it is generated rather than committed: the interpreter is `py`/`python` on
#  Windows and `python3` elsewhere, and an absolute path sidesteps both the
#  naming and the Microsoft Store python stub. Re-run after moving the folder.
#
#    Windows:          py -3 setup_claude_code.py
#    macOS and Linux:  python3 setup_claude_code.py
# ──────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import json
import sys
from pathlib import Path

import launch_studio_mcp

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE / "claude-code"
LAUNCHER = HERE / "launch_studio_mcp.py"
SERVER_ID = "roblox"


def write_mcp_config(workspace: Path = WORKSPACE, python: str = sys.executable,
                     launcher: Path = LAUNCHER) -> Path:
    """Create or update <workspace>/.mcp.json and return its path.

    Only the roblox entry's command and args are set: its other keys (such as
    an "env" block of ZS_STUDIO_MCP_* overrides) and any other servers in the
    file are kept. A file that is not valid JSON is left untouched."""
    path = workspace / ".mcp.json"
    config: dict = {}
    if path.is_file():
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as e:
            raise SystemExit(f"{path} is not valid JSON ({e}). Fix or delete it, then run this again.")
        if not isinstance(config, dict):
            raise SystemExit(f"{path} does not hold a JSON object. Fix or delete it, then run this again.")
    servers = config.setdefault("mcpServers", {})
    entry = servers.get(SERVER_ID)
    if not isinstance(entry, dict):
        entry = {}
    entry["command"] = python
    entry["args"] = [str(launcher)]
    servers[SERVER_ID] = entry
    workspace.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> int:
    # Legacy Windows consoles (cp1252) can't print every path; never crash on it.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    path = write_mcp_config()
    print(f"Wrote {path}")
    print(f"  Python:   {sys.executable}")
    print(f"  Launcher: {LAUNCHER}")
    print()
    exe = launch_studio_mcp.find_studio_mcp()
    if exe:
        print(f"Found Roblox Studio's MCP server: {exe}")
    else:
        print("Roblox Studio's MCP server was not found yet.")
        print(launch_studio_mcp.not_found_hint())
    print()
    print("Next:")
    print("  1. Open a place in Roblox Studio and turn on its MCP server:")
    print("     Assistant AI > ... > Manage MCP Servers > Enable Studio as MCP Server")
    print(f"  2. Open {WORKSPACE} in Claude Code")
    print("     (VS Code: File > Open Folder. Terminal: cd into it, then run claude).")
    print("  3. Approve the 'roblox' server and check that /mcp shows it connected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
