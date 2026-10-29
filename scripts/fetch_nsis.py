"""Download the pinned official NSIS archive and verify bytes before extraction."""

import argparse
import hashlib
from pathlib import Path
import urllib.request
import zipfile

URL = "https://downloads.sourceforge.net/project/nsis/NSIS%203/3.13/nsis-3.13.zip"
SHA256 = "ba63dffc4410ee89193e1cb5a41989991bd77c61068da17e3156d136b7b0b3d8"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True, help="New directory for verified NSIS files")
    args = parser.parse_args()
    target = args.out.resolve()
    if target.exists() and any(target.iterdir()):
        parser.error("Output directory must be empty; existing files are preserved")
    target.mkdir(parents=True, exist_ok=True)
    archive = target / "nsis-3.13.zip"
    with urllib.request.urlopen(URL, timeout=120) as response:
        data = response.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError("NSIS checksum mismatch; archive will not be extracted")
    archive.write_bytes(data)
    with zipfile.ZipFile(archive) as package:
        for item in package.infolist():
            if not (target / item.filename).resolve().is_relative_to(target):
                raise ValueError("Unsafe archive entry")
        package.extractall(target)
    print(target / "nsis-3.13" / "makensis.exe")


if __name__ == "__main__":
    main()
