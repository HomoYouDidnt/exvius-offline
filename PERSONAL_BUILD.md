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

## First-time setup (Windows)

Do this once. Everything goes in your copy of the fork, except the JDK, Python and your signing key.
Gradle and Chaquopy download themselves on the first build, so stay online for it.

1. **Get the fork.** In PowerShell, from the folder you want it in:

   ```powershell
   git clone -b qol https://github.com/HomoYouDidnt/exvius-offline.git
   cd exvius-offline
   ```

   Every path below is relative to this folder.

2. **JDK 11.** Install any JDK 11 (Eclipse Temurin 11 is a common one). A Java runtime bundled with an IDE
   isn't enough, because the build needs `javac`. `JAVA_HOME` is the JDK's folder, the one with `bin\javac.exe`.

3. **Python 3.10.** Install Python 3.10 next to any newer Python you have. Chaquopy checks that `python` is
   3.10, so put it first on the PATH in the window you build from:

   ```powershell
   $env:Path = 'C:\path\to\Python310;' + $env:Path
   python --version   # should say 3.10.x
   ```

4. **Android SDK parts.** The build needs platform 33 and build-tools 36.0.0. With the SDK's command-line tools
   (`Sdk\cmdline-tools\<version>\bin`):

   ```powershell
   sdkmanager.bat "platforms;android-33" "build-tools;36.0.0"
   ```

   `ANDROID_HOME` is the `Sdk` folder, usually `%LOCALAPPDATA%\Android\Sdk`.

5. **`tools\vendor\`.** This folder isn't in the repository. Make it and fill it:

   - `tools\vendor\apktool_3.0.3.jar`: the jar from Apktool's GitHub release v3.0.3.
   - `tools\vendor\apktool-framework\`: an empty folder. Apktool fills it on the first run.
   - `tools\vendor\frida-gadget-17.24.3-android-arm64.so`: from Frida's GitHub release 17.24.3, the file
     `frida-gadget-17.24.3-android-arm64.so.xz`, unpacked (7-Zip or WinRAR open `.xz`).
   - `tools\vendor\android-agent\`: frida-compile, installed with npm:

     ```powershell
     New-Item -ItemType Directory tools\vendor\android-agent | Out-Null
     Push-Location tools\vendor\android-agent
     npm init -y
     npm install frida-compile
     Pop-Location
     ```

     The original project doesn't record which frida-compile version it used. The scripts don't use the Frida
     APIs that changed in Frida 17, so the current version should work. If this step of the build fails, the
     error names the version problem.
   - No Python packages are needed here: the build only uses Python's standard library.

6. **The original game.** Put the FFBE Global v9.0.0 APK at
   `repository snapshots\FFBE-Global-v9.0.0-original.apk` and check it:

   ```powershell
   (Get-FileHash 'repository snapshots\FFBE-Global-v9.0.0-original.apk' -Algorithm SHA256).Hash
   ```

   It must be `955DEACFBE4B3D0CD04E2947EB005E310915BA98132D71216626BFB3554AD246`. Any other version won't work:
   the hooks, the offline server and the game data are all made for v9.0.0.

7. **Your signing key.** Make it once, keep it outside the repository, and back it up. Every later build must
   use it, or Android won't update the installed app:

   ```powershell
   & "$env:JAVA_HOME\bin\keytool.exe" -genkeypair -v -keystore $HOME\exvius-2.0.jks -alias exvius -keyalg RSA -keysize 4096 -validity 36500
   ```

   Never commit the `.jks` file or its password.

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
powershell -ExecutionPolicy Bypass -File source\exvius\build_personal.ps1 -KeyStore $HOME\exvius-2.0.jks -KeyAlias exvius
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

The published app keeps its own save; playing 2.0 afterwards never changes it.

Since v0.1.25 the published app runs a newer, native game engine whose source isn't in this repository.
Exvius 2.0 is built on the older engine that is here. The newer engine writes the same save fields, so the
copied save should load, but that hasn't been tried. If it doesn't load, nothing is lost: the published app
still has the original save.
