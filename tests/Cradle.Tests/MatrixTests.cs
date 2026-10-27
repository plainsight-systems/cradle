using System.Collections;
using Xunit;

namespace Cradle.Tests;

public class MatrixTests
{
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
        Assert.All(matrix, value => Assert.Equal(0f, value));
    }

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

        Assert.False(left == right);
        Assert.Throws<ArgumentException>(() => left + right);
    }

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

    [Fact]
    public void FactoriesRejectInvalidDimensionsLengthsAndOverflow()
    {
        Assert.Throws<ArgumentOutOfRangeException>(() => Matrix.Create(0, 2));
        Assert.Throws<ArgumentOutOfRangeException>(() => Matrix.Create(2, -1));
        Assert.Throws<OverflowException>(() => Matrix.Create(int.MaxValue, 2));
        Assert.Throws<ArgumentException>(() => Matrix.FromArray(2, 3, new float[5]));
        Assert.Throws<ArgumentNullException>(() => Matrix.FromArray(1, 1, null!));
    }

    [Fact]
    public void MultiplicationProducesKnownRectangularProduct()
    {
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

        var result = left * right;

        Assert.Equal(2, result.Rows);
        Assert.Equal(2, result.Columns);
        Assert.Equal(
            new float[] { 58, 64, 139, 154 },
            result.ToArray());
    }

    [Fact]
    public void MultiplicationRejectsIncompatibleDimensions()
    {
        var left = Matrix.Create(2, 3);
        var right = Matrix.Create(2, 3);

        Assert.Throws<ArgumentException>(() => left * right);
    }

    [Fact]
    public void MultiplicationAppliesMatrixToColumnVector()
    {
        var weights = Matrix.FromArray(2, 3,
        [
            1, 2, 3,
            4, 5, 6
        ]);

        var vector = Matrix.FromArray(3, 1,
        [
            1,
            2,
            3
        ]);

        var result = weights * vector;

        Assert.Equal(2, result.Rows);
        Assert.Equal(1, result.Columns);
        Assert.Equal(new float[] { 14, 32 }, result.ToArray());
    }
}
