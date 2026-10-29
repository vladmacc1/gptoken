# Public release gate

Status: **candidate-05 verified locally; public release pending**. See [current QA report](QA-RELEASE-2026-10-29.md) and [earlier QA report](QA-2026-10-29.md) for measured
results; unchecked items are not implied to have passed.

- [x] Owner chose proprietary freeware terms; VLADMACC attribution/logo retained.
- [x] Source and user data separated; logs/settings/credentials excluded from Git.
- [x] Local lifecycle reading and startup are explicit opt-in settings.
- [x] Read-only RPC allowlist prevents model/task/payment operations.
- [x] Build script, pinned dependencies, license notices and CI definition supplied.
- [x] Source checks and runtime dependency audit on candidate source.
- [x] Frozen self-test and interactive GUI check on release binary.
- [x] Candidate-05 uses Python 3.14.10 / OpenSSL 3.5.9 / Tcl/Tk 9.0.4 with matching notices.
- [x] Installer first install and update; wrong-directory rejection (isolated QA mode).
- [x] Approved removal test preserves user/unknown files in candidate-03; candidate-04 removal not repeated.
- [x] Windows CI successful for revision `a7cc017856028d772fb0136f5c2e3f771f0227b6`: [run 40926148832](https://github.com/vladmacc1/gptoken/actions/runs/40926148832).
- [ ] Clean Windows 10 and Windows 11 user testing without developer Python.
- [x] Microsoft Defender scan recorded for exact installer hash.
- [x] Code-signing status recorded; unsigned publisher disclosed.
- [x] SHA-256 and final release notes match exact candidate binaries.
- [ ] Owner approves public binary release.

Do not mark a source build or API success as a complete public release test.
No certificate, service or subscription is purchased as part of preparation.
