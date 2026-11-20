function T=cnse2_compare(stage)
% Compare v2 stage results with the accepted v1 CSV, run by run.
% Counts and loss fractions must match exactly. Jitter, on-time share, P95
% and AoI may differ by 2% relative or 1 ms (absolute 0.02 for fractions).
root=fileparts(fileparts(mfilename('fullpath')));
v1=readtable(fullfile(root,'study_simevents',['stage_' stage '_results.csv']),'TextType','string');
v2=readtable(fullfile(root,'study_simevents_v2',['stage_' stage '_results.csv']),'TextType','string');
exact={'sent','received','results','reports_sent','reports_delivered','sender_overflow',...
 'ai_overflow','sender_replaced','ai_replaced','reordered','sequence_loss','frame_loss','late',...
 'rate_min','rate_final'};
timed={'jitter_ms','latency_p50_ms','latency_p95_ms','aoi_ms'};
share={'on_time'};
run=strings(0,1);metric=run;a=zeros(0,1);b=a;d=a;tol=a;rule=run;pass=false(0,1);
for k=1:height(v1)
 j=find(v2.run==v1.run(k),1);if isempty(j),continue;end
 for name=[exact timed share]
  x=v1.(name{1})(k);y=v2.(name{1})(j);e=abs(x-y);
  if ismember(name{1},exact),t=0;why="exact";
  elseif ismember(name{1},timed),t=max(1,.02*abs(x));why="2% or 1 ms";
  else,t=max(.02*abs(x),1e-12);why="2% relative";end
  ok=e<=t || (isnan(x)&&isnan(y));
  if isnan(x)&&isnan(y),e=0;end
  run(end+1,1)=v1.run(k);metric(end+1,1)=name{1};a(end+1,1)=x;b(end+1,1)=y; %#ok<AGROW>
  d(end+1,1)=e;tol(end+1,1)=t;rule(end+1,1)=why;pass(end+1,1)=ok; %#ok<AGROW>
 end
end
T=table(run,metric,a,b,d,tol,rule,pass,'VariableNames',...
 {'run','metric','v1_value','v2_value','abs_diff','tolerance','rule','pass'});
writetable(T,fullfile(root,'study_simevents_v2',['stage_' stage '_compare.csv']));
fprintf('Stage %s comparison: %d/%d within tolerance, %d exactly equal\n',stage,sum(T.pass),height(T),sum(T.abs_diff==0));
end
