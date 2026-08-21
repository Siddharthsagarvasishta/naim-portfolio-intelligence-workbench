# Performance and scale validation

## Validated run

The fresh benchmark report is
`outputs/performance/performance-20260801T091730Z.json`. It was generated on
2026-08-01 and does not copy or overwrite the earlier backend benchmark files.
Its schema validation status is `PASS`. Completeness is `PARTIAL` only because
Tableau Hyper could not bind its local Unix-domain socket inside the restricted
execution sandbox; no Hyper timing is claimed.

The benchmark ran on CPython 3.12.13 on an arm64 Mac with 8 logical CPUs and
8,192 MiB physical memory. The recorded analytical package versions were
NumPy 2.5.1, pandas 2.3.3, scikit-learn 1.9.0, openpyxl 3.1.5, and
python-pptx 1.0.2.

## Result schema

The report uses schema version `1.0.0`. Each profile contains immutable
configuration identity, dataset control totals, and all twelve required
operation keys. A measured operation contains `repetitions`, a `timing_ms`
summary, and a `process_peak_rss_mib` summary; both summaries contain median,
nearest-rank P95, minimum, maximum, and the retained raw samples. An unmeasured
operation must use `SKIPPED` or `EXTERNAL_EXECUTION_REQUIRED` and include a
non-empty reason. The executable validator also requires machine details,
positive dataset size, matching sample counts, and P95 greater than or equal to
the median. The unit tests cover valid aggregation, changed deterministic
controls, missing operations, missing limitation reasons, timing samples, and
memory samples.

## Dataset scale

| Requested profile | Resolved profile | Accounts | Months | Account-month rows | Raw in-memory size (MiB) | Mart in-memory size (MiB) | Quality |
|---|---|---:|---:|---:|---:|---:|---|
| fast | test | 320 | 8 | 2,312 | 3.958 | 5.248 | PASS / 100.0 |
| default | default | 25,000 | 24 | 513,923 | 800.898 | 1,003.447 | PASS / 100.0 |
| medium | medium | 50,000 | 24 | 1,025,365 | 1,598.268 | 1,941.466 | PASS / 100.0 |

`fast` is an explicit benchmark alias for the repository's deterministic
`test` profile. In-memory sizes are the sum of pandas deep-memory estimates for
the generated frames and should not be added to the process high-water mark as
if they were disjoint allocations.

## Pipeline stages

Values are median / nearest-rank P95 milliseconds across three fresh-process
samples. With three samples, the nearest-rank P95 is the maximum observed
sample; it is a transparent local bound, not a production SLO estimate.

| Profile | Data generation | Validation | Mart build | Model training | Peak process RSS after mart build (MiB) |
|---|---:|---:|---:|---:|---:|
| fast | 57.330 / 57.567 | 14.999 / 15.061 | 146.379 / 149.707 | 1,061.084 / 1,326.741 | 139.906 |
| default | 2,957.716 / 3,069.682 | 1,585.542 / 1,929.553 | 31,354.816 / 32,927.488 | 1,862.002 / 1,873.616 | 1,798.484 |
| medium | 5,799.446 / 6,304.223 | 3,743.505 / 3,793.550 | 61,465.003 / 62,196.292 | 1,882.952 / 1,908.663 | 2,523.922 |

Data generation, validation, and mart construction are timed independently in
memory without file persistence. Model training measures the governed
statistical-segmentation implementation on a deterministic cap of the first
2,000 accounts (320 for fast), using candidate cluster counts three and four.
This cap is explicit because exact silhouette diagnostics scale quadratically
with account count.

## Analytical responses

These timings cover the in-process analytical call plus strict JSON
serialisation. They exclude network transport and HTTP middleware. Read-only
calls are primed once before measurement, so the sub-millisecond root-cause
figures are cache-hit timings. The scenario run is unprimed and includes its
persistent workflow write.

| Profile | Command centre | Root cause | Vintage | Basket comparison | Scenario run |
|---|---:|---:|---:|---:|---:|
| fast | 6.761 / 7.023 | 0.515 / 0.516 | 20.510 / 20.840 | 1.080 / 1.082 | 16.029 / 16.050 |
| default | 169.343 / 179.398 | 0.817 / 0.914 | 426.020 / 441.845 | 1.127 / 1.150 | 277.088 / 325.347 |
| medium | 353.398 / 356.102 | 1.070 / 1.145 | 810.456 / 816.431 | 1.076 / 1.311 | 620.956 / 678.336 |

All three command-centre P95s remain below the repository's existing
1.5-second warm interactive target. That is a local analytical target only;
deployment latency, concurrency, and remote data-source effects are not
represented.

## Artifact generation

The presentation benchmark creates the full seven-slide editable review deck,
runs its structural validation, and writes it to an isolated temporary root.
The Excel benchmark creates the nine-sheet live service export. It is distinct
from the separately authored, styled Office workbook. Temporary benchmark
artifacts are deleted after each worker exits.

| Profile | Presentation generation | Excel generation | Hyper generation | Final process peak RSS (MiB) |
|---|---:|---:|---|---:|
| fast | 168.707 / 170.255 | 107.913 / 121.797 | External execution required | 242.078 |
| default | 3,918.759 / 4,112.804 | 273.216 / 291.497 | External execution required | 1,828.375 |
| medium | 7,605.224 / 8,219.161 | 570.885 / 709.525 | External execution required | 2,523.922 |

Hyper was attempted in all nine worker processes. Each attempt returned the
same Tableau Hyper engine error: binding the local Unix-domain socket was not
permitted by the sandbox. The harness records this as
`EXTERNAL_EXECUTION_REQUIRED`, includes a rerun requirement, and deliberately
omits median, P95, and memory values. To collect those values, run the same
harness in an environment that permits the Hyper local process:

```bash
cd /path/to/naim-portfolio-intelligence-workbench
PYTHONPATH=src .venv/bin/python scripts/benchmark_performance.py \
  --profiles fast default medium --repetitions 3 --hyper required
```

## Reproducibility and interpretation

- Every repetition executes in a fresh Python process against the same seed and
  configuration hash. The harness fails aggregation if deterministic dataset
  controls differ between repetitions.
- Median and P95 use raw wall-clock samples retained in the JSON report.
- Memory is `ru_maxrss`, the whole-process resident-memory high-water mark
  observed by completion of each operation. It includes the retained dataset
  and prior operations and is not presented as an incremental allocation.
- Response timings include JSON encoding but not FastAPI dependency injection,
  authentication, middleware, socket transport, browser rendering, or
  concurrent load.
- Presentation and Excel timings include file creation and structural/output
  checks used by their generators. Hyper remains unmeasured until the engine can
  run outside the restricted socket sandbox.
