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
