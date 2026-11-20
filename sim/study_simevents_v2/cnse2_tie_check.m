function T=cnse2_tie_check()
% Explain the B_queue_* differences: with 30 FPS, 50 ms inference and no
% network jitter, a frame's playout release and an inference completion fall
% on the same instant (bit-identical double). v1 and v2 order these
% simultaneous events differently. Moving the service time by +/-1 ns removes
% the tie; v1 and v2 must then agree exactly.
% v1 is simulated in memory only (nothing in study_simevents/ or generated/ is written).
root=fileparts(fileparts(mfilename('fullpath')));
addpath(root,fullfile(root,'study_simevents'),fullfile(root,'study_simevents_v2'),fullfile(root,'generated'));
run=strings(0,1);shift=zeros(0,1);metric=strings(0,1);a=zeros(0,1);b=a;
configs=course.cnConfigs();
cases={};
for policy={'fifo','latest'}
 c=cnse_config();c.duration=12;c.warmup=2;c.fps=30;c.samples=.05;c.policy=policy{1};c.queueCapacity=8;
 cases(end+1,:)={"B_queue_"+policy{1},c}; %#ok<AGROW>
end
for name={'T7_fifo','T7_latest'}   % Stage C: same 30 FPS / 50 ms structure
 c=cnse_config(configs(strcmp({configs.name},name{1})));c.seed=11;
 cases(end+1,:)={"C_"+name{1},c}; %#ok<AGROW>
end
for i=1:size(cases,1)
 for dt=[-1e-9 1e-9]
  c=cases{i,2};c.samples=c.samples+dt;
  m1=runV1(root,c);r2=cnse2_run(c,'tie',false);m2=r2.metrics;
  for name={'on_time','latency_p50_ms','latency_p95_ms','aoi_ms'}
   run(end+1,1)=cases{i,1};shift(end+1,1)=dt;metric(end+1,1)=name{1}; %#ok<AGROW>
   a(end+1,1)=m1.(name{1});b(end+1,1)=m2.(name{1}); %#ok<AGROW>
  end
 end
end
T=table(run,shift,metric,a,b,abs(a-b),'VariableNames',{'run','service_shift_s','metric','v1_value','v2_value','abs_diff'});
writetable(T,fullfile(root,'study_simevents_v2','tie_check.csv'));
disp(T);
end

function m=runV1(root,c)
mdl='CN_simevents';
Simulink.fileGenControl('set','CacheFolder',fullfile(root,'study_simevents_v2','cache_v1'),...
 'CodeGenFolder',fullfile(root,'study_simevents_v2','codegen_v1'),'createDir',true);
if ~bdIsLoaded(mdl),load_system(fullfile(root,'generated',[mdl '.slx']));end
c=cnse_config(c);assignin(get_param(mdl,'ModelWorkspace'),'c',c);
ov='off';if strcmp(c.policy,'latest'),ov='on';end
set_param([mdl '/Sender Queue/Frame FIFO or latest'],'OverwriteOldest',ov);
set_param([mdl '/Inference/AI waiting frames'],'OverwriteOldest',ov);
sim(mdl);s=cnse_runtime('get');m=cnse_metrics(s);
close_system(mdl,0);   % discard in-memory changes, never saved
Simulink.fileGenControl('set','CacheFolder',fullfile(root,'study_simevents_v2','cache'),...
 'CodeGenFolder',fullfile(root,'study_simevents_v2','codegen'),'createDir',true);
end
