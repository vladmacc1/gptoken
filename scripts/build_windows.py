"""Build a fresh onedir package and a per-user NSIS installer. Never cleans folders."""

import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from app_runtime import VERSION


def run(*args):
    subprocess.run([str(arg) for arg in args], cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True, help="New, empty build directory")
    parser.add_argument("--nsis", type=Path, required=True, help="Path to NSIS 3.13 makensis.exe")
    args = parser.parse_args()
    output = args.out.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("Choose a new empty output directory; existing files are preserved")
    if not args.nsis.is_file():
        parser.error("makensis.exe was not found")
    output.mkdir(parents=True, exist_ok=True)
    icon = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    draw = ImageDraw.Draw(icon)
    draw.rounded_rectangle((4, 4, 252, 252), 52, fill="#161b22")
    for x, top, color in ((48, 144, "#8cf2ce"), (106, 100, "#8cf2ce"), (164, 56, "#f3cf75")):
        draw.rounded_rectangle((x, top, x + 42, 205), 10, fill=color)
    icon_path = output / "app.ico"
    icon.save(icon_path, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    run(
        sys.executable,
        "-m",
        "PyInstaller",
        "--onedir",
        "--windowed",
        "--name",
        "CodexUsageWidget",
        "--paths",
        ROOT / "src",
        "--add-data",
        f"{ROOT / 'src' / 'assets'};assets",
        "--add-data",
        f"{ROOT / 'packaging' / 'licenses'};licenses",
        "--icon",
        icon_path,
        "--distpath",
        output / "payload",
        "--workpath",
        output / "work",
        "--specpath",
        output,
        ROOT / "src" / "codex_usage.pyw",
    )
    payload = output / "payload" / "CodexUsageWidget"
    for name in ("LICENSE", "README.md", "PRIVACY.md", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(ROOT / name, payload / name)
    shutil.copytree(ROOT / "docs", payload / "docs")
    shutil.copy2(ROOT / "docs" / "USER_GUIDE.ru.md", payload / "INSTRUCTIONS.ru.txt")
    # The generated uninstaller removes only these known files, never a whole tree.
    files = sorted(path.relative_to(payload) for path in payload.rglob("*") if path.is_file())
    folders = sorted(
        {path.parent for path in files if path.parent != Path(".")}, key=lambda p: len(p.parts), reverse=True
    )
    expanded = set(folders)
    for folder in folders:
        expanded.update(parent for parent in folder.parents if parent != Path("."))
    folders = sorted(expanded, key=lambda p: (len(p.parts), str(p)), reverse=True)

    def safe_path(path):
        value = str(path)
        if any(char in value for char in ('"', "$", "\n", "\r")) or ".." in path.parts:
            raise ValueError("Unsafe package filename")
        return value

    manifest = output / "uninstall-files.nsh"
    manifest.write_text(
        "\n".join(
            [f'Delete "$INSTDIR\\{safe_path(path)}"' for path in files]
            + [f'RMDir "$INSTDIR\\{safe_path(path)}"' for path in folders]
        )
        + "\n",
        encoding="utf-8-sig",
    )
    installer = output / f"GPTOKEN-{VERSION}-windows-x64-setup.exe"
    run(
        args.nsis.resolve(),
        "/V3",
        "/INPUTCHARSET",
        "UTF8",
        f"/DVERSION={VERSION}",
        f"/DPAYLOAD={payload}",
        f"/DUNINSTALL_FILES={manifest}",
        f"/DOUTPUT={installer}",
        f"/DAPP_ICON={icon_path}",
        ROOT / "packaging" / "installer.nsi",
    )
    portable = output / f"GPTOKEN-{VERSION}-windows-x64-portable.zip"
    with zipfile.ZipFile(portable, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(payload.rglob("*")):
            if path.is_file():
                archive.write(path, Path("CodexUsageWidget") / path.relative_to(payload))
    checksum = output / "SHA256SUMS.txt"
    checksum.write_text(
        "".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in (installer, portable)),
        encoding="ascii",
    )
    print(f"Built {installer.name} and {portable.name}")


if __name__ == "__main__":
    main()
