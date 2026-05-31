# Audio Config Switcher

Toggles your PC between two audio configurations: (hard codded atm)

| | Config A | Config B |
|---|---|---|
| **Label** | Voicemeeter (VAIO) | Headset Direct |
| **System output** | Voicemeeter Input (VAIO) | Corsair HS60 Earphone |
| **System input** | Voicemeeter Out B1 | Corsair HS60 Mic |
| **Brave** | → VAIO AUX | default |
| **VLC** | → VAIO AUX | default |
| **WhatsApp** | → VAIO AUX | default |

---

## One-time setup

### 1. Install Python dependencies

```
pip install pycaw comtypes pywin32
```

### 2. Install PowerShell AudioDeviceCmdlets (for system device switching)

Open PowerShell as Administrator and run:

```powershell
Install-Module -Name AudioDeviceCmdlets -Force
```

> **Alternative:** Download [nircmd.exe](https://www.nirsoft.net/utils/nircmd.html) (tiny, free, no install)
> and place it in the same folder as `audio_switcher.py`.
> nircmd is faster and more reliable than the PowerShell module.

### 3. (Optional) Create a desktop hotkey shortcut

Right-click `create_shortcut.ps1` → **Run with PowerShell**

This creates a Desktop shortcut bound to **Ctrl+Alt+A**.

---

## Usage

| Method | Command |
|---|---|
| Double-click | `toggle_audio.bat` |
| Terminal | `python audio_switcher.py` |
| Force Config A | `python audio_switcher.py --a` |
| Force Config B | `python audio_switcher.py --b` |
| Check current | `python audio_switcher.py --status` |
| Re-run setup | `python audio_switcher.py --setup` |

---

## Customising `config.json`

Edit `config.json` to change device names, add apps, or adjust the startup delay.

Device names must match **exactly** what Windows shows in Settings → Sound.

```json
{
  "voicemeeter": {
    "executable": "C:\\Program Files (x86)\\VB\\Voicemeeter\\voicemeeterpro.exe",
    "startup_delay": 3
  },
  "config_a": {
    "system_output": "Voicemeeter Input (VB-Audio Voicemeeter VAIO)",
    "system_input":  "Voicemeeter Out B1 (VB-Audio Voicemeeter VAIO)",
    "apps": {
      "brave.exe": { "output": "Voicemeeter AUX Input ...", "input": "default" }
    }
  },
  "config_b": {
    "system_output": "Headset Earphone (Corsair HS60 PRO Surround USB Sound Adapter)",
    "system_input":  "Headset Microphone (Corsair HS60 PRO Surround USB Sound Adapter)",
    "apps": {}
  }
}
```

---

## How it works

1. **Config A → B**: clears per-app overrides, sets headset as default, stops Voicemeeter
2. **Config B → A**: starts Voicemeeter (waits for it), sets VAIO as system default, writes per-app overrides

Per-app device overrides are written to the same Windows registry location that the
Settings → Sound → Volume Mixer page uses, so changes take effect immediately.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| "Device not found" | Open Settings → Sound → Volume Mixer and copy the exact device name into `config.json` |
| System default doesn't change | Install `AudioDeviceCmdlets` or download `nircmd.exe` |
| Voicemeeter doesn't start | Check the `executable` path in `config.json` |
| Apps don't get new device | Restart the app after switching |
