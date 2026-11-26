# Wineskin Controller Doctor

A lightweight macOS command-line utility that diagnoses and safely repairs controller detection and XInput passthrough issues in **Wineskin / Sikarugir** game wrappers on Apple Silicon (and Intel) Macs.

## Why This Exists

When running Windows games through Wineskin/Wine on macOS, controllers often fail silently because:
- The bundled `libSDL2-2.0.0.dylib` is missing, 0-byte/corrupted, or built for the wrong CPU architecture (`arm64` instead of `x86_64`)
- Wine's `winebus.sys` driver fails to initialize SDL and native HID fallback is disabled in the registry
- `winexinput.sys` never exposes a virtual XInput gamepad to the game
- Registry DLL overrides or duplicate HID backends interfere with input

**Wineskin Controller Doctor** automates root-cause analysis and applies minimal, reversible fixes with full backup and rollback support.

## Requirements

- macOS (tested on Apple Silicon ARM64 with Rosetta 2 + Sikarugir/Wineskin Wine)
- Python 3.9+ (uses only the Python standard library — zero external pip dependencies)
- Standard macOS CLI tools (`ioreg`, `file`, `otool`)

## Installation

### Option 1: Clone from GitHub

```bash
git clone https://github.com/shrish-sharma-git/wineskin-doctor.git ~/wineskin-doctor
chmod +x ~/wineskin-doctor/wineskin-doctor

# Optional: add to PATH
ln -sf ~/wineskin-doctor/wineskin-doctor /usr/local/bin/wineskin-doctor
```

### Option 2: Download a Release

Download the latest `.tar.gz` archive from the [GitHub Releases](https://github.com/shrish-sharma-git/wineskin-doctor/releases) page, extract it, and run `./wineskin-doctor`.

## Usage

### 1. Check connected controllers
```bash
wineskin-doctor status
```
Inspects macOS `IOUSB` and `IOHIDDevice` trees to confirm your wired or Bluetooth controller is recognized by macOS.

### 2. Scan for Wineskin wrappers
```bash
wineskin-doctor scan
```
Searches `/Applications`, `~/Applications`, `~/Desktop`, and `~/Games` for Wineskin/Sikarugir `.app` wrappers.

### 3. Diagnose a wrapper (read-only)
```bash
wineskin-doctor diagnose "/Applications/Alan Wake Remastered.app"
```
Performs a non-destructive inspection of:
- Wine engine binary and version
- Wine prefix integrity
- `libSDL2-2.0.0.dylib` existence, size, CPU architecture (`x86_64` vs `arm64`), install ID, and dependencies
- Wine `lib/` `@rpath` symlink resolution
- `winebus.sys` and `winebus.so` presence
- `HKLM\System\CurrentControlSet\Services\winebus` registry keys (`Enable SDL`, `Map Controllers`, `DisableHidraw`, `DisableInput`)
- `xinput*.dll` and `winexinput.sys` availability
- Conflicting controller DLL overrides in `user.reg`

### 4. Repair a wrapper (interactive, with backups)
```bash
wineskin-doctor repair "/Applications/Some Game.app"
```
1. Runs full diagnostics
2. Builds a targeted `RepairPlan` from the findings
3. Displays the exact proposed changes and asks for `[y/N]` confirmation
4. Backs up every modified file inside `<Wrapper>.app/Contents/.wineskin-doctor-backups/` with a `manifest.json`
5. Re-runs diagnostics to verify the fix

### 5. Roll back repairs
```bash
wineskin-doctor rollback "/Applications/Some Game.app"
```
Restores all backed-up files and removes any added symlinks in reverse order.

## Repair Profiles

| Profile | Trigger | Action |
| :--- | :--- | :--- |
| **SDL2 replacement** | Missing, 0-byte, corrupted, or wrong-arch `libSDL2-2.0.0.dylib` | Copies a verified `x86_64` `libSDL2-2.0.0.dylib` from a local donor (e.g. Whisky or `/usr/local`) |
| **SDL2 `@rpath` symlinks** | SDL2 exists in `Frameworks/` but is not linked in `SharedSupport/wine/lib/` | Creates relative symlinks (`libSDL2-2.0.0.dylib`, `libSDL2.dylib`) |
| **WineBus SDL enable** | `"Enable SDL"` is `0` in `system.reg` | Sets `"Enable SDL"=dword:00000001` under `Services\winebus` |

## Safety Guarantees

- **Read-only by default** — `scan`, `status`, and `diagnose` never write to disk
- **Explicit approval required** — `repair` and `rollback` always prompt `[y/N]` before modifying files
- **Automatic timestamped backups** — stored in `<Wrapper>.app/Contents/.wineskin-doctor-backups/`
- **Never deletes** game saves, prefixes, or executables
- **Never installs** unsigned kernel drivers or disables macOS security protections
- **Architecture-verified** — never copies an `arm64` library into an `x86_64` Wine wrapper

## Running Tests

```bash
python3 -m unittest discover -s tests -v
```

## Project Structure

```text
wineskin-doctor/
├── wineskin-doctor          # Executable CLI entrypoint
├── README.md                # Documentation
├── LICENSE                  # MIT License
├── doctor/
│   ├── __init__.py          # Package version
│   ├── scanner.py           # Wrapper discovery & read-only inspection
│   ├── diagnoser.py         # Root-cause analysis engine
│   ├── repairer.py          # Safe repair & rollback engine
│   ├── formatter.py         # Terminal report formatting
│   └── cli.py               # CLI command router
└── tests/
    └── test_doctor.py       # Unit & mock-wrapper integration tests
```

## License

MIT License — see [LICENSE](LICENSE).
