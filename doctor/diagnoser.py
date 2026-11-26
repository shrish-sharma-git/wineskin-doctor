"""
diagnoser.py — Analyse a WrapperInfo and produce a structured diagnostic report.

Identifies specific problems and their causes. Never modifies anything.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .scanner import WrapperInfo, ControllerInfo


class Severity(Enum):
    OK = "ok"
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class ProblemCategory(Enum):
    SDL2_MISSING = "sdl2_missing"
    SDL2_EMPTY = "sdl2_empty"
    SDL2_WRONG_ARCH = "sdl2_wrong_arch"
    SDL2_BROKEN_DEPS = "sdl2_broken_deps"
    SDL2_NO_WINE_LIB = "sdl2_no_wine_lib_symlink"
    WINEBUS_SDL_DISABLED = "winebus_sdl_disabled"
    WINEBUS_ALL_DISABLED = "winebus_all_disabled"
    XINPUT_MISSING = "xinput_missing"
    WINEXINPUT_MISSING = "winexinput_missing"
    WINEBUS_SYS_MISSING = "winebus_sys_missing"
    WINEBUS_SO_MISSING = "winebus_so_missing"
    HID_PASSTHROUGH_BLOCKED = "hid_passthrough_blocked"
    CONTROLLER_NOT_DETECTED = "controller_not_detected"
    WINE_BIN_MISSING = "wine_bin_missing"
    PREFIX_MISSING = "prefix_missing"
    DLL_OVERRIDE_CONFLICT = "dll_override_conflict"


@dataclass
class Finding:
    """A single diagnostic finding."""
    severity: Severity
    category: Optional[ProblemCategory]
    title: str
    detail: str
    recommendation: str = ""


@dataclass
class DiagnosticReport:
    """Complete diagnostic report for a wrapper."""
    wrapper_path: str = ""
    wrapper_name: str = ""
    wine_version: str = ""
    game_exe: str = ""
    findings: list = field(default_factory=list)
    controllers: list = field(default_factory=list)

    @property
    def has_critical(self) -> bool:
        return any(f.severity == Severity.CRITICAL for f in self.findings)

    @property
    def has_warnings(self) -> bool:
        return any(f.severity == Severity.WARNING for f in self.findings)

    @property
    def all_ok(self) -> bool:
        return not self.has_critical and not self.has_warnings


def diagnose(info: WrapperInfo, controllers: list[ControllerInfo]) -> DiagnosticReport:
    """
    Run all diagnostic checks against a scanned wrapper.

    Returns a DiagnosticReport with findings sorted by severity.
    """
    report = DiagnosticReport(
        wrapper_path=info.path,
        wrapper_name=info.bundle_name or info.path.split("/")[-1],
        wine_version=info.wine_version,
        game_exe=info.game_exe,
        controllers=controllers,
    )

    # ── 1. Controller detection ──
    _check_controllers(report, controllers)

    # ── 2. Wine binary ──
    _check_wine_binary(report, info)

    # ── 3. Wine prefix ──
    _check_prefix(report, info)

    # ── 4. SDL2 library ──
    _check_sdl2(report, info)

    # ── 5. Wine lib SDL2 symlink ──
    _check_wine_lib_sdl2(report, info)

    # ── 6. WineBus driver ──
    _check_winebus_driver(report, info)

    # ── 7. WineBus registry ──
    _check_winebus_registry(report, info)

    # ── 8. XInput DLLs ──
    _check_xinput(report, info)

    # ── 9. WineXInput driver ──
    _check_winexinput(report, info)

    # ── 10. DLL overrides ──
    _check_dll_overrides(report, info)

    # ── 11. HID passthrough ──
    _check_hid_passthrough(report, info)

    # Sort: critical first
    severity_order = {Severity.CRITICAL: 0, Severity.WARNING: 1, Severity.INFO: 2, Severity.OK: 3}
    report.findings.sort(key=lambda f: severity_order.get(f.severity, 99))

    return report


# ─── Individual checks ───────────────────────────────────────────────


def _check_controllers(report: DiagnosticReport, controllers: list[ControllerInfo]):
    if not controllers:
        report.findings.append(Finding(
            severity=Severity.WARNING,
            category=ProblemCategory.CONTROLLER_NOT_DETECTED,
            title="No controller detected by macOS",
            detail="No known gamepad was found connected via USB or Bluetooth.",
            recommendation="Connect your controller and ensure macOS recognises it.",
        ))
    else:
        for c in controllers:
            report.findings.append(Finding(
                severity=Severity.OK,
                category=None,
                title=f"Controller detected: {c.name}",
                detail=f"VID:{c.vendor_hex} PID:{c.product_hex} via {c.connection}",
            ))


def _check_wine_binary(report: DiagnosticReport, info: WrapperInfo):
    if not info.wine_bin:
        report.findings.append(Finding(
            severity=Severity.CRITICAL,
            category=ProblemCategory.WINE_BIN_MISSING,
            title="Wine binary not found",
            detail="No wine or wine64 binary in SharedSupport/wine/bin.",
            recommendation="The Wine engine may be missing or corrupted. Re-install the wrapper.",
        ))
    else:
        report.findings.append(Finding(
            severity=Severity.OK,
            category=None,
            title=f"Wine engine: {info.wine_version}",
            detail=f"Binary: {info.wine_bin}",
        ))


def _check_prefix(report: DiagnosticReport, info: WrapperInfo):
    import os
    if not os.path.isdir(info.wine_prefix):
        report.findings.append(Finding(
            severity=Severity.CRITICAL,
            category=ProblemCategory.PREFIX_MISSING,
            title="Wine prefix not found",
            detail=f"Expected at: {info.wine_prefix}",
            recommendation="The Wine prefix is missing. The wrapper may be corrupted.",
        ))


def _check_sdl2(report: DiagnosticReport, info: WrapperInfo):
    if not info.sdl2_path:
        report.findings.append(Finding(
            severity=Severity.CRITICAL,
            category=ProblemCategory.SDL2_MISSING,
            title="SDL2 library not found",
            detail="No libSDL2-2.0.0.dylib or libSDL2.dylib in Frameworks.",
            recommendation="Provide an x86_64 SDL2 library for Wine's controller subsystem.",
        ))
        return

    if info.sdl2_size == 0:
        report.findings.append(Finding(
            severity=Severity.CRITICAL,
            category=ProblemCategory.SDL2_EMPTY,
            title="SDL2 library is empty (0 bytes)",
            detail=f"File: {info.sdl2_path}",
            recommendation=(
                "Replace with a valid x86_64 libSDL2-2.0.0.dylib. "
                "Wine cannot load an empty library, so controller detection fails."
            ),
        ))
        return

    if info.sdl2_size < 1024:
        report.findings.append(Finding(
            severity=Severity.CRITICAL,
            category=ProblemCategory.SDL2_EMPTY,
            title=f"SDL2 library is suspiciously small ({info.sdl2_size} bytes)",
            detail=f"File: {info.sdl2_path}",
            recommendation="This file appears corrupt. Replace with a valid x86_64 build.",
        ))
        return

    if info.sdl2_arch and info.sdl2_arch not in ("x86_64", "universal"):
        report.findings.append(Finding(
            severity=Severity.CRITICAL,
            category=ProblemCategory.SDL2_WRONG_ARCH,
            title=f"SDL2 has wrong architecture: {info.sdl2_arch}",
            detail=f"Wine runs x86_64 binaries under Rosetta. An {info.sdl2_arch} SDL2 cannot be loaded.",
            recommendation="Replace with an x86_64 build of libSDL2-2.0.0.dylib.",
        ))
        return

    report.findings.append(Finding(
        severity=Severity.OK,
        category=None,
        title=f"SDL2 library OK ({info.sdl2_arch}, {info.sdl2_size:,} bytes)",
        detail=f"File: {info.sdl2_path}",
    ))


def _check_wine_lib_sdl2(report: DiagnosticReport, info: WrapperInfo):
    import os
    if info.sdl2_path and info.sdl2_size > 0 and not info.wine_lib_sdl2_exists:
        rel_target = os.path.relpath(
            os.path.join(info.frameworks_dir, "libSDL2-2.0.0.dylib"),
            info.wine_lib_dir,
        )
        report.findings.append(Finding(
            severity=Severity.WARNING,
            category=ProblemCategory.SDL2_NO_WINE_LIB,
            title="SDL2 not linked in Wine lib directory",
            detail=(
                f"SDL2 exists in Frameworks but no valid symlink at {info.wine_lib_sdl2_path}. "
                "Wine's winebus.so uses @rpath which may not resolve without it."
            ),
            recommendation=(
                f"Create a symlink: ln -sf {rel_target} "
                f'"{info.wine_lib_sdl2_path}"'
            ),
        ))


def _check_winebus_driver(report: DiagnosticReport, info: WrapperInfo):
    if not info.winebus_sys:
        report.findings.append(Finding(
            severity=Severity.CRITICAL,
            category=ProblemCategory.WINEBUS_SYS_MISSING,
            title="winebus.sys not found",
            detail="Missing from system32/drivers.",
            recommendation="The Wine engine may be incomplete. Controller support requires winebus.sys.",
        ))
    if not info.winebus_so:
        report.findings.append(Finding(
            severity=Severity.CRITICAL,
            category=ProblemCategory.WINEBUS_SO_MISSING,
            title="winebus.so not found",
            detail="Missing from wine/lib/wine/x86_64-unix.",
            recommendation="The Wine engine may be incomplete. Controller support requires winebus.so.",
        ))


def _check_winebus_registry(report: DiagnosticReport, info: WrapperInfo):
    # SDL enabled?
    if info.reg_enable_sdl is not None and info.reg_enable_sdl == 0:
        report.findings.append(Finding(
            severity=Severity.WARNING,
            category=ProblemCategory.WINEBUS_SDL_DISABLED,
            title='WineBus "Enable SDL" is OFF',
            detail="SDL controller detection is disabled in the registry.",
            recommendation='Set "Enable SDL" to 1 in HKLM\\System\\CurrentControlSet\\Services\\winebus.',
        ))
    elif info.reg_enable_sdl == 1:
        report.findings.append(Finding(
            severity=Severity.OK,
            category=None,
            title='WineBus "Enable SDL" is ON',
            detail="SDL controller detection is enabled.",
        ))

    # Check for all-disabled scenario
    sdl_off = (info.reg_enable_sdl == 0)
    hidraw_off = (info.reg_disable_hidraw == 1)
    input_off = (info.reg_disable_input == 1)

    if sdl_off and hidraw_off and input_off:
        report.findings.append(Finding(
            severity=Severity.CRITICAL,
            category=ProblemCategory.WINEBUS_ALL_DISABLED,
            title="All WineBus controller backends are disabled",
            detail="SDL is OFF, DisableHidraw is 1, DisableInput is 1. No backend can find controllers.",
            recommendation="Enable at least one backend (SDL recommended).",
        ))

    # Map Controllers
    if info.reg_map_controllers is not None:
        status = "ON" if info.reg_map_controllers == 1 else "OFF"
        report.findings.append(Finding(
            severity=Severity.INFO,
            category=None,
            title=f'WineBus "Map Controllers" is {status}',
            detail="When ON, Wine maps generic gamepads to XInput layout.",
        ))


def _check_xinput(report: DiagnosticReport, info: WrapperInfo):
    critical_dlls = ["xinput1_3.dll", "xinput1_4.dll", "xinput9_1_0.dll"]
    missing = [d for d in critical_dlls if d not in info.xinput_dlls]

    if missing:
        report.findings.append(Finding(
            severity=Severity.WARNING,
            category=ProblemCategory.XINPUT_MISSING,
            title=f"Missing XInput DLLs: {', '.join(missing)}",
            detail="Some games require specific xinput DLLs.",
            recommendation="Check if the Wine engine provides these. They may need to be regenerated.",
        ))
    else:
        empty = [d for d, s in info.xinput_dlls.items() if s == 0]
        if empty:
            report.findings.append(Finding(
                severity=Severity.WARNING,
                category=ProblemCategory.XINPUT_MISSING,
                title=f"Empty XInput DLLs: {', '.join(empty)}",
                detail="These DLLs exist but are 0 bytes.",
            ))
        else:
            report.findings.append(Finding(
                severity=Severity.OK,
                category=None,
                title=f"XInput DLLs present ({len(info.xinput_dlls)} files)",
                detail=", ".join(info.xinput_dlls.keys()),
            ))


def _check_winexinput(report: DiagnosticReport, info: WrapperInfo):
    if not info.winexinput_sys:
        report.findings.append(Finding(
            severity=Severity.WARNING,
            category=ProblemCategory.WINEXINPUT_MISSING,
            title="winexinput.sys not found",
            detail="Missing from system32/drivers. XInput controller exposure may not work.",
            recommendation="Check Wine engine compatibility. Modern Wine (8+) includes winexinput.sys.",
        ))
    else:
        report.findings.append(Finding(
            severity=Severity.OK,
            category=None,
            title="winexinput.sys present",
            detail=f"Path: {info.winexinput_sys}",
        ))


def _check_dll_overrides(report: DiagnosticReport, info: WrapperInfo):
    controller_dlls = {"xinput1_3", "xinput1_4", "xinput9_1_0", "dinput", "dinput8"}
    conflicts = {k: v for k, v in info.dll_overrides.items() if k in controller_dlls}

    if conflicts:
        detail_lines = [f"  {k} = {v}" for k, v in conflicts.items()]
        report.findings.append(Finding(
            severity=Severity.WARNING,
            category=ProblemCategory.DLL_OVERRIDE_CONFLICT,
            title="Controller-related DLL overrides detected",
            detail="These overrides may interfere with controller detection:\n" + "\n".join(detail_lines),
            recommendation="Review whether these are intentional. 'native' overrides bypass Wine's built-in XInput.",
        ))


def _check_hid_passthrough(report: DiagnosticReport, info: WrapperInfo):
    # Only warn if SDL is enabled but hidraw/input are also enabled (potential duplicates)
    if info.reg_enable_sdl == 1:
        if info.reg_disable_hidraw == 0 or info.reg_disable_input == 0:
            report.findings.append(Finding(
                severity=Severity.INFO,
                category=None,
                title="HID raw passthrough is enabled alongside SDL",
                detail=(
                    "Both SDL and native HID backends are active. "
                    "This may cause duplicate controller devices in some games."
                ),
                recommendation="If you see duplicate inputs, set DisableHidraw=1 and DisableInput=1.",
            ))
