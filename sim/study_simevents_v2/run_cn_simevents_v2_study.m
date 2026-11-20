function run_cn_simevents_v2_study(stage)
% v2 copy of study_simevents/run_cn_simevents_study.m: same cases, seeds and
% configs, run on CN_simevents_v2, then compared with the v1 result CSV.
root=fileparts(fileparts(mfilename('fullpath')));folder=fullfile(root,'study_simevents_v2');
addpath(root,fullfile(root,'study_simevents'),folder,fullfile(root,'generated'));
rows=struct([]);validation=table;
switch upper(stage)
 case 'A'
  for seed=[1 17 903]
   c=cnse_config();c.duration=20;c.warmup=2;c.seed=seed;c.loss=.05;c.delay=.02;c.jitter=.02;c.depth=.05;
   collect(c,sprintf('A_seed%d',seed));
  end
  c=cnse_config();c.duration=5;c.warmup=1;c.loss=1;collect(c,'A_all_lost');
  c.loss=0;collect(c,'A_no_loss');
 case 'B'
  for adaptive=[false true]
   c=cnse_config();c.duration=50;c.warmup=2;c.adaptive=adaptive;
   c.lossSteps=[0 0;15 .15;35 0];
   collect(c,sprintf('B_adaptive%d',adaptive));
  end
  for adaptive=[false true]
   c=cnse_config();c.duration=20;c.warmup=10;c.drain=15;c.adaptive=adaptive;c.loss=.05;c.rate=.55e6;
   collect(c,sprintf('B_bottleneck%d',adaptive));
  end
  for policy={'fifo','latest'}
   c=cnse_config();c.duration=12;c.warmup=2;c.fps=30;c.samples=.05;c.policy=policy{1};c.queueCapacity=8;
   collect(c,['B_queue_' policy{1}]);
  end
  c=cnse_config();c.duration=6;c.warmup=1;c.adaptive=true;c.loss=.15;c.reverseLoss=1;
  collect(c,'B_reverse_all_lost');
  c.reverseLoss=.25;c.reverseDelay=.05;c.reverseJitter=.02;
  collect(c,'B_reverse_impaired');
  for policy={'fifo','latest'}
   c=cnse_config();c.duration=12;c.warmup=2;c.fps=30;c.senderService=.05;
   c.policy=policy{1};c.queueCapacity=8;
   collect(c,['B_sender_' policy{1}]);
  end
 case 'C'
  configs=course.cnConfigs();
  for k=1:numel(configs)
   c=cnse_config(configs(k));c.seed=11;
   collect(c,['C_' c.name]);
  end
 otherwise,error('CNSE2:Stage','Expected A, B or C');
end
writetable(struct2table(rows),fullfile(folder,['stage_' upper(stage) '_results.csv']));
writetable(validation,fullfile(folder,['stage_' upper(stage) '_validation.csv']));
cnse2_compare(upper(stage));
assert(all(validation.pass),'CNSE2:Validation','A trace-oracle check failed; inspect the stage validation CSV.');

 function collect(c,label)
  r=cnse2_run(c,label);m=r.metrics;
  m.run=string(label);m.config=string(c.name);m.seed=c.seed;m.duration=c.duration;
  rate=r.rateLog(r.rateLog(:,1)<=c.duration,2);
  m.rate_min=min(rate);m.rate_final=rate(end);
  m.sent=size(r.tx,1);m.received=size(r.rx,1);m.results=size(r.results,1);
  m.reports_sent=size(r.reports,1);m.reports_delivered=size(r.feedback,1);
  m.sender_overflow=r.senderDrops;m.ai_overflow=r.aiDrops;
  m.sender_replaced=size(r.camera,1)-size(r.qLog,1)-r.senderDrops;
  m.ai_replaced=sum(r.frames(:,6)==1)-size(r.results,1)-r.aiDrops;
  m.reordered=sum(r.rx(:,11));
  m.late_fragments=r.late;
  if isempty(rows),rows=m;else,rows(end+1)=m;end
  v=r.validation;v.run=repmat(string(label),height(v),1);
  if isempty(validation),validation=v;else,validation=[validation;v];end %#ok<AGROW>
  writetable(struct2table(rows),fullfile(folder,['stage_' upper(stage) '_results.csv']));
 end
end
