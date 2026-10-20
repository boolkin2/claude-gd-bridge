# Управление окном игры: скриншот, клики, клавиши. DPI-aware, координаты —
# в пикселях основного экрана (1920x1080).
# Использование:
#   ui.ps1 shot <out.png> [scale]        — снимок основного экрана
#   ui.ps1 click <x> <y>                 — левый клик
#   ui.ps1 rclick <x> <y>
#   ui.ps1 drag <x1> <y1> <x2> <y2>
#   ui.ps1 key <VK hex|name> [count]     — нажать и отпустить
#   ui.ps1 down|up <VK>                  — удержание
#   ui.ps1 focus                         — вывести окно GD на передний план
#   ui.ps1 wheel <x> <y> <delta>
param([string]$cmd, [string]$a1, [string]$a2, [string]$a3, [string]$a4)
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class U {
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, int d, UIntPtr e);
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint f, UIntPtr e);
  [DllImport("user32.dll")] public static extern uint MapVirtualKey(uint code, uint type);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
}
"@
[U]::SetProcessDPIAware() | Out-Null
$names = @{ 'esc'=0x1B; 'enter'=0x0D; 'space'=0x20; 'tab'=0x09; 'left'=0x25; 'up'=0x26; 'right'=0x27; 'down'=0x28;
  'ctrl'=0x11; 'shift'=0x10; 'alt'=0x12; 'del'=0x2E; 'f1'=0x70; 'f2'=0x71; 'f3'=0x72; 'f4'=0x73; 'home'=0x24; 'end'=0x23 }
function VK($s) { if ($names.ContainsKey($s)) { return [byte]$names[$s] }; if ($s.Length -eq 1) { return [byte][char]$s.ToUpper() }; return [byte]([Convert]::ToInt32($s, 16)) }
function KeyDown($vk) { $sc = [byte][U]::MapVirtualKey($vk, 0); $ext = 0; if ($vk -in 0x25,0x26,0x27,0x28,0x2E,0x24,0x23) { $ext = 1 }; [U]::keybd_event($vk, $sc, $ext, [UIntPtr]::Zero) }
function KeyUp($vk) { $sc = [byte][U]::MapVirtualKey($vk, 0); $ext = 0; if ($vk -in 0x25,0x26,0x27,0x28,0x2E,0x24,0x23) { $ext = 1 }; [U]::keybd_event($vk, $sc, (2 -bor $ext), [UIntPtr]::Zero) }
switch ($cmd) {
  'shot' {
    $bmp = New-Object System.Drawing.Bitmap 1920, 1080
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen(0, 0, 0, 0, $bmp.Size)
    $scale = 1.0; if ($a2) { $scale = [double]$a2 }
    if ($scale -ne 1.0) {
      $w = [int](1920 * $scale); $h = [int](1080 * $scale)
      $small = New-Object System.Drawing.Bitmap $w, $h
      $g2 = [System.Drawing.Graphics]::FromImage($small)
      $g2.InterpolationMode = 'HighQualityBicubic'
      $g2.DrawImage($bmp, 0, 0, $w, $h)
      $small.Save($a1, [System.Drawing.Imaging.ImageFormat]::Png)
    } else { $bmp.Save($a1, [System.Drawing.Imaging.ImageFormat]::Png) }
  }
  'click' { [U]::SetCursorPos([int]$a1, [int]$a2) | Out-Null; Start-Sleep -Milliseconds 60; [U]::mouse_event(2, 0, 0, 0, [UIntPtr]::Zero); Start-Sleep -Milliseconds 50; [U]::mouse_event(4, 0, 0, 0, [UIntPtr]::Zero) }
  'rclick' { [U]::SetCursorPos([int]$a1, [int]$a2) | Out-Null; Start-Sleep -Milliseconds 60; [U]::mouse_event(8, 0, 0, 0, [UIntPtr]::Zero); Start-Sleep -Milliseconds 50; [U]::mouse_event(16, 0, 0, 0, [UIntPtr]::Zero) }
  'move' { [U]::SetCursorPos([int]$a1, [int]$a2) | Out-Null }
  'drag' { [U]::SetCursorPos([int]$a1, [int]$a2) | Out-Null; Start-Sleep -Milliseconds 60; [U]::mouse_event(2, 0, 0, 0, [UIntPtr]::Zero);
           for ($i = 1; $i -le 20; $i++) { $x = [int]$a1 + ([int]$a3 - [int]$a1) * $i / 20; $y = [int]$a2 + ([int]$a4 - [int]$a2) * $i / 20; [U]::SetCursorPos([int]$x, [int]$y) | Out-Null; Start-Sleep -Milliseconds 15 }
           [U]::mouse_event(4, 0, 0, 0, [UIntPtr]::Zero) }
  'wheel' { [U]::SetCursorPos([int]$a1, [int]$a2) | Out-Null; Start-Sleep -Milliseconds 40; [U]::mouse_event(0x800, 0, 0, [int]$a3, [UIntPtr]::Zero) }
  'key' { $vk = VK $a1; $n = 1; if ($a2) { $n = [int]$a2 }; for ($i = 0; $i -lt $n; $i++) { KeyDown $vk; Start-Sleep -Milliseconds 40; KeyUp $vk; Start-Sleep -Milliseconds 40 } }
  'combo' { $m = VK $a1; $k = VK $a2; KeyDown $m; Start-Sleep -Milliseconds 40; KeyDown $k; Start-Sleep -Milliseconds 40; KeyUp $k; Start-Sleep -Milliseconds 30; KeyUp $m }
  'down' { KeyDown (VK $a1) }
  'up' { KeyUp (VK $a1) }
  'focus' { $p = Get-Process GeometryDash -ErrorAction SilentlyContinue | Select-Object -First 1; if ($p) { [U]::ShowWindow($p.MainWindowHandle, 9) | Out-Null; [U]::SetForegroundWindow($p.MainWindowHandle) | Out-Null; "focused $($p.Id)" } else { 'no GD' } }
}
