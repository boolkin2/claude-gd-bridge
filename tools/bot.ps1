# Бот-проверка лайаута: жмёт кнопку плейтеста редактора и воспроизводит расписание
# кликов генератора по реальному времени. Отсчёт — от кадра, где исчез интерфейс
# редактора (пиксель зелёной кнопки), конец/смерть — когда интерфейс вернулся.
# Лог — bot_log.json: задержка старта, время смерти (в игровом времени), события.
param([double]$Offset = 0.0, [double]$TEnd = 400.0, [int]$ClickX = 116, [int]$ClickY = 388,
      [string]$Inputs = "", [double]$TStart = 0.0, [int]$PX = 1640, [int]$PY = 830)
$sp = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Inputs) { $Inputs = Join-Path $sp '..\out\retina_inputs.json' }
Add-Type @"
using System; using System.Diagnostics; using System.Runtime.InteropServices; using System.Threading; using System.Globalization;
public static class Bot {
  [DllImport("user32.dll")] static extern void keybd_event(byte vk, byte scan, uint f, UIntPtr e);
  [DllImport("user32.dll")] static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] static extern void mouse_event(uint f, uint dx, uint dy, int d, UIntPtr e);
  [DllImport("user32.dll")] static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] static extern IntPtr GetDC(IntPtr h);
  [DllImport("gdi32.dll")] static extern uint GetPixel(IntPtr dc, int x, int y);
  [DllImport("winmm.dll")] static extern uint timeBeginPeriod(uint p);
  static IntPtr dc; static int px, py;
  static bool EditorUI() {
    uint c = GetPixel(dc, px, py);
    int r = (int)(c & 0xFF), g = (int)((c >> 8) & 0xFF), b = (int)((c >> 16) & 0xFF);
    return Math.Abs(r - 122) < 30 && Math.Abs(g - 222) < 30 && Math.Abs(b - 45) < 30;
  }
  static string F(double v) { return v.ToString("F4", CultureInfo.InvariantCulture); }
  public static string Run(double[] ts, int[] st, double offset, double tEnd, int cx, int cy, int ppx, int ppy) {
    SetProcessDPIAware(); timeBeginPeriod(1); px = ppx; py = ppy; dc = GetDC(IntPtr.Zero);
    Thread.CurrentThread.Priority = ThreadPriority.Highest;
    if (!EditorUI()) return "{\"error\":\"editor UI not visible\"}";
    SetCursorPos(cx, cy); Thread.Sleep(120);
    var sw = Stopwatch.StartNew();
    mouse_event(2, 0, 0, 0, UIntPtr.Zero); Thread.Sleep(40); mouse_event(4, 0, 0, 0, UIntPtr.Zero);
    double tUp = sw.Elapsed.TotalSeconds;
    while (EditorUI()) { if (sw.Elapsed.TotalSeconds - tUp > 3) return "{\"error\":\"playtest did not start\"}"; }
    double t0 = sw.Elapsed.TotalSeconds;
    SetCursorPos(cx + 600, cy + 500);
    double maxLate = 0; int n = 0; bool down = false; double death = -1; double lastPoll = 0;
    for (int i = 0; i < ts.Length && death < 0; i++) {
      if (ts[i] > tEnd) break;
      double target = t0 + offset + ts[i];
      while (sw.Elapsed.TotalSeconds < target - 0.004) {
        double now = sw.Elapsed.TotalSeconds;
        if (now - lastPoll > 0.03) { lastPoll = now; if (EditorUI()) { death = now - t0 - offset; break; } }
        Thread.Sleep(1);
      }
      if (death >= 0) break;
      while (sw.Elapsed.TotalSeconds < target) { }
      bool want = st[i] == 1;
      if (want != down) { keybd_event(0x20, 0x39, want ? 0u : 2u, UIntPtr.Zero); down = want; n++; }
      double late = sw.Elapsed.TotalSeconds - target; if (late > maxLate) maxLate = late;
    }
    if (down) keybd_event(0x20, 0x39, 2u, UIntPtr.Zero);
    // ещё немного следим: жив ли к концу
    if (death < 0) {
      double until = sw.Elapsed.TotalSeconds + 0.3;
      while (sw.Elapsed.TotalSeconds < until) { if (EditorUI()) { death = sw.Elapsed.TotalSeconds - t0 - offset; break; } Thread.Sleep(5); }
    }
    return "{\"start_latency\":" + F(t0 - tUp) + ",\"events\":" + n + ",\"max_late_ms\":" + F(maxLate * 1000) +
           ",\"death\":" + F(death) + ",\"t_run\":" + F(sw.Elapsed.TotalSeconds - t0) + "}";
  }
}
"@
$j = Get-Content $Inputs -Raw | ConvertFrom-Json
$ts = New-Object System.Collections.Generic.List[double]; $st = New-Object System.Collections.Generic.List[int]
foreach ($e in $j.inputs) { if ([double]$e[0] -ge $TStart) { $ts.Add([double]$e[0] - $TStart); $st.Add([int]$e[1]) } }
$r = [Bot]::Run($ts.ToArray(), $st.ToArray(), $Offset, $TEnd - $TStart, $ClickX, $ClickY, $PX, $PY)
$r | Set-Content (Join-Path $sp '..\out\bot_log.json')
$r
