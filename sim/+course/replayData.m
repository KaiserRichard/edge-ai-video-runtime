function d=replayData(input)
% App interchange: panel cells contain time, values, labels, note, mode.
names={'Video and AI label','Sequence gaps and reorder','Loss counters',...
 'Packet and frame jitter','Playout occupancy and deadline','Deadline hit ratio',...
 'Capture to result and breakdown','RTCP SR RR APP timeline','Bitrate decisions',...
 'FIFO or latest age and queue','Hardware temperature and throttle','Supervisor state',...
 'Inference latency distribution','Per-core CPU and memory','UART activity','Fault markers'};
d=struct('name','Unavailable','duration',1,'panels',{cell(1,numel(names))});
for k=1:numel(names)
 d.panels{k}=struct('name',names{k},'t',[],'y',[],'labels',{{}},...
  'note','Not present in this log. No values inferred.','mode','line');
end
if ischar(input) || isstring(input)
 [~,name,ext]=fileparts(input);d.name=name;
 if strcmpi(ext,'.mat'),s=load(input,'result');d=course.replayData(s.result);return;end
 opts=detectImportOptions(input);
 textColumns=intersect({'image_file','ai_label'},opts.VariableNames);
 if ~isempty(textColumns),opts=setvartype(opts,textColumns,'string');end
 T=readtable(input,opts);vars=T.Properties.VariableNames;
 assert(height(T)>0,'course:LogSchema','Replay CSV must contain at least one row');
 if all(ismember({'t_input_ns','t_send_ns'},vars))
  assert(all(isfinite(T.t_input_ns)) && all(isfinite(T.t_send_ns)) && ...
   all(T.t_send_ns>=T.t_input_ns) && all(diff(T.t_send_ns)>=0),...
   'course:LogTime','Bridge timestamps must be finite, causal and ordered by send time');
  origin=min(T.t_input_ns);t=(T.t_send_ns-origin)*1e-9;cap=(T.t_input_ns-origin)*1e-9;
  d=put(d,7,t,1000*(t-cap),{'capture to bridge send (ms)'},'Measured Pi clock; UART arrival unavailable.');
  if numel(t)>1 && t(end)>t(1)
   [~,at,age]=course.aoi(t,cap,t(1),t(end));
   d=put(d,10,at,age*1000,{'AoI at bridge send (ms)'},'Measured log. Endpoint differs from MCU reception.');
  end
  if ismember('t_done_ns',vars)
   v=1000*((T.t_done_ns-origin)*1e-9-cap);
   d=put(d,13,t,v,{'capture to inference completion (ms)'},'Includes input wait; not isolated inference service.');
   d.panels{13}.mode='hist';
  end
  d.duration=max(t);return;
 end
 assert(ismember('t',vars),'course:LogSchema','CSV needs t seconds, or native bridge timestamps.');
 assert(all(isfinite(T.t)) && all(diff(T.t)>=0),'course:LogTime','t must be finite and nondecreasing');
 d.duration=max(T.t);
 % Canonical wide CSV; absent columns remain explicitly unavailable.
 maps={{2,{'seq','packet_status'}},{3,{'kernel_loss','sequence_loss','rr_loss'}},...
  {4,{'jitter_ms','frame_jitter_ms','configured_jitter_ms'}},...
  {5,{'playout_occupancy','deadline_slack_ms'}},{6,{'ontime_rolling','ontime_cumulative'}},...
  {7,{'latency_ms','capture_send_ms','network_playout_ms','queue_ms','inference_ms'}},...
  {8,{'rtcp_type'}},{9,{'bitrate_mbps','quality','fps'}},...
  {10,{'aoi_fifo_ms','aoi_latest_ms','queue_fifo','queue_latest'}},...
  {11,{'temperature_c','throttled','rssi_dbm','tx_mbps'}},...
  {12,{'state','reason'}},{13,{'inference_ms'}},...
  {14,{'cpu0','cpu1','cpu2','cpu3','rss_mib'}},{15,{'uart_bytes','crc_errors'}},{16,{'fault_active'}}};
 for k=1:numel(maps)
  cols=maps{k}{2};cols=cols(ismember(cols,vars));
  if ~isempty(cols),d=put(d,maps{k}{1},T.t,T{:,cols},cols,'Imported canonical log; units named in legend.');end
 end
 if ismember('seq',vars)
  status=zeros(height(T),1);
  if ismember('packet_status',vars),status=T.packet_status;end
  d.panels{2}.y=[T.seq status];d.panels{2}.mode='packets';
 end
 if any(ismember({'ai_label','image_file'},vars))
  video=struct('t',T.t,'file',strings(height(T),1),'label',strings(height(T),1),...
   'confidence',NaN(height(T),1),'bad',false(height(T),1));
  if ismember('ai_label',vars),video.label=T.ai_label;end
  if ismember('image_file',vars)
   for j=find(~ismissing(T.image_file) & strlength(T.image_file)>0)'
    video.file(j)=string(fullfile(fileparts(input),T.image_file(j)));
   end
  end
  if ismember('ai_confidence',vars),video.confidence=T.ai_confidence;end
  if ismember('frame_bad',vars),video.bad=T.frame_bad==1;end
  d.panels{1}.video=video;d.panels{1}.mode='video';
  d.panels{1}.note='Timestamped replay images and labels; no classifier runs in the app.';
 end
 d.panels{13}.mode='hist';return;
end
r=input;c=r.config;d.name=[c.project ': ' c.name ' (' r.backend ')'];d.duration=c.duration;
ai=r.Inference.log;
if ~isempty(ai)
 d=put(d,7,ai(:,1),1000*[ai(:,1)-ai(:,3) ai(:,4) ai(:,5)],...
  {'capture-result','inference','queue'},'Simulation milliseconds; labels/classification are not simulated.');
 if strcmpi(c.project,'CN')
  [~,t,a]=course.aoi(ai(:,1),ai(:,3),c.warmup,c.duration);
  d=put(d,10,t,a*1000,{[c.policy ' result AoI (ms)']},...
   'Configured observation window; unavailable if uninitialized at warm-up. Compare the paired policy file.');
  d.panels{10}.secondary=r.Inference.aux(:,1:2);
 end
 d=put(d,13,ai(:,1),1000*ai(:,4),{'service ms'},'Empirical resampling or configured fixed service.');d.panels{13}.mode='hist';
end
if strcmpi(c.project,'CN')
 p=r.Netem.log;rx=r.Receiver.log;rr=r.Receiver.aux;f=r.Receiver.frames;
 if ~isempty(p)
  dropped=any(p(:,4:5)>0,2);
  events=sortrows([p(dropped,1:2) ones(sum(dropped),1);rx(:,1:2) 2*rx(:,5)],1);
  d=put(d,2,events(:,1),events(:,2:3),{'sequence','status'},...
   'Grey: received; red: channel drop; orange: reordered. Drops use simulator send time; receives use arrival time.');
  d.panels{2}.mode='packets';
  ts=(0:.1:c.duration)';loss=zeros(numel(ts),3);
  for i=1:numel(ts)
   sent=p(:,1)<=ts(i);ns=sum(sent);received=rx(:,1)<=ts(i);
   loss(i,1)=sum(any(p(sent,4:5)>0,2))/max(1,ns);
   loss(i,2)=max(0,1-sum(received & rx(:,4)==0)/max(1,ns));
   j=find(rr(:,1)<=ts(i),1,'last');if ~isempty(j),loss(i,3)=rr(j,3)/256;end
  end
  d=put(d,3,ts,loss,{'channel drops / sent','not yet received / sent','RR interval fraction'},...
   'Channel replaces kernel counter in simulation. In-flight packets affect sender/receiver gap count.');
 end
 if ~isempty(rx)
  d=put(d,4,rx(:,1),[rx(:,6:7) repmat(1000*c.jitter,size(rx,1),1)],...
   {'packet J (ms)','frame J (ms)','configured jitter (ms)'},'Configured jitter is a channel parameter, not an estimator target.');
 end
 if ~isempty(f)
  valid=isfinite(f(:,3));ff=f(valid,:);slack=1000*(ff(:,3)-ff(:,4));slack(~isfinite(slack))=NaN;
  d=put(d,5,ff(:,3),slack,{'deadline - completion (ms)'},'Negative means late; missing completion is NaN. Right axis: complete frames waiting.');
  ts=(0:.01:c.duration)';occ=zeros(size(ts));
  for i=1:numel(ts),occ(i)=sum(f(:,4)<=ts(i) & f(:,3)>ts(i));end
  d.panels{5}.secondary=[ts occ];
  hits=ff(:,6);rolling=zeros(size(hits));
  for i=1:numel(hits),rolling(i)=mean(hits(ff(:,3)>ff(i,3)-5 & ff(:,3)<=ff(i,3)));end
  d=put(d,6,ff(:,3),[rolling cumsum(hits)./(1:numel(hits))'],{'rolling 5 s','cumulative'},'All generated frames in denominator.');
 end
 if ~isempty(rr),d=put(d,8,rr(:,1),[201*ones(size(rr,1),1) rr(:,3)/256],{'RR type','RR fraction'},'RR metadata every second. SR/APP wire exchange is outside this model.');end
 cam=r.Camera.log;
 if ~isempty(cam),d=put(d,9,cam(:,1),[cam(:,4)*8*c.fps/1e6 cam(:,5)],{'payload Mb/s','AIMD size scale'},'Camera bytes respond to the Stateflow output.');end
else
 s=r.state;d=put(d,12,s(:,1),s(:,2:3),{'state: 0 INIT 1 FRESH 2 HOLD 3 FAILSAFE','reason'},'1 kHz Stateflow or MATLAB oracle; FAILSAFE latched.');
 u=r.UART.log;
 if ~isempty(u)
  d=put(d,15,u(:,1),1000*u(:,6),{'reception source age (ms)'},'35-byte result frames, 8N1 at 921600 baud.');
  [~,at,age]=course.aoi(u(:,1),u(:,3),c.warmup,c.duration);
  d=put(d,10,at,age*1000,{[c.policy ' MCU receipt AoI (ms)']},...
   'Configured window at MCU receipt; unavailable if uninitialized at warm-up. Right axis: input waiting frames.');
  d.panels{10}.secondary=r.Inference.aux(:,1:2);
 end
 a=r.UART.aux;
 if ~isempty(a),d=put(d,16,a(:,1),a(:,4),{'fault active'},['Injected ' c.fault '; no Linux scheduler model.']);end
end
end
function d=put(d,k,t,y,labels,note)
d.panels{k}.t=t;d.panels{k}.y=y;d.panels{k}.labels=labels;d.panels{k}.note=note;
end
