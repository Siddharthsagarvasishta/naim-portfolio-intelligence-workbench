%include "00_setup.sas";

%macro import_csv(file=, out=);
  proc import datafile="&NAIM_DATA./&file"
    out=&out dbms=csv replace;
    guessingrows=max;
    getnames=yes;
  run;
%mend;

%import_csv(file=kpi_snapshot.csv, out=naim.kpi_snapshot);
%import_csv(file=strategy_snapshot.csv, out=naim.strategy_snapshot);
%import_csv(file=entity_rating_snapshot.csv, out=naim.entity_rating_snapshot);
%import_csv(file=scenario_snapshot.csv, out=naim.scenario_snapshot);
%import_csv(file=evidence_scope.csv, out=naim.evidence_scope);
%import_csv(file=metric_dictionary.csv, out=naim.metric_dictionary);

data naim.kpi_snapshot;
  set naim.kpi_snapshot;
  reporting_date=input(reporting_period,yymmdd10.);
  comparison_date=input(comparison_period,yymmdd10.);
  format reporting_date comparison_date yymmdd10.;
run;

proc contents data=naim._all_ nods; run;
