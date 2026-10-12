+++
title = 'Matrix multiplication'
description = 'Every attention head and feed-forward layer will need this operation. We’ll start with a small matrix whose answer we can check by hand.'
type = 'lessons'
lesson = 3
draft = true
specimen = true
start_tag = 'lesson-02'
end_tag = 'lesson-03'
+++

## The shape of the result

A matrix with two rows and three columns can multiply a matrix with three rows and two columns. The shared dimension is three. The result has two rows and two columns.

\[
(2 \times 3) \cdot (3 \times 2) \longrightarrow (2 \times 2)
\]

Each output is a dot product: one row from the first matrix and one column from the second.

## One output at a time

```text
row    = [1, 2, 3]
column = [7, 9, 11]

1 × 7 + 2 × 9 + 3 × 11 = 58
```

One row, one column, one value in the result. Once we can check one output, we can repeat the operation for every row and column.

## Checking the answer

| Output | Row | Column | Expected value |
| :----- | :-- | :----- | -------------: |
| First | 1, 2, 3 | 7, 9, 11 | 58 |
| Second | 1, 2, 3 | 8, 10, 12 | 64 |

This page is a layout specimen. Its text is sample content, and its release labels are examples. It is excluded from production builds and article exports.
