"""
repairer.py — Safe repair engine with backup and rollback.

Every repair action is:
1. Described before execution.
2. Requires explicit confirmation.
3. Backed up before modification.
4. Reversible via rollback.
"""

import os
import shutil
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from .scanner import WrapperInfo, find_sdl2_donors
from .diagnoser import DiagnosticReport, ProblemCategory, Severity


BACKUP_DIR_NAME = ".wineskin-doctor-backups"


def get_backup_dir(wrapper_path: str) -> str:
    """Return the backup directory inside the wrapper."""
    return os.path.join(wrapper_path, "Contents", BACKUP_DIR_NAME)


def _create_backup_manifest(backup_dir: str) -> str:
    """Return path to the manifest file."""
    os.makedirs(backup_dir, exist_ok=True)
    return os.path.join(backup_dir, "manifest.json")


def _load_manifest(wrapper_path: str) -> dict:
    """Load or create the backup manifest."""
    manifest_path = os.path.join(get_backup_dir(wrapper_path), "manifest.json")
    if os.path.isfile(manifest_path):
        with open(manifest_path) as f:
            return json.load(f)
    return {"wrapper": wrapper_path, "repairs": []}


def _save_manifest(wrapper_path: str, manifest: dict):
    """Save the backup manifest."""
    backup_dir = get_backup_dir(wrapper_path)
    os.makedirs(backup_dir, exist_ok=True)
    manifest_path = os.path.join(backup_dir, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)


class RepairPlan:
    """A set of proposed repair actions for a wrapper."""

    def __init__(self, wrapper_path: str, report: DiagnosticReport, info: WrapperInfo):
        self.wrapper_path = wrapper_path
        self.report = report
        self.info = info
        self.actions: list[dict] = []
        self._build()

    def _build(self):
        """Analyse the report and produce repair actions."""
        categories = {f.category for f in self.report.findings if f.severity in (Severity.CRITICAL, Severity.WARNING)}

        # ── SDL2 empty/missing ──
        if ProblemCategory.SDL2_EMPTY in categories or ProblemCategory.SDL2_MISSING in categories:
            donors = find_sdl2_donors()
            x86_donors = [d for d in donors if d["arch"] == "x86_64"]

            if x86_donors:
                best = max(x86_donors, key=lambda d: d["size"])
                self.actions.append({
                    "type": "replace_sdl2",
                    "description": "Replace empty/missing SDL2 library with a working x86_64 build",
                    "source": best["path"],
                    "source_size": best["size"],
                    "source_arch": best["arch"],
                    "target": os.path.join(self.info.frameworks_dir, "libSDL2-2.0.0.dylib"),
                    "detail": (
                        f"Source: {best['path']}\n"
                        f"  Size: {best['size']:,} bytes, Arch: {best['arch']}\n"
                        f"Target: {self.info.frameworks_dir}/libSDL2-2.0.0.dylib"
                    ),
                })
            else:
                self.actions.append({
                    "type": "manual",
                    "description": "No x86_64 SDL2 donor library found on this system",
                    "detail": (
                        "Install SDL2 via: brew install sdl2\n"
                        "Or install Whisky (which bundles an x86_64 SDL2).\n"
                        "Then re-run 'wineskin-doctor repair'."
                    ),
                })

        # ── SDL2 wrong architecture ──
        if ProblemCategory.SDL2_WRONG_ARCH in categories:
            donors = find_sdl2_donors()
            x86_donors = [d for d in donors if d["arch"] == "x86_64"]

            if x86_donors:
                best = max(x86_donors, key=lambda d: d["size"])
                self.actions.append({
                    "type": "replace_sdl2",
                    "description": f"Replace {self.info.sdl2_arch} SDL2 with x86_64 build",
                    "source": best["path"],
                    "source_size": best["size"],
                    "source_arch": best["arch"],
                    "target": self.info.sdl2_path,
                    "detail": (
                        f"Current: {self.info.sdl2_arch}\n"
                        f"Source: {best['path']} ({best['arch']})"
                    ),
                })

        # ── SDL2 not in wine/lib ──
        if ProblemCategory.SDL2_NO_WINE_LIB in categories:
            rel_target = os.path.relpath(
                os.path.join(self.info.frameworks_dir, "libSDL2-2.0.0.dylib"),
                self.info.wine_lib_dir,
            )
            self.actions.append({
                "type": "create_sdl2_symlinks",
                "description": "Create SDL2 symlinks in Wine lib directory",
                "wine_lib_dir": self.info.wine_lib_dir,
                "frameworks_dir": self.info.frameworks_dir,
                "detail": (
                    f"Create symlinks in {self.info.wine_lib_dir}:\n"
                    f"  libSDL2-2.0.0.dylib -> {rel_target}\n"
                    f"  libSDL2.dylib -> {rel_target}"
                ),
            })

        # ── WineBus SDL disabled ──
        if ProblemCategory.WINEBUS_SDL_DISABLED in categories or ProblemCategory.WINEBUS_ALL_DISABLED in categories:
            self.actions.append({
                "type": "enable_sdl_registry",
                "description": 'Enable SDL in WineBus registry ("Enable SDL" = 1)',
                "registry_file": os.path.join(self.info.wine_prefix, "system.reg"),
                "detail": (
                    "Modify system.reg:\n"
                    '  Set "Enable SDL"=dword:00000001 in\n'
                    "  [System\\ControlSet001\\Services\\winebus]"
                ),
            })

    @property
    def has_actions(self) -> bool:
        return bool(self.actions)

    @property
    def has_manual_only(self) -> bool:
        return all(a["type"] == "manual" for a in self.actions)


def execute_repair(plan: RepairPlan, dry_run: bool = False) -> list[dict]:
    """
    Execute all actions in a repair plan.

    Returns a list of result dicts describing what was done.
    """
    results = []
    manifest = _load_manifest(plan.wrapper_path)
    timestamp = datetime.now().isoformat()

    for action in plan.actions:
        if action["type"] == "manual":
            results.append({
                "action": action["description"],
                "status": "manual_required",
                "detail": action["detail"],
            })
            continue

        if action["type"] == "replace_sdl2":
            result = _do_replace_sdl2(plan, action, manifest, timestamp, dry_run)
            results.append(result)

        elif action["type"] == "create_sdl2_symlinks":
            result = _do_create_symlinks(plan, action, manifest, timestamp, dry_run)
            results.append(result)

        elif action["type"] == "enable_sdl_registry":
            result = _do_enable_sdl_registry(plan, action, manifest, timestamp, dry_run)
            results.append(result)

    if not dry_run:
        _save_manifest(plan.wrapper_path, manifest)

    return results


def _do_replace_sdl2(plan, action, manifest, timestamp, dry_run) -> dict:
    """Replace SDL2 library with a donor."""
    target = action["target"]
    source = action["source"]
    backup_dir = get_backup_dir(plan.wrapper_path)

    if dry_run:
        return {"action": "replace_sdl2", "status": "dry_run", "detail": action["detail"]}

    # Backup existing
    backup_name = f"libSDL2-2.0.0.dylib.{timestamp.replace(':', '-')}"
    backup_path = os.path.join(backup_dir, backup_name)
    os.makedirs(backup_dir, exist_ok=True)

    if os.path.exists(target):
        shutil.copy2(target, backup_path)

    # Copy donor
    shutil.copy2(source, target)
    os.chmod(target, 0o755)

    # Also create the companion symlink if needed
    symlink_path = os.path.join(os.path.dirname(target), "libSDL2.dylib")
    if os.path.islink(symlink_path):
        pass  # already points to the right place
    elif not os.path.exists(symlink_path):
        os.symlink("libSDL2-2.0.0.dylib", symlink_path)

    repair_record = {
        "timestamp": timestamp,
        "type": "replace_sdl2",
        "target": target,
        "backup": backup_path,
        "source": source,
    }
    manifest.setdefault("repairs", []).append(repair_record)

    return {
        "action": "replace_sdl2",
        "status": "done",
        "target": target,
        "backup": backup_path,
        "source": source,
    }


def _do_create_symlinks(plan, action, manifest, timestamp, dry_run) -> dict:
    """Create SDL2 symlinks in wine/lib."""
    wine_lib = action["wine_lib_dir"]
    frameworks_dir = action["frameworks_dir"]
    target_rel = os.path.relpath(
        os.path.join(frameworks_dir, "libSDL2-2.0.0.dylib"),
        wine_lib,
    )

    if dry_run:
        return {"action": "create_sdl2_symlinks", "status": "dry_run", "detail": action["detail"]}

    os.makedirs(wine_lib, exist_ok=True)
    created = []

    for name in ("libSDL2-2.0.0.dylib", "libSDL2.dylib"):
        link_path = os.path.join(wine_lib, name)

        if os.path.islink(link_path):
            os.unlink(link_path)
        elif os.path.exists(link_path):
            backup_name = f"{name}.{timestamp.replace(':', '-')}"
            backup_path = os.path.join(get_backup_dir(plan.wrapper_path), backup_name)
            os.makedirs(os.path.dirname(backup_path), exist_ok=True)
            shutil.copy2(link_path, backup_path)
            os.unlink(link_path)

        os.symlink(target_rel, link_path)
        created.append(link_path)

    repair_record = {
        "timestamp": timestamp,
        "type": "create_sdl2_symlinks",
        "links": created,
    }
    manifest.setdefault("repairs", []).append(repair_record)

    return {"action": "create_sdl2_symlinks", "status": "done", "links": created}


def _do_enable_sdl_registry(plan, action, manifest, timestamp, dry_run) -> dict:
    """Enable SDL in the WineBus registry."""
    reg_file = action["registry_file"]

    if dry_run:
        return {"action": "enable_sdl_registry", "status": "dry_run", "detail": action["detail"]}

    if not os.path.isfile(reg_file):
        return {"action": "enable_sdl_registry", "status": "error", "detail": "system.reg not found"}

    # Backup
    backup_name = f"system.reg.{timestamp.replace(':', '-')}"
    backup_path = os.path.join(get_backup_dir(plan.wrapper_path), backup_name)
    os.makedirs(os.path.dirname(backup_path), exist_ok=True)
    shutil.copy2(reg_file, backup_path)

    text = Path(reg_file).read_text(errors="ignore")

    # Replace "Enable SDL"=dword:00000000 with 00000001
    import re
    new_text = re.sub(
        r'"Enable SDL"=dword:00000000',
        '"Enable SDL"=dword:00000001',
        text
    )

    if new_text == text:
        # Key might not exist, we need to add it
        pattern = r'(\[System\\\\ControlSet001\\\\Services\\\\winebus\].*?\n#time=[^\n]+\n)'
        def replacer(m):
            return m.group(1) + '"Enable SDL"=dword:00000001\n'
        new_text = re.sub(pattern, replacer, text, count=1)

    Path(reg_file).write_text(new_text)

    repair_record = {
        "timestamp": timestamp,
        "type": "enable_sdl_registry",
        "file": reg_file,
        "backup": backup_path,
    }
    manifest.setdefault("repairs", []).append(repair_record)

    return {"action": "enable_sdl_registry", "status": "done", "backup": backup_path}


# ─── Rollback ────────────────────────────────────────────────────────


def rollback(wrapper_path: str) -> list[dict]:
    """
    Roll back all repairs for a wrapper, restoring backups in reverse order.
    """
    manifest = _load_manifest(wrapper_path)
    repairs = manifest.get("repairs", [])

    if not repairs:
        return [{"status": "nothing", "detail": "No repairs recorded for this wrapper."}]

    results = []

    # Process in reverse order
    for repair in reversed(repairs):
        rtype = repair.get("type")

        if rtype == "replace_sdl2":
            backup = repair.get("backup")
            target = repair.get("target")
            if backup and os.path.isfile(backup) and target:
                shutil.copy2(backup, target)
                results.append({
                    "action": f"rollback {rtype}",
                    "status": "done",
                    "restored": target,
                    "from_backup": backup,
                })
            else:
                results.append({
                    "action": f"rollback {rtype}",
                    "status": "error",
                    "detail": f"Backup not found: {backup}",
                })

        elif rtype == "create_sdl2_symlinks":
            for link in repair.get("links", []):
                if os.path.islink(link):
                    os.unlink(link)
                    results.append({
                        "action": f"rollback symlink",
                        "status": "done",
                        "removed": link,
                    })

        elif rtype == "enable_sdl_registry":
            backup = repair.get("backup")
            reg_file = repair.get("file")
            if backup and os.path.isfile(backup) and reg_file:
                shutil.copy2(backup, reg_file)
                results.append({
                    "action": f"rollback {rtype}",
                    "status": "done",
                    "restored": reg_file,
                    "from_backup": backup,
                })

    # Clear repairs from manifest
    manifest["repairs"] = []
    _save_manifest(wrapper_path, manifest)

    return results
