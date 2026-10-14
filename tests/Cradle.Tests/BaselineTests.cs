using System.Reflection;
using Xunit;

namespace Cradle.Tests;

public class BaselineTests
{
    [Fact]
    public void RuntimeDependencyLoadsWithoutRequiringAGpu()
    {
        // Loading the runtime proves the source dependency reaches the test host.
        // This check does not discover devices or execute GPU work.
        var runtime = Assembly.Load("ILGPU");
        Assert.NotNull(runtime.GetType("ILGPU.Runtime.Accelerator", throwOnError: true));
    }
}
