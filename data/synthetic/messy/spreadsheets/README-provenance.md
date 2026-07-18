# Spreadsheet provenance — raw human exports

These two CSVs are deliberately messy, exactly as they land from a finance
analyst's workbook. They are NOT tidy. A structuring agent has to clean them.

## q1-budget-vs-actual.csv
- Raw export from a finance workbook. The header row is NOT row 1.
  Row 1 is a title, row 2 is blank, row 3 is a "Prepared by ..." provenance
  line, and the real header lands on row 4.
- Embedded aggregate rows are mixed into the data: "Engineering subtotal"
  and "G&A subtotal" are subtotals, not departments; there is a blank row,
  a "TOTAL" row, and two trailing footnote rows (`*`, `**`).
- Amounts are text, not numbers: `$` signs and thousands commas, so every
  money field is a quoted string like `"$1,240,000"`.
- Ground-truth check: the grand total Actual is **$2,622,400** (sum of the
  department rows, excluding the subtotal and TOTAL rows). A correct parse
  that re-sums the leaf department rows must reproduce this figure.

## headcount-plan-eu-locale.csv
- Exported under an EU locale. Delimiter is `;` (semicolon), the decimal
  separator is `,` (comma), and thousands use `.` — so `8.500,00` means
  8500.00 and `12,5` means 12.5.
- Dates are `DD.MM.YYYY`.
- Column headers mix German (`Abteilung`, `Kosten pro FTE`, `Stichtag`) with
  English department values.
- One row (People) is ragged: it carries a trailing empty extra column.

## Structuring task
Produce a single tidy **long-format** table: one row per
(department, quarter) with numeric planned FTE and a normalized cost-per-FTE
and ISO date. De-duplicate the aggregate/subtotal/total rows out of the
budget file; keep only leaf department rows for the numeric roll-up.
