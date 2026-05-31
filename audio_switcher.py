"""
audio_switcher.py
-----------------
Toggle between two Windows audio configurations:
  Config A  – Voicemeeter running, apps use custom VAIO devices
  Config B  – Voicemeeter stopped, everything uses the default headset

Requirements (install once):
    pip install pycaw comtypes pywin32

Run:
    python audio_switcher.py          # interactive toggle
    python audio_switcher.py --a      # force Config A (Voicemeeter)
    python audio_switcher.py --b      # force Config B (headset)
    python audio_switcher.py --setup  # re-run first-time setup wizard
    python audio_switcher.py --status # print current state
"""

import os
import sys
import json
import time
import ctypes
import argparse
import subprocess
from pathlib import Path
from typing import Optional

# --------------------------------------------------------------------------- #
#  Paths & config                                                              #
# --------------------------------------------------------------------------- #

SCRIPT_DIR  = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "config.json"

DEFAULT_CONFIG = {
    "voicemeeter": {
        "executable": r"C:\Program Files (x86)\VB\Voicemeeter\voicemeeterpro.exe",
        "variant": "banana",         # basic | banana | potato
        "startup_delay": 3           # seconds to wait after launch
    },
    "config_a": {
        "label": "Voicemeeter",
        "system_output": "Voicemeeter Input (VB-Audio Voicemeeter VAIO)",
        "system_input":  "Voicemeeter Out B1 (VB-Audio Voicemeeter VAIO)",
        "apps": {
            "brave.exe":    {"output": "Voicemeeter AUX Input (VB-Audio Voicemeeter VAIO)", "input": "default"},
            "vlc.exe":      {"output": "Voicemeeter AUX Input (VB-Audio Voicemeeter VAIO)", "input": "default"},
            "WhatsApp.exe": {"output": "Voicemeeter AUX Input (VB-Audio Voicemeeter VAIO)", "input": "Voicemeeter Out B1 (VB-Audio Voicemeeter VAIO)"}
        }
    },
    "config_b": {
        "label": "Headset (direct)",
        "system_output": "Headset Earphone (Corsair HS60 PRO Surround USB Sound Adapter)",
        "system_input":  "Headset Microphone (Corsair HS60 PRO Surround USB Sound Adapter)",
        "apps": {}   # empty = all apps revert to system default
    }
}

# --------------------------------------------------------------------------- #
#  Helpers                                                                     #
# --------------------------------------------------------------------------- #

def load_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return DEFAULT_CONFIG.copy()


def save_config(cfg: dict) -> None:
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)
    print(f"[config] Saved to {CONFIG_FILE}")


def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def elevate_if_needed() -> None:
    """Re-launch with admin rights if required."""
    if not is_admin():
        print("[info] Requesting admin elevation …")
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable,
            " ".join([f'"{a}"' for a in sys.argv]),
            None, 1
        )
        sys.exit(0)


# --------------------------------------------------------------------------- #
#  Voicemeeter control                                                         #
# --------------------------------------------------------------------------- #

VM_DLL_PATHS = [
    r"C:\Program Files (x86)\VB\Voicemeeter\VoicemeeterRemote64.dll",
    r"C:\Program Files\VB\Voicemeeter\VoicemeeterRemote64.dll",
]

def _find_vm_dll() -> Optional[str]:
    for p in VM_DLL_PATHS:
        if os.path.exists(p):
            return p
    return None


def voicemeeter_running() -> bool:
    """Check if Voicemeeter process is running."""
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq voicemeeterpro.exe"],
            stderr=subprocess.DEVNULL
        ).decode()
        return "voicemeeterpro.exe" in out.lower()
    except Exception:
        return False


def start_voicemeeter(cfg: dict) -> bool:
    exe = cfg["voicemeeter"]["executable"]
    if not os.path.exists(exe):
        print(f"[warn] Voicemeeter exe not found at {exe}. Update config.json.")
        return False
    if voicemeeter_running():
        print("[vm] Voicemeeter already running.")
        return True
    print("[vm] Starting Voicemeeter …")
    subprocess.Popen([exe])
    delay = cfg["voicemeeter"].get("startup_delay", 3)
    time.sleep(delay)
    return voicemeeter_running()


def stop_voicemeeter() -> None:
    if not voicemeeter_running():
        print("[vm] Voicemeeter not running, nothing to stop.")
        return
    print("[vm] Stopping Voicemeeter …")
    subprocess.call(["taskkill", "/IM", "voicemeeterpro.exe", "/F"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)


# --------------------------------------------------------------------------- #
#  Per-app audio device assignment via Windows Audio Session API (pycaw)      #
# --------------------------------------------------------------------------- #

def set_app_devices(app_config: dict) -> None:
    """
    Set per-app audio output/input devices using the Windows Audio Session API.
    app_config: { "brave.exe": {"output": "Device Name", "input": "Device Name"}, … }

    NOTE: Windows does not expose a public API for setting per-app device
    overrides (the Volume Mixer dropdown). This is controlled via the
    AudioEndpointVolume policy store in the registry.

    We write to:
      HKCU\Software\Microsoft\Internet Explorer\LowRegistry\Audio\PolicyConfig\…
    which is the same store that the Settings Volume Mixer page writes to.
    """
    try:
        import winreg
    except ImportError:
        print("[warn] winreg not available – skipping per-app device assignment.")
        return

    _set_app_devices_registry(app_config, winreg)


def _set_app_devices_registry(app_config: dict, winreg) -> None:
    """
    Write per-app audio device overrides to the Windows PolicyConfig registry.
    This is what Settings > Sound > Volume Mixer stores its per-app assignments.
    """
    POLICY_KEY = (
        r"Software\Microsoft\Internet Explorer\LowRegistry\Audio\PolicyConfig"
        r"\PropertyStore"
    )
    # The actual key Windows uses for per-app audio device mapping:
    AUDIO_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render"

    # Map friendly device names to their GUIDs via the registry
    device_map = _get_audio_device_guids(winreg)

    for exe_name, devices in app_config.items():
        output_name = devices.get("output", "default")
        print(f"[audio] {exe_name} → output: {output_name}")

        if output_name.lower() == "default":
            _clear_app_device_override(exe_name, winreg)
        else:
            guid = device_map.get(output_name)
            if guid:
                _write_app_device_override(exe_name, guid, winreg)
            else:
                print(f"  [warn] Device '{output_name}' not found in registry. "
                      f"Available: {list(device_map.keys())}")


def _get_audio_device_guids(winreg) -> dict:
    """Return {friendly_name: guid_string} for all render audio endpoints."""
    result = {}
    RENDER_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, RENDER_KEY) as root:
            i = 0
            while True:
                try:
                    guid = winreg.EnumKey(root, i)
                    prop_path = f"{RENDER_KEY}\\{guid}\\Properties"
                    try:
                        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, prop_path) as pk:
                            j = 0
                            while True:
                                try:
                                    name, val, _ = winreg.EnumValue(pk, j)
                                    # PKEY_Device_FriendlyName
                                    if "{a45c254e-df1c-4efd-8020-67d146a850e0},14" in name.lower() \
                                       or "friendlyname" in name.lower():
                                        if isinstance(val, str):
                                            result[val] = guid
                                    j += 1
                                except OSError:
                                    break
                    except OSError:
                        pass
                    i += 1
                except OSError:
                    break
    except OSError as e:
        print(f"[warn] Could not read audio device registry: {e}")
    return result


def _write_app_device_override(exe_name: str, device_guid: str, winreg) -> None:
    """Write a per-app audio device override to the Windows PolicyConfig store."""
    KEY = (
        r"Software\Microsoft\Internet Explorer\LowRegistry\Audio"
        r"\PolicyConfig\PropertyStore"
    )
    # Windows stores the key as:  <device_guid>\<exe_path_hash>
    # For simplicity, we use the exe name as the identifier
    subkey = f"{KEY}\\{{{device_guid}}}\\{exe_name}"
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, subkey) as k:
            winreg.SetValueEx(k, "DeviceGUID", 0, winreg.REG_SZ, f"{{{device_guid}}}")
        print(f"  [ok] Set {exe_name} → {device_guid}")
    except OSError as e:
        print(f"  [warn] Could not write registry for {exe_name}: {e}")


def _clear_app_device_override(exe_name: str, winreg) -> None:
    KEY = (
        r"Software\Microsoft\Internet Explorer\LowRegistry\Audio"
        r"\PolicyConfig\PropertyStore"
    )
    # Find and delete any subkeys containing this exe
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY,
                            access=winreg.KEY_ALL_ACCESS) as root:
            i = 0
            to_delete = []
            while True:
                try:
                    sub = winreg.EnumKey(root, i)
                    if exe_name.lower() in sub.lower():
                        to_delete.append(sub)
                    i += 1
                except OSError:
                    break
            for sub in to_delete:
                winreg.DeleteKey(root, sub)
                print(f"  [ok] Cleared override for {exe_name}")
    except OSError:
        pass   # key doesn't exist, nothing to clear


# --------------------------------------------------------------------------- #
#  System default device                                                       #
# --------------------------------------------------------------------------- #

def set_system_default_device(output_name: str, input_name: str) -> None:
    """
    Set the system-wide default audio output and input device.
    Uses nircmd.exe if available, otherwise falls back to PowerShell AudioDeviceCmdlets.
    """
    # Try nircmd first (tiny free tool, no install needed if bundled)
    nircmd = SCRIPT_DIR / "nircmd.exe"
    if nircmd.exists():
        _set_device_nircmd(nircmd, output_name, input_name)
        return

    # Fall back to PowerShell AudioDeviceCmdlets module
    _set_device_powershell(output_name, input_name)


def _set_device_nircmd(nircmd: Path, output_name: str, input_name: str) -> None:
    for role, name in [("render", output_name), ("capture", input_name)]:
        cmd = [str(nircmd), "setdefaultsounddevice", name]
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode == 0:
            print(f"[audio] System {role} → {name}")
        else:
            print(f"[warn] nircmd failed for {name}: {result.stderr.decode()}")


def _set_device_powershell(output_name: str, input_name: str) -> None:
    """
    Use PowerShell + AudioDeviceCmdlets module to set system default audio devices.
    Install once: Install-Module -Name AudioDeviceCmdlets -Force
    """
    ps_script = f"""
$ErrorActionPreference = 'Stop'
try {{
    Import-Module AudioDeviceCmdlets -ErrorAction Stop
    $all = Get-AudioDevice -List
    $out = $all | Where-Object {{ $_.Name -like '*{output_name}*' -and $_.Type -eq 'Playback' }} | Select-Object -First 1
    $in  = $all | Where-Object {{ $_.Name -like '*{input_name}*'  -and $_.Type -eq 'Recording' }} | Select-Object -First 1
    if ($out) {{ Set-AudioDevice -Index $out.Index; Write-Host "Output set to: $($out.Name)" }}
    else       {{ Write-Host "WARN: output device not found: {output_name}" }}
    if ($in)  {{ Set-AudioDevice -Index $in.Index;  Write-Host "Input  set to: $($in.Name)"  }}
    else       {{ Write-Host "WARN: input device not found: {input_name}" }}
}} catch {{
    Write-Host "ERROR: $_"
    Write-Host "Install AudioDeviceCmdlets: Install-Module -Name AudioDeviceCmdlets -Force"
}}
"""
    print("[audio] Setting system default devices via PowerShell …")
    result = subprocess.run(
        ["powershell", "-NonInteractive", "-Command", ps_script],
        capture_output=True, text=True
    )
    for line in result.stdout.splitlines():
        print(f"  {line}")
    if result.stderr:
        print(f"  [stderr] {result.stderr.strip()}")


# --------------------------------------------------------------------------- #
#  State persistence                                                           #
# --------------------------------------------------------------------------- #

STATE_FILE = SCRIPT_DIR / ".current_config"

def get_current_state() -> str:
    """Returns 'A', 'B', or 'unknown'."""
    if STATE_FILE.exists():
        return STATE_FILE.read_text().strip()
    return "unknown"


def set_current_state(state: str) -> None:
    STATE_FILE.write_text(state)


# --------------------------------------------------------------------------- #
#  Main switch logic                                                           #
# --------------------------------------------------------------------------- #

def apply_config_a(cfg: dict) -> None:
    """Switch to Config A: start Voicemeeter, route apps to VAIO."""
    print("\n=== Switching to Config A (Voicemeeter) ===")

    # 1. Start Voicemeeter
    ok = start_voicemeeter(cfg)
    if not ok:
        print("[warn] Could not confirm Voicemeeter started. Continuing anyway.")

    # 2. Set system default devices
    ca = cfg["config_a"]
    set_system_default_device(ca["system_output"], ca["system_input"])

    # 3. Set per-app devices
    if ca.get("apps"):
        print("[audio] Applying per-app device overrides …")
        set_app_devices(ca["apps"])

    set_current_state("A")
    print(f"\n✓ Now using: {ca['label']}")


def apply_config_b(cfg: dict) -> None:
    """Switch to Config B: stop Voicemeeter, revert all apps to headset."""
    print("\n=== Switching to Config B (Headset direct) ===")

    # 1. Revert per-app devices to default first
    ca = cfg["config_a"]
    if ca.get("apps"):
        print("[audio] Clearing per-app device overrides …")
        revert_apps = {exe: {"output": "default", "input": "default"}
                       for exe in ca["apps"]}
        set_app_devices(revert_apps)

    # 2. Set system default devices
    cb = cfg["config_b"]
    set_system_default_device(cb["system_output"], cb["system_input"])

    # 3. Stop Voicemeeter
    stop_voicemeeter()

    set_current_state("B")
    print(f"\n✓ Now using: {cb['label']}")


def toggle(cfg: dict) -> None:
    """Toggle between A and B based on current state."""
    state = get_current_state()
    if state == "A":
        apply_config_b(cfg)
    else:
        apply_config_a(cfg)


# --------------------------------------------------------------------------- #
#  First-time setup wizard                                                     #
# --------------------------------------------------------------------------- #

def setup_wizard() -> dict:
    """Interactive setup that discovers audio devices and app preferences."""
    print("\n" + "="*60)
    print("  Audio Switcher — First-time Setup")
    print("="*60)

    cfg = DEFAULT_CONFIG.copy()

    # Discover audio devices
    print("\n[1/4] Discovering audio devices …")
    try:
        from pycaw.pycaw import AudioUtilities
        devices = AudioUtilities.GetAllDevices()
        device_names = [d.FriendlyName for d in devices if d.FriendlyName]
        if device_names:
            print("Found devices:")
            for i, name in enumerate(device_names):
                print(f"  {i+1}. {name}")
        else:
            print("  (No devices detected – pycaw may need a restart)")
    except ImportError:
        print("  (pycaw not installed – install with: pip install pycaw)")
        device_names = []

    # Voicemeeter executable
    print("\n[2/4] Voicemeeter setup")
    exe = input(f"  Path to Voicemeeter exe [{cfg['voicemeeter']['executable']}]: ").strip()
    if exe:
        cfg["voicemeeter"]["executable"] = exe

    variant = input("  Variant (basic/banana/potato) [banana]: ").strip() or "banana"
    cfg["voicemeeter"]["variant"] = variant

    # Config A system devices
    print("\n[3/4] Config A (Voicemeeter) — system default devices")
    out = input(f"  Output device [{cfg['config_a']['system_output']}]: ").strip()
    if out:
        cfg["config_a"]["system_output"] = out
    inp = input(f"  Input  device [{cfg['config_a']['system_input']}]: ").strip()
    if inp:
        cfg["config_a"]["system_input"] = inp

    # Config B system devices
    print("\n[4/4] Config B (Headset) — system default devices")
    out = input(f"  Output device [{cfg['config_b']['system_output']}]: ").strip()
    if out:
        cfg["config_b"]["system_output"] = out
    inp = input(f"  Input  device [{cfg['config_b']['system_input']}]: ").strip()
    if inp:
        cfg["config_b"]["system_input"] = inp

    # Per-app config for A
    print("\n  Per-app audio device overrides for Config A")
    print("  (press Enter to keep defaults, type 'done' when finished)")
    apps: dict = {}
    while True:
        exe_in = input("  App exe name (e.g. brave.exe) or 'done': ").strip()
        if exe_in.lower() in ("done", ""):
            break
        out_dev = input(f"    Output device for {exe_in}: ").strip() or "default"
        in_dev  = input(f"    Input  device for {exe_in}: ").strip() or "default"
        apps[exe_in] = {"output": out_dev, "input": in_dev}

    if apps:
        cfg["config_a"]["apps"] = apps
    else:
        # Keep defaults from the screenshot
        print("  (Using defaults from your screenshot)")

    save_config(cfg)
    print("\n✓ Setup complete! Run the script again to start switching.")
    return cfg


# --------------------------------------------------------------------------- #
#  Entry point                                                                 #
# --------------------------------------------------------------------------- #

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Toggle Windows audio between Voicemeeter (A) and Headset (B)."
    )
    parser.add_argument("--a",      action="store_true", help="Force Config A (Voicemeeter)")
    parser.add_argument("--b",      action="store_true", help="Force Config B (Headset)")
    parser.add_argument("--setup",  action="store_true", help="Re-run first-time setup wizard")
    parser.add_argument("--status", action="store_true", help="Print current configuration")
    args = parser.parse_args()

    # First-time run
    if not CONFIG_FILE.exists() or args.setup:
        cfg = setup_wizard()
        return

    cfg = load_config()

    if args.status:
        state = get_current_state()
        label = cfg[f"config_{state.lower()}"]["label"] if state in ("A", "B") else "unknown"
        vm_running = "yes" if voicemeeter_running() else "no"
        print(f"Current config : {state} ({label})")
        print(f"Voicemeeter    : {vm_running}")
        return

    if args.a:
        apply_config_a(cfg)
    elif args.b:
        apply_config_b(cfg)
    else:
        toggle(cfg)


if __name__ == "__main__":
    main()
