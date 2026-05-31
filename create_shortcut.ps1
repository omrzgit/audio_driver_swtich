# create_shortcut.ps1
# Run this ONCE to create a desktop shortcut with a hotkey (Ctrl+Alt+A)
# Right-click → Run with PowerShell

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ShortcutPath = "$env:USERPROFILE\Desktop\Toggle Audio.lnk"

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)

$Shortcut.TargetPath       = "python"
$Shortcut.Arguments        = "`"$ScriptDir\audio_switcher.py`""
$Shortcut.WorkingDirectory = $ScriptDir
$Shortcut.IconLocation     = "C:\Windows\System32\SndVol.exe,0"
$Shortcut.Hotkey           = "CTRL+ALT+A"   # Change this if you want a different key
$Shortcut.Description      = "Toggle between Voicemeeter and Headset audio configs"
$Shortcut.WindowStyle      = 7              # 7 = minimized (runs silently in background)
$Shortcut.Save()

Write-Host "Shortcut created at: $ShortcutPath"
Write-Host "Hotkey: Ctrl+Alt+A"
Write-Host ""
Write-Host "NOTE: For the hotkey to work, the shortcut must stay on the Desktop."
Write-Host "You can also pin it to the taskbar."
