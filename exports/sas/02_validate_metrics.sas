%include "00_setup.sas";
%require_dataset(naim.kpi_snapshot);

proc import datafile="&NAIM_ROOT./../validation/interop_reconciliation_totals.csv"
  out=work.expected dbms=csv replace;
  guessingrows=max;
  getnames=yes;
run;

proc sql;
  create table work.reconciliation as
  select
    e.metric_id,
    e.current_value as expected_current,
    k.value as sas_current,
    abs(calculated sas_current-calculated expected_current) as absolute_difference,
    e.tolerance,
    case
      when calculated absolute_difference <= e.tolerance then 'PASS'
      else 'FAIL'
    end as validation_status length=4
  from work.expected e
  left join naim.kpi_snapshot k
    on e.metric_id=k.metric_id
  where e.scope='All portfolio';
quit;

proc freq data=work.reconciliation;
  tables validation_status / missing;
run;

proc print data=work.reconciliation noobs; run;

proc sql noprint;
  select count(*) into :reconciliation_failures
  from work.reconciliation where validation_status='FAIL';
quit;

%if &reconciliation_failures > 0 %then %do;
  %put ERROR: Governed metric reconciliation failed.;
  %abort cancel;
%end;

