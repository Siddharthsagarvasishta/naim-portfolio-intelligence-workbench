# VBA and VBScript Compatibility

## Positioning

The optional sources in `exports/vba/` and `exports/vbscript/` bridge approved Windows workflows. They are not used for core calculations. Modern orchestration through Python, PowerShell or an enterprise scheduler is preferred.

## VBA modules

The modules demonstrate configuration loading, safe CSV import to named tables, pivot refresh, approved formatting, PowerPoint pack creation and refresh logging. Paths come from a configuration sheet/file; no user-specific directories are hard-coded.

Before use:

- review source under change control;
- sign macros with an enterprise-managed certificate;
- distribute through a trusted location;
- disable programmatic VBA-project access;
- restrict allowed root paths and file extensions;
- verify reconciliation after refresh.

The non-macro alternative is Power Query or manual import into named tables followed by workbook recalculation.

## VBScript utilities

The minimal scripts read a simple configuration file, validate source/destination roots, create timestamped copies, launch an approved command or workbook and append a run log. They never calculate metrics and should run with least privilege.

## Security warning

Unsigned macros and scripts can execute arbitrary code. Do not lower Office security controls or bypass endpoint policy to use these examples. Store no credentials in source or config.

