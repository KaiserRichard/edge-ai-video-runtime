function r=cnse_run(c,label)
root=fileparts(fileparts(mfilename('fullpath')));m='CN_simevents';
Simulink.fileGenControl('set','CacheFolder',fullfile(root,'generated','se_cache'),...
 'CodeGenFolder',fullfile(root,'generated','se_codegen'),'createDir',true);
if ~bdIsLoaded(m),load_system(fullfile(root,'generated',[m '.slx']));end
c=cnse_config(c);
assignin(get_param(m,'ModelWorkspace'),'c',c);
overwrite='off';if strcmp(c.policy,'latest'),overwrite='on';end
set_param([m '/Sender Queue/Frame FIFO or latest'],'OverwriteOldest',overwrite);
set_param([m '/Inference/AI waiting frames'],'OverwriteOldest',overwrite);
o=sim(m);s=cnse_runtime('get');
r=rmfield(s,{'P','L','D','R','PB','DP','RL','RD','cameraRng','packets'});
r.dashboard=o.get('dashboard');r.label=label;r.metrics=cnse_metrics(r);
r.validation=cnse_validate(r);
save(fullfile(root,'study_simevents',[label '.mat']),'r','-v7');
fprintf('%s: %d packets, loss %.5f, jitter %.3f ms, P95 %.3f ms, AoI %.3f ms, validation %d/%d\n',...
 label,size(r.tx,1),r.metrics.sequence_loss,r.metrics.jitter_ms,...
 r.metrics.latency_p95_ms,r.metrics.aoi_ms,sum(r.validation.pass),height(r.validation));
end
