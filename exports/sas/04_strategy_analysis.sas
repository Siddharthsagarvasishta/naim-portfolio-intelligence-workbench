%include "00_setup.sas";
%require_dataset(naim.strategy_snapshot);

proc means data=naim.strategy_snapshot n mean min max;
  class strategy;
  var fraud_bps manual_review_rate false_positive_rate
      customer_friction_rate expected_profit;
run;

proc freq data=naim.strategy_snapshot;
  tables strategy*minimum_sample_met / missing;
run;

/* Optional row-level governed decision table.
   Required columns: confirmed_fraud_flag, strategy, risk_score,
   months_on_book, acquisition_channel. */
%if %sysfunc(exist(naim.strategy_decision_level)) %then %do;
  proc logistic data=naim.strategy_decision_level descending;
    class strategy acquisition_channel / param=ref;
    model confirmed_fraud_flag =
      strategy risk_score months_on_book acquisition_channel;
    ods output ParameterEstimates=naim.logistic_parameter_estimates;
  run;
%end;
%else %put NOTE: PROC LOGISTIC skipped; governed row-level strategy_decision_level was not supplied.;

