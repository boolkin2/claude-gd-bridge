# Перезапуск GD напрямую (не через Steam) и ожидание моста claude.bridge (порт 47800).
# Выход — ТОЛЬКО штатный: команда моста game_exit (Geode сохраняет и закрывает игру). Принудительное
# завершение процесса Geode считает падением и показывает окно «игра упала» при следующем запуске,
# поэтому его здесь нет: если игра не закрылась сама — скрипт останавливается и просит закрыть её.
param([int]$Wait = 90)
$g = 'C:\Program Files (x86)\Steam\steamapps\common\Geometry Dash'
if (Get-Process GeometryDash -ErrorAction SilentlyContinue) {
    try {
        $c = New-Object Net.Sockets.TcpClient
        $c.Connect('127.0.0.1', 47800)
        $s = $c.GetStream()
        $b = [Text.Encoding]::UTF8.GetBytes('{"cmd":"game_exit"}' + "`n")
        $s.Write($b, 0, $b.Length)
        $s.ReadTimeout = 5000
        try { [void]$s.ReadByte() } catch {}
        $c.Close()
    } catch { "bridge unavailable for game_exit" }
    for ($i = 0; $i -lt 30 -and (Get-Process GeometryDash -ErrorAction SilentlyContinue); $i++) { Start-Sleep 1 }
    if (Get-Process GeometryDash -ErrorAction SilentlyContinue) {
        "GD did not exit cleanly (old mod without game_exit or game busy) - close it manually; not killing"
        exit 2
    }
    Start-Sleep 1
}
Start-Process "$g\GeometryDash.exe" -WorkingDirectory $g
for ($i = 0; $i -lt $Wait; $i++) {
    Start-Sleep 1
    try { $c = New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1', 47800); $c.Close(); "bridge up after $i s"; exit 0 } catch {}
}
"bridge NOT up after $Wait s"; exit 1
