+++
title = "Buffers and shapes"
description = "Give our data rows and columns, make ownership explicit, and add matrices on the GPU."
lesson = 2
date = 2026-10-18
draft = false
start_tag = "lesson-01"
end_tag = "lesson-02"
personal_slug = "cradle-02-buffers-and-shapes"
publish_assets = []
tags = ["C#", "GPU", "Transformers"]
math = false
+++

In [the last installment](lesson:01), we got a C# kernel running on the GPU and checked all 1,031 answers. The data was a pair of flat arrays. Each invocation took two values at the same position, added them, and wrote the result back at that position.

A transformer will need more structure than that. A matrix has rows and columns, and the operations we write need to know where one row ends and the next begins. Six values could describe two rows of three or three rows of two. An array’s length cannot tell us which we meant.

Today we’ll give those values a shape and use it all the way through the program: preparing inputs, allocating GPU buffers, launching a kernel, and checking the answer. We’ll also move device setup out of `Program.cs`, so it stops taking up half the file every time we want to do some arithmetic.

## Pick up the cradle

Start from `lesson-01`. With a clean working tree, create a local branch and run the program before changing it:

```sh
git switch -c work/lesson-02 lesson-01
dotnet run --project src/Cradle
```

You should still see `All 1031 results match.` Keep the dependency pin and build settings from the previous lesson. If you selected a backend with something like `-p:ILGPUBackend=OpenCL`, keep passing that setting on commands that build. The backend compiled into the application must still match the device we select.

## Give the runtime an owner

Our context discovers devices and holds ILGPU runtime resources. The accelerator is our working connection to the selected GPU. Both need to remain alive while we use the buffers, and both need to be disposed afterward.

Those two resources belong together. Put the following in a new `src/Cradle/GpuRuntime.cs`, in the same `Cradle` namespace as `Program`:

```csharp
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
```

Most of this is code we already had. `GetCompiledBackend` reads the assembly metadata, and `PreferredDevice` applies the same backend and GPU filters before choosing the qualifying device with the most memory. Moving those methods does not change how we select hardware.

`CompiledBackend` is a static, get-only property because it describes the application we built. Creating another runtime cannot change the backend in that assembly. Its initializer reads the setting once; there is no need for each instance to read it again. The `ILGPUBackend` constant uses `nameof` to supply the exact metadata key declared in the project file. Keep that spelling aligned with the project setting.

The new part is ownership. I want resource acquisition to be an explicit operation, so the public entry point is `GpuRuntime.Create()`. The private constructor only assigns resources that have already been acquired. We can read `Create` from top to bottom: create the context, select a device, create its accelerator, and return an owner for both.

If anything after context creation fails, the `catch` disposes that context and rethrows the exception. There would be no successfully returned runtime for the caller to dispose. Catching every exception here matters because backend initialization can fail with exceptions other than `InvalidOperationException`.

On normal disposal, the accelerator goes first. The `finally` ensures that we also attempt to release the context if accelerator disposal throws. The class is sealed and owns disposable objects, so this is all the disposal machinery we need here.

In `Program.cs`, remove `GetCompiledBackend` and the device setup and reporting at the start of `Main`, up to the array preparation. Replace that setup with:

```csharp
using var gpu = GpuRuntime.Create();
var accelerator = gpu.Accelerator;

WriteSection("Selected GPU");
Console.WriteLine($"GPU: {accelerator.Name} ({GpuRuntime.CompiledBackend})");
```

The local `accelerator` is a borrowed reference. Its owner is `gpu`, so it no longer gets its own `using` declaration. Keep the buffer `using` declarations later in the method. They will dispose the buffers before the runtime releases the accelerator and context.

Wrap the body of `Main` in a `try` and add this catch after it:

```csharp
catch (InvalidOperationException e)
{
    Console.Error.WriteLine(e.Message);
    Environment.ExitCode = 1;
}
```

This preserves a readable error and a failing exit code when no compatible GPU is found. The runtime handles resource cleanup; `Program` handles how that failure is presented. Remove the now-unused reflection and OpenCL imports. The imports left in `Program.cs` can be:

```csharp
using ILGPU;
using ILGPU.Runtime;
```

The project supplies the usual `System` imports implicitly. Leave the old arrays, kernel, and result check alone for this step, then run it. You should get the same 1,031 matching answers with a much shorter device report. We have moved responsibility without changing the calculation.

## Six values, two rows

Here is the next calculation:

```text
 1   2   3       10  20  30       11  22  33
 4   5   6   +   40  50  60   =   44  55  66
```

Each matrix has two rows and three columns. Addition still pairs corresponding elements, so each GPU invocation can calculate one answer independently. What changes is how we describe a position.

Both row and column numbering start at zero. Labeling the first matrix makes the positions easier to see:

```text
         column 0   column 1   column 2
row 0        1          2          3
row 1        4          5          6
```

Row 1, column 2 contains the value 6. We’ll store these values in one contiguous array, with all of row 0 followed by all of row 1. This is called *row-major* storage:

```text
array index:   0   1   2   3   4   5
stored value:  1   2   3   4   5   6
```

To find row 1, column 2 in that array, skip the three elements in row 0, then move two positions into row 1. That gives us array index 5. The value stored at that index is 6. Once we add our matrix indexer, `matrix[1, 2]` will reach the same element as the underlying array’s `[5]`.

The general calculation is:

```text
offset = row * columns + column
```

Here, `columns` is the total number of columns (3), while `column` is the zero-based position within the row (2). The result, `1 * 3 + 2 = 5`, is an offset measured in array elements: it tells us where to read the value. This one calculation is enough for our contiguous matrices; we can introduce more general layouts when an operation needs them.

## A matrix on the CPU

The shape and its values need a home. We’ll use a `Matrix` class that owns a managed `float[]`, knows its dimensions, and provides ordinary C# indexing and arithmetic. The caller will continue to own GPU allocations and transfers.

That division keeps the movement of data visible. Constructing a matrix prepares CPU data. Allocating an ILGPU buffer reserves GPU storage. An upload moves values between them. We should be able to point to each of those operations in the program.

Start with storage, shape, and indexing. Put this in `src/Cradle/Matrix.cs`:

```csharp
namespace Cradle;

/// <summary>
/// A CPU matrix stored row by row in a contiguous float array.
/// Dimensions are fixed; elements can be changed through the indexer.
/// </summary>
public sealed class Matrix
{
    private const string ValuesMustMatchShape =
        "The number of values must equal rows multiplied by columns.";

    private readonly float[] _values;

    private Matrix(int rows, int columns, float[] values)
    {
        Rows = rows;
        Columns = columns;
        _values = values;
    }

    public int Rows { get; }
    public int Columns { get; }
    public int Length => _values.Length;

    public float this[int row, int column]
    {
        get => _values[GetIndex(row, column)];
        set => _values[GetIndex(row, column)] = value;
    }

    public static Matrix Create(int rows, int columns)
    {
        var length = GetLength(rows, columns);
        return new Matrix(rows, columns, new float[length]);
    }

    /// <summary>Copies row-major values into storage owned by the matrix.</summary>
    public static Matrix FromArray(int rows, int columns, float[] values)
    {
        ArgumentNullException.ThrowIfNull(values);
        var length = GetLength(rows, columns);
        if (values.Length != length)
            throw new ArgumentException(ValuesMustMatchShape, nameof(values));

        return new Matrix(rows, columns, (float[])values.Clone());
    }

    private int GetIndex(int row, int column)
    {
        ArgumentOutOfRangeException.ThrowIfNegative(row);
        ArgumentOutOfRangeException.ThrowIfGreaterThanOrEqual(row, Rows);
        ArgumentOutOfRangeException.ThrowIfNegative(column);
        ArgumentOutOfRangeException.ThrowIfGreaterThanOrEqual(column, Columns);
        return row * Columns + column;
    }

    private static int GetLength(int rows, int columns)
    {
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(rows);
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(columns);
        return checked(rows * columns);
    }
}
```

This is a complete class we can compile and use now. `Rows` and `Columns` are fixed after construction, while the elements can change through the indexer. `Length` is the total number of values, which we’ll need when allocating a buffer.

`Create` gives us zero-filled storage. `FromArray` takes existing row-major values, checks the count, and copies them into storage owned by the matrix. Both dimensions must be positive. `checked` makes an overflowing element count throw instead of wrapping into some unrelated value.

The indexer checks each coordinate before flattening it. In our two-by-three matrix, `[0, 3]` is invalid, even though its calculated array index of 3 would land inside the storage. It would select the first element of the next row. Likewise, `[1, -1]` would select a valid element in the preceding row. A flat array bounds check cannot catch those mistakes for us.

Let’s check those decisions while they’re the only things this class does. Create `tests/Cradle.Tests/MatrixTests.cs`:

```csharp
using Xunit;

namespace Cradle.Tests;

public class MatrixTests
{
    [Fact]
    public void RectangularMatrixUsesRowMajorIndexing()
    {
        var values = new float[] { 1, 2, 3, 4, 5, 6 };
        var matrix = Matrix.FromArray(2, 3, values);

        Assert.Equal(6, matrix.Length);
        Assert.Equal(3f, matrix[0, 2]);
        Assert.Equal(4f, matrix[1, 0]);
        Assert.Equal(6f, matrix[1, 2]);
    }


    [Theory]
    [InlineData(0, 3)]
    [InlineData(1, -1)]
    [InlineData(2, 0)]
    [InlineData(-1, 0)]
    public void IndexerRejectsCoordinatesEvenWhenFlatIndexWouldBeValid(int row, int column)
    {
        var matrix = Matrix.Create(2, 3);

        Assert.Throws<ArgumentOutOfRangeException>(() => matrix[row, column]);
        Assert.Throws<ArgumentOutOfRangeException>(() => matrix[row, column] = 99);
        for (int r = 0; r < matrix.Rows; r++)
        {
            for (int c = 0; c < matrix.Columns; c++)
                Assert.Equal(0f, matrix[r, c]);
        }
    }


    [Fact]
    public void FactoriesRejectInvalidDimensionsLengthsAndOverflow()
    {
        Assert.Throws<ArgumentOutOfRangeException>(() => Matrix.Create(0, 2));
        Assert.Throws<ArgumentOutOfRangeException>(() => Matrix.Create(2, -1));
        Assert.Throws<OverflowException>(() => Matrix.Create(int.MaxValue, 2));
        Assert.Throws<ArgumentException>(() => Matrix.FromArray(2, 3, new float[5]));
        Assert.Throws<ArgumentNullException>(() => Matrix.FromArray(1, 1, null!));
    }
}
```

The first test checks positions on both sides of the row boundary against values we wrote down ourselves. The theory runs once for each pair of coordinates. It checks both the getter and setter, then confirms that a rejected write left the zero-filled matrix unchanged. The final test checks the factory’s input requirements.

Run the existing test project:

```sh
dotnet test Cradle.slnx -c Release --no-restore
```

Expect eight passing cases: the two tests from earlier lessons and six from this file. Keep your backend override on this command if you use one. These new tests only exercise CPU data; they don’t select a GPU. `Program.cs` still runs the addition from lesson 1.

Before going further, try removing the upper-bound check on `column` in `GetIndex` and run the tests again. The `[0, 3]` case should fail because the getter accepts that invalid coordinate. Restore the check and get all eight cases passing again. We now have a test that catches exactly the row-boundary mistake we were concerned about.

## Copy values, or borrow them

We’ll need to supply the matrix’s values to ILGPU without exposing its owned array for arbitrary changes. Add these members inside `Matrix`:

```csharp
public Matrix Clone() => new(Rows, Columns, ToArray());

/// <summary>Returns an independent copy of the row-major values.</summary>
public float[] ToArray() => (float[])_values.Clone();

/// <summary>
/// Borrows the CPU storage without copying. Later element changes are visible
/// through this span. This does not allocate GPU memory or transfer data.
/// </summary>
public ReadOnlySpan<float> AsReadOnlySpan() => _values;

/// <summary>Copies the values to an array; shape information is not retained.</summary>
public static explicit operator float[](Matrix matrix)
{
    ArgumentNullException.ThrowIfNull(matrix);
    return matrix.ToArray();
}
```

`ToArray` and the explicit cast both return independent copies. The cast will let us supply a matrix directly at an API boundary that expects `float[]`, while keeping the conversion visible in the call. The resulting array has values but no row or column information.

`Clone` copies the whole matrix. Ordinary assignment still copies a reference, so `var other = matrix` would give us two names for the same mutable object. C# has no copy-assignment operator for us to override.

`AsReadOnlySpan` is the borrowing option. It gives CPU code a read-only view without allocating another array. Read-only describes access through that view: later changes made through the matrix’s indexer will still be visible through the span.

We can make that distinction observable. Add this test inside `MatrixTests`:

```csharp
[Fact]
public void CopiesAreIndependentWhileReadOnlySpanBorrowsStorage()
{
    var source = new float[] { 1, 2, 3, 4 };
    var matrix = Matrix.FromArray(2, 2, source);
    source[0] = 99;
    Assert.Equal(1f, matrix[0, 0]);

    var clone = matrix.Clone();
    var array = matrix.ToArray();
    var converted = (float[])matrix;
    var borrowed = matrix.AsReadOnlySpan();
    matrix[0, 0] = 10;

    Assert.Equal(1f, clone[0, 0]);
    Assert.Equal(1f, array[0]);
    Assert.Equal(1f, converted[0]);
    Assert.Equal(10f, borrowed[0]);
    converted[1] = 99;
    Assert.Equal(2f, matrix[0, 1]);
}
```

Changing the original source array must not change the matrix. Changing the matrix must leave the clone and copied arrays alone, while the borrowed span sees the update. Changing the converted array must also leave the matrix alone. These are the ownership rules we’ll rely on when preparing GPU inputs.

Run the same command again:

```sh
dotnet test Cradle.slnx -c Release --no-restore
```

Expect nine passing cases. We’ve checked what a copy means before using one at the upload boundary.

## Add on the CPU first

We need a reference answer to compare with the GPU result. Add this constant alongside `ValuesMustMatchShape`:

```csharp
private const string ShapesMustMatch =
    "Matrix addition requires matching rows and columns.";
```

Then add the addition operator inside `Matrix`:

```csharp
public static Matrix operator +(Matrix left, Matrix right)
{
    ArgumentNullException.ThrowIfNull(left);
    ArgumentNullException.ThrowIfNull(right);
    if (left.Rows != right.Rows || left.Columns != right.Columns)
        throw new ArgumentException(ShapesMustMatch, nameof(right));

    var result = Create(left.Rows, left.Columns);
    for (int row = 0; row < left.Rows; row++)
    {
        for (int column = 0; column < left.Columns; column++)
            result[row, column] = left[row, column] + right[row, column];
    }

    return result;
}
```

The operands must have matching rows and columns. Two-by-three and three-by-two both contain six values, but their corresponding positions differ. Comparing `Length` alone would accept the wrong operation.

The operator allocates a result and leaves both inputs alone. `left + right` here executes on the CPU. Two nested loops visit each position and add its two values.

Before treating that calculation as our reference, check it against answers we know. Add these two tests to `MatrixTests`:

```csharp
[Fact]
public void AdditionProducesKnownValuesWithoutChangingInputs()
{
    var left = Matrix.FromArray(2, 3, new float[] { 1, 2, 3, 4, 5, 6 });
    var right = Matrix.FromArray(2, 3, new float[] { 6, 5, 4, 3, 2, 1 });

    var result = left + right;

    Assert.Equal(2, result.Rows);
    Assert.Equal(3, result.Columns);
    Assert.Equal(new float[] { 7, 7, 7, 7, 7, 7 }, result.ToArray());
    Assert.Equal(1f, left[0, 0]);
    Assert.Equal(6f, right[0, 0]);
    result[0, 0] = 100;
    Assert.Equal(1f, left[0, 0]);
}


[Fact]
public void ShapeMattersEvenWhenElementCountsMatch()
{
    var values = new float[] { 1, 2, 3, 4, 5, 6 };
    var left = Matrix.FromArray(2, 3, values);
    var right = Matrix.FromArray(3, 2, values);

    Assert.Throws<ArgumentException>(() => left + right);
}
```

The first test uses inputs whose corresponding values all add to 7. It checks the result’s shape and values, then verifies that neither input was overwritten and that changing the result leaves the left input alone. The second test gives us two valid matrices with the same element count but different shapes. Their addition must be rejected.

Run the tests:

```sh
dotnet test Cradle.slnx -c Release --no-restore
```

Expect 11 passing cases. We now have a checked CPU addition to compare with the GPU kernel we’ll write below.

## Define equality

We also want to compare matrices as ordinary C# values. Update the class declaration to add `IEquatable<Matrix>`:

```csharp
public sealed class Matrix : IEquatable<Matrix>
```

Keep the existing class body and add these members:

```csharp
/// <summary>
/// Compares shape and elements using float.Equals, without a tolerance.
/// NaNs compare equal to NaNs, and positive and negative zero compare equal.
/// Numerical GPU checks should choose their tolerance separately.
/// </summary>
public bool Equals(Matrix? other)
{
    if (ReferenceEquals(this, other))
        return true;
    if (other is null || Rows != other.Rows || Columns != other.Columns)
        return false;

    for (int i = 0; i < Length; i++)
    {
        if (!_values[i].Equals(other._values[i]))
            return false;
    }

    return true;
}

public override bool Equals(object? obj) => obj is Matrix other && Equals(other);

// Element changes affect the hash: do not mutate a matrix while it is a hash key.
public override int GetHashCode()
{
    var hash = new HashCode();
    hash.Add(Rows);
    hash.Add(Columns);
    foreach (var value in _values)
        hash.Add(value);
    return hash.ToHashCode();
}

public static bool operator ==(Matrix? left, Matrix? right) =>
    ReferenceEquals(left, right) || (left is not null && left.Equals(right));

public static bool operator !=(Matrix? left, Matrix? right) => !(left == right);
```

Equality includes both the shape and every value. The overloads make `==`, `!=`, `Equals`, and `IEquatable<Matrix>` agree, including when one or both operands are null. `GetHashCode` uses the same data. Since the elements are mutable, changing them also changes the hash; don’t mutate a matrix while using it as a dictionary key or a hash-set member.

For the elements we use exact `float.Equals` semantics: no tolerance, `NaN` equals another `NaN`, and positive and negative zero compare equal. Checking numerical GPU results has a different job, so we’ll keep our finite-value and tolerance checks there.

Add this test to `MatrixTests`:

```csharp
[Fact]
public void EqualityAndHashingAgreeIncludingNaNsZerosAndNulls()
{
    var left = Matrix.FromArray(1, 3, new float[] { float.NaN, 0f, 4f });
    var right = Matrix.FromArray(1, 3, new float[] { float.NaN, -0f, 4f });
    Matrix? missing = null;

    Assert.True(left == right);
    Assert.False(left != right);
    Assert.True(((IEquatable<Matrix>)left).Equals(right));
    Assert.True(left.Equals((object)right));
    Assert.Equal(left.GetHashCode(), right.GetHashCode());
    Assert.True(missing == null);
    Assert.False(left == missing);
    Assert.False(missing == left);
    Assert.False(left.Equals(null));
    Assert.False(left.Equals(new object()));

    right[0, 2] = 4.000001f;
    Assert.True(left != right);
}
```

The test starts with two matrices that should compare equal, including the special cases of `NaN` and signed zero. It checks the different equality entry points and matching hashes, then makes a small change that exact equality must detect.

Our existing shape test can now check equality too. In `ShapeMattersEvenWhenElementCountsMatch`, add this immediately before `Assert.Throws`:

```csharp
Assert.False(left == right);
```

That gives us a case where every stored value matches but the shapes differ. Run the tests again:

```sh
dotnet test Cradle.slnx -c Release --no-restore
```

Expect 12 passing cases. The interface and its implementation arrived together, so we could compile and check this addition immediately.

## Walk through the values

For output, we want to use `foreach` and `string.Join` directly on a matrix. Add this import at the top of `Matrix.cs`:

```csharp
using System.Collections;
```

Extend the declaration once more:

```csharp
public sealed class Matrix : IEquatable<Matrix>, IEnumerable<float>
```

Then add the enumeration members:

```csharp
/// <summary>Enumerates elements from left to right, one row at a time.</summary>
public IEnumerator<float> GetEnumerator() =>
    ((IEnumerable<float>)_values).GetEnumerator();

IEnumerator IEnumerable.GetEnumerator() => GetEnumerator();
```

Enumeration follows the underlying array from left to right, row by row. The non-generic implementation delegates to the generic one.

Add `using System.Collections;` to the top of `MatrixTests.cs` as well. Replace our first test, `RectangularMatrixUsesRowMajorIndexing`, with this expanded version:

```csharp
[Fact]
public void RectangularMatrixUsesRowMajorIndexingAndEnumeration()
{
    var values = new float[] { 1, 2, 3, 4, 5, 6 };
    var matrix = Matrix.FromArray(2, 3, values);

    Assert.Equal(6, matrix.Length);
    Assert.Equal(3f, matrix[0, 2]);
    Assert.Equal(4f, matrix[1, 0]);
    Assert.Equal(6f, matrix[1, 2]);
    Assert.Equal(values, matrix.ToList());
    Assert.Equal(values, ((IEnumerable)matrix).Cast<float>().ToList());
}
```

The two added assertions check the order through both enumeration interfaces against the original six values. In `IndexerRejectsCoordinatesEvenWhenFlatIndexWouldBeValid`, we can now replace the nested loops at the end with:

```csharp
Assert.All(matrix, value => Assert.Equal(0f, value));
```

It checks the same zero-filled storage through our new enumeration support. Run the tests once more:

```sh
dotnet test Cradle.slnx -c Release --no-restore
```

The count stays at 12 because we extended existing tests. We’ve now checked storage, coordinates, copying, addition, equality, and iteration as we introduced them. You can compare your files with the completed [Matrix.cs](https://github.com/plainsight-systems/cradle/blob/lesson-02/src/Cradle/Matrix.cs) and [MatrixTests.cs](https://github.com/plainsight-systems/cradle/blob/lesson-02/tests/Cradle.Tests/MatrixTests.cs).

Let’s use those pieces in the GPU path. Keep the two tests from earlier lessons as well; no project-file, dependency, or CI changes are needed.

## Use rows and columns in the kernel

Replace the old `Kernel` method at the top of `Program` with:

```csharp
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
```

The kernel now receives an `Index2D`. We choose to use `X` for the row and `Y` for the column. Those names do not impose a screen-coordinate convention; what matters is that the launch and the address calculation use the same interpretation.

`columns` tells the kernel how far apart successive rows begin. The calculation is the same one we wrote for the CPU indexer. At `[1, 0]`, the offset is `1 * 3 + 0`, or 3, so the kernel adds 4 and 40. At `[1, 2]`, it adds 6 and 60 at offset 5.

The buffers themselves are still flat. We have given their contents a two-dimensional interpretation. The kernel receives an integer and buffer views, which ILGPU can represent on the device. Our managed `Matrix` object stays on the CPU.

Each invocation writes a distinct offset. There is no shared running total or dependency between the answers, so no invocation needs to wait for another.

## Check a shaped answer

Replace `CheckResults` with:

```csharp
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
```

The first check compares both dimensions. Then we visit each row and column, reject non-finite values on either side, and compare with the same small absolute tolerance we used for addition in lesson 1. A failure now reports its matrix coordinates.

We deliberately keep this separate from `Matrix.Equals`. A numerical check should reject `NaN`, even when both calculations produce one. It should also let us choose a tolerance appropriate to the operation. The integer-valued sums in this example are exactly representable as floats, and we already know their six expected answers.

## Put the matrix through the whole path

Keep `WriteSection` as it is. Replace `Main` with this version, which brings the pieces together:

```csharp
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
```

The inputs are now matrices, and their shape drives the work. The `left + right` call produces our CPU reference answer before we allocate buffers or launch the kernel. That ordering also makes a shape mismatch fail before the GPU can read incompatible inputs.

At the allocation boundary, `(float[])left` invokes our explicit conversion and produces a managed copy. The `Allocate1D` overload taking that array allocates the GPU buffer **and uploads its contents**. Do not keep the separate `CopyFromCPU` calls from lesson 1; they would upload the same inputs again. The [array allocation extension in our pinned ILGPU source](https://github.com/m4rs-mt/ILGPU/blob/24cb87d6669c177428bd4ef1b8d05d9652b21c4b/Src/ILGPU/Runtime/ArrayViewExtensions.cs) shows the allocation followed by the copy.

The output allocation still takes only a length. We don’t need initial output values because the kernel writes every requested element. Its `using` declaration, like those on the input buffers, keeps ownership with the caller. `Matrix` has no GPU allocation to dispose.

The launch extent is now `new Index2D(left.Rows, left.Columns)`. For this input, it describes six coordinates, from `[0, 0]` through `[1, 2]`. The lambda supplies the column count and buffer views to `AddMatrices`. Although `left.Columns` appears in that launch expression, the kernel’s parameter is an `int`; we are supplying the dimension, not sending the managed matrix to the device.

This overload still uses the build integration we established in lesson 1. ILGPU generates the launch code and compiles the kernel for our selected backend. The [two-dimensional launcher in the pinned source](https://github.com/m4rs-mt/ILGPU/blob/24cb87d6669c177428bd4ef1b8d05d9652b21c4b/Src/ILGPU/Runtime/AcceleratorStream.Launchers.cs) reconstructs the two coordinates and checks the requested bounds before invoking our function.

After synchronization, `GetAsArray1D` reads the values back to a managed array. `Matrix.FromArray` attaches the intended shape by constructing a matrix from a copy of those values. That means there is an additional CPU copy on this path. It is a consequence of the ownership rule we chose for `FromArray`: the matrix always owns its storage. Nothing about adding rows and columns changes where the GPU transfer happens.

Finally, the check consumes matrices, and `string.Join` uses their row-major enumeration. We have kept the shape from input preparation through result checking, with an explicit array conversion where ILGPU needs one.

## Run it

Build and run the updated cradle:

```sh
dotnet run --project src/Cradle
```

The GPU name and backend will depend on your machine. The results should be:

```text
--- Results ---

Shape: 2x3
Actual:   11, 22, 33, 44, 55, 66
Expected: 11, 22, 33, 44, 55, 66

All 6 matrix elements match.
```

Compare those values with the two rows we wrote down earlier. In particular, 44 begins the second row and 66 finishes it. We’ve exercised a row boundary, and using different row and column counts makes an accidental swap harder to hide.

The CPU checks established our matrix’s behavior as we built it. This run adds the complete GPU path: upload the inputs, address them by row and column, and bring back a shaped result that agrees with the reference calculation.

For a final check of the assembled cradle, run the tests and then the GPU program:

```sh
dotnet test Cradle.slnx -c Release --no-restore
dotnet run --project src/Cradle -c Release --no-build --no-restore
```

If you use a backend override, put it on the test command that builds the application. Expect the same 12 passing test cases and all six matrix elements matching in the GPU run.

The broader repository check remains the same command from the prologue:

```sh
python3 scripts/check_dotnet.py
```

It builds the backend variants and runs the CPU-side tests, then restores the platform’s default build. Run the application with your chosen backend afterward to exercise your actual GPU. The two generated-code warnings discussed in lesson 1 remain on the Metal path; we’ll return to them as planned.

## Ready for a different operation

Try changing the right input’s shape from `2, 3` to `3, 2`, keeping its six values. Both matrices are individually valid. Their addition should fail at `left + right`, before any GPU buffers are allocated. Put the shape back when you’ve seen that happen.

We now have a cradle that knows what its data means: how many rows it contains, how to locate an element, who owns the storage, and how to compare a result. The CPU class and GPU kernel use the same row-major layout, and the program still shows us where data moves onto and off the device. The [completed lesson-02 snapshot](https://github.com/plainsight-systems/cradle/tree/lesson-02) contains all three application files and the tests if you want to compare your version.

So far, each output value has needed just one value from each input. Matrix multiplication changes that. To apply a row of weights to an input vector, we’ll multiply corresponding values and add those products into one answer. That is a calculation we’ll use throughout the transformer, and we now have the shape and indexing needed to write it. Keep the cradle working. Next time we’ll put those rows to work.
