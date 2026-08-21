%include "00_setup.sas";
%require_dataset(naim.portfolio_summary);

ods excel file="&NAIM_OUT./nAIM_SAS_Validation_Output.xlsx"
  options(sheet_interval="proc" embedded_titles="yes");

title "Synthetic nAIM Portfolio Summary";
proc print data=naim.portfolio_summary noobs; run;

%if %sysfunc(exist(work.reconciliation)) %then %do;
  title "Governed Metric Reconciliation";
  proc print data=work.reconciliation noobs; run;
%end;

title "Strategy Summary";
proc means data=naim.strategy_snapshot n mean min max;
  class strategy;
  var fraud_bps manual_review_rate false_positive_rate
      customer_friction_rate expected_profit;
run;

ods excel close;
title;

