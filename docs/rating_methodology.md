# Rating Methodology

## Score construction

Ratings convert transparent components to a 0–100 internal score. Each component declares metric ID, direction, normalization, weight, missing-data treatment, caps, override rules and effective version. Weights must sum to 100%.

Supported normalization methods are percentile rank, z-score, min–max, target-based scoring and threshold bands. Higher raw performance may map up or down according to the declared direction.

## Grades

| Score | Internal grade |
|---:|---|
| 80–100 | Grade 1: Strong |
| 65–<80 | Grade 2: Stable |
| 50–<65 | Grade 3: Watch |
| 35–<50 | Grade 4: Weak |
| 0–<35 | Grade 5: Critical |

These are synthetic internal categories and must not be confused with agency credit ratings.

## Confidence

Confidence reflects data quality, completeness, peer strength, sample size and component coverage. A high score with low confidence remains visibly qualified. Overrides record old/new grade, reason, evidence, approver and expiry.

## Change attribution

Rating migration is separated into underlying performance, benchmark movement, methodology change, data-quality change and manual override. Methodology changes receive an impact preview across historical entities before approval.

## Validation

Review sensitivity to weights/thresholds, component correlation, missingness, grade concentration, migration volatility, monotonicity with adverse outcomes and stability across approved segments. Ratings support prioritization and review; they do not substitute for judgment.

