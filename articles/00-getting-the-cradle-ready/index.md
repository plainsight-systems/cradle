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

The script downloads the pinned ILGPU source into `.deps/`, checks its revision, restores its dependencies, and builds the kernel compiler. It then restores the Cradle solution. The first run needs internet access and takes longer than subsequent runs. Everything it downloads or builds stays out of the repository’s published source.

There is another set of versions involved: the packages used to build ILGPU itself. One of its package references allows several versions, so pinning the Git revision alone would leave that choice open. The files in `eng/ilgpu-locks/` record the resolved versions and package hashes. Our own projects have `packages.lock.json` files for the same reason. Setup uses locked restore, which fails if the dependency declarations no longer agree with those files.

You can rerun setup. It checks the existing checkout and refuses changed source instead of quietly building a different ILGPU. If it fails, read the reported error before changing any version pins.

## Build and run the cradle

The solution has two projects:

| Project | Purpose |
| --- | --- |
| `src/Cradle/Cradle.csproj` | The console program we’ll extend throughout the series |
| `tests/Cradle.Tests/Cradle.Tests.csproj` | Checks that will grow alongside the implementation |

The application references the ILGPU project in the pinned checkout. That project reference also brings its runtime dependencies into our build. The test project references the application and uses xUnit, with its package versions pinned in the project file and lock file.

Here is the whole of `src/Cradle/Program.cs`:

```csharp
Console.WriteLine("Cradle is ready.");
```

C# supplies the entry point for this top-level statement. We don’t need any application structure around it yet.

Build the solution, run its tests, and launch the application:

```sh
dotnet build Cradle.slnx -c Release --no-restore
dotnet test Cradle.slnx -c Release --no-build --no-restore
dotnet run --project src/Cradle -c Release --no-build --no-restore
```

The restore happened during setup. `--no-build` tells the last two commands to use the binaries from the build we just completed. Expect one passing test, followed by `Cradle is ready.` from the application.

For ordinary editing, you can use `dotnet run --project src/Cradle`; it builds before running. The longer sequence above makes the initial checks explicit.

## What we have checked

The first test loads the ILGPU runtime assembly and checks that its accelerator type is available. That exercises the dependency path from the pinned source through our projects to the test runner. It does not create an accelerator or run a kernel.

That distinction will matter throughout the series. A successful build and a passing setup test tell us the tools fit together. Running a kernel on a particular GPU tells us something more, and that needs its own check.

We now have a program that runs, a place for its tests, and fixed versions of the tools it depends on. In lesson 1, we’ll put those tools to work on the GPU.
