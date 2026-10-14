using System;
using System.Reflection;
using ILGPU;
using ILGPU.Runtime;
using ILGPU.Runtime.OpenCL;

namespace Cradle;

internal static class Program
{
    //define the kernel
    private static void Kernel(Index1D i, ArrayView<float> input1, ArrayView<float> input2, ArrayView<float> output)
    {
        output[i] = input1[i] + input2[i];
    }

    private static AcceleratorType GetCompiledBackend()
    {
        // The project records the same setting used by the kernel compiler.
        var backendName = typeof(Program).Assembly
            .GetCustomAttributes<AssemblyMetadataAttribute>()
            .Single(attribute => attribute.Key == "ILGPUBackend").Value!;

        return Enum.Parse<AcceleratorType>(backendName, ignoreCase: true);
    }

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

    private static void Main()
    {
        var compiledBackend = GetCompiledBackend();
        using var context = Context.CreateDefault();

        WriteSection("Available devices");
        Console.WriteLine($"Compiled kernel backend: {compiledBackend}");
        Console.WriteLine();
        foreach(var device in context.Devices)
        {
            device.PrintInformation(Console.Out);
            Console.WriteLine();
        }

        //Selecting device
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

        //If cannot find GPU report and exit
        if (preferredDevice is null)
        {
            Console.Error.WriteLine(
                $"No GPU compatible with the compiled {compiledBackend} backend was found.");
            Console.Error.WriteLine(
                "Check your GPU driver, or rebuild for its backend with -p:ILGPUBackend=CUDA, ROCm, OpenCL, or Metal.");
            Environment.ExitCode = 1;
            return;
        }

        //Get the 'handle' to the actual device: GPU
        using var accelerator = preferredDevice.CreateAccelerator(context);

        WriteSection("Selected accelerator");
        accelerator.PrintInformation(Console.Out);

        // Use an awkward length to exercise a partially filled final threadgroup.
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

        //Allocate 3 buffers, 2 for input and 1 for the result
        var stream = accelerator.DefaultStream;
        using var buffer1 = stream.Allocate1D<float>(array1.Length);
        using var buffer2 = stream.Allocate1D<float>(array2.Length);
        using var outputBuffer = stream.Allocate1D<float>(array1.Length);

        //copy input arrays into the buffers
        buffer1.CopyFromCPU(array1);
        buffer2.CopyFromCPU(array2);

        // Launch one kernel invocation per array element
        stream.Launch(
            (Index1D)array1.Length,
            i => Kernel(i, buffer1.View, buffer2.View, outputBuffer.View)
        );

        stream.Synchronize();

        var result = outputBuffer.GetAsArray1D();

        WriteSection("Results");
        Console.WriteLine("First 8 values:");
        Console.WriteLine($"Actual:   {string.Join(", ", result.Take(8))}");
        Console.WriteLine($"Expected: {string.Join(", ", expected.Take(8))}");
        Console.WriteLine();

        if (!CheckResults(result, expected))
        {
            Environment.ExitCode = 1;
            return;
        }

        Console.WriteLine($"All {result.Length} results match.");
        Console.WriteLine();
    }
}
