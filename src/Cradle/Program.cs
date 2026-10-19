using ILGPU;
using ILGPU.Runtime;

namespace Cradle;

internal static class Program
{
    private static void AddMatrices(
        Index2D index,
        int columns,
        ArrayView<float> left,
        ArrayView<float> right,
        ArrayView<float> output)
    {
        var row = index.X;
        var column = index.Y;
        var offset = row * columns + column;

        output[offset] = left[offset] + right[offset];
    }

    private static bool CheckResults(Matrix result, Matrix expected)
    {
        const float tolerance = 0.00001f;

        if (result.Rows != expected.Rows ||
            result.Columns != expected.Columns)
        {
            Console.Error.WriteLine(
                $"Expected {expected.Rows}x{expected.Columns}, " +
                $"got {result.Rows}x{result.Columns}.");
            return false;
        }

        for (int row = 0; row < expected.Rows; row++)
        {
            for (int column = 0; column < expected.Columns; column++)
            {
                var actualValue = result[row, column];
                var expectedValue = expected[row, column];

                if (!float.IsFinite(actualValue) ||
                    !float.IsFinite(expectedValue) ||
                    MathF.Abs(actualValue - expectedValue) > tolerance)
                {
                    Console.Error.WriteLine(
                        $"Element [{row}, {column}]: " +
                        $"expected {expectedValue}, got {actualValue}.");
                    return false;
                }
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
        try
        {
            using var gpu = GpuRuntime.Create();
            var accelerator = gpu.Accelerator;

            WriteSection("Selected GPU");
            Console.WriteLine($"GPU: {accelerator.Name} ({GpuRuntime.CompiledBackend})");

            var left = Matrix.FromArray(2, 3,
            [
                1, 2, 3,
                4, 5, 6
            ]);

            var right = Matrix.FromArray(2, 3,
            [
                10, 20, 30,
                40, 50, 60
            ]);

            var expected = left + right;

            var stream = accelerator.DefaultStream;

            // Allocate and upload the inputs; the kernel fills the output buffer.
            using var leftBuffer = stream.Allocate1D((float[])left);
            using var rightBuffer = stream.Allocate1D((float[])right);
            using var outputBuffer = stream.Allocate1D<float>(left.Length);

            // Launch one kernel invocation per matrix element.
            stream.Launch(
                new Index2D(left.Rows, left.Columns),
                index => AddMatrices(
                    index, left.Columns,
                    leftBuffer.View, rightBuffer.View, outputBuffer.View)
            );

            stream.Synchronize();

            var actual = Matrix.FromArray(
                left.Rows, left.Columns, outputBuffer.GetAsArray1D());

            if (!CheckResults(actual, expected))
            {
                Environment.ExitCode = 1;
                return;
            }

            WriteSection("Results");
            Console.WriteLine($"Shape: {actual.Rows}x{actual.Columns}");
            Console.WriteLine($"Actual:   {string.Join(", ", actual)}");
            Console.WriteLine($"Expected: {string.Join(", ", expected)}");
            Console.WriteLine();
            Console.WriteLine($"All {actual.Length} matrix elements match.");
        }
        catch (InvalidOperationException e)
        {
            Console.Error.WriteLine(e.Message);
            Environment.ExitCode = 1;
        }
    }
}
