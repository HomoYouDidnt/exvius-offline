# Personal build (Exvius 2.0)

This builds the qol branch as its own app, signed with your own key. It has its own app id
(`com.exvius.offline.qol`), so Android installs it **next to** the published Exvius Offline instead of
over it. The published app, its save and its game data stay exactly as they are.

What's different from the published build:

- Home screen names: **Exvius 2.0** (game) and **Exvius 2.0 Settings** (speed, summon tweaks, save export/import).
- Version 2.0 (version code 20000).
- Game data still comes from the published data packs. The published app's own APK updates are never offered
  to this build.
- It keeps its own save. Nothing is shared with the published app unless you copy the save across (below).

## Build (Windows, on the PC)

You need the same tools as a normal build (see `source/README.md`): Java 11, Python 3.10, Node.js, Android SDK
platform 33 with build-tools 36.0.0, and `tools/vendor/` (apktool 3.0.3 and its framework folder, Frida Gadget
17.24.3 arm64, frida-compile under `tools/vendor/android-agent`, the vendored Python). Put the original Global
v9.0.0 APK at `repository snapshots/FFBE-Global-v9.0.0-original.apk` (SHA-256 in `source/README.md`).

Neither `tools/vendor/` nor the original APK is in this repository: you gather both yourself. Python 3.10 has to be
the `python` on your PATH while building, because Chaquopy checks its version. You also need a signing key; `keytool`
from the JDK makes one.

```powershell
$env:JAVA_HOME = 'C:\path\to\jdk-11'
$env:ANDROID_HOME = 'C:\path\to\Android\Sdk'
$env:EXVIUS_KEYSTORE_PASSWORD = 'your key password'
powershell -ExecutionPolicy Bypass -File source\exvius\build_personal.ps1 -KeyStore C:\path\to\your.jks -KeyAlias youralias
```

The APK lands at `source\build\personal\exvius-2.0.apk`. The script decodes the original APK fresh every time,
so an older build folder can't leak the published app id into this one.

Use the same key for every later build. A build signed with another key can't update this one.
Optional parameters: `-Package`, `-Label`, `-Version`, `-VersionCode` (keep the code at 9071 or higher and raise
it for each new build you install over an older one).

## Install

Copy `exvius-2.0.apk` to the phone and open it (allow installs from that app if Android asks). Open
**Exvius 2.0** once with Wi-Fi: it downloads its own copy of the game data, about 17.8 GB, so the phone needs
about 21 GB free.

## Copy the save from the published app (one time, PC + USB)

The published app has no export button, but it is a debuggable build, so `adb` can read its save.

1. On the phone: turn on Developer options and USB debugging, plug into the PC, accept the prompt.
2. Close Exvius Offline fully (swipe it away), so its save isn't mid-write.
3. On the PC, with Android platform-tools:

   ```powershell
   adb shell "run-as com.exvius.offline.test cat files/exvius/state/campaign.json > /sdcard/Download/campaign.json"
   ```

   Keep the quotes: the redirect runs on the phone, so the file isn't re-encoded by PowerShell.
4. On the phone: make sure Exvius 2.0 isn't running, open **Exvius 2.0 Settings**, tap
   **Import save from a file** and pick `Download/campaign.json`. Any 2.0 save already there is kept in its
   backups folder first.

The published app keeps its own save; playing 2.0 afterwards never changes it. Both apps use the same save
format, so the copied save needs no conversion.
