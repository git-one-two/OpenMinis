# OpenMinis 1.14 Harmony / Windows Dev Build

## Baseline

- Upstream: `OpenMinis/OpenMinis`
- Upstream baseline commit: `b4c0661d5631ebab4d1a2e6f3fd4c805d4030a6c`
- Version: Android `1.14` / `versionCode 28`
- Working branch: `upgrade/openminis-1.14-harmony`

## Dev app identity

The debug build intentionally stays separate from the official app:

- applicationId: `com.openminis.app.dev`
- versionName: `1.14-dev`
- versionCode: `28`

This preserves the package identity used by the previous side-loaded dev build and allows the official OpenMinis app to coexist.

## What was NOT carried forward from the old compatibility branch

The old branch `fix/android-proot-native-offload` contained four compatibility commits from the 2026-08 investigation.

Do not blindly cherry-pick them onto 1.14.

OpenMinis 1.14 already contains substantially newer Android sandbox fixes, including:

- external PRoot loaders under nativeLibraryDir
- `PROOT_LOADER` / `PROOT_LOADER_32`
- sandbox artifact verification
- seccomp self-healing with one retry under `PROOT_NO_SECCOMP=1`
- explicit handling/diagnostics for early SIGBUS / SIGSEGV / SIGSYS failures
- newer PRoot/native-offload code

The old "disable native-offload by default" behavior is intentionally not restored because 1.14 depends on the newer native-offload path for additional Android capabilities.

## Compatibility changes retained on top of 1.14

### 1. Separate dev package

`src/android/app/build.gradle.kts`

Debug builds add:

- `applicationIdSuffix = ".dev"`
- `versionNameSuffix = "-dev"`

### 2. Windows Git Bash / Android NDK support

`deps/build_proot.sh`

The build script additionally supports:

- MINGW / MSYS / CYGWIN hosts
- Windows NDK toolchain path `windows-x86_64`
- NDK `.cmd` compiler wrappers and `.exe` LLVM tools
- Android Studio's normal Windows SDK/NDK location
- a no-space shell path for Windows GNU Make

### 3. Configurable readelf

`deps/patches/0001-configurable-readelf.patch`

The pinned PRoot GNUmakefile invokes `readelf` directly. On Windows Git Bash that tool is not guaranteed to exist on PATH, so the build patches it to use `$(READELF)` and points that at the NDK's `llvm-readelf.exe`.

### 4. Unix line endings for guest assets

`.gitattributes`

The following are forced to LF on Windows checkouts:

- `*.sh`
- `src/android/app/src/main/assets/default_mount/**`

This prevents CRLF from leaking into files executed inside the Alpine guest.

## CI validation

The branch includes `.github/workflows/build-android-dev.yml`.

The 1.14 dev build has completed successfully in GitHub Actions, including:

- submodules
- PRoot/sandbox build
- rclone Android build
- Gradle `:app:assembleDebug`
- APK identity inspection

The CI artifact uses an ephemeral GitHub runner debug key and is only a build-validation artifact.

## Local signing

The installable personal dev APK must be re-signed locally with the existing Android debug keystore so it keeps the same signing identity as the long-lived dev installation.

Never commit the keystore or its private key to this repository.

Expected signing certificate SHA-256 (verified against the original `OpenMinis-final.apk` / `0.20-preview-dev`):

`87:58:60:30:A1:61:4B:E8:8A:5F:66:F3:A0:9C:4F:47:67:82:FB:75:5F:6A:F8:1F:22:87:12:6D:12:CF:5D:60`

Before installing an upgrade, verify both:

1. package name matches `com.openminis.app.dev`
2. installed app certificate matches the expected SHA-256 certificate

Only then perform an in-place update.


## Agent sandbox self-healing (post-1.14 field fix)

A real HarmonyOS long-running Agent task exposed a gap that simple shell smoke tests did not catch: the Agent's default `FreshProcessShell` can lose the PRoot host process to SIGSEGV/SIGBUS after startup, while the upstream 1.14 seccomp fallback only covers early, no-output crashes.

The custom branch therefore adds Agent-scoped runtime recovery:

1. Distinguish a PRoot crash from a guest program returning the same numeric exit code using the fresh-process status file.
2. Run a side-effect-free, 5-second `apk --version` recovery probe.
3. Prefer `PROOT_NO_SECCOMP=1` when that alone is sufficient.
4. If PRoot still dies, disable native-offload for Agent shell execution only and keep no-seccomp enabled.
5. Persist the working compatibility mode for later Agent commands and app restarts.
6. Do not automatically replay the interrupted user command after a late crash, because it may already have caused side effects; return a recovery notice so the Agent retries once on the now-stable sandbox.

Terminal and other native-offload integrations remain on the normal OpenMinis 1.14 path.
