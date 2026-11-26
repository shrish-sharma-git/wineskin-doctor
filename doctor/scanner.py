"""
scanner.py — Discover Wineskin wrappers and extract their configuration.

Provides WrapperInfo dataclass and scan functions that never modify anything.
"""

import os
import re
import plistlib
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class WrapperInfo:
    """Everything we can learn about a Wineskin wrapper without modifying it."""
    path: str = ""
    bundle_name: str = ""
    bundle_id: str = ""

    # Wine engine
    wine_version: str = ""
    wine_bin: str = ""
    wineserver_bin: str = ""
    wine_prefix: str = ""

    # Game executable
    game_exe: str = ""
    game_exe_full: str = ""
    game_dir: str = ""

    # SDL2
    sdl2_path: str = ""
    sdl2_size: int = -1
    sdl2_arch: str = ""
    sdl2_install_name: str = ""
    sdl2_deps: list = field(default_factory=list)
    sdl2_symlink_target: str = ""  # if it's a symlink

    # Wine lib dir
    wine_lib_dir: str = ""
    wine_lib_sdl2_path: str = ""
    wine_lib_sdl2_exists: bool = False

    # XInput DLLs
    xinput_dlls: dict = field(default_factory=dict)  # name -> size
    winexinput_sys: str = ""

    # WineBus
    winebus_sys: str = ""
    winebus_so: str = ""

    # Registry — winebus service config
    reg_enable_sdl: Optional[int] = None
    reg_map_controllers: Optional[int] = None
    reg_disable_hidraw: Optional[int] = None
    reg_disable_input: Optional[int] = None
    reg_enable_hidraw: Optional[str] = None

    # DLL overrides
    dll_overrides: dict = field(default_factory=dict)

    # Frameworks dir
    frameworks_dir: str = ""

    # Plist settings
    plist_data: dict = field(default_factory=dict)

    # Errors encountered during scan
    scan_errors: list = field(default_factory=list)


def find_wineskin_wrappers(search_dirs=None) -> list[str]:
    """
    Scan directories for Wineskin-style .app bundles.

    A wrapper is identified by having Contents/SharedSupport/prefix
    and either Contents/SharedSupport/wine or a wine-like binary.
    """
    if search_dirs is None:
        search_dirs = [
            "/Applications",
            os.path.expanduser("~/Applications"),
            os.path.expanduser("~/Desktop"),
            os.path.expanduser("~/Games"),
        ]

    wrappers = []
    for search_dir in search_dirs:
        if not os.path.isdir(search_dir):
            continue
        for entry in os.listdir(search_dir):
            if not entry.endswith(".app"):
                continue
            app_path = os.path.join(search_dir, entry)
            if _is_wineskin_wrapper(app_path):
                wrappers.append(app_path)
    return sorted(wrappers)


def _is_wineskin_wrapper(app_path: str) -> bool:
    """Check if an .app bundle looks like a Wineskin wrapper."""
    contents = os.path.join(app_path, "Contents")
    prefix = os.path.join(contents, "SharedSupport", "prefix")
    wine_dir = os.path.join(contents, "SharedSupport", "wine")
    macos_dir = os.path.join(contents, "MacOS")

    if not os.path.isdir(prefix):
        return False

    # Check for wine directory
    if os.path.isdir(wine_dir):
        return True

    # Check for wineskinlauncher symlink or Sikarugir binary
    if os.path.isdir(macos_dir):
        for f in os.listdir(macos_dir):
            fp = os.path.join(macos_dir, f)
            if f.lower() in ("wineskinlauncher", "launcher"):
                return True
            if os.path.islink(fp):
                target = os.readlink(fp)
                if "launcher" in target.lower() or "sikarugir" in target.lower():
                    return True
    return False


def scan_wrapper(app_path: str) -> WrapperInfo:
    """
    Perform a comprehensive, read-only inspection of a Wineskin wrapper.

    Never modifies any file. All errors are captured in scan_errors.
    """
    info = WrapperInfo(path=app_path)
    contents = os.path.join(app_path, "Contents")

    # ── Bundle identity ──
    _read_plist(info, contents)

    # ── Wine engine ──
    _read_wine_version(info, contents)

    # ── Wine prefix ──
    info.wine_prefix = os.path.join(contents, "SharedSupport", "prefix")

    # ── Game executable ──
    _read_game_exe(info)

    # ── Frameworks & SDL2 ──
    info.frameworks_dir = os.path.join(contents, "Frameworks")
    _read_sdl2(info)

    # ── Wine lib directory ──
    _read_wine_lib(info, contents)

    # ── XInput DLLs ──
    _read_xinput(info)

    # ── WineBus ──
    _read_winebus(info, contents)

    # ── Registry ──
    _read_registry(info)

    return info


# ─── Internal helpers ────────────────────────────────────────────────


def _read_plist(info: WrapperInfo, contents: str):
    """Read Info.plist."""
    plist_path = os.path.join(contents, "Info.plist")
    try:
        with open(plist_path, "rb") as f:
            plist = plistlib.load(f)
        info.plist_data = plist
        info.bundle_name = plist.get("CFBundleName", "")
        info.bundle_id = plist.get("CFBundleIdentifier", "")
        info.game_exe = plist.get("Program Name and Path", "")
    except Exception as e:
        info.scan_errors.append(f"Info.plist: {e}")


def _read_wine_version(info: WrapperInfo, contents: str):
    """Read Wine engine version."""
    wine_dir = os.path.join(contents, "SharedSupport", "wine")
    version_file = os.path.join(wine_dir, "version")
    try:
        if os.path.isfile(version_file):
            info.wine_version = Path(version_file).read_text().strip()
    except Exception as e:
        info.scan_errors.append(f"Wine version: {e}")

    for name in ("wine", "wine64"):
        candidate = os.path.join(wine_dir, "bin", name)
        if os.path.isfile(candidate):
            info.wine_bin = candidate
            break

    wineserver = os.path.join(wine_dir, "bin", "wineserver")
    if os.path.isfile(wineserver):
        info.wineserver_bin = wineserver


def _read_game_exe(info: WrapperInfo):
    """Resolve game executable full path."""
    if info.game_exe and info.wine_prefix:
        drive_c = os.path.join(info.wine_prefix, "drive_c")
        # game_exe typically starts with /
        rel = info.game_exe.lstrip("/")
        full = os.path.join(drive_c, rel)
        if os.path.isfile(full):
            info.game_exe_full = full
            info.game_dir = os.path.dirname(full)


def _read_sdl2(info: WrapperInfo):
    """Inspect SDL2 library in Frameworks."""
    sdl2_names = ["libSDL2-2.0.0.dylib", "libSDL2.dylib"]
    for name in sdl2_names:
        candidate = os.path.join(info.frameworks_dir, name)
        if os.path.exists(candidate):
            info.sdl2_path = candidate
            break

    if not info.sdl2_path:
        return

    # Follow symlinks
    if os.path.islink(info.sdl2_path):
        info.sdl2_symlink_target = os.readlink(info.sdl2_path)
        real = os.path.realpath(info.sdl2_path)
        if os.path.isfile(real):
            info.sdl2_path = real

    try:
        info.sdl2_size = os.path.getsize(info.sdl2_path)
    except OSError:
        info.sdl2_size = -1

    if info.sdl2_size > 0:
        _get_dylib_info(info)


def _get_dylib_info(info: WrapperInfo):
    """Get architecture and install name of SDL2 dylib."""
    try:
        result = subprocess.run(
            ["file", info.sdl2_path],
            capture_output=True, text=True, timeout=5
        )
        output = result.stdout
        if "x86_64" in output:
            info.sdl2_arch = "x86_64"
        elif "arm64" in output:
            info.sdl2_arch = "arm64"
        elif "universal" in output.lower():
            info.sdl2_arch = "universal"
        else:
            info.sdl2_arch = "unknown"
    except Exception as e:
        info.scan_errors.append(f"SDL2 file type: {e}")

    try:
        result = subprocess.run(
            ["otool", "-D", info.sdl2_path],
            capture_output=True, text=True, timeout=5
        )
        lines = result.stdout.strip().split("\n")
        if len(lines) >= 2:
            info.sdl2_install_name = lines[1].strip()
    except Exception as e:
        info.scan_errors.append(f"SDL2 install name: {e}")

    try:
        result = subprocess.run(
            ["otool", "-L", info.sdl2_path],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.strip().split("\n")[1:]:
            dep = line.strip().split(" (")[0].strip()
            if dep:
                info.sdl2_deps.append(dep)
    except Exception as e:
        info.scan_errors.append(f"SDL2 deps: {e}")


def _read_wine_lib(info: WrapperInfo, contents: str):
    """Check wine/lib for SDL2 symlinks."""
    info.wine_lib_dir = os.path.join(contents, "SharedSupport", "wine", "lib")
    sdl2_in_lib = os.path.join(info.wine_lib_dir, "libSDL2-2.0.0.dylib")
    info.wine_lib_sdl2_path = sdl2_in_lib
    info.wine_lib_sdl2_exists = os.path.exists(sdl2_in_lib)


def _read_xinput(info: WrapperInfo):
    """Check XInput DLLs in system32."""
    sys32 = os.path.join(info.wine_prefix, "drive_c", "windows", "system32")
    xinput_names = [
        "xinput1_1.dll", "xinput1_2.dll", "xinput1_3.dll",
        "xinput1_4.dll", "xinput9_1_0.dll", "xinputuap.dll",
    ]
    for name in xinput_names:
        p = os.path.join(sys32, name)
        if os.path.isfile(p):
            info.xinput_dlls[name] = os.path.getsize(p)

    drivers_dir = os.path.join(sys32, "drivers")
    winexinput = os.path.join(drivers_dir, "winexinput.sys")
    if os.path.isfile(winexinput):
        info.winexinput_sys = winexinput

    winebus = os.path.join(drivers_dir, "winebus.sys")
    if os.path.isfile(winebus):
        info.winebus_sys = winebus


def _read_winebus(info: WrapperInfo, contents: str):
    """Check winebus.so in unix driver directory."""
    unix_dir = os.path.join(
        contents, "SharedSupport", "wine", "lib", "wine", "x86_64-unix"
    )
    so_path = os.path.join(unix_dir, "winebus.so")
    if os.path.isfile(so_path):
        info.winebus_so = so_path


def _read_registry(info: WrapperInfo):
    """Parse winebus service config and DLL overrides from registry files."""
    system_reg = os.path.join(info.wine_prefix, "system.reg")
    user_reg = os.path.join(info.wine_prefix, "user.reg")

    # ── winebus service from system.reg ──
    if os.path.isfile(system_reg):
        try:
            text = Path(system_reg).read_text(errors="ignore")
            _parse_winebus_service(info, text)
        except Exception as e:
            info.scan_errors.append(f"system.reg: {e}")

    # ── DLL overrides from user.reg ──
    if os.path.isfile(user_reg):
        try:
            text = Path(user_reg).read_text(errors="ignore")
            _parse_dll_overrides(info, text)
        except Exception as e:
            info.scan_errors.append(f"user.reg DllOverrides: {e}")


def _parse_winebus_service(info: WrapperInfo, text: str):
    """Extract winebus service registry values."""
    # Find the [System\\ControlSet001\\Services\\winebus] section
    pattern = r'\[System\\\\ControlSet001\\\\Services\\\\winebus\].*?\n((?:[^\[]+)*)'
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        return

    section = match.group(1)

    def _get_dword(key: str) -> Optional[int]:
        m = re.search(rf'"{re.escape(key)}"=dword:([0-9a-fA-F]+)', section)
        return int(m.group(1), 16) if m else None

    info.reg_enable_sdl = _get_dword("Enable SDL")
    info.reg_map_controllers = _get_dword("Map Controllers")
    info.reg_disable_hidraw = _get_dword("DisableHidraw")
    info.reg_disable_input = _get_dword("DisableInput")

    # EnableHidraw is a multi-string
    m = re.search(r'"EnableHidraw"=(.+)', section)
    if m:
        info.reg_enable_hidraw = m.group(1).strip()


def _parse_dll_overrides(info: WrapperInfo, text: str):
    """Extract DLL override configuration."""
    pattern = r'\[Software\\\\Wine\\\\DllOverrides\].*?\n((?:[^\[]+)*)'
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        return

    section = match.group(1)
    for line in section.split("\n"):
        m = re.match(r'"([^"]+)"="([^"]*)"', line.strip())
        if m:
            info.dll_overrides[m.group(1)] = m.group(2)


# ─── Controller detection (macOS level) ─────────────────────────────


@dataclass
class ControllerInfo:
    """A macOS-detected controller."""
    name: str = ""
    vendor_id: int = 0
    product_id: int = 0
    vendor_hex: str = ""
    product_hex: str = ""
    connection: str = ""  # "USB" or "Bluetooth"


def detect_macos_controllers() -> list[ControllerInfo]:
    """Detect USB and Bluetooth controllers via ioreg (read-only, no modifications)."""
    controllers = []
    seen = set()

    controller_vids = {
        0x054c,  # Sony
        0x045e,  # Microsoft
        0x057e,  # Nintendo
        0x2dc8,  # 8BitDo
        0x0f0d,  # Hori
        0x1532,  # Razer
        0x0738,  # MadCatz
        0x046d,  # Logitech
        0x28de,  # Valve
        0x1038,  # SteelSeries
        0x0e6f,  # PDP
        0x24c6,  # PowerA
    }

    def _parse_ioreg_blocks(cmd: list[str], default_conn: str):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        except Exception:
            return
        # Split on IORegistry node boundaries ("+-o ")
        blocks = re.split(r'(?=^\s*\|*\s*\+-o\s)', result.stdout, flags=re.MULTILINE)
        for block in blocks:
            vid_m = re.search(r'"(?:idVendor|VendorID)"\s*=\s*(\d+)', block)
            pid_m = re.search(r'"(?:idProduct|ProductID)"\s*=\s*(\d+)', block)
            if not (vid_m and pid_m):
                continue
            vid = int(vid_m.group(1))
            pid = int(pid_m.group(1))
            if vid not in controller_vids:
                continue

            name_m = re.search(r'"(?:USB Product Name|Product)"\s*=\s*"(.+?)"', block)
            name = name_m.group(1) if name_m else f"Controller {vid:04x}:{pid:04x}"

            transport_m = re.search(r'"Transport"\s*=\s*"(.+?)"', block)
            conn = transport_m.group(1) if transport_m else default_conn

            key = (vid, pid, conn)
            if key in seen:
                continue
            seen.add(key)

            controllers.append(ControllerInfo(
                name=name,
                vendor_id=vid,
                product_id=pid,
                vendor_hex=f"{vid:04x}",
                product_hex=f"{pid:04x}",
                connection=conn,
            ))

    _parse_ioreg_blocks(["ioreg", "-p", "IOUSB", "-l", "-w", "0"], "USB")
    _parse_ioreg_blocks(["ioreg", "-r", "-c", "IOHIDDevice", "-l", "-w", "0"], "HID/Bluetooth")

    return controllers


def find_sdl2_donors() -> list[dict]:
    """
    Find usable x86_64 SDL2 libraries on this system that could serve as
    replacement donors. Never modifies anything.
    """
    candidates = []
    search_paths = [
        os.path.expanduser(
            "~/Library/Application Support/com.isaacmarovitz.Whisky/Libraries/Wine/lib"
        ),
        "/usr/local/lib",
        "/usr/local/opt/sdl2/lib",
        "/opt/homebrew/lib",
        "/opt/homebrew/Cellar/sdl2",
    ]

    for base in search_paths:
        if not os.path.exists(base):
            continue
        for root, dirs, files in os.walk(base):
            for f in files:
                if "libSDL2" in f and f.endswith(".dylib") and not os.path.islink(
                    os.path.join(root, f)
                ):
                    full = os.path.join(root, f)
                    size = os.path.getsize(full)
                    if size < 1024:
                        continue
                    try:
                        result = subprocess.run(
                            ["file", full],
                            capture_output=True, text=True, timeout=5
                        )
                        arch = "unknown"
                        if "x86_64" in result.stdout:
                            arch = "x86_64"
                        elif "arm64" in result.stdout:
                            arch = "arm64"
                        candidates.append({
                            "path": full,
                            "size": size,
                            "arch": arch,
                        })
                    except Exception:
                        pass
    return candidates
