using System.Collections;

namespace Cradle;

/// <summary>
/// A CPU matrix stored row by row in a contiguous float array.
/// Dimensions are fixed; elements can be changed through the indexer.
/// </summary>
public sealed class Matrix : IEquatable<Matrix>, IEnumerable<float>
{
    private const string ValuesMustMatchShape =
        "The number of values must equal rows multiplied by columns.";
    private const string ShapesMustMatch =
        "Matrix addition requires matching rows and columns.";

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

    /// <summary>Enumerates elements from left to right, one row at a time.</summary>
    public IEnumerator<float> GetEnumerator() =>
        ((IEnumerable<float>)_values).GetEnumerator();

    IEnumerator IEnumerable.GetEnumerator() => GetEnumerator();

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
