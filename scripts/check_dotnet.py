#!/usr/bin/env python3
"""Run the same dependency, build, and CPU-side checks as hosted CI; no GPU required."""

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run(*command):
    print("+ " + " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def build_and_test(*properties):
    run("dotnet", "build", "Cradle.slnx", "-c", "Release", "--no-restore", *properties)
    run("dotnet", "test", "Cradle.slnx", "-c", "Release", "--no-build", "--no-restore", *properties)


def main():
    run(sys.executable, "scripts/setup.py")
    for backend in ["CUDA", "ROCm", "OpenCL", "Metal"]:
        run(sys.executable, "scripts/check_kernel_setup.py", "--backend", backend, "--compile-only")
        build_and_test(f"-p:ILGPUBackend={backend}")

    # Leave the application built for the platform default after checking other backends.
    build_and_test()
    print("Build and CPU-side checks passed. GPU execution is a separate check.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, subprocess.CalledProcessError) as exc:
        sys.exit(f"check_dotnet: {exc}")
