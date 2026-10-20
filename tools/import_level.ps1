# Импорт .gdlvl через кнопку «Import» в «Моих уровнях» (экран уже открыт).
param([Parameter(Mandatory = $true)][string]$Path)
$sp = Split-Path -Parent $MyInvocation.MyCommand.Path
$ui = Join-Path $sp 'ui.ps1'
Add-Type @"
using System; using System.Runtime.InteropServices; using System.Text;
public static class WIN {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc f, IntPtr l);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr h);
  public static IntPtr Find(string title) {
    IntPtr found = IntPtr.Zero;
    EnumWindows((h, l) => { var sb = new StringBuilder(256); GetWindowText(h, sb, 256);
      if (IsWindowVisible(h) && sb.ToString() == title) { found = h; return false; } return true; }, IntPtr.Zero);
    return found;
  }
}
"@
& $ui click 120 820
$h = [IntPtr]::Zero
for ($i = 0; $i -lt 40 -and $h -eq [IntPtr]::Zero; $i++) { Start-Sleep -Milliseconds 150; $h = [WIN]::Find('Import Levels') }
if ($h -eq [IntPtr]::Zero) { 'no dialog'; exit 1 }
[WIN]::BringWindowToTop($h) | Out-Null; [WIN]::SetForegroundWindow($h) | Out-Null
Start-Sleep -Milliseconds 400
Set-Clipboard -Value $Path
& $ui click 470 472; Start-Sleep -Milliseconds 300
& $ui combo ctrl a; & $ui combo ctrl v; Start-Sleep -Milliseconds 300
& $ui key enter
for ($i = 0; $i -lt 40; $i++) { Start-Sleep -Milliseconds 150; if ([WIN]::Find('Import Levels') -eq [IntPtr]::Zero) { 'imported'; exit 0 } }
'dialog still open'
