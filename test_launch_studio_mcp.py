# Quick smoke test for launch_studio_mcp.py and setup_claude_code.py
# (run: python3 test_launch_studio_mcp.py - on Windows: py -3 test_launch_studio_mcp.py). Not shipped.
# Each OS's Studio layout is faked in a temp folder, so the Windows, macOS and
# Linux discovery and launch logic is checked on any machine. The process
# lifetime checks at the end can only run on their own OS.
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import launch_studio_mcp as m
import setup_claude_code as setup

HERE = Path(__file__).resolve().parent
# A venv's python.exe on Windows is a redirector that runs the real interpreter
# as a child; process tests need the real one so killing it means something.
PY = getattr(sys, "_base_executable", None) or sys.executable
failed = False


def ok(name, cond):
    global failed
    print(("PASS" if cond else "FAIL") + "  " + name)
    if not cond:
        failed = True


def skip(name, why):
    print(f"SKIP  {name} ({why})")


def touch(path, mtime=None, content=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def studio_version(root, name, mtime, paired=True, studio_exe="RobloxStudioBeta.exe"):
    """A Studio version folder; paired=False makes a post-update zombie."""
    mcp = touch(root / name / "StudioMCP.exe", mtime)
    if paired:
        touch(root / name / studio_exe)
    return mcp


def with_env(name, value, fn):
    saved = os.environ.get(name)
    os.environ[name] = value
    try:
        return fn()
    finally:
        if saved is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = saved


with tempfile.TemporaryDirectory() as tmp_name:
    tmp = Path(tmp_name)

    # ── Windows: %LOCALAPPDATA%\Roblox\Versions ─────────────────────────
    root = tmp / "win" / "Versions"
    studio_version(root, "version-old", 1000)
    newest_paired = studio_version(root, "version-new", 2000)
    studio_version(root, "version-zombie", 3000, paired=False)
    ok("Windows: newest paired version folder beats a newer zombie",
       m._find_paired_studio_mcp([root]) == newest_paired)
    zombie_root = tmp / "win-zombie" / "Versions"
    zombie = studio_version(zombie_root, "version-z", 1000, paired=False)
    ok("Windows: a zombie is used only when nothing is paired",
       m._find_paired_studio_mcp([zombie_root]) == zombie)
    alt_root = tmp / "win-alt" / "Versions"
    alt = studio_version(alt_root, "version-a", 1000, studio_exe="RobloxStudio.exe")
    ok("Windows: RobloxStudio.exe also counts as a live install", m._find_paired_studio_mcp([alt_root]) == alt)
    ok("Windows: missing roots find nothing", m._find_paired_studio_mcp([tmp / "missing"]) is None)

    # ── macOS: app bundles ──────────────────────────────────────────────
    app = tmp / "Applications" / "RobloxStudio.app"
    mac_mcp = touch(app / "Contents" / "MacOS" / "StudioMCP")
    touch(app / "Contents" / "MacOS" / "RobloxStudio")
    no_studio = tmp / "Applications" / "Roblox.app"
    touch(no_studio / "Contents" / "MacOS" / "StudioMCP")
    ok("macOS: StudioMCP inside a Studio app bundle", m._find_studio_mcp_mac([no_studio, app]) == mac_mcp)
    ok("macOS: a bundle without Studio next to StudioMCP is skipped", m._find_studio_mcp_mac([no_studio]) is None)

    # ── Linux: Vinegar (Flatpak and native) ─────────────────────────────
    home = tmp / "home"
    flat = home / ".var" / "app" / m.VINEGAR_FLATPAK_ID / "data" / "vinegar"
    native = home / ".local" / "share" / "vinegar"
    flat_mcp = studio_version(flat / "versions", "version-f", 1000)
    native_mcp = studio_version(native / "versions", "version-n", 2000)
    ok("Linux: Flatpak and native Vinegar data folders, Flatpak first",
       m._vinegar_data_dirs(home=home, environ={}) == [flat, native])
    xdg = tmp / "xdg"
    (xdg / "vinegar").mkdir(parents=True)
    ok("Linux: XDG_DATA_HOME locates a native Vinegar",
       m._vinegar_data_dirs(home=home, environ={"XDG_DATA_HOME": str(xdg)}) == [flat, xdg / "vinegar"])
    ok("Linux: no Vinegar, no data folders", m._vinegar_data_dirs(home=tmp / "empty", environ={}) == [])
    ok("Linux: newest paired StudioMCP.exe across Vinegar installs",
       m._find_studio_mcp_linux([flat, native]) == native_mcp)

    flat_wine = touch(flat / "kombucha" / "bin" / "wine")
    ok("Linux: Flatpak Vinegar runs it in Vinegar's sandbox, Wine build and Studio prefix",
       m._wine_command(flat_mcp, data_dirs=[flat, native], environ={}) == [
           "flatpak", "run", "--die-with-parent", f"--command={flat_wine}",
           f"--env=WINEPREFIX={flat / 'prefixes' / 'studio'}", "--env=WINEDEBUG=-all",
           m.VINEGAR_FLATPAK_ID])
    ok("Linux: native Vinegar without its Wine build falls back to wine on PATH",
       m._wine_command(native_mcp, data_dirs=[flat, native], environ={}) == [
           "env", f"WINEPREFIX={native / 'prefixes' / 'studio'}", "WINEDEBUG=-all", "wine"])
    native_wine = touch(native / "kombucha" / "bin" / "wine")
    ok("Linux: native Vinegar uses its own Wine build",
       m._wine_command(native_mcp, data_dirs=[flat, native], environ={})[-1] == str(native_wine))
    flat_wine.unlink()
    ok("Linux: Flatpak Vinegar without its Wine build uses the sandbox's wine",
       "--command=wine" in m._wine_command(flat_mcp, data_dirs=[flat], environ={}))
    outside = touch(tmp / "elsewhere" / "StudioMCP.exe")
    ok("Linux: an exe outside Vinegar still gets the first Vinegar install's prefix",
       m._wine_command(outside, data_dirs=[native], environ={})[1] == f"WINEPREFIX={native / 'prefixes' / 'studio'}")
    ok("Linux: without Vinegar, plain wine", m._wine_command(outside, data_dirs=[], environ={}) == ["wine"])
    ok("Linux: ZS_STUDIO_MCP_WINE replaces the Wine command",
       m._wine_command(flat_mcp, data_dirs=[flat],
                       environ={m.WINE_OVERRIDE: "env WINEPREFIX='/my prefix' wine"})
       == ["env", "WINEPREFIX=/my prefix", "wine"])

    # ── launch_command per platform ─────────────────────────────────────
    exe = tmp / "StudioMCP.exe"
    ok("Windows: launches StudioMCP.exe directly", m.launch_command(exe, "win32") == [str(exe)])
    ok("macOS: launches StudioMCP directly", m.launch_command(exe, "darwin") == [str(exe)])
    ok("Linux: launches StudioMCP.exe under Wine",
       with_env(m.WINE_OVERRIDE, "mywine --flag", lambda: m.launch_command(exe, "linux"))
       == ["mywine", "--flag", str(exe)])

    # ── ZS_STUDIO_MCP_PATH override ─────────────────────────────────────
    ok("override: a file path is used as-is", m._resolve_override_path(str(flat_mcp)) == flat_mcp)
    if sys.platform == "darwin":
        ok("override: an app bundle resolves to its StudioMCP", m._resolve_override_path(str(app)) == mac_mcp)
    else:
        ok("override: a version folder resolves to its StudioMCP.exe",
           m._resolve_override_path(str(flat_mcp.parent)) == flat_mcp)
    ok("override: a bad path resolves to nothing", m._resolve_override_path(str(tmp / "missing")) is None)
    ok("override: ZS_STUDIO_MCP_PATH wins on every platform",
       with_env(m.ENV_OVERRIDE, str(flat_mcp), m.find_studio_mcp) == flat_mcp)

    # ── setup_claude_code.py writes .mcp.json ───────────────────────────
    ws = tmp / "workspace"
    launcher = tmp / "zs" / "launch_studio_mcp.py"
    path = setup.write_mcp_config(workspace=ws, python="/py/python3", launcher=launcher)
    cfg = json.loads(path.read_text(encoding="utf-8"))
    ok("setup: writes the roblox server with the given Python and launcher",
       cfg == {"mcpServers": {"roblox": {"command": "/py/python3", "args": [str(launcher)]}}})
    first = path.read_bytes()
    setup.write_mcp_config(workspace=ws, python="/py/python3", launcher=launcher)
    ok("setup: running it twice gives the same file", path.read_bytes() == first)
    cfg["mcpServers"]["blender"] = {"command": "uvx", "args": ["blender-mcp"]}
    cfg["mcpServers"]["roblox"]["env"] = {m.WINE_OVERRIDE: "wine"}
    path.write_text(json.dumps(cfg), encoding="utf-8")
    setup.write_mcp_config(workspace=ws, python="/new/python", launcher=launcher)
    servers = json.loads(path.read_text(encoding="utf-8"))["mcpServers"]
    ok("setup: keeps other servers and the roblox env overrides",
       servers["blender"] == {"command": "uvx", "args": ["blender-mcp"]}
       and servers["roblox"] == {"command": "/new/python", "args": [str(launcher)],
                                 "env": {m.WINE_OVERRIDE: "wine"}})
    path.write_text("{ not json", encoding="utf-8")
    try:
        setup.write_mcp_config(workspace=ws)
        refused = False
    except SystemExit:
        refused = True
    ok("setup: refuses to overwrite a broken .mcp.json",
       refused and path.read_text(encoding="utf-8") == "{ not json")
    roblox = json.loads(setup.write_mcp_config(workspace=tmp / "defaults").read_text(encoding="utf-8"))["mcpServers"]["roblox"]
    ok("setup: defaults to this Python and the repo's launcher, as absolute paths",
       roblox == {"command": sys.executable, "args": [str(HERE / "launch_studio_mcp.py")]}
       and Path(roblox["args"][0]).is_absolute())

    # ── Process lifetime on this OS ─────────────────────────────────────
    if sys.platform == "win32":
        skip("macOS/Linux: the launcher becomes the server", "macOS and Linux only")
        # Use python.exe itself as the fake StudioMCP; it records its pid.
        pid_file = tmp / "server.pid"
        code = f"import os, time; open(r'{pid_file}', 'w').write(str(os.getpid())); time.sleep(60)"
        launcher_proc = subprocess.Popen(
            [PY, str(HERE / "launch_studio_mcp.py"), "-c", code],
            env=dict(os.environ, **{m.ENV_OVERRIDE: PY}),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            if pid_file.is_file() and pid_file.read_text().strip():
                break
            time.sleep(0.1)
        server_pid = pid_file.read_text().strip() if pid_file.is_file() else ""
        launcher_proc.kill()  # TerminateProcess: the launcher gets no chance to clean up
        launcher_proc.wait()
        time.sleep(1)
        listing = subprocess.run(["tasklist", "/FI", f"PID eq {server_pid}", "/NH"],
                                 capture_output=True, text=True).stdout if server_pid else ""
        alive = bool(server_pid) and server_pid in listing
        ok("Windows: killing the launcher also kills the server (job object)", bool(server_pid) and not alive)
        if alive:
            subprocess.run(["taskkill", "/F", "/PID", server_pid], capture_output=True)
    else:
        fake = touch(tmp / "fake" / "StudioMCP.exe", content="#!/bin/sh\nexec sleep 30\n")
        fake.chmod(0o755)
        env = dict(os.environ, **{m.ENV_OVERRIDE: str(fake)})
        if sys.platform.startswith("linux"):
            env[m.WINE_OVERRIDE] = "env"  # run the fake directly instead of under Wine
        launcher_proc = subprocess.Popen(
            [PY, str(HERE / "launch_studio_mcp.py")], env=env,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            command = ""
            for _ in range(50):
                time.sleep(0.1)
                command = subprocess.run(["ps", "-o", "command=", "-p", str(launcher_proc.pid)],
                                         capture_output=True, text=True).stdout.strip()
                if command.startswith("sleep"):
                    break
            ok("macOS/Linux: the launcher becomes the server (same process, so no orphan)",
               command.startswith("sleep"))
        finally:
            launcher_proc.terminate()
            launcher_proc.wait(timeout=10)
        ok("Windows-only job object helper is a harmless no-op here", m._tie_to_this_process(object()) is None)
        skip("Windows: killing the launcher also kills the server", "Windows only")

sys.exit(1 if failed else 0)
