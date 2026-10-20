# Из редактора (или из «Моих уровней») — в редактор уровня, стоящего первым в списке.
# -FromEditor: сначала выйти из текущего редактора без сохранения.
# -Import <файл>: перед открытием импортировать .gdlvl (он встанет первым).
param([switch]$FromEditor, [string]$Import = "")
$sp = Split-Path -Parent $MyInvocation.MyCommand.Path
$ui = Join-Path $sp 'ui.ps1'
if ($FromEditor) {
  & $ui click 1818 96; Start-Sleep -Seconds 1
  & $ui click 960 824; Start-Sleep -Milliseconds 900
  & $ui click 1074 682; Start-Sleep -Seconds 2
  & $ui click 116 110; Start-Sleep -Seconds 2
}
if ($Import) { & (Join-Path $sp 'import_level.ps1') -Path $Import | Out-Null; Start-Sleep -Seconds 1 }
for ($i = 0; $i -lt 15; $i++) { & $ui wheel 960 560 120; Start-Sleep -Milliseconds 50 }
Start-Sleep -Milliseconds 500
& $ui click 1406 322; Start-Sleep -Seconds 2
& $ui click 642 634; Start-Sleep -Seconds 4
