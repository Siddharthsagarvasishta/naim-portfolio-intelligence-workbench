/* Update to an approved extracted nAIM package root. */
%let NAIM_ROOT=.;
%let NAIM_DATA=&NAIM_ROOT./data;
%let NAIM_OUT=&NAIM_ROOT./output;

options validvarname=any mprint mlogic symbolgen;
libname naim "&NAIM_OUT.";

%macro require_dataset(ds);
  %if not %sysfunc(exist(&ds)) %then %do;
    %put ERROR: Required governed dataset &ds does not exist.;
    %abort cancel;
  %end;
%mend;

