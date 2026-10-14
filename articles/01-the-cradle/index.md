+++
title = "The cradle"
description = "Find a GPU, run our first C# kernel, and check every result before building on it."
lesson = 1
date = 2026-10-13
draft = false
start_tag = "lesson-00"
end_tag = "lesson-01"
personal_slug = "cradle-01-the-cradle"
publish_assets = []
tags = ["C#", "GPU", "Transformers"]
math = false
+++

I learned top-down recursive-descent parsing from Jack Crenshaw’s [Let’s Build a Compiler!](https://compilers.iecc.com/crenshaw/). I’ve used it many times since, including for a custom color formatter I wrote for a C board that didn’t have one. His approach stayed with me: write a small piece, run it, understand what happened, and extend the same program.

I want to do that here with transformer inference. We’ll build a program that takes a prompt, loads a model’s weights, and generates text. Along the way we’ll write the operations that turn those weights and our input into the next token. We’ll introduce the arithmetic needed to understand each piece as we write it. You don’t need a course in machine learning before starting.

We’ll use C#, and we’ll use the GPU from the beginning. The .NET community includes developers on Windows, Linux, and Mac, so reaching that community means accounting for all three. As we covered in the [prologue](lesson:00), native Metal support on Mac is the reason we’re using a pinned development revision of ILGPU. Keep that revision for this lesson; the examples depend on its API.

Today we’ll add two arrays. That gives us a small enough calculation to check by eye while we establish the whole path: choose a GPU, put data in its buffers, run our code there, and bring the result back. Element-by-element addition will also have a job later, when we connect parts of the transformer through residual connections.

## Start with the program we have

Start from `lesson-00`, the completed prologue. If you’re following with Git and have a clean working tree, create a local branch for your changes:

```sh
git switch -c work/lesson-01 lesson-00
dotnet run --project src/Cradle
```

You should see:

```text
Cradle is ready.
```

If you haven’t prepared the dependencies yet, follow the prologue first. From here on, commands run from the repository root. All our application code stays in `src/Cradle/Program.cs`, inside the existing `Program` class. We’ll add a few static methods, but we don’t yet need another class to manage the GPU for us. I want us to see what it takes to do that job before we package it up.

## Choose what we’re building for

There are two choices involved in running our kernel: the kind of GPU code we build, and the device we run it on. ILGPU calls the first choice a *backend*. The project already defaults to `Metal` on Mac and `CUDA` elsewhere. CUDA is the NVIDIA path; a Windows or Linux machine with another GPU will need a different choice.

This compiler revision builds our application’s kernels for one backend at a time. The device we select must support that backend. Finding a Metal device doesn’t help a program containing CUDA kernels, even though both devices are GPUs. A device exposed through OpenCL is also a different target from one exposed through CUDA, even when they refer to the same physical card.

You can override the project default when building or running. For example, with an appropriate OpenCL device and driver:

```sh
dotnet run --project src/Cradle -p:ILGPUBackend=OpenCL
```

The GPU backend choices in this revision are `CUDA`, `ROCm`, `OpenCL`, and `Metal`. Choose for your device and installed driver, then use that setting on subsequent commands that build, including `dotnet test`. The commands below use the project default to keep them readable. If you chose an override, keep adding it. Passing a different setting with `--no-build` cannot change the kernels in a binary we’ve already built.

We need our running program to know that build-time choice. Open `src/Cradle/Cradle.csproj` and add this line to the existing `ItemGroup`, alongside the ILGPU project reference:

```xml
<AssemblyMetadata Include="ILGPUBackend" Value="$(ILGPUBackend)" />
```

The build writes the value into our application assembly. That avoids maintaining a second, hard-coded backend choice in `Program.cs`.

Add these imports above `namespace Cradle;`:

```csharp
using System;
using System.Reflection;
using ILGPU;
using ILGPU.Runtime;
using ILGPU.Runtime.OpenCL;
```

Then add this method inside `Program`, above `Main`:

```csharp
private static AcceleratorType GetCompiledBackend()
{
    // The project records the same setting used by the kernel compiler.
    var backendName = typeof(Program).Assembly
        .GetCustomAttributes<AssemblyMetadataAttribute>()
        .Single(attribute => attribute.Key == "ILGPUBackend").Value!;

    return Enum.Parse<AcceleratorType>(backendName, ignoreCase: true);
}
```

This reads the metadata we just added and converts its name into ILGPU’s `AcceleratorType`. Now the compiler and device-selection code have the same source for that choice.

## Find a device

Replace the greeting inside `Main` with:

```csharp
var compiledBackend = GetCompiledBackend();
using var context = Context.CreateDefault();

Console.WriteLine("Available devices");
Console.WriteLine($"Compiled kernel backend: {compiledBackend}");
Console.WriteLine();
foreach (var device in context.Devices)
{
    device.PrintInformation(Console.Out);
    Console.WriteLine();
}
```

The context is our entry point into ILGPU. It discovers available devices and owns runtime resources used to work with them. Creating it hasn’t selected a GPU or launched any work.

Run the program again. You should get device information in place of the greeting. Look at the reported backend as well as the device names. A CPU entry is normal: ILGPU can also execute kernels on the CPU. We’re going to select a GPU explicitly.

Add the following after the device loop, still inside `Main`:

```csharp
var preferredDevice = context.Devices
    .Where(device => device.AcceleratorType == compiledBackend)
    .Where(device => device switch
    {
        CLDevice cl =>
            (cl.DeviceType & CLDeviceType.CL_DEVICE_TYPE_GPU) != 0,

        _ => device.AcceleratorType is
            AcceleratorType.Cuda or
            AcceleratorType.ROCm or
            AcceleratorType.Metal
    })
    .OrderByDescending(device => device.MemorySize)
    .FirstOrDefault();

if (preferredDevice is null)
{
    Console.Error.WriteLine(
        $"No GPU compatible with the compiled {compiledBackend} backend was found.");
    Console.Error.WriteLine(
        "Check your GPU driver, or rebuild for its backend with -p:ILGPUBackend=CUDA, ROCm, OpenCL, or Metal.");
    Environment.ExitCode = 1;
    return;
}

using var accelerator = preferredDevice.CreateAccelerator(context);

Console.WriteLine("Selected accelerator");
accelerator.PrintInformation(Console.Out);
```

The first filter matches the backend. The second keeps GPU devices. OpenCL needs an extra check because an OpenCL device can be a CPU; its device-type flags tell us which it is. If several GPUs qualify, we pick the one reporting the most memory. That is a simple selection rule, not a claim that it will be the fastest.

The device describes hardware ILGPU found. The *accelerator* is our working connection to that device: through it we can obtain streams, allocate memory, and launch work. Thinking of it as a handle to the GPU is useful, provided we remember that it owns resources and must be disposed. The `using` declarations handle that, disposing the accelerator before the context when `Main` ends.

Run again and check the selected accelerator. On my Mac, this selects the Apple M3 Max through Metal. If your program reports that no compatible GPU was found, compare the compiled backend with the devices listed above it. Correct the backend or driver before going further. We don’t silently fall back to the CPU, because this exercise needs to establish that our kernel actually runs on the GPU.

## Give it something to add

After printing the selected accelerator, add two ordinary C# arrays and the answer we expect:

```csharp
var array1 = new float[] { 1.5f, 2.0f, 3.2f };
var array2 = new float[] { 2.1f, 4.2f, 3.0f };
var expected = new float[] { 3.6f, 6.2f, 6.2f };
```

At index zero we want `1.5 + 2.1`; at index one, `2.0 + 4.2`; at index two, `3.2 + 3.0`. Each answer is independent of the others. That makes this a useful first parallel operation: no invocation has to wait for another invocation’s answer.

These arrays live on the host, in memory managed by .NET. They are one-dimensional because our operation has one index. Later we’ll give flat buffers rows, columns, and other shapes. For now, adding a second dimension would give us another thing to explain without changing the calculation.

We use `float`, the 32-bit floating-point type. GPU kernel code has restrictions that ordinary C# code doesn’t: we can’t send an arbitrary object graph to the GPU and expect it to run there. ILGPU’s buffer allocations require unmanaged element types, and the backend must support the operations we perform on those types. The `float` addition we need here is supported across our CUDA, ROCm, OpenCL, and Metal backends.

Next, allocate three buffers:

```csharp
var stream = accelerator.DefaultStream;
using var buffer1 = stream.Allocate1D<float>(array1.Length);
using var buffer2 = stream.Allocate1D<float>(array2.Length);
using var outputBuffer = stream.Allocate1D<float>(array1.Length);
```

A stream orders work submitted to the accelerator. We’ll use its default stream throughout this lesson. The accelerator owns that stream; we’re borrowing it. The buffers have their own `using` declarations and will be disposed before the accelerator.

Notice that allocating the input buffers hasn’t copied the arrays. We have reserved space for three floats in each buffer. Put the upload immediately after the allocations:

```csharp
buffer1.CopyFromCPU(array1);
buffer2.CopyFromCPU(array2);
```

We don’t upload anything to `outputBuffer`. Our kernel will write every element before we read it. We also don’t need to allocate a host output array yet; the readback call will give us one.

If you’re consulting the online ILGPU tutorials, this is one place where their examples differ from our pinned revision. They show allocation through the accelerator. Here, `Allocate1D` belongs to the stream. The [allocation methods in the pinned source](https://github.com/m4rs-mt/ILGPU/blob/24cb87d6669c177428bd4ef1b8d05d9652b21c4b/Src/ILGPU/Runtime/AcceleratorStream.Allocations.cs) are the reference for the API we’re using.

## Write the kernel

Add this method at the top of the `Program` class, before our other methods:

```csharp
private static void Kernel(
    Index1D i,
    ArrayView<float> input1,
    ArrayView<float> input2,
    ArrayView<float> output)
{
    output[i] = input1[i] + input2[i];
}
```

That assignment is the whole calculation. A *kernel* is the function we arrange to execute across many GPU invocations. Each invocation receives an index, and this one uses its index to read two values and write their sum.

`ArrayView<float>` lets the kernel access a buffer’s elements. The view describes existing storage; creating one doesn’t allocate or copy another array. The buffer owns the memory, which is why we keep it alive through execution and readback.

There’s no loop here. We’ll ask ILGPU to launch an invocation for each array element. For our three-element input, the useful indices are zero, one, and two. Those invocations can run independently because each writes a different output element. We make no assumption about their execution order.

## Launch and read back

Return to `Main`. Immediately after the two uploads, add:

```csharp
stream.Launch(
    (Index1D)array1.Length,
    i => Kernel(i, buffer1.View, buffer2.View, outputBuffer.View)
);

stream.Synchronize();

var result = outputBuffer.GetAsArray1D();

Console.WriteLine("Results");
Console.WriteLine($"Actual:   {string.Join(", ", result)}");
Console.WriteLine($"Expected: {string.Join(", ", expected)}");
```

The first argument to `Launch` is the extent: how many elements we want to process. The lambda supplies the operation and the views it needs. Although this looks like an ordinary C# lambda call, our build integration gives it a different job.

During the build, ILGPU’s compiler finds the launch, translates the kernel, and generates the launch code. It writes generated files under `obj`; it doesn’t rewrite our source file. That is why there is no separate call here to compile a kernel through the accelerator, as older ILGPU examples show. On Metal, the build embeds shader source that Metal compiles for the GPU at runtime.

Launching work doesn’t mean the GPU has finished it by the time the next C# statement runs. `Synchronize` waits for the stream’s work to finish. Then `GetAsArray1D` reads the output into a managed array that we can inspect on the CPU. We now have an explicit path from our two host arrays, through GPU execution, back to ordinary C# values.

Run it:

```sh
dotnet run --project src/Cradle
```

After the device information, the result should be:

```text
Results
Actual:   3.6, 6.2, 6.2
Expected: 3.6, 6.2, 6.2
```

Your locale may format decimal numbers differently. If you’re using Metal, this pinned compiler also emits warnings about embedded shader source and a generated member hiding an inherited member. Those don’t prevent this kernel from building and running. We’ll return to what produces them and how to address them in a later installment. The finished cradle should build without warnings; for now, these two come from the compiler’s generated code.

## Make the program check its answer

Looking at three numbers is manageable. It won’t be enough once we’re working with thousands, and a program that prints a wrong answer should report failure.

Add this static method above `Main`:

```csharp
private static bool CheckResults(float[] result, float[] expected)
{
    if (result.Length != expected.Length)
    {
        Console.Error.WriteLine(
            $"Expected {expected.Length} results, got {result.Length}.");
        return false;
    }

    for (int i = 0; i < expected.Length; i++)
    {
        if (!float.IsFinite(result[i]) ||
            MathF.Abs(result[i] - expected[i]) > 0.00001f)
        {
            Console.Error.WriteLine(
                $"Element {i}: expected {expected[i]}, got {result[i]}");
            return false;
        }
    }

    return true;
}
```

Decimal fractions don’t all have exact binary floating-point representations, so we allow a small absolute difference for these sums. The `0.00001f` tolerance is for this example, not a rule we’ll apply blindly to every operation in the series. We also reject infinities and `NaN`. Without the finite check, a `NaN` could slip through because comparing its absolute difference with our tolerance doesn’t produce `true`.

After printing the actual and expected arrays, add:

```csharp
if (!CheckResults(result, expected))
{
    Environment.ExitCode = 1;
    return;
}

Console.WriteLine($"All {result.Length} results match.");
Console.WriteLine();
```

Run again. You should now get `All 3 results match.` Try temporarily changing the first expected value to `3.7f`. The program should identify element zero as wrong and exit with a failure code. Put the expected value back before continuing. We want to know that our check can complain as well as agree.

## Cross a group boundary

Three elements let us follow every sum. Now let’s give the GPU enough work to cover more than a tiny launch, with a length that doesn’t divide neatly into the groups of threads it uses.

Replace the three array declarations with this input preparation:

```csharp
const int count = 1031;
var array1 = new float[count];
var array2 = new float[count];
var expected = new float[count];

for (int i = 0; i < count; i++)
{
    array1[i] = i;
    array2[i] = 2 * i;
    expected[i] = 3 * i;
}
```

Keep the allocation, upload, kernel, launch, and readback code as it is. We’ve only changed the inputs. The answer at index `i` is `i + 2 * i`, so we can prepare the expected array independently on the CPU. These small integer values are exactly representable as floats.

GPUs execute work in groups of threads. ILGPU chooses the group size for this launch, and 1,031 leaves a partially filled final group for the usual group sizes. The last valid index is 1,030, where the answer should be 3,090. Checking that far end matters: a kernel that gets its first few answers right could still miss the tail.

Our kernel doesn’t contain an explicit bounds check because this one-dimensional `Launch` overload provides one before calling it. You can see that check in the [pinned launcher source](https://github.com/m4rs-mt/ILGPU/blob/24cb87d6669c177428bd4ef1b8d05d9652b21c4b/Src/ILGPU/Runtime/AcceleratorStream.Launchers.cs). Threads beyond the requested extent return without calling our function. We’re relying on that particular launch API, not assuming every way of launching a GPU kernel protects its bounds.

Printing 1,031 numbers would hide more than it tells us. Replace the two lines that print the arrays with:

```csharp
Console.WriteLine("First 8 values:");
Console.WriteLine($"Actual:   {string.Join(", ", result.Take(8))}");
Console.WriteLine($"Expected: {string.Join(", ", expected.Take(8))}");
Console.WriteLine();
```

`CheckResults` still examines every element. Run again and expect:

```text
Results
First 8 values:
Actual:   0, 3, 6, 9, 12, 15, 18, 21
Expected: 0, 3, 6, 9, 12, 15, 18, 21

All 1031 results match.
```

## Give the output some space

We now have three kinds of output mixed together: available devices, the selected accelerator, and results. Before leaving this file, add one small helper above `Main` to separate them:

```csharp
private static void WriteSection(string title)
{
    Console.WriteLine();
    if (Console.IsOutputRedirected)
    {
        Console.WriteLine($"--- {title} ---");
    }
    else
    {
        var previousColor = Console.ForegroundColor;
        try
        {
            Console.ForegroundColor = ConsoleColor.Cyan;
            Console.WriteLine($"--- {title} ---");
        }
        finally
        {
            Console.ForegroundColor = previousColor;
        }
    }
    Console.WriteLine();
}
```

Replace the three `Console.WriteLine` calls that print `Available devices`, `Selected accelerator`, and `Results` with calls to `WriteSection`, keeping the same strings. That gives each section a little space and a colored divider in an interactive terminal, with plain output when redirected. The calculation hasn’t changed.

## Check what the build produced

We’ve checked the numerical result on our GPU. There is one more useful check to keep alongside it: did the application build actually include generated kernels for the backend its device-selection code expects?

Add `tests/Cradle.Tests/KernelBuildTests.cs`:

```csharp
using System.Reflection;
using ILGPU.Runtime;
using Xunit;

namespace Cradle.Tests;

public class KernelBuildTests
{
    [Fact]
    public void GeneratedKernelsMatchTheBackendRecordedForDeviceSelection()
    {
        var application = Assembly.Load("Cradle");
        var backendName = application.GetCustomAttributes<AssemblyMetadataAttribute>()
            .Single(attribute => attribute.Key == "ILGPUBackend").Value!;
        var expected = Enum.Parse<AcceleratorType>(backendName, ignoreCase: true);
        var kernels = application.GetTypes()
            .Where(type => typeof(ICompiledKernelKind).IsAssignableFrom(type))
            .ToArray();

        Assert.NotEmpty(kernels);
        foreach (var kernel in kernels)
        {
            var backend = kernel.GetProperty("GeneralAcceleratorType",
                BindingFlags.Public | BindingFlags.Static | BindingFlags.DeclaredOnly);
            Assert.NotNull(backend);
            Assert.Equal(expected, Assert.IsType<AcceleratorType>(backend.GetValue(null)));
        }
    }
}
```

ILGPU marks its generated kernel types with `ICompiledKernelKind`. This test finds those types in the application assembly, requires at least one, and checks their backend against the metadata we added earlier. Looking in the assembly matters: generated files sitting under `obj` wouldn’t prove they made it into the executable.

This test doesn’t select a device or execute a GPU kernel, so it can run on a machine without a GPU. It checks the build’s output; the program’s numerical check exercises the GPU path.

In the existing `BaselineTests.cs`, replace the comment about GPU discovery and numerical checks arriving with the first kernel with:

```csharp
// This check does not discover devices or execute GPU work.
```

That original test still checks that the runtime dependency reaches the test host. Run both tests, then the program:

```sh
dotnet test Cradle.slnx -c Release --no-restore
dotnet run --project src/Cradle -c Release --no-build --no-restore
```

If you use a backend override, put it on the `dotnet test` command that builds the application. The following `--no-build` run uses that binary. Expect two passing tests and all 1,031 GPU results matching.

The prologue already supplied the broader repository check:

```sh
python3 scripts/check_dotnet.py
```

It runs the same build checks as CI, including building for each backend and running the CPU-side tests. It finishes by restoring the platform’s default build. You don’t need a new workflow or another set of support files for this lesson. Use the ordinary `dotnet run` command, with your backend override if needed, to check execution on your GPU afterward.

## Where the cradle stands

We started with a greeting. We now have our own C# function running on the GPU, with 1,031 answers checked against values we calculated independently. The kernel itself is one line. Getting its inputs into the right memory, launching it on a compatible device, and knowing when we can read the answer accounts for much of the work around it. We’ll use that machinery throughout the series.

Before moving on, try changing `count` to 1,024, then 1,025. Both should pass without changing the kernel or its launch. Our program asks for a number of elements; ILGPU arranges the groups and protects the boundary. Put it back to 1,031 when you’re done. The [completed `lesson-01` snapshot](https://github.com/plainsight-systems/cradle/blob/lesson-01/src/Cradle/Program.cs) is there if you want to compare your version.

Next we need to give those numbers some structure. A transformer works with vectors and matrices, and a flat buffer doesn’t tell us how many rows it holds or where a row begins. We’ll add that information, work out how it maps to the indices our kernels use, and give the buffers a home outside `Program.cs`. Keep this program handy. We’ll build that next piece into the cradle we’ve just got working.
