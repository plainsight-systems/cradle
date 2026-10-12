#!/usr/bin/env python3
"""Fetch and build Cradle's pinned ILGPU toolchain. Python 3.11+, Git, .NET SDK required."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = "https://github.com/m4rs-mt/ILGPU.git"


def run(*args, cwd=ROOT, capture=False):
    return subprocess.run(args, cwd=cwd, check=True, text=True,
                          stdout=subprocess.PIPE if capture else None).stdout


def main():
    expected_sdk = json.loads((ROOT / "global.json").read_text())["sdk"]["version"]
    sdk = run("dotnet", "--version", capture=True).strip()
    if sdk != expected_sdk:
        raise ValueError(f"Install .NET SDK {expected_sdk}; found {sdk} on PATH")
    revision = ET.parse(ROOT / "eng/ILGPU.props").findtext("./PropertyGroup/ILGPURevision")
    source = ROOT / ".deps" / f"ilgpu-{revision}"
    if not (source / ".git").exists():
        if source.exists() and any(source.iterdir()):
            raise ValueError(f"Expected an empty dependency directory: {source}")
        source.mkdir(parents=True, exist_ok=True)
        run("git", "init", "-q", str(source))
        run("git", "-C", str(source), "config", "core.autocrlf", "false")
        run("git", "-C", str(source), "remote", "add", "origin", UPSTREAM)
    # Allow retry after an interrupted initial fetch, without resetting an existing checkout.
    head = subprocess.run(["git", "-C", str(source), "rev-parse", "--verify", "HEAD"],
                          text=True, capture_output=True)
    if head.returncode:
        run("git", "-C", str(source), "fetch", "--depth", "1", "origin", revision)
        run("git", "-C", str(source), "checkout", "-q", "--detach", "FETCH_HEAD")
    actual = run("git", "-C", str(source), "rev-parse", "HEAD", capture=True).strip()
    if actual != revision:
        raise ValueError(f"ILGPU must be at {revision}; found {actual}. Preserve edits and use a fresh checkout.")
    run("git", "-C", str(source), "diff", "--exit-code", "HEAD", "--")
    # Upstream has a floating package reference. Our reviewed lock files fix that graph too.
    locks = sorted((ROOT / "eng/ilgpu-locks").glob("*.json"))
    if not locks:
        raise ValueError("Missing ILGPU package lock files")
    allowed = {f"Src/{p.stem}/packages.lock.json" for p in locks}
    extra = set(run("git", "-C", str(source), "ls-files", "--others", "--exclude-standard",
                    capture=True).splitlines()) - allowed
    if extra:
        raise ValueError(f"Unexpected files in ILGPU checkout: {', '.join(sorted(extra))}")
    for lock in locks:
        shutil.copyfile(lock, source / "Src" / lock.stem / "packages.lock.json")
    compiler = source / "Src/ILGPUC/ILGPUC.csproj"
    print(f"SDK: {sdk}\nILGPU: {revision}", flush=True)
    run("dotnet", "restore", str(compiler), "--locked-mode",
        "-p:RestorePackagesWithLockFile=true", "--configfile", str(ROOT / "NuGet.Config"))
    run("dotnet", "build", str(compiler), "-c", "Release", "--no-restore", "--nologo", "-v", "quiet")
    run("dotnet", "restore", str(ROOT / "Cradle.slnx"), "--locked-mode")
    print("Dependencies are ready. Run: dotnet run --project src/Cradle", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        sys.exit(f"setup: {exc}")
