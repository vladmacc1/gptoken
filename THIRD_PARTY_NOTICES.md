# Third-party notices

GPTOKEN application code and VLADMACC artwork are proprietary. The following
unmodified components retain their own licenses, reproduced in `_internal/licenses`
in the binary distribution and `packaging/licenses` in the repository.

| Component | Version | License / notice |
|---|---|---|
| CPython — local candidate 05 and CI target | 3.14.10 | PSF license and Windows distribution notices, Python-3.14.10.txt and Python-3.14.10-Windows.txt |
| OpenSSL | 3.5.9 | Apache License 2.0, OpenSSL-3.5.9.txt; attribution below |
| Tcl / Tk | 9.0.4 | Tcl/Tk terms, Tcl-9.0.4.txt and Tk-9.0.4.txt |
| Pillow and its binary libraries | 13.0.0 | MIT-CMU and included component notices, Pillow-13.0.0.txt |
| PyInstaller bootloader | 6.22.3 | GPL with distribution exception, PyInstaller-6.22.3.txt |
| NSIS installer and zlib compressor | 3.13 | NSIS-3.13.txt; zlib compressor selected |

`Python-3.14.10.txt` is the unchanged [CPython 3.14.10 source license](https://github.com/python/cpython/blob/v3.14.10/LICENSE).
`Python-3.14.10-Windows.txt` is the unchanged complete `LICENSE.txt` from the
inspected Python 3.14.10 Windows x64 distribution used for the local build.
It preserves the distribution's additional Windows and bundled-component terms.
The local and CI candidates remain separate artifacts: matching runtime versions
do not transfer frozen, GUI or installer checks from one binary to another.

The inspected local build interpreter reports Python 3.14.10 and
`OpenSSL 3.5.9 29 Sep 2026`; `libssl-3.dll` and `libcrypto-3.dll` report 3.5.9.
Tcl reports patch level 9.0.4, and `tcl90.dll` / `tcl9tk90.dll` report 9.0.4.
`OpenSSL-3.5.9.txt` reproduces the unchanged [official OpenSSL 3.5.9 license](https://github.com/openssl/openssl/blob/openssl-3.5.9/LICENSE.txt).
`Tcl-9.0.4.txt` and `Tk-9.0.4.txt` reproduce the upstream
[Tcl](https://github.com/tcltk/tcl/blob/core-9-0-4/license.terms) and
[Tk](https://github.com/tcltk/tk/blob/core-9-0-4/license.terms) license terms.
The OpenSSL [upstream attribution](https://github.com/openssl/openssl/blob/openssl-3.5.9/README.md#copyright) is:

Copyright (c) 1998-2026 The OpenSSL Project Authors

Copyright (c) 1995-1998 Eric A. Young, Tim J. Hudson

All rights reserved.

This interpreter inspection does not establish every file in a frozen package.
Each final local and CI package still needs its own runtime and notice inventory.
The earlier local Python 3.12.14 / OpenSSL 3.5.8 candidate 04 is superseded and
must not be distributed. `Python-3.12.txt`, `OpenSSL-3.5.8.txt`, `Tcl-8.6.txt` and
`Tk-8.6.txt` are retained for the earlier development artifacts.

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
