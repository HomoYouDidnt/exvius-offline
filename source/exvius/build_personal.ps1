# Personal build: a separate app beside the published Exvius Offline, signed with your own key.
# It has its own app id, so Android installs it next to the published app instead of over it,
# and the published app's save and game data are never touched. Game data still comes from the
# published data packs; app updates for the published APK are not offered to this build.
param(
    [Parameter(Mandatory = $true)][string]$KeyStore,
    [Parameter(Mandatory = $true)][string]$KeyAlias,
    [string]$Package = 'com.exvius.offline.qol',
    [string]$Label = 'Exvius 2.0',
    [string]$Version = '2.0',
    [int]$VersionCode = 20000
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location -LiteralPath $taskRoot
if (-not $env:JAVA_HOME -or -not $env:ANDROID_HOME) { throw 'Set JAVA_HOME and ANDROID_HOME first.' }
if (-not $env:EXVIUS_KEYSTORE_PASSWORD) { throw 'Set EXVIUS_KEYSTORE_PASSWORD to your signing-key password.' }
if (-not (Test-Path -LiteralPath $KeyStore)) { throw "Signing key not found: $KeyStore" }
# Must stay at or above the data manifest's minAppVersionCode, or the shared game data is refused.
if ($VersionCode -lt 9071) { throw 'VersionCode must be 9071 or higher.' }
New-Item -ItemType Directory -Path logs, source/build/personal -Force | Out-Null
Start-Transcript -Path logs/personal-build.log -Append | Out-Null
try {
    $env:PYTHONUTF8 = '1'
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $env:FFBE_DATA = Join-Path $taskRoot 'data'
    $env:PYTHONPATH = (Join-Path $taskRoot 'tools/vendor/python') + ';' + (Join-Path $taskRoot 'source/exvius') + ';' + (Join-Path $taskRoot 'source/server')
    $env:Path = (Join-Path $env:JAVA_HOME 'bin') + ';' + $env:Path
    $taskBuildTools = Join-Path $env:ANDROID_HOME 'build-tools/36.0.0'
    node source/exvius/test_android_display.js
    if ($LASTEXITCODE -ne 0) { throw 'Display checks failed' }
    node source/exvius/test_home_carousel.js
    if ($LASTEXITCODE -ne 0) { throw 'Home checks failed' }
    node source/exvius/test_summon_art.js
    if ($LASTEXITCODE -ne 0) { throw 'Summon banner checks failed' }
    # Start from a fresh decode of the verified original APK, so nothing from a published build carries over.
    $original = 'repository snapshots/FFBE-Global-v9.0.0-original.apk'
    if (-not (Test-Path -LiteralPath $original)) { throw "Original APK not found: $original" }
    if (Test-Path -LiteralPath source/build/android/client) { Remove-Item -LiteralPath source/build/android/client -Recurse -Force }
    java -jar tools/vendor/apktool_3.0.3.jar d --no-src -p tools/vendor/apktool-framework -o source/build/android/client $original
    if ($LASTEXITCODE -ne 0) { throw 'APK decoding failed' }
    # The offline changes edit the original Java code (smali), which the resource-only decode above
    # leaves out. Decode it once from the same verified APK; later builds reuse it.
    $decodedCode = 'source/build/android/decoded-code'
    if (-not (Test-Path -LiteralPath "$decodedCode/smali/com/square_enix/android_googleplay/FFBEWW/GooglePlayLapis.smali")) {
        java -jar tools/vendor/apktool_3.0.3.jar d -f --no-res -p tools/vendor/apktool-framework -o $decodedCode $original
        if ($LASTEXITCODE -ne 0) { throw 'Java code decoding failed' }
    }
    java -cp source/memorial/android/gradle/wrapper/gradle-wrapper.jar org.gradle.wrapper.GradleWrapperMain -p source/memorial/android --no-daemon assembleDebug
    if ($LASTEXITCODE -ne 0) { throw 'Android runtime build failed' }
    python source/exvius/android_build.py --local-engine --speed 1 --package $Package --label $Label --release-version $Version --release-code $VersionCode
    if ($LASTEXITCODE -ne 0) { throw 'Original client integration failed' }
    node tools/vendor/android-agent/node_modules/frida-compile/dist/cli.js source/exvius/android_test.js -o source/build/android/android_test.bundle.js -S -c -T none
    if ($LASTEXITCODE -ne 0) { throw 'Native integration compilation failed' }
    Copy-Item -LiteralPath source/build/android/android_test.bundle.js -Destination source/build/android/client/lib/arm64-v8a/libexviustest.js.so
    $taskUnsigned = 'source/build/personal/personal-unsigned.apk'
    $taskAligned = 'source/build/personal/personal-aligned.apk'
    $taskFinal = "source/build/personal/exvius-$Version.apk"
    java -jar tools/vendor/apktool_3.0.3.jar b source/build/android/client -p tools/vendor/apktool-framework -o $taskUnsigned
    if ($LASTEXITCODE -ne 0) { throw 'APK packaging failed' }
    & "$taskBuildTools/zipalign.exe" -P 16 -f 4 $taskUnsigned $taskAligned
    if ($LASTEXITCODE -ne 0) { throw 'APK alignment failed' }
    & "$taskBuildTools/apksigner.bat" sign --ks $KeyStore --ks-key-alias $KeyAlias --ks-pass env:EXVIUS_KEYSTORE_PASSWORD --out $taskFinal $taskAligned
    if ($LASTEXITCODE -ne 0) { throw 'APK signing failed' }
    & "$taskBuildTools/apksigner.bat" verify $taskFinal
    if ($LASTEXITCODE -ne 0) { throw 'APK signature check failed' }
    Remove-Item -LiteralPath $taskUnsigned, $taskAligned -Force
    Write-Host "Built $taskFinal ($Package, $Label $Version). Keep the same key for every later build."
} finally {
    Stop-Transcript | Out-Null
}
