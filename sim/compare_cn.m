function errors=compare_cn(summary)
root=setup_coursework();
if nargin<1,summary=readtable(fullfile(root,'output','cn_runs.csv'),'TextType','string');end
targets=readtable(fullfile(root,'data','cn_targets.csv'),'TextType','string');
rows=struct([]);
for k=1:height(targets)
 t=targets(k,:);values=summary{string(summary.config)==t.config,char(t.metric)};
 if isempty(values),continue;end
 v=values(isfinite(values));if isempty(v),v=NaN;end
 av=mean(v);rel=NaN;if t.value~=0,rel=100*(av-t.value)/t.value;end
 rows(end+1)=struct('config',t.config,'metric',t.metric,'unit',t.unit,...
  'seeds',numel(values),'sim_mean',av,'sim_min',min(v),'sim_max',max(v),...
  'measured',t.value,'signed_error',av-t.value,'absolute_error',abs(av-t.value),...
  'relative_error_percent',rel,'evidence',t.evidence); %#ok<AGROW>
end
errors=struct2table(rows);writetable(errors,fullfile(root,'output','cn_error_table.csv'));
for metric=unique(errors.metric)'
 t=errors(errors.metric==metric,:);f=figure('Visible','off','Position',[100 100 1200 550]);
 cleanup=onCleanup(@()close(f));x=1:height(t);
 errorbar(x-.12,t.sim_mean,t.sim_mean-t.sim_min,t.sim_max-t.sim_mean,'o','LineWidth',1.3);hold on;
 plot(x+.12,t.measured,'kx','LineWidth',1.5);xticks(x);xticklabels(t.config);xtickangle(40);
 ylabel(t.unit(1));title(metric+' : simulation mean/min-max vs measured means','Interpreter','none');
 legend('Simulation: 5 seeds (min-max)','Measurement: reported means','Location','best');grid on;
 exportgraphics(f,fullfile(root,'output',['cn_' char(metric) '.png']));clear cleanup;
end
% Formula is a diagnostic only: integer packet-count mixture, not fractional n.
cs=course.cnConfigs();formula=table;
for c=cs
 if strcmp(c.lossMode,'bernoulli') && c.payload<=1400 && isempty(c.lossSteps)
  a=floor(c.meanPackets);q=mod(c.meanPackets,1);
  f=1-((1-q)*(1-c.loss)^a+q*(1-c.loss)^(a+1));
  formula=[formula;table(string(c.name),f,'VariableNames',{'config','formula_frame_loss'})]; %#ok<AGROW>
 end
end
writetable(formula,fullfile(root,'output','cn_formula.csv'));
end
