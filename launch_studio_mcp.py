# SPDX-License-Identifier: GPL-3.0-or-later
# launch_studio_mcp.py
# ──────────────────────────────────────────────────────────────────────────
#  Robust launcher for Roblox's StudioMCP.exe (the Studio MCP studio server).
#
#  Roblox ships a %LOCALAPPDATA%\Roblox\mcp.bat, but it hard-codes ONE Studio
#  version path. When Studio auto-updates, that folder is eventually removed and
#  the .bat's fallback branch is broken batch syntax (`else` on its own line),
#  so StudioMCP.exe never launches -> the bridge sees 0 tools -> the extension
#  reports "Bridge or Studio offline".
#
#  This launcher sidesteps that entirely: it finds the NEWEST StudioMCP.exe
#  across all installed Studio versions and launches it, transparently forwarding
#  stdio and any CLI args. It also supports an explicit override path via
#  `ZS_STUDIO_MCP_PATH` when discovery is not enough.
#
#  Linux: Roblox Studio runs under Wine through Vinegar (Flatpak or native).
#  StudioMCP.exe is found in Vinegar's version folders and run with Vinegar's
#  own Wine build and Studio prefix - the same environment Studio runs in.
#  `ZS_STUDIO_MCP_WINE` replaces that Wine command for any other setup, e.g.
#  "env WINEPREFIX=/path/to/prefix wine".
#
#  Any MCP client can use this as its server command (the bridge, Claude Code).
#  The server never outlives its client: a leftover StudioMCP keeps Studio's
#  MCP port and hijacks every later session (see _kill_orphan_studio_mcp in
#  bridge.py). On macOS/Linux this process becomes the server (exec); on
#  Windows the server is tied to us with a kill-on-close job object.
# ──────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Mapping, Optional

ENV_OVERRIDE = "ZS_STUDIO_MCP_PATH"
WINE_OVERRIDE = "ZS_STUDIO_MCP_WINE"
WINDOWS_STUDIO_EXECUTABLES = ("RobloxStudioBeta.exe", "RobloxStudio.exe")
MAC_STUDIO_EXECUTABLES = ("RobloxStudio", "RobloxStudioBeta", "Roblox")
VINEGAR_FLATPAK_ID = "org.vinegarhq.Vinegar"


def _candidate_roots() -> list[Path]:
    """Directories that may contain Roblox Studio version folders (Windows)."""
    roots: list[Path] = []
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        roots.append(Path(local_appdata) / "Roblox" / "Versions")
    for env in ("ProgramFiles", "ProgramFiles(x86)"):
        value = os.environ.get(env)
        if value:
            roots.append(Path(value) / "Roblox" / "Versions")
    return roots


def _resolve_override_path(path_value: str) -> Optional[Path]:
    path = Path(path_value).expanduser()
    if path.is_file():
        return path
    if path.is_dir():
        if sys.platform == "darwin":
            candidate = path / "Contents" / "MacOS" / "StudioMCP"
        else:
            candidate = path / "StudioMCP.exe"
        if candidate.is_file():
            return candidate
    return None


def _newest_path(paths: Iterable[Path]) -> Optional[Path]:
    try:
        return max(paths, key=lambda p: p.stat().st_mtime)
    except (ValueError, OSError):
        return None


def _find_paired_studio_mcp(roots: Iterable[Path]) -> Optional[Path]:
    """Return the StudioMCP.exe of the live Studio install under `roots`, or None.

    Roblox leaves "zombie" version folders behind after an update: they still
    contain a StudioMCP.exe but no RobloxStudioBeta.exe / RobloxStudio.exe
    (the actual Studio is gone). Picking the newest StudioMCP.exe by mtime can
    land on such a zombie, which launches fine but has no Studio to attach to ->
    the bridge sees 0 tools.

    We only consider version folders that ALSO contain a current Studio
    executable, and prefer the newest of those. We keep zombie StudioMCP.exe
    paths only as a last-resort fallback if no paired install exists.
    """
    paired: list[Path] = []
    orphans: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        try:
            for version_dir in root.iterdir():
                if not version_dir.is_dir():
                    continue
                studio_mcp = version_dir / "StudioMCP.exe"
                if not studio_mcp.is_file():
                    continue
                if any((version_dir / exe_name).is_file() for exe_name in WINDOWS_STUDIO_EXECUTABLES):
                    paired.append(studio_mcp)
                else:
                    orphans.append(studio_mcp)
        except OSError:
            continue
    return _newest_path(paired) or _newest_path(orphans)


def _find_studio_mcp_windows() -> Optional[Path]:
    """Return the path to the StudioMCP.exe of the live Studio install, or None."""
    return _find_paired_studio_mcp(_candidate_roots())


def _vinegar_data_dirs(home: Optional[Path] = None,
                       environ: Optional[Mapping[str, str]] = None) -> list[Path]:
    """Vinegar's data folders that exist: the Flatpak install first, then a native one."""
    home = Path.home() if home is None else home
    environ = os.environ if environ is None else environ
    xdg_data = Path(environ.get("XDG_DATA_HOME") or home / ".local" / "share")
    candidates = [
        home / ".var" / "app" / VINEGAR_FLATPAK_ID / "data" / "vinegar",
        xdg_data / "vinegar",
    ]
    return [d for d in candidates if d.is_dir()]


def _find_studio_mcp_linux(data_dirs: Optional[Iterable[Path]] = None) -> Optional[Path]:
    """Return the StudioMCP.exe of the Studio that Vinegar runs under Wine, or None.

    Vinegar keeps one folder per Studio version, laid out exactly like the
    Windows install (StudioMCP.exe next to RobloxStudioBeta.exe), so the same
    zombie-folder rules apply."""
    dirs = _vinegar_data_dirs() if data_dirs is None else data_dirs
    return _find_paired_studio_mcp(d / "versions" for d in dirs)


def _mac_app_candidates() -> list[Path]:
    """Locations where Roblox Studio may be installed on macOS."""
    home = Path.home()
    return [
        Path("/Applications/RobloxStudio.app"),
        home / "Applications" / "RobloxStudio.app",
        Path("/Applications/Roblox.app"),
        home / "Applications" / "Roblox.app",
        Path("/Applications/RobloxStudioBeta.app"),
        home / "Applications" / "RobloxStudioBeta.app",
    ]


def _find_studio_mcp_mac(apps: Optional[Iterable[Path]] = None) -> Optional[Path]:
    """Return the path to StudioMCP inside a Roblox Studio app bundle, or None."""
    for app in (_mac_app_candidates() if apps is None else apps):
        macos_dir = app / "Contents" / "MacOS"
        studio_mcp = macos_dir / "StudioMCP"
        if not studio_mcp.is_file():
            continue
        if any((macos_dir / exe_name).is_file() for exe_name in MAC_STUDIO_EXECUTABLES):
            return studio_mcp
    return None


def find_studio_mcp() -> Optional[Path]:
    override_value = os.environ.get(ENV_OVERRIDE)
    if override_value:
        override_path = _resolve_override_path(override_value)
        if override_path:
            return override_path
        sys.stderr.write(
            f"launch_studio_mcp: {ENV_OVERRIDE} is set but does not point to a valid StudioMCP binary: {override_value}\n"
        )
    if sys.platform == "darwin":
        return _find_studio_mcp_mac()
    if sys.platform.startswith("linux"):
        return _find_studio_mcp_linux()
    return _find_studio_mcp_windows()


def _wine_command(exe: Path,
                  data_dirs: Optional[list[Path]] = None,
                  environ: Optional[Mapping[str, str]] = None) -> list[str]:
    """Command prefix that runs a Windows exe the way Vinegar runs Studio (Linux).

    Uses the Vinegar install that owns `exe` (<data>/versions/<ver>/StudioMCP.exe),
    or the first one found for an override path outside Vinegar. A Flatpak
    Vinegar is entered with `flatpak run --die-with-parent`, so the sandbox
    dies with whoever started us."""
    environ = os.environ if environ is None else environ
    override = environ.get(WINE_OVERRIDE)
    if override:
        return shlex.split(override)
    dirs = _vinegar_data_dirs(environ=environ) if data_dirs is None else data_dirs
    data = next((d for d in dirs if d in exe.parents), dirs[0] if dirs else None)
    if data is None:
        return ["wine"]
    # "kombucha" is Vinegar's Wine build, a symlink to the current version.
    wine = data / "kombucha" / "bin" / "wine"
    wine_cmd = str(wine) if wine.is_file() else "wine"
    prefix = data / "prefixes" / "studio"
    if VINEGAR_FLATPAK_ID in data.parts:
        return ["flatpak", "run", "--die-with-parent", f"--command={wine_cmd}",
                f"--env=WINEPREFIX={prefix}", "--env=WINEDEBUG=-all", VINEGAR_FLATPAK_ID]
    return ["env", f"WINEPREFIX={prefix}", "WINEDEBUG=-all", wine_cmd]


def launch_command(exe: Path, platform: Optional[str] = None) -> list[str]:
    """The argv that starts StudioMCP on this platform (before any forwarded args)."""
    platform = sys.platform if platform is None else platform
    if platform.startswith("linux"):
        return _wine_command(exe) + [str(exe)]
    return [str(exe)]


def not_found_hint() -> str:
    if sys.platform.startswith("linux"):
        return (
            "On Linux, Roblox Studio runs under Wine through Vinegar (https://vinegarhq.org): "
            "install Studio with Vinegar, open it and enable 'Studio as MCP server' "
            "(Assistant Settings > MCP Servers). For another Wine setup, set "
            f"{ENV_OVERRIDE} to StudioMCP.exe and {WINE_OVERRIDE} to your Wine command."
        )
    return "Open Roblox Studio and enable 'Studio as MCP server' (Assistant Settings > MCP Servers)."


def _tie_to_this_process(proc: subprocess.Popen) -> None:
    """Windows: make `proc` die with this launcher, however the launcher dies.

    Windows does not kill children with their parent, so a client that kills
    us (TerminateProcess) would leave StudioMCP.exe running on Studio's port.
    A job object flagged KILL_ON_JOB_CLOSE is closed by the OS when our last
    handle goes away - at our exit - and it takes the child with it.
    Best-effort: on any failure the child simply runs as it always has.
    """
    try:
        import ctypes
        from ctypes import wintypes

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in (
                "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
        JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.SetInformationJobObject.argtypes = (
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)

        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(
                job, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
                ctypes.byref(info), ctypes.sizeof(info)):
            return
        # The job handle is deliberately never closed: it must live exactly as
        # long as this process does.
        kernel32.AssignProcessToJobObject(job, int(proc._handle))
    except Exception:
        pass


def main() -> int:
    exe = find_studio_mcp()
    binary_name = "StudioMCP" if sys.platform == "darwin" else "StudioMCP.exe"
    if not exe:
        sys.stderr.write(f"launch_studio_mcp: no {binary_name} found. {not_found_hint()}\n")
        return 1
    cmd = launch_command(exe) + sys.argv[1:]
    sys.stderr.write(f"launch_studio_mcp: using {exe}\n")
    sys.stderr.flush()
    if sys.platform != "win32":
        # Become the server instead of parenting it: whoever stops us (Claude
        # Code, the bridge's proc.terminate()) then stops StudioMCP itself.
        try:
            os.execvp(cmd[0], cmd)
        except OSError as e:
            sys.stderr.write(f"launch_studio_mcp: could not start {cmd[0]}: {e}\n")
            return 1
    proc = subprocess.Popen(cmd)
    _tie_to_this_process(proc)
    try:
        return proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        return proc.wait()


if __name__ == "__main__":
    sys.exit(main())
