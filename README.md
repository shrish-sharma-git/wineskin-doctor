# Wineskin Controller Doctor

A macOS command-line utility that diagnoses and repairs controller issues in Wineskin game wrappers running Windows games through Wine on Apple Silicon.

## The Problem

When running Windows games through Wineskin/Wine on macOS, controllers often don't work because:
- The bundled SDL2 library is missing, empty, or has the wrong CPU architecture
- Wine's controller bus driver (winebus) cannot initialise without SDL2
- XInput devices are never exposed to the game
- Registry settings may disable controller backends

This tool automates the diagnosis and provides safe, targeted fixes.

## Requirements

- macOS on Apple Silicon (ARM64)
- Python 3.9+
- One or more Wineskin game wrappers

## Installation

No installation required. Clone or copy the `wineskin-doctor` directory anywhere:

```bash
# Option 1: Add to PATH
ln -sf ~/wineskin-doctor/wineskin-doctor /usr/local/bin/wineskin-doctor

# Option 2: Run directly
~/wineskin-doctor/wineskin-doctor scan
```

## Usage

### Scan for Wineskin wrappers

```bash
wineskin-doctor scan
```

Finds all Wineskin game wrappers in `/Applications`, `~/Applications`, `~/Desktop`, and `~/Games`.

### Check controller status

```bash
wineskin-doctor status
```

Shows which controllers macOS currently detects via USB and Bluetooth.

### Diagnose a wrapper

```bash
wineskin-doctor diagnose "/Applications/Alan Wake Remastered.app"
```

Performs a comprehensive read-only inspection:
- Verifies Wine engine and prefix
- Checks SDL2 library integrity, architecture, and dependencies
- Inspects WineBus registry configuration
- Checks XInput and WineXInput driver availability
- Identifies DLL override conflicts
- Detects HID passthrough issues

Produces a colour-coded report with findings and recommendations.

### Repair a wrapper

```bash
wineskin-doctor repair "/Applications/Some Game.app"
```

1. Runs full diagnostics
2. Builds a repair plan based on the findings
3. Shows proposed changes for your review
4. **Asks for your explicit approval** before modifying anything
5. Creates timestamped backups of every file before changing it
6. Verifies the repair after applying it

### Roll back repairs

```bash
wineskin-doctor rollback "/Applications/Some Game.app"
```

Restores all files to their pre-repair state using the timestamped backups stored inside the wrapper.

## What It Checks

| Check | Description |
|-------|-------------|
| Controller detection | macOS USB/Bluetooth HID recognition |
| Wine engine | Binary presence and version |
| Wine prefix | Prefix directory integrity |
| SDL2 library | Existence, size, architecture (x86_64), install name, dependencies |
| SDL2 Wine linkage | Symlinks in wine/lib for @rpath resolution |
| WineBus driver | winebus.sys and winebus.so presence |
| WineBus registry | Enable SDL, Map Controllers, DisableHidraw, DisableInput |
| XInput DLLs | xinput1_3.dll, xinput1_4.dll, etc. |
| WineXInput driver | winexinput.sys presence |
| DLL overrides | Conflicts with controller-related DLLs |
| HID passthrough | Potential duplicate device detection |

## Repair Profiles

The tool selects repairs based on diagnostic evidence, not game names:

| Profile | Trigger | Action |
|---------|---------|--------|
| SDL2 replacement | Empty/missing/wrong-arch SDL2 | Copy x86_64 SDL2 from a known donor on the system |
| SDL2 symlinks | SDL2 present but not linked in wine/lib | Create relative symlinks |
| WineBus SDL enable | "Enable SDL" registry value is 0 | Set to 1 in system.reg |

## Safety Guarantees

- **Never modifies without approval** — every change requires explicit confirmation
- **Never deletes** game files, saves, prefixes, or configurations
- **Always backs up** before modifying — timestamped copies stored in the wrapper
- **Never installs** unsigned drivers or third-party software
- **Never disables** macOS security protections
- **Architecture-verified** — only copies x86_64 libraries for x86_64 Wine
- **Rollback available** — every repair can be fully reversed

## File Structure

```
wineskin-doctor/
├── wineskin-doctor          # CLI entry point (executable)
├── README.md                # This file
└── doctor/
    ├── __init__.py
    ├── scanner.py           # Wrapper discovery and read-only inspection
    ├── diagnoser.py         # Root-cause analysis engine
    ├── repairer.py          # Safe repair with backup/rollback
    ├── formatter.py         # Terminal output formatting
    └── cli.py               # Command-line interface
```

## Backups

All backups are stored inside each wrapper at:

```
<Wrapper>.app/Contents/.wineskin-doctor-backups/
├── manifest.json
├── libSDL2-2.0.0.dylib.<timestamp>
├── system.reg.<timestamp>
└── ...
```

The `manifest.json` tracks every repair action for rollback.

## Example Workflow

```bash
# 1. See what wrappers you have
wineskin-doctor scan

# 2. Check if your controller is connected
wineskin-doctor status

# 3. Diagnose a game that won't detect the controller
wineskin-doctor diagnose "/Applications/Some Game.app"

# 4. If issues found, review and apply repairs
wineskin-doctor repair "/Applications/Some Game.app"

# 5. Launch the game and test
# 6. If something went wrong, roll back
wineskin-doctor rollback "/Applications/Some Game.app"
```

## Licence

Personal use utility. No warranty.
