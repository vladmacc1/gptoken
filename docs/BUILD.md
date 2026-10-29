# Windows release build

Build on Windows x64 using **CPython 3.14.10**, NSIS 3.13 and the pinned Python
build dependencies. These tools are free. No code-signing certificate is included.
The source license remains proprietary; build instructions do not grant a
separate right to distribute modified builds.

CI pins Python 3.14.10 x64, which has a Windows artifact in the official
[actions/python-versions manifest](https://raw.githubusercontent.com/actions/python-versions/main/versions-manifest.json).
Python 3.12.14 has no Windows artifact there and cannot be installed by
`actions/setup-python` on a Windows runner. [Pillow 13](https://pillow.readthedocs.io/en/stable/installation/python-support.html)
and [PyInstaller 6.22.3](https://github.com/pyinstaller/pyinstaller/blob/v6.22.3/pyproject.toml)
support Python 3.14. Recheck manifest availability before changing this pin.

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.lock
.\.venv\Scripts\python.exe scripts/check.py
.\.venv\Scripts\python.exe -m pip_audit -r requirements.txt --no-deps --disable-pip
.\.venv\Scripts\python.exe scripts/fetch_nsis.py --out build-tools/nsis
.\.venv\Scripts\python.exe scripts/build_windows.py --out release-output --nsis build-tools/nsis/nsis-3.13/makensis.exe
```

The download helper verifies the official NSIS 3.13 archive SHA-256 before
extracting it. Every output directory must be new/empty: scripts do not clean
existing directories. Use another output path for a subsequent build.

The build embeds Python, Tcl/Tk, Pillow, the original studio logo and component
licenses into a PyInstaller **onedir** package. Keeping runtime files installed
avoids unpacking them to a temporary directory at every launch. Only the actual
Codex executable and account remain external. The source distribution contains
no author credentials, user histories, local settings or packaged environment.

Outputs: per-user NSIS setup EXE, portable ZIP, SHA256SUMS.txt. The ZIP includes
the whole `CodexUsageWidget` directory; do not distribute its EXE alone.
Build output is excluded from Git. `requirements-build.lock` records resolved
tool versions; matching versions do not guarantee bit-identical PE/ZIP bytes.
Use the same Python patch version to reproduce the CI build locally. The local
candidate uses Python 3.12.14; its checks apply only to that candidate's
exact files. The Python 3.14.10 CI candidate needs its own frozen, GUI and installer
checks. Neither candidate's results validate the other runtime or artifact.

The local Python 3.12.14 build environment reports OpenSSL 3.5.8, with matching
`libssl-3-x64.dll` and `libcrypto-3-x64.dll`. The HTTP status reader imports `ssl`,
so inspect the frozen package for these runtime dependencies and ship the matching
license from `packaging/licenses`. This local inspection does not establish the
OpenSSL version or complete bundled-notice set of the Python 3.14.10 CI package.

## Offline executable checks

```powershell
$exe = (Resolve-Path 'release-output/payload/CodexUsageWidget/CodexUsageWidget.exe').Path
$report = Join-Path $PWD 'release-output/self-test.json'
Start-Process $exe -ArgumentList @('--self-test', ('"'+$report+'"')) -WindowStyle Hidden -Wait
$gui = Join-Path $PWD 'release-output/gui-test.json'
$isolated = Join-Path $PWD 'release-output/isolated-qa-data'
Start-Process $exe -ArgumentList @('--smoke-test', ('"'+$gui+'"'), '--data-dir', ('"'+$isolated+'"')) -WindowStyle Hidden -Wait
```

The GUI check needs an interactive Windows desktop. It uses synthetic quotas
and disables all metadata fetching. The data directory must be an isolated
absolute path; the test writes its own settings there.

## Installer verification

Use a fresh directory for each test. `/TEST=1` skips shortcuts/Windows application
registration and uses an isolated shutdown namespace. NSIS `/D=` must be the
last argument and is not quoted. Test normal installation, launching the installed
EXE, update to the same directory, and rejection of an unrelated nonempty folder.

Uninstall removes only the build manifest's files and empty subdirectories,
after checking the application marker. It preserves settings and unknown files.
Run removal tests only with explicit owner approval on a verified QA directory.
Never substitute a recursive directory deletion for the actual uninstaller.

GitHub Actions performs source checks, runtime dependency audit, build and
packaged offline check. It stores candidate artifacts, with read-only repository
permissions. It does not publish Releases or claim a clean Windows 10/11 GUI test.
