# Снимок окна GD без вывода на передний план и без нажатий (PrintWindow, PW_RENDERFULLCONTENT).
#   winshot.ps1 <out.png> [scale=0.5]
param([string]$Out, [double]$Scale = 0.5)
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System; using System.Runtime.InteropServices;
public static class WS {
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint flags);
  public struct RECT { public int L, T, R, B; }
}
"@
[WS]::SetProcessDPIAware() | Out-Null
$p = Get-Process GeometryDash -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $p) { "no GD window"; exit 1 }
$h = $p.MainWindowHandle
$r = New-Object WS+RECT
[WS]::GetClientRect($h, [ref]$r) | Out-Null
$w = $r.R - $r.L; $hh = $r.B - $r.T
$bmp = New-Object System.Drawing.Bitmap $w, $hh
$g = [System.Drawing.Graphics]::FromImage($bmp)
$dc = $g.GetHdc()
[WS]::PrintWindow($h, $dc, 3) | Out-Null   # 1 = client only, 2 = full content (DX/GL)
$g.ReleaseHdc($dc); $g.Dispose()
$sw = [int]($w * $Scale); $sh = [int]($hh * $Scale)
$small = New-Object System.Drawing.Bitmap $bmp, $sw, $sh
$small.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
"$Out ${sw}x${sh}"
