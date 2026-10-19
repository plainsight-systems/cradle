using System.Reflection;
using ILGPU;
using ILGPU.Runtime;
using ILGPU.Runtime.OpenCL;

namespace Cradle;

internal sealed class GpuRuntime : IDisposable
{
    private GpuRuntime(Context context, Accelerator accelerator)
    {
        Context = context;
        Accelerator = accelerator;
    }

    public static AcceleratorType CompiledBackend { get; } = GetCompiledBackend();

    public Context Context { get; }

    public Accelerator Accelerator { get; }

    private const string ILGPUBackend = nameof(ILGPUBackend);

    private static AcceleratorType GetCompiledBackend()
    {
        // The project records the same setting used by the kernel compiler.
        var backendName = typeof(GpuRuntime).Assembly
            .GetCustomAttributes<AssemblyMetadataAttribute>()
            .Single(attribute => attribute.Key == ILGPUBackend).Value!;

        return Enum.Parse<AcceleratorType>(backendName, ignoreCase: true);
    }

    private static Device? PreferredDevice(Context c) =>
        c.Devices
            .Where(device => device.AcceleratorType == CompiledBackend)
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

    public static GpuRuntime Create()
    {
        var context = ILGPU.Context.CreateDefault();
        try
        {
            var preferredDevice = PreferredDevice(context);

            if (preferredDevice is null)
            {
                var errorMessage =
                    $"No GPU compatible with the compiled {CompiledBackend} backend was found. Check your GPU driver, or rebuild for its backend with -p:ILGPUBackend=CUDA, ROCm, OpenCL, or Metal.";
                throw new InvalidOperationException(errorMessage);
            }

            var accelerator = preferredDevice.CreateAccelerator(context);

            return new GpuRuntime(context, accelerator);
        }
        catch
        {
            context.Dispose();
            throw;
        }
    }

    public void Dispose()
    {
        try
        {
            Accelerator.Dispose();
        }
        finally
        {
            Context.Dispose();
        }
    }
}
