"""
formatter.py — Human-readable report output for the CLI.
"""

import os
from .diagnoser import DiagnosticReport, Finding, Severity
from .scanner import WrapperInfo, ControllerInfo


# ANSI colours
_RESET = "\033[0m"
_BOLD = "\033[1m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_GREEN = "\033[92m"
_CYAN = "\033[96m"
_DIM = "\033[2m"


def _sev_icon(sev: Severity) -> str:
    return {
        Severity.OK: f"{_GREEN}✓{_RESET}",
        Severity.INFO: f"{_CYAN}ℹ{_RESET}",
        Severity.WARNING: f"{_YELLOW}⚠{_RESET}",
        Severity.CRITICAL: f"{_RED}✗{_RESET}",
    }.get(sev, "?")


def format_scan_results(wrappers: list[str]) -> str:
    """Format the results of a scan."""
    lines = []
    lines.append(f"\n{_BOLD}Wineskin Controller Doctor — Wrapper Scan{_RESET}")
    lines.append("─" * 50)

    if not wrappers:
        lines.append(f"{_YELLOW}No Wineskin wrappers found.{_RESET}")
        lines.append("Searched: /Applications, ~/Applications, ~/Desktop, ~/Games")
        return "\n".join(lines)

    lines.append(f"Found {_BOLD}{len(wrappers)}{_RESET} Wineskin wrapper(s):\n")
    for w in wrappers:
        name = os.path.basename(w).replace(".app", "")
        lines.append(f"  {_GREEN}●{_RESET} {_BOLD}{name}{_RESET}")
        lines.append(f"    {_DIM}{w}{_RESET}")

    lines.append(f"\nRun: {_CYAN}wineskin-doctor diagnose <path>{_RESET} to inspect a wrapper.")
    return "\n".join(lines)


def format_controller_status(controllers: list[ControllerInfo]) -> str:
    """Format controller detection status."""
    lines = []
    lines.append(f"\n{_BOLD}macOS Controller Detection{_RESET}")
    lines.append("─" * 35)

    if not controllers:
        lines.append(f"  {_YELLOW}⚠ No controllers detected{_RESET}")
        return "\n".join(lines)

    for c in controllers:
        lines.append(
            f"  {_GREEN}✓{_RESET} {_BOLD}{c.name}{_RESET}  "
            f"[{c.vendor_hex}:{c.product_hex}] via {c.connection}"
        )
    return "\n".join(lines)


def format_diagnostic_report(report: DiagnosticReport, info: WrapperInfo) -> str:
    """Format a full diagnostic report."""
    lines = []
    name = report.wrapper_name or os.path.basename(report.wrapper_path)

    lines.append(f"\n{_BOLD}{'═' * 60}{_RESET}")
    lines.append(f"{_BOLD}  Wineskin Controller Doctor — Diagnostic Report{_RESET}")
    lines.append(f"{_BOLD}{'═' * 60}{_RESET}")

    # ── Wrapper info ──
    lines.append(f"\n{_BOLD}Wrapper{_RESET}")
    lines.append(f"  Name:        {name}")
    lines.append(f"  Path:        {report.wrapper_path}")
    lines.append(f"  Wine:        {report.wine_version or 'unknown'}")
    lines.append(f"  Game:        {report.game_exe or 'unknown'}")
    lines.append(f"  Bundle ID:   {info.bundle_id or 'unknown'}")

    # ── Controller status ──
    if report.controllers:
        lines.append(f"\n{_BOLD}Controllers{_RESET}")
        for c in report.controllers:
            lines.append(
                f"  {_GREEN}●{_RESET} {c.name} [{c.vendor_hex}:{c.product_hex}] {c.connection}"
            )
    else:
        lines.append(f"\n{_BOLD}Controllers{_RESET}")
        lines.append(f"  {_YELLOW}● No controllers connected{_RESET}")

    # ── SDL2 ──
    lines.append(f"\n{_BOLD}SDL2 Library{_RESET}")
    if info.sdl2_path:
        lines.append(f"  Path:        {info.sdl2_path}")
        lines.append(f"  Size:        {info.sdl2_size:,} bytes")
        lines.append(f"  Arch:        {info.sdl2_arch or 'unknown'}")
        if info.sdl2_install_name:
            lines.append(f"  Install ID:  {info.sdl2_install_name}")
    else:
        lines.append(f"  {_RED}Not found{_RESET}")

    # ── WineBus Registry ──
    lines.append(f"\n{_BOLD}WineBus Configuration{_RESET}")
    _reg_line(lines, "Enable SDL", info.reg_enable_sdl)
    _reg_line(lines, "Map Controllers", info.reg_map_controllers)
    _reg_line(lines, "DisableHidraw", info.reg_disable_hidraw)
    _reg_line(lines, "DisableInput", info.reg_disable_input)

    # ── XInput ──
    lines.append(f"\n{_BOLD}XInput DLLs{_RESET}")
    if info.xinput_dlls:
        for dll, size in sorted(info.xinput_dlls.items()):
            status = f"{_GREEN}✓{_RESET}" if size > 0 else f"{_RED}✗ (empty){_RESET}"
            lines.append(f"  {status} {dll} ({size:,} bytes)")
    else:
        lines.append(f"  {_RED}None found{_RESET}")

    lines.append(f"  winexinput.sys: {'✓' if info.winexinput_sys else '✗ missing'}")

    # ── Findings ──
    lines.append(f"\n{_BOLD}{'─' * 60}{_RESET}")
    lines.append(f"{_BOLD}  Diagnostic Findings{_RESET}")
    lines.append(f"{_BOLD}{'─' * 60}{_RESET}")

    for f in report.findings:
        icon = _sev_icon(f.severity)
        lines.append(f"\n  {icon} {_BOLD}{f.title}{_RESET}")
        if f.detail:
            for dl in f.detail.split("\n"):
                lines.append(f"    {_DIM}{dl}{_RESET}")
        if f.recommendation:
            lines.append(f"    {_CYAN}→ {f.recommendation}{_RESET}")

    # ── Summary ──
    lines.append(f"\n{_BOLD}{'─' * 60}{_RESET}")
    crits = sum(1 for f in report.findings if f.severity == Severity.CRITICAL)
    warns = sum(1 for f in report.findings if f.severity == Severity.WARNING)
    oks = sum(1 for f in report.findings if f.severity == Severity.OK)

    if crits:
        lines.append(f"  {_RED}{_BOLD}CRITICAL: {crits} issue(s) found{_RESET}")
    if warns:
        lines.append(f"  {_YELLOW}WARNING: {warns} issue(s) found{_RESET}")
    lines.append(f"  {_GREEN}PASSED: {oks} check(s){_RESET}")

    if report.has_critical:
        lines.append(f"\n  Run: {_CYAN}wineskin-doctor repair \"{report.wrapper_path}\"{_RESET}")
    elif report.all_ok:
        lines.append(f"\n  {_GREEN}{_BOLD}All checks passed. Controller should work.{_RESET}")

    lines.append("")
    return "\n".join(lines)


def format_repair_plan(plan) -> str:
    """Format a repair plan for user review."""
    lines = []
    lines.append(f"\n{_BOLD}{'═' * 60}{_RESET}")
    lines.append(f"{_BOLD}  Proposed Repair Plan{_RESET}")
    lines.append(f"{_BOLD}{'═' * 60}{_RESET}")

    if not plan.has_actions:
        lines.append(f"\n  {_GREEN}No repairs needed.{_RESET}")
        return "\n".join(lines)

    for i, action in enumerate(plan.actions, 1):
        lines.append(f"\n  {_BOLD}Step {i}: {action['description']}{_RESET}")
        if "detail" in action:
            for dl in action["detail"].split("\n"):
                lines.append(f"    {dl}")

    lines.append(f"\n{_BOLD}{'─' * 60}{_RESET}")
    lines.append(f"  Backups will be stored inside the wrapper at:")
    lines.append(f"    {plan.wrapper_path}/Contents/{BACKUP_DIR_NAME}/")
    lines.append("")
    return "\n".join(lines)


def format_repair_results(results: list[dict]) -> str:
    """Format repair execution results."""
    lines = []
    lines.append(f"\n{_BOLD}Repair Results{_RESET}")
    lines.append("─" * 40)

    for r in results:
        status = r.get("status", "unknown")
        action = r.get("action", "unknown")

        if status == "done":
            lines.append(f"  {_GREEN}✓{_RESET} {action}")
            if "backup" in r:
                lines.append(f"    {_DIM}Backup: {r['backup']}{_RESET}")
        elif status == "dry_run":
            lines.append(f"  {_CYAN}⟳{_RESET} {action} (dry run)")
        elif status == "manual_required":
            lines.append(f"  {_YELLOW}⚠{_RESET} {action}")
            if "detail" in r:
                for dl in r["detail"].split("\n"):
                    lines.append(f"    {dl}")
        elif status == "error":
            lines.append(f"  {_RED}✗{_RESET} {action}")
            if "detail" in r:
                lines.append(f"    {_RED}{r['detail']}{_RESET}")

    lines.append("")
    return "\n".join(lines)


def format_rollback_results(results: list[dict]) -> str:
    """Format rollback results."""
    lines = []
    lines.append(f"\n{_BOLD}Rollback Results{_RESET}")
    lines.append("─" * 40)

    for r in results:
        status = r.get("status", "unknown")
        if status == "done":
            lines.append(f"  {_GREEN}✓{_RESET} Restored: {r.get('restored', r.get('removed', ''))}")
        elif status == "nothing":
            lines.append(f"  {_CYAN}ℹ{_RESET} {r.get('detail', 'Nothing to roll back.')}")
        elif status == "error":
            lines.append(f"  {_RED}✗{_RESET} {r.get('detail', 'Error')}")

    lines.append("")
    return "\n".join(lines)


def _reg_line(lines, name, value):
    if value is None:
        lines.append(f"  {name}: {_DIM}not set{_RESET}")
    elif value == 1:
        lines.append(f"  {name}: {_GREEN}1 (enabled){_RESET}")
    elif value == 0:
        lines.append(f"  {name}: {_YELLOW}0 (disabled){_RESET}")
    else:
        lines.append(f"  {name}: {value}")


BACKUP_DIR_NAME = ".wineskin-doctor-backups"
