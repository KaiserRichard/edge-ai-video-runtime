function r=cnse2_run(c,label,saveIt)
% Run CN_simevents_v2 with one configuration (same config path as v1 cnse_run).
if nargin<3,saveIt=true;end
root=fileparts(fileparts(mfilename('fullpath')));v2=fullfile(root,'study_simevents_v2');m='CN_simevents_v2';
Simulink.fileGenControl('set','CacheFolder',fullfile(v2,'cache'),...
 'CodeGenFolder',fullfile(v2,'codegen'),'createDir',true);
if ~bdIsLoaded(m),load_system(fullfile(root,'generated',[m '.slx']));end
c=cnse_config(c);
assignin(get_param(m,'ModelWorkspace'),'c',c);cnse2_params(m,c);
overwrite='off';if strcmp(c.policy,'latest'),overwrite='on';end
set_param([m '/Sender Queue/Frame FIFO or latest'],'OverwriteOldest',overwrite);
set_param([m '/Inference/AI waiting frames'],'OverwriteOldest',overwrite);
o=sim(m);s=cnse2_runtime('get');
r=rmfield(s,{'L','D','R','DP','RL','RD','cameraRng'});
r.dashboard=o.get('dashboard');r.label=label;r.metrics=cnse_metrics(r);
r.validation=cnse2_validate(r);
if saveIt
 runs=fullfile(v2,'runs');if ~isfolder(runs),mkdir(runs);end
 save(fullfile(runs,[label '.mat']),'r','-v7');
end
fprintf('%s: %d packets, loss %.5f, jitter %.3f ms, P95 %.3f ms, AoI %.3f ms, validation %d/%d\n',...
 label,size(r.tx,1),r.metrics.sequence_loss,r.metrics.jitter_ms,...
 r.metrics.latency_p95_ms,r.metrics.aoi_ms,sum(r.validation.pass),height(r.validation));
end
