function summary=run_monte_carlo(backend,configs)
% Five independent seeds, sequential execution: never starts a parallel pool.
if nargin<1,backend='simulink';end
if nargin<2,configs=course.cnConfigs();end
root=setup_coursework();rows=struct([]);
for k=1:numel(configs)
 for seed=1:5
  c=configs(k);c.seed=seed;
  fprintf('%s seed %d/5 (%s)\n',c.name,seed,backend);
  result=run_coursework(c,backend);
  row=result.metrics;row.config=string(c.name);row.seed=seed;row.backend=string(backend);
  rows(end+1)=row; %#ok<AGROW>
  if seed==1,save(fullfile(root,'output',[c.name '_seed1.mat']),'result');end
 end
end
summary=struct2table(rows);writetable(summary,fullfile(root,'output','cn_runs.csv'));
compare_cn(summary);
end
