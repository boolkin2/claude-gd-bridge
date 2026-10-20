# Сборка claude.bridge (Release x64) и установка .geode в папку модов игры.
param([switch]$Configure, [switch]$NoInstall)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
& 'D:\VS\BuildTools\Common7\Tools\Launch-VsDevShell.ps1' -Arch amd64 -HostArch amd64 -SkipAutomaticLocation | Out-Null
$env:GEODE_SDK = 'D:\GDRetina\sdk\geode'
$env:GEODE_BINDINGS_REPO_PATH = 'D:\GDRetina\sdk\bindings'
$env:CPM_SOURCE_CACHE = 'D:\GDRetina\sdk\cpm-cache'
$build = Join-Path $root 'build'
if ($Configure -or -not (Test-Path "$build\build.ninja")) {
    cmake -S $root -B $build -G Ninja -DCMAKE_BUILD_TYPE=Release `
        -DGEODE_CLI=D:/GDRetina/sdk/cli/geode.exe -DGEODE_DONT_INSTALL_MODS=ON
    if ($LASTEXITCODE) { throw "configure failed" }
}
cmake --build $build --config Release
if ($LASTEXITCODE) { throw "build failed" }
if (-not $NoInstall) {
    $mods = 'C:\Program Files (x86)\Steam\steamapps\common\Geometry Dash\geode\mods'
    Copy-Item "$build\claude.bridge.geode" $mods -Force
    "installed -> $mods"
}
