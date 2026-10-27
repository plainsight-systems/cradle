using ILGPU;
using ILGPU.Runtime;

namespace Cradle;

internal static class Program
{
    private static void MultiplyMatrices(
        Index2D index,
        int sharedDimensions,
        int rightColumns,
        ArrayView<float> left,
        ArrayView<float> right,
        ArrayView<float> output)
    {
        float sum = 0;

        for (int i = 0; i < sharedDimensions; i++)
        {
            var leftElement = left[index.X * sharedDimensions + i];
            var rightElement = right[i * rightColumns + index.Y];
            sum += leftElement * rightElement;
        }

        output[index.X * rightColumns + index.Y] = sum;
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

    private static bool RunMultiplication(
        AcceleratorStream stream, Matrix left, Matrix right)
    {
        var expected = left * right;

        // Allocate and upload the inputs; the kernel fills the output buffer.
        using var leftBuffer = stream.Allocate1D((float[])left);
        using var rightBuffer = stream.Allocate1D((float[])right);
        using var outputBuffer = stream.Allocate1D<float>(expected.Length);

        // Launch one kernel invocation per output element.
        stream.Launch(
            new Index2D(expected.Rows, expected.Columns),
            index => MultiplyMatrices(
                index, left.Columns, right.Columns,
                leftBuffer.View, rightBuffer.View, outputBuffer.View)
        );

        stream.Synchronize();

        var actual = Matrix.FromArray(
            expected.Rows, expected.Columns, outputBuffer.GetAsArray1D());

        if (!CheckResults(actual, expected))
        {
            return false;
        }

        Console.WriteLine($"Shape: {actual.Rows}x{actual.Columns}");
        Console.WriteLine($"Actual:   {string.Join(", ", actual)}");
        Console.WriteLine($"Expected: {string.Join(", ", expected)}");
        Console.WriteLine();
        Console.WriteLine($"All {actual.Length} matrix elements match.");

        return true;
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

            var right = Matrix.FromArray(3, 2,
            [
                7, 8,
                9, 10,
                11, 12
            ]);

            var stream = accelerator.DefaultStream;

            WriteSection("Matrix multiplication");
            if (!RunMultiplication(stream, left, right))
            {
                Environment.ExitCode = 1;
                return;
            }

            var vector = Matrix.FromArray(3, 1,
            [
                1,
                2,
                3
            ]);

            WriteSection("Matrix-vector multiplication");
            if (!RunMultiplication(stream, left, vector))
            {
                Environment.ExitCode = 1;
                return;
            }
        }
        catch (InvalidOperationException e)
        {
            Console.Error.WriteLine(e.Message);
            Environment.ExitCode = 1;
        }
    }
}
