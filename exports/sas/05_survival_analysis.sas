%include "00_setup.sas";

/* Optional row-level survival table.
   Required: duration_months, attrition_event, membership_tier,
   strategy, risk_score, customer_segment. */
%if %sysfunc(exist(naim.survival_account_level)) %then %do;
  proc lifetest data=naim.survival_account_level plots=survival;
    time duration_months*attrition_event(0);
    strata membership_tier;
  run;

  proc phreg data=naim.survival_account_level;
    class membership_tier strategy customer_segment / param=ref;
    model duration_months*attrition_event(0) =
      membership_tier strategy risk_score customer_segment;
    assess ph / resample;
  run;

  proc genmod data=naim.survival_account_level;
    class membership_tier strategy customer_segment;
    model complaint_count =
      membership_tier strategy risk_score customer_segment
      / dist=negbin link=log;
  run;
%end;
%else %put NOTE: LIFETEST, PHREG and GENMOD skipped; governed survival_account_level was not supplied.;

