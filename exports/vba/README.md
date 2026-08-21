# Optional VBA Compatibility Bridge

The `.bas` files are reviewable source only; no macro-enabled workbook is distributed. Import them into an approved workbook only after code review and signing under enterprise policy.

## Modules

- `NaimConfig.bas`: reads configuration from a named `Naim_Config` range and validates allowed roots.
- `NaimRefresh.bas`: imports approved CSV files into existing named tables, refreshes pivots and writes refresh metadata.
- `NaimPresentation.bas`: creates a basic editable PowerPoint pack from approved Excel ranges.

The code does not calculate risk metrics. It refreshes governed exports and records evidence metadata. Use Power Query or manual named-table import as the non-macro alternative.

## Security

Never lower Office macro security. Sign reviewed modules with an enterprise-managed certificate, distribute through a trusted location, restrict writable folders, and keep credentials out of workbooks. Validate the reconciliation table after every refresh.

