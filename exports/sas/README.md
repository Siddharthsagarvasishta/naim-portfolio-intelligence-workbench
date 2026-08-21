# nAIM Base SAS Compatibility Sources

These scripts demonstrate import, governed-metric reconciliation and common analytical workflows. They have not been executed because no SAS runtime is available in this environment.

Set `NAIM_ROOT` in `00_setup.sas`, then run scripts in numeric order. `01_import_data.sas` imports live CSV extracts generated from `WorkbenchService`. `02_validate_metrics.sas` must pass before analytical output is distributed.

The aggregate snapshot supports PROC SQL, FREQ and MEANS examples. PROC LOGISTIC, LIFETEST, PHREG and GENMOD templates run only when the named row-level governed tables have been supplied; the scripts check table existence and otherwise emit an explanatory note.

Review SAS logs for truncation, automatic conversion, uninitialized variables, invalid data and merge warnings. Any unexplained note fails validation.

