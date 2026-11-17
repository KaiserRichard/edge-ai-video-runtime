function errors=run_fault_study(backend)
% Compare state timing with reason-specific references, not GPIO timing.
if nargin<1,backend='simulink';end
root=setup_coursework();rows=struct([]);
for fault={'F1','F2','F3','F4','F5'}
 for seed=1:5
  c=course.defaults('OS');c.name=['OS_' fault{1}];c.fault=fault{1};c.seed=seed;
  c.fps=10;c.samples=.020;c.faultTime=5.0134+(seed-1)*.00017;
  c.recoverTime=6.2;c.rearmTime=8.5;c.duration=10;
  result=run_coursework(c,backend);
  rows=[rows course.faultTransitions(result)]; %#ok<AGROW>
  if seed==1,save(fullfile(root,'output',[c.name '.mat']),'result');end
 end
end
runs=struct2table(rows);writetable(runs,fullfile(root,'output','os_fault_runs.csv'));
% Corrected STAGE_REPORT values supersede e4_faults.csv first-transition refs.
targets=readtable(fullfile(root,'data','os_fault_targets.csv'),'TextType','string');
errors=table;
for k=1:height(targets)
 target=targets(k,:);
 t=runs(runs.fault==target.fault & runs.state==target.state & ...
  runs.reason==target.reason & runs.reference==target.reference,:);
 local=course.percentile(t.local_ms,50);mapped=course.percentile(t.fault_to_state_ms,50);
 errors=[errors;table(target.fault,target.state,target.reason,target.reference,local,target.local_p50_ms,local-target.local_p50_ms,...
  mapped,target.fault_p50_ms,mapped-target.fault_p50_ms,height(t),target.accepted_runs,target.evidence,'VariableNames',...
  {'fault','state','reason','reference','sim_local_ms','measured_local_ms','local_error_ms','sim_fault_ms','measured_fault_ms',...
   'fault_error_ms','sim_seeds','measured_runs','evidence'})]; %#ok<AGROW>
end
writetable(errors,fullfile(root,'output','os_t6_error_table.csv'));
f=figure('Visible','off');clean=onCleanup(@()close(f));
tiledlayout(f,2,1);
for state=[2 3]
 nexttile;t=errors(errors.state==state,:);
 bar([t.sim_local_ms t.measured_local_ms]);xticks(1:height(t));xticklabels(t.fault);
 ylabel('After reference event (ms)');
 if state==2,title('HOLD: after last inference reception');
 else,title('FAILSAFE: F1/F2/F4 after heartbeat; F3/F5 after inference');end
 legend('Simulation P50','Measured P50');grid on;
end
exportgraphics(f,fullfile(root,'output','os_t6_reaction.png'));
end
