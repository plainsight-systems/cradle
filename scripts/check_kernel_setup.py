#!/usr/bin/env python3
"""Verify the application's kernel build wiring in an isolated temporary project."""

import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]

PROBE = """using ILGPU;
using ILGPU.Runtime;

namespace Cradle;

internal static class Program
{
    private static void Main(string[] args)
    {
        if (!typeof(Program).Assembly.GetTypes().Any(t => t.Name == "Probe_CompiledKernel"))
            throw new InvalidOperationException("Generated kernel was not included in the application");
        if (args.Single() == "--verify-compiled-only")
            return;
        // CPU is an explicit compiler check for hosted CI, never a GPU fallback.
        var backend = Enum.Parse<AcceleratorType>(args.Single());
        using var context = Context.CreateDefault();
        var device = context.Devices.FirstOrDefault(d => d.AcceleratorType == backend)
            ?? throw new InvalidOperationException($"Required backend unavailable: {backend}");
        using var accelerator = device.CreateAccelerator(context);
        var stream = accelerator.DefaultStream;
        const int count = 1031;
        using var output = stream.Allocate1D<float>(count);
        output.CopyFromCPU(Enumerable.Repeat(float.NaN, count).ToArray());

        stream.Launch((Index1D)count, index => Probe(index, output.View));
        stream.Synchronize();
        var actual = output.GetAsArray1D();
        for (int i = 0; i < count; ++i)
        {
            if (actual[i] != i + 17)
                throw new InvalidOperationException($"Element {i}: expected {i + 17}, got {actual[i]}");
        }
        Console.WriteLine($"Kernel setup verified: {backend}, {count} checked outputs.");
    }

    private static void Probe(Index1D index, ArrayView<float> result)
    {
        result[index] = index + 17;
    }
}
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["CPU", "CUDA", "ROCm", "OpenCL", "Metal"], default="CPU",
                        help="Kernel backend to build and execute; default: CPU for hosted CI")
    parser.add_argument("--compile-only", action="store_true",
                        help="Check compilation without claiming execution on that hardware")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="cradle kernel check ") as name:
        directory = Path(name)
        for source in [ROOT / "global.json", ROOT / "NuGet.Config",
                       ROOT / "src/Cradle/Cradle.csproj",
                       ROOT / "src/Cradle/packages.lock.json"]:
            shutil.copy2(source, directory / source.name)
        # Retain the app's relative import layout in the temporary copy.
        project_directory = directory / "src/Cradle"
        project_directory.mkdir(parents=True)
        for filename in ["Cradle.csproj", "packages.lock.json"]:
            (directory / filename).rename(project_directory / filename)
        shutil.copytree(ROOT / "eng", directory / "eng")
        # Import the same settings as the real app. Only the probe source differs.
        props = ET.Element("Project")
        ET.SubElement(props, "Import", Project=str(ROOT / "Directory.Build.props"))
        ET.ElementTree(props).write(directory / "Directory.Build.props", encoding="unicode")
        (project_directory / "Program.cs").write_text(PROBE, encoding="utf-8")
        subprocess.run(["dotnet", "restore", "Cradle.csproj", "--locked-mode"],
                       cwd=project_directory, check=True)
        # Both a fresh build and the next build must compile the generated sources.
        # Checking only their presence on disk misses incorrect MSBuild ordering.
        for attempt in range(2):
            print(f"Kernel build check {attempt + 1}/2: {args.backend}", flush=True)
            subprocess.run(["dotnet", "build", "Cradle.csproj", "-c", "Release", "--no-restore",
                            f"-p:ILGPUBackend={args.backend}"],
                           cwd=project_directory, check=True)
            generated = project_directory / "obj/Release/net10.0/ilgpu/generated"
            if not list(generated.glob("*_CompiledKernel.cs")):
                raise RuntimeError("Build did not generate a compiled kernel; check the targets import")
            if args.compile_only:
                subprocess.run(["dotnet", "run", "--project", "Cradle.csproj", "-c", "Release",
                                "--no-build", "--no-restore", "--", "--verify-compiled-only"],
                               cwd=project_directory, check=True)
                print(f"Kernel source generation verified: {args.backend}; no device execution.")
            else:
                subprocess.run(["dotnet", "run", "--project", "Cradle.csproj", "-c", "Release",
                                "--no-build", "--no-restore", "--",
                                "Cuda" if args.backend == "CUDA" else args.backend],
                               cwd=project_directory, check=True)


if __name__ == "__main__":
    main()
