%include "00_setup.sas";
%require_dataset(naim.kpi_snapshot);

proc means data=naim.kpi_snapshot n nmiss min mean median max;
  class status unit;
  var value prior_value absolute_change;
run;

proc freq data=naim.kpi_snapshot;
  tables status*unit / missing;
run;

proc sql;
  create table naim.portfolio_summary as
  select reporting_period, metric_id, name, value, prior_value,
         absolute_change, relative_change, unit, status,
         metric_version, denominator
  from naim.kpi_snapshot
  order by metric_id;
quit;

