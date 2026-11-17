function comparison=run_os_study(backend)
if nargin<1,backend='simulink';end
root=setup_coursework();rows=struct([]);
% Same arrival stream and service random stream per seed for each policy pair.
for load={'idle','cpu23','memory'}
 T=readtable(fullfile(root,'data',['os_' load{1} '_samples.csv']));
 for policy={'fifo','latest'}
  for seed=1:5
   c=course.defaults('OS');c.duration=65;c.seed=seed;c.load=load{1};
   c.samples=T.seconds;c.policy=policy{1};c.name=['OS_' load{1} '_' policy{1}];
   result=run_coursework(c,backend);
   target=NaN;
   if strcmp(load{1},'idle')
    if strcmp(policy{1},'fifo'),target=191.9839235563057;else,target=92.75980493546966;end
   end
   rows(end+1)=struct('load',string(load{1}),'policy',string(policy{1}),...
    'seed',seed,'aoi_ms',result.metrics.aoi_ms,'measured_aoi_ms',target); %#ok<AGROW>
   if seed==1,save(fullfile(root,'output',[c.name '.mat']),'result');end
  end
 end
end
runs=struct2table(rows);writetable(runs,fullfile(root,'output','os_aoi_runs.csv'));
comparison=table;
for load=unique(runs.load)'
 for policy=["fifo","latest"]
  t=runs(runs.load==load & runs.policy==policy,:);v=t.aoi_ms;
  comparison=[comparison;table(load,policy,mean(v),min(v),max(v),t.measured_aoi_ms(1),...
   mean(v)-t.measured_aoi_ms(1),'VariableNames',...
   {'load','policy','sim_mean_ms','sim_min_ms','sim_max_ms','measured_ms','error_ms'})]; %#ok<AGROW>
 end
end
writetable(comparison,fullfile(root,'output','os_aoi_error_table.csv'));
f=figure('Visible','off');clean=onCleanup(@()close(f));t=comparison(comparison.load=="idle",:);
errorbar(1:2,t.sim_mean_ms,t.sim_mean_ms-t.sim_min_ms,t.sim_max_ms-t.sim_mean_ms,'o');hold on;
plot(1:2,t.measured_ms,'kx');xticks(1:2);xticklabels(t.policy);ylabel('Time-average AoI (ms)');
title('OS-T4: input policy (bridge latest); cross-campaign comparison');
legend('Simulation mean/min-max, 5 seeds','Measured 192 / 93 ms');grid on;
exportgraphics(f,fullfile(root,'output','os_t4_aoi.png'));clear clean;
% Demonstrate that bridge-only replacement does not remove inference backlog.
for policy={'fifo','latest'}
 c=course.defaults('OS');c.duration=20;c.policy='fifo';c.bridgePolicy=policy{1};
 c.name=['OS_bridge_' policy{1}];result=run_coursework(c,backend);
 save(fullfile(root,'output',[c.name '.mat']),'result');
end
run_fault_study(backend);
end
