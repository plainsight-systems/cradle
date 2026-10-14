+++
title = "Prologue: Getting the cradle ready"
description = "Set up the tools, build the starting program, and check the dependencies we’ll use in the first lesson."
lesson = 0
date = 2026-10-12
draft = false
start_tag = ""
end_tag = "lesson-00"
personal_slug = "cradle-00-getting-the-cradle-ready"
publish_assets = []
tags = ["C#", "GPU", "Transformers"]
math = false
+++

I want to build a transformer inference engine in C# and explain it as it grows. There is a lot of material that shows how to get a model to generate text. I’m interested in the work inside those calls: how the data gets to the GPU, what each kernel does to it, and how those operations eventually produce the next token.

We’ll work through that a piece at a time, following the approach Jack Crenshaw used in [Let’s Build a Compiler!](https://compilers.iecc.com/crenshaw/). Each lesson adds something to the same running program. We’ll introduce the arithmetic when we need it to understand the code we’re writing, with small examples we can check for ourselves. You should be comfortable reading C#. You don’t need to arrive knowing how a transformer works.

Crenshaw called his starting program a cradle. Ours starts here, with the project and tools the first lesson will build on.

## The starting point

The program for this prologue prints one line:

```text
Cradle is ready.
```

That gives us a way to check the project setup before we add GPU execution. In lesson 1 we’ll find a GPU, upload two arrays, add them in a C# kernel, and read back the result. From there, the same program will grow toward loading model weights and generating text.

Each article has a completed code snapshot. The prologue’s snapshot is `lesson-00`; lesson 1 starts there and finishes at `lesson-01`. These are Git tags, so you can return to the code an article describes even after the series has moved on. If you use Git, check out the snapshot on a local branch before making your own changes. Downloading the snapshot also works.

Open the snapshot linked above and work from the repository’s root directory, where `Cradle.slnx` lives. The `articles/` and `web/` directories hold the writing and project site. You won’t need to build the website to follow the code.

## Tools and versions

You’ll need Git, Python 3.11 or newer for the dependency setup script, and **.NET SDK 10.0.401**. Install the SDK for your operating system and processor from Microsoft’s [.NET 10 downloads](https://dotnet.microsoft.com/en-us/download/dotnet/10.0). The SDK includes the build tools; installing only the runtime won’t be enough.

From the repository directory, run:

```sh
dotnet --version
```

It should report `10.0.401`. The repository’s `global.json` makes that choice explicit:

```json
{
  "sdk": {
    "version": "10.0.401",
    "rollForward": "disable",
    "allowPrerelease": false
  }
}
```

If that SDK isn’t installed, `dotnet` stops and tells you. This is deliberate. When we compare a result or investigate a compiler problem, knowing which tools produced it matters. You can keep other SDK versions installed for your other projects.

The project targets .NET 10 and uses C# 13, the language version understood by the ILGPU compiler revision we’re using. Those settings live in `Directory.Build.props`, which applies them to both the application and its tests.

## Why the GPU dependency takes an extra step

I chose C# because I want this series to be useful to .NET developers. That includes people working on Windows, Linux, and Mac. Mac needs some additional care here: the native Metal support used in our experiments comes from a development version of ILGPU.

For this starting point, we’re using [ILGPU revision `24cb87d`](https://github.com/m4rs-mt/ILGPU/commit/24cb87d6669c177428bd4ef1b8d05d9652b21c4b). The full revision is recorded in `eng/ILGPU.props`. Keeping that revision fixed lets us explain the behavior and workarounds of the compiler we have actually exercised.

Run the setup command from the repository root:

```sh
python3 scripts/setup.py
```

On Windows, use `python` in place of `python3` if that is how Python is installed.

The script downloads the pinned ILGPU source into `.deps/`, checks its revision, restores its dependencies, and builds the kernel compiler. It then restores the Cradle solution and checks the compiler wiring by building and running a small temporary kernel on the CPU. You should see `Kernel setup verified: CPU, 1031 checked outputs.` The temporary program is removed afterward; our cradle still starts with a greeting. The first run needs internet access and takes longer than subsequent runs. Everything it downloads or builds stays out of the repository’s published source.

There is another set of versions involved: the packages used to build ILGPU itself. One of its package references allows several versions, so pinning the Git revision alone would leave that choice open. The files in `eng/ilgpu-locks/` record the resolved versions and package hashes. Our own projects have `packages.lock.json` files for the same reason. Setup uses locked restore, which fails if the dependency declarations no longer agree with those files.

You can rerun setup. It checks the existing checkout and refuses changed source instead of quietly building a different ILGPU. If it fails, read the reported error before changing any version pins.

## Connect the kernel compiler

Building ILGPU’s compiler is only half the setup. Our application also needs to call it when we build. `Cradle.csproj` points to that compiler and imports `eng/Cradle.Kernels.targets`, which connects it to `dotnet build`. The generated launch code uses unsafe operations internally, so the project enables `AllowUnsafeBlocks`. We won't need to write those operations ourselves.

In this version, ILGPU finds kernel launches during the build, translates the kernel code, and generates the code that launches it. On Metal, the build embeds shader source that the Metal runtime compiles for the GPU when the program runs. The online ILGPU tutorials describe an older API: they compile kernels through the accelerator at runtime and allocate buffers directly through it. Our version uses build-time kernel translation and stream-based allocation. We’ll introduce those calls as we use them in lesson 1.

The project’s `ILGPUBackend` setting chooses the kind of kernel code to generate. It defaults to `Metal` on Mac and `CUDA` elsewhere. Other build targets are `ROCm` and `OpenCL`; choose the backend that matches the device and driver you intend to use. For example, an OpenCL build uses:

```sh
dotnet build Cradle.slnx -c Release --no-restore -p:ILGPUBackend=OpenCL
```

Use the same setting when rebuilding, including with `dotnet run`. This compiler revision needs a separate build for each backend. The setting controls compilation; it doesn't select a device. We’ll make that selection in lesson 1. The temporary setup check explicitly uses `CPU`, so preparing the tools does not require a GPU.

## Build and run the cradle

We have two projects of our own:

| Project | Purpose |
| --- | --- |
| `src/Cradle/Cradle.csproj` | The console program we’ll extend throughout the series |
| `tests/Cradle.Tests/Cradle.Tests.csproj` | Checks that will grow alongside the implementation |

The application references the ILGPU project in the pinned checkout, which also appears under `Dependencies` in the solution so the editor can load its source. That project reference brings its runtime dependencies into our build. The test project references the application and uses xUnit, with its package versions pinned in the project file and lock file.

Here is the whole of `src/Cradle/Program.cs`:

```csharp
namespace Cradle;

internal static class Program
{
    private static void Main()
    {
        Console.WriteLine("Cradle is ready.");
    }
}
```

We use an explicit `Main` because this ILGPU compiler revision cannot process top-level statements once a kernel launch is present. It is a little more structure than a one-line console program needs, but it gives us a starting point the kernel compiler can use. Everything stays in this file for lesson 1.

Build the solution, run its tests, and launch the application:

```sh
dotnet build Cradle.slnx -c Release --no-restore
dotnet test Cradle.slnx -c Release --no-build --no-restore
dotnet run --project src/Cradle -c Release --no-build --no-restore
```

The restore happened during setup. `--no-build` tells the last two commands to use the binaries from the build we just completed. Expect one passing test, followed by `Cradle is ready.` from the application.

For ordinary editing, you can use `dotnet run --project src/Cradle`; it builds before running. The longer sequence above makes the initial checks explicit.

## What we have checked

Setup has already checked that the application's compiler settings can translate, launch, and verify a temporary kernel on the CPU. The xUnit test loads the ILGPU runtime assembly and checks that its accelerator type is available. Together they check the compiler wiring and the dependency path through our projects to the test runner.

The repository also includes a command for the broader build checks:

```sh
python3 scripts/check_dotnet.py
```

GitHub Actions runs this same command on Windows, Linux, and macOS. It prepares the dependencies, checks
that a kernel can be built repeatedly, builds the current program for each GPU backend, and runs the
CPU-side tests. As we extend the program, those same commands check the new code and tests. You can run
them locally too, without a GPU.

Running the program on an actual GPU is a separate check, using the same `dotnet run` command we use
while developing it. We’ll do that in lesson 1, when we choose a backend and start using the GPU.

We now have a program that runs, a place for its tests, and fixed versions of the tools it depends on. In lesson 1, we’ll put those tools to work on the GPU.
