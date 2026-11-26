"""
cli.py — Command-line interface for Wineskin Controller Doctor.

Commands:
    scan        — Find all Wineskin wrappers on this Mac.
    diagnose    — Inspect a specific wrapper and produce a report.
    repair      — Propose and apply fixes for a wrapper.
    rollback    — Undo all repairs applied to a wrapper.
    status      — Show macOS controller detection status.
"""

import sys
import os

from .scanner import find_wineskin_wrappers, scan_wrapper, detect_macos_controllers
from .diagnoser import diagnose
from .repairer import RepairPlan, execute_repair, rollback
from .formatter import (
    format_scan_results,
    format_controller_status,
    format_diagnostic_report,
    format_repair_plan,
    format_repair_results,
    format_rollback_results,
)


USAGE = """\
\033[1mWineskin Controller Doctor\033[0m — Diagnose and repair controller issues in Wineskin games.

\033[1mUsage:\033[0m
  wineskin-doctor scan                        Find Wineskin wrappers
  wineskin-doctor diagnose <wrapper.app>      Inspect a wrapper
  wineskin-doctor repair <wrapper.app>        Fix controller issues
  wineskin-doctor rollback <wrapper.app>      Undo repairs
  wineskin-doctor status                      Show controller status

\033[1mExamples:\033[0m
  wineskin-doctor scan
  wineskin-doctor diagnose "/Applications/Alan Wake Remastered.app"
  wineskin-doctor repair "/Applications/Mafia Definitive Edition.app"
  wineskin-doctor rollback "/Applications/Mafia Definitive Edition.app"
"""


def main():
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help", "help"):
        print(USAGE)
        sys.exit(0)

    command = args[0]

    if command == "scan":
        cmd_scan()
    elif command == "status":
        cmd_status()
    elif command == "diagnose":
        if len(args) < 2:
            print("Error: provide the path to a .app wrapper.", file=sys.stderr)
            sys.exit(1)
        cmd_diagnose(args[1])
    elif command == "repair":
        if len(args) < 2:
            print("Error: provide the path to a .app wrapper.", file=sys.stderr)
            sys.exit(1)
        cmd_repair(args[1])
    elif command == "rollback":
        if len(args) < 2:
            print("Error: provide the path to a .app wrapper.", file=sys.stderr)
            sys.exit(1)
        cmd_rollback(args[1])
    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        print(USAGE)
        sys.exit(1)


def cmd_scan():
    """Find all Wineskin wrappers."""
    controllers = detect_macos_controllers()
    print(format_controller_status(controllers))

    wrappers = find_wineskin_wrappers()
    print(format_scan_results(wrappers))


def cmd_status():
    """Show controller detection status."""
    controllers = detect_macos_controllers()
    print(format_controller_status(controllers))


def cmd_diagnose(wrapper_path: str):
    """Run full diagnostics on a wrapper."""
    wrapper_path = os.path.abspath(wrapper_path)

    if not os.path.isdir(wrapper_path):
        print(f"Error: not a directory: {wrapper_path}", file=sys.stderr)
        sys.exit(1)

    # Detect controllers
    controllers = detect_macos_controllers()
    print(format_controller_status(controllers))

    # Scan wrapper
    print(f"\nScanning: {wrapper_path}")
    info = scan_wrapper(wrapper_path)

    if info.scan_errors:
        print(f"\n\033[93mScan warnings:\033[0m")
        for e in info.scan_errors:
            print(f"  - {e}")

    # Diagnose
    report = diagnose(info, controllers)
    print(format_diagnostic_report(report, info))


def cmd_repair(wrapper_path: str):
    """Propose and apply repairs to a wrapper."""
    wrapper_path = os.path.abspath(wrapper_path)

    if not os.path.isdir(wrapper_path):
        print(f"Error: not a directory: {wrapper_path}", file=sys.stderr)
        sys.exit(1)

    # Detect controllers
    controllers = detect_macos_controllers()
    print(format_controller_status(controllers))

    # Scan and diagnose
    print(f"\nScanning: {wrapper_path}")
    info = scan_wrapper(wrapper_path)
    report = diagnose(info, controllers)
    print(format_diagnostic_report(report, info))

    if report.all_ok:
        print("\033[92mNo repairs needed. Controller setup looks correct.\033[0m")
        return

    # Build repair plan
    plan = RepairPlan(wrapper_path, report, info)

    if not plan.has_actions:
        print("\033[93mNo automatic repairs available for the detected issues.\033[0m")
        return

    print(format_repair_plan(plan))

    if plan.has_manual_only:
        print("\033[93mAll required actions are manual. See above for instructions.\033[0m")
        return

    # Ask for confirmation
    print("\033[1mApply these repairs?\033[0m", end=" ")
    try:
        answer = input("[y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        sys.exit(1)

    if answer not in ("y", "yes"):
        print("Aborted. No changes made.")
        return

    # Execute
    results = execute_repair(plan)
    print(format_repair_results(results))

    # Verify
    print("\033[1mVerifying repair...\033[0m")
    info2 = scan_wrapper(wrapper_path)
    report2 = diagnose(info2, controllers)

    if report2.all_ok:
        print("\033[92m✓ All checks now pass. Launch the game to test controller input.\033[0m\n")
    else:
        crits = sum(1 for f in report2.findings if f.severity.value == "critical")
        if crits:
            print(f"\033[93m⚠ {crits} issue(s) remain after repair. Run diagnose for details.\033[0m\n")
        else:
            print("\033[92m✓ Critical issues resolved. Some warnings remain — run diagnose for details.\033[0m\n")


def cmd_rollback(wrapper_path: str):
    """Roll back all repairs to a wrapper."""
    wrapper_path = os.path.abspath(wrapper_path)

    if not os.path.isdir(wrapper_path):
        print(f"Error: not a directory: {wrapper_path}", file=sys.stderr)
        sys.exit(1)

    print(f"\n\033[1mRollback repairs for:\033[0m {wrapper_path}")
    print("\033[1mThis will restore all backed-up files to their original state.\033[0m")
    print("\033[1mProceed?\033[0m", end=" ")

    try:
        answer = input("[y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        sys.exit(1)

    if answer not in ("y", "yes"):
        print("Aborted. No changes made.")
        return

    results = rollback(wrapper_path)
    print(format_rollback_results(results))
