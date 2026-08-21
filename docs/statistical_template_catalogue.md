# Statistical Template Catalogue

Every template emits question, population, estimator, assumptions, diagnostics, uncertainty, materiality, limitations, data/configuration versions and a reproducible output table.

| Template | Use | Required diagnostics |
|---|---|---|
| Proportion/rate comparison | delinquency, fraud, friction | denominators, interval method, multiple tests |
| Mean/median comparison | cost, time, value | distribution, robust alternative, effect size |
| Transition matrix | delinquency/rating/tier migration | row reconciliation, exposure window |
| Survival / hazard | attrition, time-to-event | censoring, proportional-hazards check if used |
| Logistic/GLM | binary/count outcomes | calibration, residuals/dispersion, stability |
| Panel regression | repeated entity-month outcomes | entity/time effects, clustered errors |
| Matched observational comparison | strategy/partner differences | overlap, balance, sensitivity |
| Difference-in-differences | controlled change analysis | parallel pre-trends, timing, contamination |
| Change-point / control chart | emerging movement | false-alarm rate, persistence, seasonality |
| Forecast | trend and scenario baseline | rolling-origin backtest, naive benchmark |
| Decomposition | mix versus performance | exact identity and rounding residual |
| Concentration/network | dependency risk | weight definition, disconnected components |

Templates are exploratory or confirmatory according to a pre-declared analysis plan. Negative findings are reported; unstable results are suppressed or qualified. P-values are never the sole decision criterion.

