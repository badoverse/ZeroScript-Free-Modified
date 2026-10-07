# ZeroScript for Claude Code

Use Claude Code as your Roblox Studio agent, running Claude Opus 5.5, on Windows, macOS or Linux. Claude Code connects straight to Roblox Studio's built-in MCP server, the same one ZeroScript's bridge uses, and calls Studio's tools directly. You don't need the browser extension or the bridge for this.

This folder is the workspace you open in Claude Code:

- **`CLAUDE.md`:** how to work in Studio, ported from ZeroScript's prompt and its tested tool notes.
- **`.claude/settings.json`:** runs this workspace on Claude Opus 5.5 and lets Claude use Studio's read-only tools without asking. Anything that changes your place still asks first.
- **`.mcp.json`:** created by the setup script, because it holds paths specific to your machine.

## Setup

1. **Install Roblox Studio.** On Windows and macOS, use the normal installer. On Linux, install it through [Vinegar](https://vinegarhq.org) (Flatpak or native), which runs Studio under Wine.
2. **Turn on Studio's MCP server.** Open a place in Studio, then (first time only) click **Assistant AI** → **…** → **Manage MCP Servers** → **Enable Studio as MCP Server**. Studio updates can switch this back off.
3. **Run the setup once**, from the ZeroScript folder:
   - Windows: `py -3 setup_claude_code.py`
   - macOS and Linux: `python3 setup_claude_code.py`
4. **Open this `claude-code` folder in Claude Code.**
   - VS Code: **File → Open Folder** and pick this folder. Opening the whole ZeroScript folder won't load it.
   - Terminal: `cd claude-code`, then `claude`.
5. **Approve the `roblox` server** when Claude Code asks, and check that `/mcp` shows it connected.

Re-run the setup if you move the ZeroScript folder or switch to a different Python install.

To try it, ask "What's in Workspace?", then "Create a red anchored part named ClaudeTest at (0, 10, 0)".

## Linux status

The connection fails under Vinegar today. Tested on 2026-10-07 with Studio 0.741 and Vinegar's Wine 11.15.

What works:
- The launcher finds and starts `StudioMCP.exe`.
- Claude Code connects to it.
- Studio connects to it on `localhost:13469`.

What fails: `StudioMCP` never reads the data Studio sends, so the WebSocket handshake times out and no tools appear. That looks like a Wine socket bug, not a setup problem. Until it's fixed, use Studio on Windows or macOS.

## Troubleshooting

- **`roblox` shows no tools.** Studio wasn't ready when Claude Code connected. Make sure a place is open and the MCP toggle is on, then reconnect `roblox` from `/mcp`.
- **`roblox` fails to start.** From this folder, run `python3 ../launch_studio_mcp.py` (Windows: `py -3 ..\launch_studio_mcp.py`) and read what it prints. If startup is just slow, set the `MCP_TIMEOUT` environment variable (milliseconds, e.g. `60000`) before starting Claude Code.
- **Windows and WSL.** Run Claude Code on Windows itself, not inside WSL: the launcher has to run on the same system as Studio.
- **ZeroScript's bridge.** Close it while you use Claude Code, since both would start a StudioMCP.
- **Non-standard installs.** Add overrides to the `roblox` entry in `.mcp.json`. The setup script keeps them when you run it again.
  ```json
  "env": {
    "ZS_STUDIO_MCP_PATH": "/path/to/StudioMCP.exe",
    "ZS_STUDIO_MCP_WINE": "env WINEPREFIX=/path/to/prefix wine"
  }
  ```
  `ZS_STUDIO_MCP_PATH` points at the StudioMCP binary, or the folder that holds it. `ZS_STUDIO_MCP_WINE` (Linux only) is the command that runs it under Wine.

## Testing on a new machine

`test_launch_studio_mcp.py` in the ZeroScript folder checks the launcher logic for every OS. Run it with `python3`, or `py -3` on Windows. On a real Windows or macOS machine, also check:

1. The setup script prints the StudioMCP path it found.
2. `/mcp` shows `roblox` connected, and the two prompts above work.
3. After you close Claude Code, no StudioMCP is left running. Check Task Manager on Windows, or `pgrep -af StudioMCP` on macOS.
4. ZeroScript's own bridge still starts and connects as before.

## Keeping it up to date

The tool notes in `CLAUDE.md` are copied from `TOOL_NOTES` and the system prompt in `zeroscript-extension/core/config.js`. When one changes, update the other.
