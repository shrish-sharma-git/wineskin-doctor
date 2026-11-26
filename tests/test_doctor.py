"""Unit and integration tests for Wineskin Controller Doctor."""

import os
import shutil
import tempfile
import unittest

from doctor.scanner import scan_wrapper, ControllerInfo
from doctor.diagnoser import diagnose, ProblemCategory, Severity
from doctor.repairer import RepairPlan, execute_repair, rollback


def _create_mock_wrapper(base_dir: str, sdl2_bytes: bytes = b"", enable_sdl: int = 0) -> str:
    app = os.path.join(base_dir, "MockGame.app")
    contents = os.path.join(app, "Contents")
    fw = os.path.join(contents, "Frameworks")
    wine_bin = os.path.join(contents, "SharedSupport", "wine", "bin")
    wine_lib = os.path.join(contents, "SharedSupport", "wine", "lib")
    unix_dir = os.path.join(wine_lib, "wine", "x86_64-unix")
    prefix = os.path.join(contents, "SharedSupport", "prefix")
    sys32 = os.path.join(prefix, "drive_c", "windows", "system32")
    drivers = os.path.join(sys32, "drivers")

    for d in (fw, wine_bin, unix_dir, drivers):
        os.makedirs(d, exist_ok=True)

    with open(os.path.join(fw, "libSDL2-2.0.0.dylib"), "wb") as f:
        f.write(sdl2_bytes)
    open(os.path.join(wine_bin, "wine"), "w").close()
    open(os.path.join(drivers, "winebus.sys"), "w").close()
    open(os.path.join(drivers, "winexinput.sys"), "w").close()
    open(os.path.join(unix_dir, "winebus.so"), "w").close()

    for dll in ("xinput1_3.dll", "xinput1_4.dll", "xinput9_1_0.dll"):
        with open(os.path.join(sys32, dll), "wb") as f:
            f.write(b"MZ" + b"\x00" * 100)

    with open(os.path.join(prefix, "system.reg"), "w") as f:
        f.write(
            "[System\\\\ControlSet001\\\\Services\\\\winebus]\n"
            "#time=123\n"
            f'"Enable SDL"=dword:{enable_sdl:08x}\n'
            '"Map Controllers"=dword:00000001\n'
            '"DisableHidraw"=dword:00000001\n'
        )
    return app


class TestWineskinDoctor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="wineskin_doc_test_")
        self.controller = ControllerInfo(
            name="Wireless Controller",
            vendor_id=0x054C,
            product_id=0x09CC,
            vendor_hex="054c",
            product_hex="09cc",
            connection="USB",
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_diagnose_empty_sdl2_and_disabled_sdl(self):
        app = _create_mock_wrapper(self.tmp, sdl2_bytes=b"", enable_sdl=0)
        info = scan_wrapper(app)
        report = diagnose(info, [self.controller])

        categories = {f.category for f in report.findings}
        self.assertTrue(report.has_critical)
        self.assertIn(ProblemCategory.SDL2_EMPTY, categories)
        self.assertIn(ProblemCategory.WINEBUS_SDL_DISABLED, categories)

    def test_repair_and_rollback_dry_run_and_live(self):
        app = _create_mock_wrapper(self.tmp, sdl2_bytes=b"", enable_sdl=0)
        info = scan_wrapper(app)
        report = diagnose(info, [self.controller])
        plan = RepairPlan(app, report, info)
        self.assertTrue(plan.has_actions)

        # Dry run must not modify files
        dry_results = execute_repair(plan, dry_run=True)
        self.assertTrue(all(r["status"] in ("dry_run", "manual_required") for r in dry_results))
        self.assertEqual(
            os.path.getsize(os.path.join(app, "Contents", "Frameworks", "libSDL2-2.0.0.dylib")),
            0,
        )

        # Live repair + rollback (registry repair always runs; SDL2 replacement runs if donor exists)
        results = execute_repair(plan, dry_run=False)
        self.assertTrue(any(r["status"] == "done" for r in results))
        self.assertIn("dword:00000001", open(os.path.join(app, "Contents", "SharedSupport", "prefix", "system.reg")).read())

        rb = rollback(app)
        self.assertTrue(any(r["status"] == "done" for r in rb))
        self.assertIn("dword:00000000", open(os.path.join(app, "Contents", "SharedSupport", "prefix", "system.reg")).read())
        self.assertEqual(
            os.path.getsize(os.path.join(app, "Contents", "Frameworks", "libSDL2-2.0.0.dylib")),
            0,
        )


if __name__ == "__main__":
    unittest.main()
