#!/usr/bin/env python3
import argparse
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(cmd, cwd=ROOT):
    subprocess.run(cmd, cwd=cwd, check=True)


def out(cmd, cwd=ROOT):
    return subprocess.check_output(cmd, cwd=cwd, text=True).strip()


def version():
    return (ROOT / "VERSION").read_text().strip()


def git_sha():
    try:
        return out(["git", "rev-parse", "--short", "HEAD"])
    except Exception:
        return "nogit"


def add_tree(zf, src, prefix, excludes=()):
    for p in sorted(src.rglob("*")):
        if p.is_dir():
            continue
        rel = p.relative_to(src)
        if any(str(rel).startswith(e) for e in excludes):
            continue
        zf.write(p, Path(prefix) / rel)


def write_manifest(path, kind, envs):
    data = {
        "name": "vibe-lamp",
        "kind": kind,
        "version": version(),
        "git": git_sha(),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "firmware_envs": envs,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def package_daemon(dist, tag):
    name = f"vibe-lamp-daemon-{tag}.zip"
    path = dist / name
    manifest = dist / "daemon-manifest.json"
    write_manifest(manifest, "daemon", [])
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(ROOT / "VERSION", "VERSION")
        zf.write(manifest, "manifest.json")
        zf.write(ROOT / "README.zh-CN.md", "README.zh-CN.md")
        zf.write(ROOT / "README.md", "README.md")
        zf.write(ROOT / "daemon" / "install.py", "daemon/install.py")
        zf.write(ROOT / "daemon" / "pyproject.toml", "daemon/pyproject.toml")
        zf.write(ROOT / "daemon" / "com.vibelamp.daemon.plist.template",
                 "daemon/com.vibelamp.daemon.plist.template")
        add_tree(zf, ROOT / "daemon" / "vibelamp", "daemon/vibelamp",
                 excludes=("__pycache__",))
        add_tree(zf, ROOT / "daemon" / "tests", "daemon/tests",
                 excludes=("__pycache__",))
    manifest.unlink(missing_ok=True)
    return path


def package_firmware(dist, tag, envs, build):
    if build:
        for env in envs:
            run(["../.venv/bin/pio", "run", "-e", env], cwd=ROOT / "firmware")

    name = f"vibe-lamp-firmware-{tag}.zip"
    path = dist / name
    manifest = dist / "firmware-manifest.json"
    write_manifest(manifest, "firmware", envs)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(ROOT / "VERSION", "VERSION")
        zf.write(manifest, "manifest.json")
        zf.write(ROOT / "firmware" / "platformio.ini", "firmware/platformio.ini")
        zf.write(ROOT / "README.zh-CN.md", "README.zh-CN.md")
        zf.write(ROOT / "HARDWARE.md", "HARDWARE.md")
        for env in envs:
            build_dir = ROOT / "firmware" / ".pio" / "build" / env
            for filename in ("firmware.bin", "firmware.elf", "partitions.bin"):
                src = build_dir / filename
                if src.exists():
                    zf.write(src, f"firmware/{env}/{filename}")
    manifest.unlink(missing_ok=True)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-build", action="store_true", help="只打包已有固件产物，不重新编译")
    ap.add_argument("--env", action="append", dest="envs",
                    help="固件 env，可重复；默认打包 c3_rgb")
    args = ap.parse_args()

    dist = ROOT / "dist"
    shutil.rmtree(dist, ignore_errors=True)
    dist.mkdir(parents=True)

    tag = f"v{version()}-{datetime.now().strftime('%Y%m%d')}-{git_sha()}"
    envs = args.envs or ["c3_rgb"]
    daemon_zip = package_daemon(dist, tag)
    firmware_zip = package_firmware(dist, tag, envs, build=not args.no_build)
    print(daemon_zip)
    print(firmware_zip)


if __name__ == "__main__":
    sys.exit(main())
