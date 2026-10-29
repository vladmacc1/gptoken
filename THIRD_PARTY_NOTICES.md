# Third-party notices

GPTOKEN application code and VLADMACC artwork are proprietary. The following
unmodified components retain their own licenses, reproduced in `_internal/licenses`
in the binary distribution and `packaging/licenses` in the repository.

| Component | Version | License / notice |
|---|---|---|
| CPython — CI candidate | 3.14.10 | PSF license, Python-3.14.10.txt; verify bundled notices against the exact CI runtime |
| CPython — local candidate | 3.12.14 | PSF license and bundled third-party notices, Python-3.12.txt |
| OpenSSL — local build runtime | 3.5.8 | Apache License 2.0, OpenSSL-3.5.8.txt; attribution below |
| Tcl / Tk | 8.6 (exact patch version in diagnostics) | Tcl/Tk terms, Tcl-8.6.txt and Tk-8.6.txt |
| Pillow and its binary libraries | 13.0.0 | MIT-CMU and included component notices, Pillow-13.0.0.txt |
| PyInstaller bootloader | 6.22.3 | GPL with distribution exception, PyInstaller-6.22.3.txt |
| NSIS installer and zlib compressor | 3.13 | NSIS-3.13.txt; zlib compressor selected |

`Python-3.14.10.txt` is the unchanged [CPython 3.14.10 source license](https://github.com/python/cpython/blob/v3.14.10/LICENSE).
`Python-3.12.txt` covers the local Python 3.12.14 candidate.
The local and CI candidates are separate artifacts; runtime versions and notices
must be checked against each final binary. The source license alone is not an
inventory of all third-party libraries bundled with the Windows runtime.

The local Python 3.12.14 build environment reports `OpenSSL 3.5.8 25 Aug 2026`;
its `_ssl.pyd` uses `libssl-3-x64.dll` and `libcrypto-3-x64.dll`, both version 3.5.8.
`OpenSSL-3.5.8.txt` reproduces the unchanged [official OpenSSL 3.5.8 license](https://github.com/openssl/openssl/blob/openssl-3.5.8/LICENSE.txt).
The [upstream attribution](https://github.com/openssl/openssl/blob/openssl-3.5.8/README.md#copyright) is:

Copyright (c) 1998-2026 The OpenSSL Project Authors

Copyright (c) 1995-1998 Eric A. Young, Tim J. Hudson

All rights reserved.

This runtime inspection does not establish the exact files in a frozen package.
The OpenSSL version and complete bundled-notice set for the Python 3.14.10 CI
runtime have not been inspected; verify them against that candidate separately.

Portions of this software are copyright © 2026 The FreeType Project
(https://freetype.org). All rights reserved. We select the FreeType License for
the FreeType component, not its alternative GPL license.

This software is based in part on the work of the Independent JPEG Group.
Pillow's complete binary-wheel license file includes the notices for its image,
font and compression dependencies. Windows Segoe UI fonts are used from the
user's operating system and are not redistributed.

Build tools (ruff, pip-audit, pip and their dependencies) run only during
development and are not application dependencies.

Pillow-12.3.0.txt is retained as the notice from the earlier development copy;
the public candidate uses Pillow 13.0.0.
