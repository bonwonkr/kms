<# : batch portion
@echo off
chcp 65001 >nul
set "SC_SELF=%~f0"

rem ---- Administrator check: relaunch elevated (UAC) if needed ----
if /i "%~1"=="elevated" goto :run
fltmc >nul 2>&1
if not errorlevel 1 goto :run
echo Requesting administrator rights. Click "Yes" on the UAC window...
powershell -NoProfile -Command "try { Start-Process -FilePath $env:SC_SELF -ArgumentList 'elevated' -Verb RunAs -ErrorAction Stop } catch { exit 1 }"
if errorlevel 1 (
  echo.
  echo [!] Administrator rights were not granted.
  echo     Right-click this file and choose "Run as administrator".
  echo.
  pause
)
exit /b

:run
title Security check - Node.js / Java / Synology
echo Node.js / Java / Synology security check (read-only)
echo.
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
#  * 실행하면 관리자 권한을 자동으로 요청합니다(UAC 창에서 "예").
#  * 읽기 전용: 아무것도 설치·삭제·변경하지 않으며 네트워크 스캔도 하지 않습니다.
#    (Node.js 최신 버전 확인을 위해 nodejs.org 에 한 번 접속하며, 실패해도 점검은 계속됩니다.)
#  * 결과는 바탕화면에 "보안점검결과_컴퓨터이름_날짜.txt" 로 저장되고, 마지막에 화면에도 표시됩니다.
# =====================================================================

$ErrorActionPreference = 'SilentlyContinue'
$lines = New-Object System.Collections.Generic.List[string]
function Out-Line([string]$s = '') { $lines.Add($s) }
function Step([string]$s) { Write-Host ("  > " + $s) -ForegroundColor Cyan }

# ---------- 공문 기준 버전 ----------
# Node.js: 각 버전대별 "이 버전 이상"이면 조치 완료 (공문 표 기준)
$NodeFixed = @{ 22 = [version]'22.23.4'; 24 = [version]'24.22.1'; 26 = [version]'26.12.1' }

# ---------- 업데이트 안내 링크 ----------
$Link = [ordered]@{
    NodeDownload  = 'https://nodejs.org/ko/download'
    NodeReleases  = 'https://nodejs.org/en/about/previous-releases'
    JavaConsumer  = 'https://www.java.com/ko/download/'
    JavaJdk       = 'https://www.oracle.com/java/technologies/downloads/'
    GraalVM       = 'https://www.graalvm.org/downloads/'
    JavaEmudhra   = 'https://ops.java/emudhra  (공문에 기재된 주소)'
    SynoAdvisory  = 'https://www.synology.com/ko-kr/security/advisory/Synology_SA_26_13'
    SynoDownload  = 'https://www.synology.com/ko-kr/support/download'
}

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)

Write-Host ''
Write-Host ' 보안 권고 대상 소프트웨어 점검을 시작합니다.' -ForegroundColor Yellow
Write-Host ''

Out-Line '====================================================='
Out-Line ' 보안 권고 대상 소프트웨어 점검 결과'
Out-Line '====================================================='
Out-Line (' 점검 일시 : ' + (Get-Date -Format 'yyyy-MM-dd HH:mm'))
Out-Line (' 컴퓨터명  : ' + $env:COMPUTERNAME)
Out-Line (' 운영체제  : ' + (Get-CimInstance Win32_OperatingSystem).Caption)
Out-Line (' 관리자권한: ' + $(if ($isAdmin) { '예' } else { '아니오 (다른 사용자 폴더는 검사되지 않을 수 있음)' }))
Out-Line ''

# ---------- 0. Node.js 최신 버전 조회 (실패해도 계속) ----------
Step 'Node.js 최신 버전 정보 확인 중 (nodejs.org)...'
$nodeIndex = $null
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $nodeIndex = Invoke-RestMethod -Uri 'https://nodejs.org/dist/index.json' -TimeoutSec 10 -UseBasicParsing -ErrorAction Stop
} catch { $nodeIndex = $null }
function Get-NodeLatest([int]$major) {
    if (-not $nodeIndex) { return $null }
    $r = $nodeIndex | Where-Object { $_.version -like "v$major.*" } | Select-Object -First 1
    if ($r) { return $r.version.TrimStart('v') } else { return $null }
}
$nodeLtsLatest = $null
if ($nodeIndex) {
    $lts = $nodeIndex | Where-Object { $_.lts } | Select-Object -First 1
    if ($lts) { $nodeLtsLatest = "$($lts.version.TrimStart('v')) (LTS '$($lts.lts)')" }
}

# ---------- 1. 설치된 프로그램 목록(레지스트리) ----------
Step '설치 프로그램 목록 확인 중...'
$uninstallKeys = @(
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
    'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
    'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*'
)
$installed = Get-ItemProperty $uninstallKeys | Where-Object { $_.DisplayName } |
    Select-Object DisplayName, DisplayVersion, Publisher, InstallLocation

# ---------- 2. 실행 파일 검색 ----------
Step '드라이브 전체에서 node.exe / java.exe 검색 중 (수 분 걸릴 수 있습니다)...'
$drives = Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | ForEach-Object { $_.DeviceID + '\' }
$skip = '\\Windows\\|\\\$Recycle\.Bin\\|\\System Volume Information\\|\\WinSxS\\'
$found = foreach ($d in $drives) {
    # 드라이브 최상위의 Windows 등 시스템 폴더는 처음부터 제외하고 검색
    $tops = Get-ChildItem -Path $d -Directory -Force |
        Where-Object { $_.Name -notin @('Windows', '$Recycle.Bin', 'System Volume Information', 'Recovery') }
    foreach ($t in $tops) {
        Write-Host ("     검색: " + $t.FullName) -ForegroundColor DarkGray
        Get-ChildItem -Path $t.FullName -Recurse -Force -File -Include 'node.exe', 'java.exe' |
            Where-Object { $_.FullName -notmatch $skip }
    }
}

Step '결과 정리 중...'

# ---------- 판정 결과 모음 ----------
$verdicts = New-Object System.Collections.Generic.List[string]
$guides   = New-Object System.Collections.Generic.List[string]
function Add-Guide([string]$s) { if (-not $guides.Contains($s)) { $guides.Add($s) } }

# =========================== Node.js ===========================
Out-Line '[1] Node.js'
Out-Line '-----------------------------------------------------'
if ($nodeLtsLatest) { Out-Line ("  (참고) nodejs.org 기준 최신 LTS: {0}" -f $nodeLtsLatest) }
else { Out-Line '  (참고) nodejs.org 접속 실패 - 최신 버전은 아래 링크에서 직접 확인' }
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

    # 직접 설치한 Node.js 인지, 다른 프로그램에 포함된 것인지 구분
    $standalone = ($f.FullName -match '\\nodejs\\node\.exe$') -or ($f.FullName -match '\\nvm\\v?\d+\.\d+\.\d+\\node\.exe$')
    $kind = $(if ($standalone) { '직접 설치' } else { '다른 프로그램에 포함' })

    $ok = $false
    if (-not $v) {
        $msg = '버전 확인 불가 - 직접 확인 필요'
    } elseif ($NodeFixed.ContainsKey($v.Major)) {
        if ($v -lt $NodeFixed[$v.Major]) { $msg = "취약 버전 -> $($NodeFixed[$v.Major]) 이상으로 업데이트 필요" }
        else { $msg = '조치 버전 이상 (양호)'; $ok = $true }
    } else {
        $msg = '공문 표(22/24/26 버전대)에 없는 버전 - 지원 여부 확인 및 최신 버전 업데이트 검토'
    }
    Out-Line ("  {0}" -f $f.FullName)
    Out-Line ("     버전: {0}  [{1}]  => {2}" -f $(if ($v) { $v } else { $raw }), $kind, $msg)

    if (-not $ok) {
        $verdicts.Add("Node.js [$kind]: $($f.FullName) ($raw) - $msg")
        if ($standalone) {
            $latest = $(if ($v) { Get-NodeLatest $v.Major } else { $null })
            $hint = $(if ($latest) { " (같은 $($v.Major) 버전대 최신: $latest)" } else { '' })
            Out-Line ("     업데이트: {0}{1}" -f $Link.NodeDownload, $hint)
            Add-Guide ("Node.js(직접 설치) : 설치 파일을 받아 실행하면 덮어쓰기 업데이트됩니다 -> {0}" -f $Link.NodeDownload)
            Add-Guide ("                     버전대별 최신 버전 확인 -> {0}" -f $Link.NodeReleases)
        } else {
            Out-Line  '     업데이트: 이 node.exe 를 포함한 프로그램을 최신 버전으로 업데이트(또는 사용하지 않으면 삭제)'
            Add-Guide 'Node.js(프로그램 포함) : 경로에 표시된 프로그램을 업데이트하거나, 사용하지 않으면 제거'
        }
    }
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
    $ver = ''; $impl = ''; $gv = ''
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
    if ($isOracle) {
        $verdicts.Add("Java: $($f.FullName) ($ver, $impl) - $msg")
        if ($gv -or $f.FullName -match 'GraalVM') {
            Out-Line ("     업데이트: {0}" -f $Link.GraalVM)
            Add-Guide ("GraalVM            : 최신 버전 다운로드 -> {0}" -f $Link.GraalVM)
        } else {
            Out-Line ("     업데이트: {0}  /  {1}" -f $Link.JavaConsumer, $Link.JavaJdk)
            Add-Guide ("Oracle Java(JRE)   : 최신 버전 다운로드 -> {0}" -f $Link.JavaConsumer)
            Add-Guide ("Oracle Java(JDK)   : 최신 버전 다운로드 -> {0}" -f $Link.JavaJdk)
        }
        Add-Guide ("Oracle 추가 조치    : 업데이트 후 인증서 추가 조치 안내 -> {0}" -f $Link.JavaEmudhra)
    }
}
if ($javaHits -eq 0) { Out-Line '  java.exe 없음 => 미사용' }
Out-Line ''

# =========================== Synology ===========================
Out-Line '[3] Synology NAS 관련 단서 (NAS 보유 여부는 장비 현황으로 최종 확인)'
Out-Line '-----------------------------------------------------'
$syn = $installed | Where-Object { $_.DisplayName -match 'Synology' -or $_.Publisher -match 'Synology' }
if ($syn) {
    foreach ($p in $syn) { Out-Line ("  (설치목록) {0}  버전 {1}" -f $p.DisplayName, $p.DisplayVersion) }
    $verdicts.Add('Synology: PC에 Synology 프로그램 설치됨 - 연결하는 NAS가 있으면 NAS의 DSM 버전 확인 필요')
    Add-Guide ("Synology NAS       : 보안 권고(대상 DSM 버전) -> {0}" -f $Link.SynoAdvisory)
    Add-Guide ("                     DSM 업데이트는 NAS 관리 화면(제어판 > 업데이트 및 복원) 또는 -> {0}" -f $Link.SynoDownload)
} else { Out-Line '  Synology 프로그램 설치 없음' }
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
    foreach ($x in $verdicts) { Out-Line (' - ' + $x) }
}
Out-Line ''

if ($guides.Count -gt 0) {
    Out-Line '====================================================='
    Out-Line ' 업데이트 안내 (최신 버전 다운로드 링크)'
    Out-Line '====================================================='
    foreach ($g in $guides) { Out-Line (' ' + $g) }
    Out-Line ''
    Out-Line ' ※ 업데이트 후 이 파일을 다시 실행해 "양호"로 바뀌었는지 확인하세요.'
    Out-Line ''
}

# =========================== 저장 및 화면 표시 ===========================
$desk = [Environment]::GetFolderPath('Desktop')
$out = Join-Path $desk ("보안점검결과_{0}_{1}.txt" -f $env:COMPUTERNAME, (Get-Date -Format 'yyyyMMdd_HHmm'))
$lines | Out-File -FilePath $out -Encoding utf8

Clear-Host
foreach ($l in $lines) {
    if     ($l -match '취약 버전|공문 대상|확인 필요|업데이트 필요') { Write-Host $l -ForegroundColor Red }
    elseif ($l -match '양호|미사용|없음')                         { Write-Host $l -ForegroundColor Green }
    elseif ($l -match '^ ?업데이트:|https?://')                  { Write-Host $l -ForegroundColor Yellow }
    else                                                        { Write-Host $l }
}
Write-Host ''
Write-Host ("결과 파일 저장 위치: {0}" -f $out) -ForegroundColor Green
