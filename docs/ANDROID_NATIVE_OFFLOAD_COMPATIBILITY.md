# Android PRoot / native-offload compatibility fix

## Root-cause analysis

The failures are not specific to `apk`. `apk`, `wget`, `ls`, and `ldd` are not
registered native-offload handlers, yet the native-offload PRoot extension was
previously attached to every `execve` in both one-shot and persistent shells.
That matches the observed cross-binary, intermittent SIGBUS/SIGSEGV failures
and explains why replacing the Alpine RootFS did not fix them: the unstable
layer is the host PRoot/offload execution path, outside the RootFS.

Two recovery gaps amplified the issue:

1. Native offload was started and passed to every PRoot process
   unconditionally, so there was no clean standard-PRoot A/B baseline.
2. A persistent PRoot process death was reported as exit code `-1`; SIGBUS
   (`135`) and SIGSEGV (`139`) were neither diagnosed nor used to disable the
   failing path.

The exact low-level instruction or memory-alignment fault still requires a
reproduction trace on the affected ARM64 device. This change contains the
failure, makes standard PRoot the default, and adds enough diagnostics for that
follow-up without special-casing any executable.

## Behavior changes

- Native offload defaults to disabled and is absent from the PRoot command
  line and host socket unless explicitly enabled.
- RootFS Management exposes an experimental native-offload switch for A/B
  testing.
- Native-offload initialization failure safely keeps standard PRoot active.
- SIGBUS/SIGSEGV while offload is active persistently disables it, restarts a
  standard PRoot shell, and retries once.
- Logs include the executable, guest executable, offload state, device ABI,
  architecture, ELF interpreter, exit signal, and fallback result.
- PRoot-side debug logs record every `execve` path and whether it is actually
  offloaded. Failed socket offload or rewrite explicitly reports that the
  original PRoot `execve` continues.
- Debug builds use `com.openminis.app.dev` and can coexist with the official
  application.

## Modified files

- `deps/build_proot.sh`
- `deps/patches/0001-native-offload-fallback-diagnostics.patch`
- `deps/patches/0002-configurable-readelf.patch`
- `src/android/app/build.gradle.kts`
- `src/android/app/src/main/java/com/openminis/app/sandbox/PRootKernel.kt`
- `src/android/app/src/main/java/com/openminis/app/sandbox/PersistentShell.kt`
- `src/android/app/src/main/java/com/openminis/app/sandbox/ShellExecutor.kt`
- `src/android/app/src/main/java/com/openminis/app/sandbox/ExecutionCoordinator.kt`
- `src/android/app/src/main/java/com/openminis/app/ui/sandbox/RootfsManagementScreen.kt`
- `src/android/app/src/main/java/com/openminis/app/ui/sandbox/RootfsManagementViewModel.kt`
- `src/android/app/src/main/res/values/strings.xml`
- `src/android/app/src/main/res/values-zh/strings.xml`
- `src/android/app/src/androidTest/java/com/openminis/app/sandbox/PRootKernelInstrumentedTest.kt`
- `src/android/app/src/androidTest/java/com/openminis/app/sandbox/PRootCompatibilityInstrumentedTest.kt`
- `src/android/app/src/test/java/com/openminis/app/sandbox/PRootKernelCompatibilityTest.kt`

## Build

Prerequisites are JDK 17+, Android SDK 36, NDK r28+, CMake 3.22.1, GNU Make,
and the files described in `BUILDING.md`.

```bash
cp src/android/app/provider-customization.properties.example \
  src/android/app/provider-customization.properties
export ANDROID_NDK_HOME=/path/to/android-ndk-r28b
./deps/build_proot.sh clean
./scripts/prepare_android_sandbox.sh
cd src/android
./gradlew :app:assembleDebug
```

APK output:

```text
src/android/app/build/outputs/apk/debug/app-debug.apk
```

## Tests

Compile the device tests:

```bash
cd src/android
./gradlew :app:compileDebugAndroidTestKotlin
```

Run the ARM64 device/network regression test:

```bash
./gradlew :app:connectedDebugAndroidTest \
  -Pandroid.testInstrumentationRunnerArguments.class=com.openminis.app.sandbox.PRootCompatibilityInstrumentedTest
```

It verifies, in standard PRoot mode:

```sh
/bin/true
uname -m
apk --version
apk update
apk add git
git --version
```

For an A/B comparison, enable native offload in RootFS Management, repeat the
commands, and capture `PRootKernel`, `PersistentShell`, `ShellExecutor`,
`PRootStderr`, and `native_offload` logs.

## Remaining risks

- The precise native crash site has not been confirmed without the affected
  physical device and its logcat/native tombstone.
- Retrying a command after a signal can repeat partial side effects. The retry
  is limited to once, and only after SIGBUS/SIGSEGV while offload was active.
- Host-only offload commands are unavailable while offload is disabled; the
  experimental switch remains available for users who require them.
- The device regression requires network access and modifies the test RootFS by
  installing Git.
