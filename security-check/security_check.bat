<# : batch portion
@echo off
chcp 65001 >nul
echo Node.js / Java / Synology security check (read-only)
echo.
set "SC_SELF=%~f0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-Expression ([IO.File]::ReadAllText($env:SC_SELF, [Text.Encoding]::UTF8))"
echo.
pause
exit /b
#>
# =====================================================================
#  보안 권고(2026.10.) 대상 소프트웨어 점검 스크립트
#   - Node.js (CVE-2026-105482 외 3건)
#   - Oracle Java / GraalVM (eMudhra CA 인증서 신뢰 관련 취약점)
#   - Synology 관련 프로그램 / 연결된 네트워크 드라이브 (NAS 단서 확인용)
#
#  * 읽기 전용: 아무것도 설치·삭제·변경하지 않으며 네트워크 스캔도 하지 않습니다.
#  * 결과는 바탕화면에 "보안점검결과_컴퓨터이름_날짜.txt" 로 저장됩니다.
#  * 관리자 권한으로 실행하면 다른 사용자 폴더까지 검사합니다.
# =====================================================================

$ErrorActionPreference = 'SilentlyContinue'
$lines = New-Object System.Collections.Generic.List[string]
function Out-Line([string]$s = '') { Write-Host $s; $lines.Add($s) }

# ---------- 공문 기준 버전 ----------
# Node.js: 각 버전대별 "이 버전 이상"이면 조치 완료 (공문 표 기준)
$NodeFixed = @{ 22 = [version]'22.23.4'; 24 = [version]'24.22.1'; 26 = [version]'26.12.1' }

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)

Out-Line '====================================================='
Out-Line ' 보안 권고 대상 소프트웨어 점검 결과'
Out-Line '====================================================='
Out-Line (' 점검 일시 : ' + (Get-Date -Format 'yyyy-MM-dd HH:mm'))
Out-Line (' 컴퓨터명  : ' + $env:COMPUTERNAME)
Out-Line (' 운영체제  : ' + (Get-CimInstance Win32_OperatingSystem).Caption)
Out-Line (' 관리자권한: ' + $(if ($isAdmin) { '예' } else { '아니오 (다른 사용자 폴더는 검사되지 않을 수 있음)' }))
Out-Line ''

# ---------- 1. 설치된 프로그램 목록(레지스트리) ----------
$uninstallKeys = @(
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
    'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
    'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*'
)
$installed = Get-ItemProperty $uninstallKeys | Where-Object { $_.DisplayName } |
    Select-Object DisplayName, DisplayVersion, Publisher, InstallLocation

# ---------- 2. 실행 파일 검색 ----------
Write-Host '파일 검색 중입니다. 수 분 걸릴 수 있습니다...' -ForegroundColor Yellow
$drives = Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | ForEach-Object { $_.DeviceID + '\' }
$skip = '\\Windows\\|\\\$Recycle\.Bin\\|\\System Volume Information\\|\\WinSxS\\'
$found = foreach ($d in $drives) {
    # 드라이브 최상위의 Windows 등 시스템 폴더는 처음부터 제외하고 검색
    $tops = Get-ChildItem -Path $d -Directory -Force |
        Where-Object { $_.Name -notin @('Windows', '$Recycle.Bin', 'System Volume Information', 'Recovery') }
    foreach ($t in $tops) {
        Get-ChildItem -Path $t.FullName -Recurse -Force -File -Include 'node.exe', 'java.exe' |
            Where-Object { $_.FullName -notmatch $skip }
    }
}

# ---------- 판정 결과 모음 ----------
$verdicts = New-Object System.Collections.Generic.List[string]

# =========================== Node.js ===========================
Out-Line '[1] Node.js'
Out-Line '-----------------------------------------------------'
$nodeHits = 0
foreach ($p in $installed | Where-Object { $_.DisplayName -match 'Node\.js' }) {
    Out-Line ("  (설치목록) {0}  버전 {1}" -f $p.DisplayName, $p.DisplayVersion)
}
foreach ($f in $found | Where-Object { $_.Name -eq 'node.exe' }) {
    $nodeHits++
    $raw = $f.VersionInfo.ProductVersion
    if (-not $raw) { $raw = $f.VersionInfo.FileVersion }
    $v = $null
    if ($raw -match '(\d+)\.(\d+)\.(\d+)') { $v = [version]"$($Matches[1]).$($Matches[2]).$($Matches[3])" }
    if (-not $v) {
        $msg = '버전 확인 불가 - 직접 확인 필요'
    } elseif ($NodeFixed.ContainsKey($v.Major)) {
        if ($v -lt $NodeFixed[$v.Major]) { $msg = "취약 버전 -> $($NodeFixed[$v.Major]) 이상으로 업데이트 필요" }
        else { $msg = '조치 버전 이상 (양호)' }
    } else {
        $msg = '공문 표(22/24/26 버전대)에 없는 버전 - 지원 여부 확인 및 최신 버전 업데이트 검토'
    }
    Out-Line ("  {0}" -f $f.FullName)
    Out-Line ("     버전: {0}  => {1}" -f $(if ($v) { $v } else { $raw }), $msg)
    if ($msg -notmatch '양호') { $verdicts.Add("Node.js: $($f.FullName) ($raw) - $msg") }
}
if ($nodeHits -eq 0) { Out-Line '  node.exe 없음 => 미사용' }
Out-Line ''

# =========================== Java / GraalVM ===========================
Out-Line '[2] Java / GraalVM'
Out-Line '-----------------------------------------------------'
$javaHits = 0
foreach ($p in $installed | Where-Object { $_.DisplayName -match 'Java|JDK|JRE|GraalVM|OpenJDK' }) {
    Out-Line ("  (설치목록) {0}  버전 {1}  제조사 {2}" -f $p.DisplayName, $p.DisplayVersion, $p.Publisher)
}
foreach ($f in $found | Where-Object { $_.Name -eq 'java.exe' }) {
    # javapath 폴더의 java.exe 는 Oracle Java 설치 시 생기는 실행 링크(실제 설치 위치는 별도로 표시됨)
    if ($f.FullName -match 'Common Files\\Oracle\\Java\\javapath') { $note = ' (Oracle Java 실행 링크)' } else { $note = '' }
    $javaHits++
    $root = Split-Path (Split-Path $f.FullName -Parent) -Parent
    $release = Join-Path $root 'release'
    $ver = ''; $impl = ''
    if (Test-Path $release) {
        $rel = Get-Content $release
        $ver  = ($rel | Where-Object { $_ -match '^JAVA_VERSION=' })  -replace '^JAVA_VERSION="?([^"]*)"?', '$1'
        $impl = ($rel | Where-Object { $_ -match '^IMPLEMENTOR=' })   -replace '^IMPLEMENTOR="?([^"]*)"?', '$1'
        $gv   = ($rel | Where-Object { $_ -match '^GRAALVM_VERSION=' }) -replace '^GRAALVM_VERSION="?([^"]*)"?', '$1'
        if ($gv) { $impl = "$impl / GraalVM $gv" }
    }
    if (-not $ver)  { $ver  = $f.VersionInfo.ProductVersion }
    if (-not $impl) { $impl = $f.VersionInfo.CompanyName }
    $isOracle = ($impl -match 'Oracle') -or ($f.FullName -match 'Oracle|GraalVM')
    if ($isOracle) { $msg = 'Oracle Java/GraalVM => 공문 대상, 최신 버전 업데이트 및 버전 확인 필요' }
    else           { $msg = 'Oracle 제품 아님(공문 직접 대상 아님) - 참고' }
    Out-Line ("  {0}{1}" -f $f.FullName, $note)
    Out-Line ("     버전: {0}  제조사: {1}  => {2}" -f $ver, $impl, $msg)
    if ($isOracle) { $verdicts.Add("Java: $($f.FullName) ($ver, $impl) - $msg") }
}
if ($javaHits -eq 0) { Out-Line '  java.exe 없음 => 미사용' }
Out-Line ''

# =========================== Synology ===========================
Out-Line '[3] Synology NAS 관련 단서 (NAS 보유 여부는 장비 현황으로 최종 확인)'
Out-Line '-----------------------------------------------------'
$syn = $installed | Where-Object { $_.DisplayName -match 'Synology' -or $_.Publisher -match 'Synology' }
if ($syn) { foreach ($p in $syn) { Out-Line ("  (설치목록) {0}  버전 {1}" -f $p.DisplayName, $p.DisplayVersion) }
            $verdicts.Add('Synology: PC에 Synology 프로그램 설치됨 - NAS 보유 여부 확인 필요') }
else      { Out-Line '  Synology 프로그램 설치 없음' }
$maps = Get-CimInstance Win32_MappedLogicalDisk
if ($maps) {
    Out-Line '  연결된 네트워크 드라이브 (NAS일 수 있으니 장비 확인):'
    foreach ($m in $maps) { Out-Line ("     {0}  {1}" -f $m.DeviceID, $m.ProviderName) }
} else { Out-Line '  연결된 네트워크 드라이브 없음' }
Out-Line ''

# =========================== 요약 ===========================
Out-Line '====================================================='
Out-Line ' 요약'
Out-Line '====================================================='
if ($verdicts.Count -eq 0) {
    Out-Line ' 조치가 필요한 항목 없음 (Node.js / Oracle Java·GraalVM 미발견)'
} else {
    Out-Line ' 확인/조치가 필요한 항목:'
    foreach ($v in $verdicts) { Out-Line (' - ' + $v) }
}
Out-Line ''

$desk = [Environment]::GetFolderPath('Desktop')
$out = Join-Path $desk ("보안점검결과_{0}_{1}.txt" -f $env:COMPUTERNAME, (Get-Date -Format 'yyyyMMdd_HHmm'))
$lines | Out-File -FilePath $out -Encoding utf8
Write-Host "결과 파일: $out" -ForegroundColor Green
