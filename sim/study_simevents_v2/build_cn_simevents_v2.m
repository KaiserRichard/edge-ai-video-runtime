function build_cn_simevents_v2()
% Build generated/CN_simevents_v2.slx. v1 (study_simevents/build_cn_simevents.m)
% is left untouched. v2 replaces every CNSEStage block by native SimEvents
% blocks (generators, servers, replicator, switches, terminators) plus small
% attribute actions and Simulink Function blocks, and frames each stage with
% coloured Simulink area annotations.
root=fileparts(fileparts(mfilename('fullpath')));v2=fullfile(root,'study_simevents_v2');
addpath(root,fullfile(root,'study_simevents'),v2,fullfile(root,'generated'));
assert(~isempty(ver('slde')) && ~isempty(ver('comm')));
Simulink.fileGenControl('set','CacheFolder',fullfile(v2,'cache'),...
 'CodeGenFolder',fullfile(v2,'codegen'),'createDir',true);
load_system('simulink');load_system('sldelib');load_system('sflib');

% Entity bus. v1 fields plus the receiver attributes that are now visible.
names={'seq','rtpTimestamp','size','SSRC','frame','fragment','count','marker','capture',...
 'route','rr','reverseDelay','forwardDelay','sentAt','arrival','deadline','jitterMs','complete'};
elements=Simulink.BusElement.empty;
for k=1:numel(names)
 e=Simulink.BusElement;e.Name=names{k};e.DataType='double';
 if strcmp(e.Name,'rr'),e.Dimensions=[1 7];else,e.Dimensions=1;end
 elements(k)=e;
end
b=Simulink.Bus;b.Elements=elements;
c=cnse_config();m='CN_simevents_v2';
if bdIsLoaded(m),close_system(m,0);end
dictionaryName=[m '.sldd'];dictionaryFile=fullfile(root,'generated',dictionaryName);
if isfile(dictionaryFile),dictionary=Simulink.data.dictionary.open(dictionaryFile);
else,dictionary=Simulink.data.dictionary.create(dictionaryFile);end
design=getSection(dictionary,'Design Data');
if exist(design,'CNSE2Entity'),setValue(getEntry(design,'CNSE2Entity'),b);
else,addEntry(design,'CNSE2Entity',b);end
saveChanges(dictionary);close(dictionary);
new_system(m);
set_param(m,'DataDictionary',dictionaryName);
ws=get_param(m,'ModelWorkspace');assignin(ws,'c',c);cnse2_params(m,c);
set_param(m,'SolverType','Variable-step','Solver','ode45','MaxStep','.001',...
 'StopTime','c.duration+c.drain','ReturnWorkspaceOutputs','on','SaveOutput','off',...
 'InitFcn','cnse2_runtime(''init'',evalin(get_param(''CN_simevents_v2'',''ModelWorkspace''),''c''));');

X='coder.extrinsic(''cnse2_runtime'');';
col.source=[0.82 0.91 0.97];col.link=[0.83 0.94 0.95];col.sink=[0.88 0.95 0.85];
col.feedback=[0.99 0.94 0.81];col.loss=[0.98 0.86 0.86];col.helper=[0.93 0.90 0.98];

%% Frames -------------------------------------------------------------------
S=sub('Frames');
inp(S,'AIMD size scale',[40 293 70 307]);
fn=sfun(S,'sizeScale() reads the AIMD wire',[150 270 330 330],'y=sizeScale()');
add_block('simulink/Sources/In1',[fn '/scale'],'Position',[100 73 130 87]);
set_param([fn '/y'],'Position',[300 70 350 90]);
add_line(fn,'scale/1','y/1');
note(fn,'Signal port -> function output: event actions can read the AIMD scale.',[60 140]);
g=gen(S,'Frame clock',[180 90 300 150],'1/c.fps');
set_param(g,'GenerateAction',txt(X,...
 'scale = sizeScale();              % AIMD size scale (wire on the left)',...
 'row = zeros(1,3);',...
 'row = cnse2_runtime(''frame'', scale);  % seeded camera draw: [frame capture bytes]',...
 'entity.frame = row(1);',...
 'entity.capture = row(2);',...
 'entity.size = row(3);',...
 'entity.route = 1 + double(row(1) == 0);  % 2 = capture window closed'));
osw(S,'Capture window open?',[470 85 520 155]);
term(S,'After capture end',[570 200 660 240]);
outp(S,'Frame',[730 98 760 112]);
add_line(S,'AIMD size scale/1',[short(fn) '/1']);
con(S,'Frame clock','Capture window open?');con(S,'Capture window open?','Frame');
con(S,'Capture window open?','After capture end',2);
area(S,[110 30 400 375],'1  Camera clock: seeded size x AIMD',col.source);
area(S,[430 30 690 270],'2  Stop after capture',col.helper);
note(S,'Frame clock action calls sizeScale()',[125 240]);
tidy(S);

%% Sender queue -------------------------------------------------------------
S=sub('Sender Queue');
inp(S,'Frame',[40 108 70 122]);
sv=server(S,'Admission check',[120 85 210 145],'0');
set_param(sv,'EntryAction',txt(X,'route = 1;',...
 'route = cnse2_runtime(''admitSender'');  % 2 when the FIFO already holds capacity frames',...
 'entity.route = route;'));
osw(S,'Sender admission',[270 80 320 150]);
q=queue(S,'Frame FIFO or latest',[400 85 490 145],'max(1,c.queueCapacity*strcmp(c.policy,''fifo''))');
set_param(q,'OverwriteOldest','on');queueActions(q,'sender');
server(S,'Sender processing',[560 85 650 145],'c.senderService');
term(S,'Sender overflow',[400 215 490 255]);
outp(S,'To packetizer',[720 108 750 122]);
con(S,'Frame','Admission check');con(S,'Admission check','Sender admission');
con(S,'Sender admission','Frame FIFO or latest');con(S,'Sender admission','Sender overflow',2);
con(S,'Frame FIFO or latest','Sender processing');con(S,'Sender processing','To packetizer');
area(S,[100 35 345 290],'1  Admission: FIFO full -> drop',col.loss);
area(S,[375 35 680 290],'2  Lesson 07 queue + service',col.source);
tidy(S);

%% RTP packetizer -----------------------------------------------------------
S=sub('RTP Packetizer');
inp(S,'Frame',[40 113 70 127]);
sv=server(S,'Count fragments',[130 85 240 155],'0');
set_param(sv,'EntryAction',txt('persistent nextSeq',X,...
 'if isempty(nextSeq), nextSeq = 0; end',...
 'cnse2_runtime(''packetize'', entity);   % trace only',...
 'entity.count = ceil(entity.size / payload);              % N fragments',...
 'entity.rtpTimestamp = mod(round(entity.capture*90000), 2^32); % 90 kHz RTP clock',...
 'entity.SSRC = 20261119;',...
 'entity.seq = nextSeq;                % first sequence number of the frame',...
 'nextSeq = nextSeq + entity.count;'));
r=[S '/Make N copies'];add_block('sldelib/Entity Replicator',r,'Position',[340 85 430 155],...
 'ReplicasDepartFrom','Single output port','ReplicationAmountSource','Attribute','ReplicateAttributeName','count');
term(S,'Original frame record',[490 205 580 245]);
queue(S,'Fragment line',[490 90 570 150],'Inf');
sv=server(S,'Stamp RTP header',[660 85 770 155],'0');
set_param(sv,'EntryAction',txt('persistent k',...
 'if isempty(k), k = 0; end',...
 'k = k + 1;                                   % fragment index 1..N',...
 'entity.fragment = k;',...
 'entity.seq = mod(entity.seq + k - 1, 65536);',...
 'entity.size = min(payload, entity.size - (k-1)*payload);',...
 'entity.marker = double(k == entity.count);  % last fragment of the frame',...
 'if k == entity.count, k = 0; end'));
outp(S,'RTP packets',[910 113 940 127]);
con(S,'Frame','Count fragments');con(S,'Count fragments','Make N copies');
con(S,'Make N copies','Fragment line');con(S,'Make N copies','Original frame record',2);
con(S,'Fragment line','Stamp RTP header');con(S,'Stamp RTP header','RTP packets');
area(S,[100 35 300 280],'1  Count N, 90 kHz stamp',col.source);
area(S,[315 35 610 280],'2  Fan-out into N copies',col.helper);
area(S,[625 35 870 280],'3  Seq, size, marker',col.source);
note(S,'N = ceil(bytes / payload)',[115 200]);
note(S,'copy k: seq + k - 1, marker if k = N',[640 200]);
tidy(S);

%% Serialization ------------------------------------------------------------
S=sub('Serialization');
inp(S,'RTP',[40 113 70 127]);
queue(S,'Packet FIFO',[140 90 220 150],'Inf');
sv=server(S,'Link serializer',[300 85 400 155],'0');
set_param(sv,'ServiceTimeSource','MATLAB action','ServiceTimeAction',...
 'dt = 8*(entity.size + 48)/linkBitRate;   % payload + 48 B headers at link bit rate',...
 'ExitAction',txt(X,'cnse2_runtime(''serialized'', entity);   % trace only'));
outp(S,'To channel',[530 113 560 127]);
con(S,'RTP','Packet FIFO');con(S,'Packet FIFO','Link serializer');con(S,'Link serializer','To channel');
area(S,[115 35 470 210],'FIFO + serial link',col.link);
note(S,'service = 8 (bytes + 48) / bit rate',[240 190]);
tidy(S);

%% Channel ------------------------------------------------------------------
S=sub('Channel');
inp(S,'RTP',[40 128 70 142]);
sv=server(S,'Seeded loss draw',[120 100 220 170],'0');
set_param(sv,'EntryAction',txt(X,'route = 1; sentAt = 0;',...
 '[route, sentAt] = cnse2_runtime(''lossDraw'', entity);  % course.Loss, seed + 200',...
 'entity.route = route;     % 2 = dropped',...
 'entity.sentAt = sentAt;'));
osw(S,'Loss route',[280 100 330 170]);
term(S,'Netem drops',[380 230 470 270]);
sv=server(S,'Seeded delay draw',[550 100 650 170],'0');
set_param(sv,'EntryAction',txt(X,'d = 0;',...
 'd = cnse2_runtime(''delayDraw'', entity);  % course.Delay, seed + 300',...
 'entity.forwardDelay = d;'));
co=[S '/Guaranteed delay (s)'];add_block('simulink/Sources/Constant',co,...
 'Value','c.transportBase+c.transportFloor','Position',[560 225 670 255]);
td=[S '/Entity Transport Delay'];add_block('simulink/Continuous/Entity Transport Delay',td,'Position',[730 100 820 170]);
set_param(td,'ShowName','on');
sv=server(S,'Per-packet delay remainder',[880 100 980 170],'0');
set_param(sv,'Capacity','Inf','ServiceTimeSource','MATLAB action','ServiceTimeAction',...
 txt(X,'dt = 0;','dt = cnse2_runtime(''propagation'', entity);  % forwardDelay - time already spent'));
outp(S,'To receiver',[1060 128 1090 142]);
con(S,'RTP','Seeded loss draw');con(S,'Seeded loss draw','Loss route');
con(S,'Loss route','Seeded delay draw');con(S,'Loss route','Netem drops',2);
con(S,'Seeded delay draw','Entity Transport Delay');
add_line(S,'Guaranteed delay (s)/1','Entity Transport Delay/2','autorouting','smart');
con(S,'Entity Transport Delay','Per-packet delay remainder');con(S,'Per-packet delay remainder','To receiver');
area(S,[100 40 500 300],'1  Seeded loss draw + loss switch',col.loss);
area(S,[525 40 1010 300],'2  Seeded delay: guaranteed + remainder',col.link);
tidy(S);

%% Receiver -----------------------------------------------------------------
S=sub('Receiver');
inp(S,'RTP',[40 128 70 142]);
sv=server(S,'Arrival',[145 95 255 175],'0');
set_param(sv,'EntryAction',txt(X,'t = 0;','t = cnse2_runtime(''time'');',...
 'entity.arrival = t;',...
 'entity.jitterMs = rfcJitter(t, entity.rtpTimestamp);               % RFC 3550 block',...
 'entity.deadline = playoutDeadline(t, entity.rtpTimestamp, playoutDepth); % playout clock',...
 'entity.complete = fragmentCounter(entity.frame, entity.count);      % 1 = frame now complete',...
 'cnse2_runtime(''receive'', entity);      % RTCP counters and trace',...
 'entity.route = 1 + double(t > entity.deadline + 1e-12);  % 2 = late'));
mfun(S,'RFC 3550 jitter',[75 290 325 350],'J=rfcJitter(t,ts)',{'t','ts'},'J','D = (R_j - R_i) 90000 - (S_j - S_i);   J = J + (|D| - J) / 16',{
 'function J = jit(t, ts)'
 '% RFC 3550 section 6.4.1 interarrival jitter, 90 kHz units, returned in ms.'
 'persistent last lastTs Jt started'
 'if isempty(started), started = false; last = 0; lastTs = 0; Jt = 0; end'
 'if started'
 '    ds = mod(ts - lastTs + 2^31, 2^32) - 2^31;'
 '    D = (t - last)*90000 - ds;'
 '    Jt = Jt + (abs(D) - Jt)/16;'
 'end'
 'started = true; last = t; lastTs = ts;'
 'J = 1000*Jt/90000;'});
mfun(S,'Playout deadline',[75 390 325 450],'d=playoutDeadline(t,ts,depth)',{'t','ts','depth'},'d','d = t_first + (ts - ts_first) / 90000 + depth',{
 'function d = dl(t, ts, depth)'
 '% Anchor on the first packet, then deadline = anchor + RTP time offset + depth.'
 'persistent anchor ts0'
 'if isempty(anchor), anchor = t; ts0 = ts; end'
 'delta = mod(ts - ts0 + 2^31, 2^32) - 2^31;'
 'd = anchor + delta/90000 + depth;'});
mfun(S,'Fragment counter',[75 490 325 550],'done=fragmentCounter(frame,count)',{'frame','count'},'done','got(frame) += 1;   done = (got(frame) == N)',{
 'function done = cnt(frame, count)'
 '% Count fragments per frame; done = 1 on the fragment that completes it.'
 'persistent got'
 'if isempty(got), got = zeros(1, 65536); end'
 'k = mod(frame, 65536) + 1;'
 'got(k) = got(k) + 1;'
 'done = double(got(k) == count);'});
osw(S,'Deadline check',[390 100 440 170]);
t=term(S,'Late fragments',[500 215 590 255]);
set_param(t,'EntryAction',txt(X,'cnse2_runtime(''lateFragment'');'));
sv=server(S,'Playout buffer',[500 95 610 175],'0');
set_param(sv,'Capacity','Inf','ServiceTimeSource','MATLAB action',...
 'ServiceTimeAction','dt = max(0, entity.deadline - entity.arrival);   % hold until playout deadline',...
 'ServiceCompleteAction','entity.route = 2 - entity.complete;   % 1 = fragment that completed the frame');
osw(S,'Frame complete?',[690 100 740 170]);
term(S,'Merged or incomplete',[800 215 890 255]);
sv=server(S,'Frame to AI',[800 95 900 175],'0');
set_param(sv,'EntryAction',txt(X,'cnse2_runtime(''release'', entity);   % trace only',...
 'entity.fragment = 0;'));
outp(S,'Playout',[980 128 1010 142]);
g=gen(S,'RTCP report clock (1 s)',[720 330 840 390],'1');
set_param(g,'GenerateEntityAtSimulationStart','off','GenerateAction',txt(X,'rr = zeros(1,7);',...
 'rr = cnse2_runtime(''report'');   % [valid fraction jitter cumulative highest 0 0]',...
 'entity.rr = rr;'));
outp(S,'RTCP RR',[980 353 1010 367]);
con(S,'RTP','Arrival');con(S,'Arrival','Deadline check');
con(S,'Deadline check','Playout buffer');con(S,'Deadline check','Late fragments',2);
con(S,'Playout buffer','Frame complete?');con(S,'Frame complete?','Frame to AI');
con(S,'Frame complete?','Merged or incomplete',2);
con(S,'Frame to AI','Playout');con(S,'RTCP report clock (1 s)','RTCP RR');
area(S,[55 40 345 580],'1  Arrival: jitter, deadline, count',col.helper);
area(S,[365 40 640 290],'2  Playout-deadline gate',col.loss);
area(S,[660 40 935 290],'3  Reassembly: 1 entity/frame',col.sink);
area(S,[660 305 935 430],'4  RTCP report every 1 s',col.feedback);
note(S,'Called by the Arrival action:',[70 255]);
tidy(S);

%% Inference ----------------------------------------------------------------
S=sub('Inference');
inp(S,'Playout frame',[40 113 70 127]);
sv=server(S,'AI admission check',[120 85 220 155],'0');
set_param(sv,'EntryAction',txt(X,'route = 1;',...
 'route = cnse2_runtime(''admitAI'');   % 2 when the AI FIFO is full','entity.route = route;'));
osw(S,'AI admission',[280 85 330 155]);
q=queue(S,'AI waiting frames',[400 90 490 150],'max(1,c.queueCapacity*strcmp(c.policy,''fifo''))');
set_param(q,'OverwriteOldest','on');queueActions(q,'ai');
server(S,'Inference service',[560 90 650 150],'c.samples(1)');
t=term(S,'AI result',[720 90 800 150]);
set_param(t,'EntryAction',txt(X,'cnse2_runtime(''result'', entity);   % result time for latency and AoI'));
term(S,'AI overflow',[400 215 490 255]);
con(S,'Playout frame','AI admission check');con(S,'AI admission check','AI admission');
con(S,'AI admission','AI waiting frames');con(S,'AI admission','AI overflow',2);
con(S,'AI waiting frames','Inference service');con(S,'Inference service','AI result');
area(S,[100 35 355 290],'1  Admission: FIFO full -> drop',col.loss);
area(S,[375 35 830 290],'2  AI queue, service and result',col.sink);
tidy(S);

%% RTCP reverse path --------------------------------------------------------
S=sub('RTCP Reverse Path');
inp(S,'From receiver',[40 113 70 127]);
sv=server(S,'Seeded reverse draw',[120 85 230 155],'0');
set_param(sv,'EntryAction',txt(X,'route = 1; d = 0;',...
 '[route, d] = cnse2_runtime(''reverseDraw'');  % course.Loss seed+600, course.Delay seed+700',...
 'entity.route = route;   % 2 = report lost','entity.reverseDelay = d;'));
osw(S,'Reverse loss',[290 85 340 155]);
term(S,'RR drops',[400 215 490 255]);
sv=server(S,'Reverse propagation',[400 85 500 155],'0');
set_param(sv,'Capacity','Inf','ServiceTimeSource','Attribute','ServiceTimeAttributeName','reverseDelay');
t=term(S,'RR at sender',[580 85 670 155]);
set_param(t,'NumberEntitiesArrived','on','EntryAction',txt(X,'cnse2_runtime(''feedback'', entity);  % queue RR for AIMD'));
outp(S,'Delivered RR count',[750 128 780 142]);
con(S,'From receiver','Seeded reverse draw');con(S,'Seeded reverse draw','Reverse loss');
con(S,'Reverse loss','Reverse propagation');con(S,'Reverse loss','RR drops',2);
con(S,'Reverse propagation','RR at sender');con(S,'RR at sender','Delivered RR count');
area(S,[100 35 360 290],'1  Seeded reverse loss',col.loss);
area(S,[380 35 700 290],'2  Reverse delay, delivery count to AIMD',col.feedback);
tidy(S);

%% Top level ----------------------------------------------------------------
media={'Frames','Sender Queue','RTP Packetizer','Serialization','Channel','Receiver','Inference'};
for k=1:numel(media)-1
 add_line(m,[media{k} '/1'],[media{k+1} '/1']);
end
add_block('simulink/User-Defined Functions/MATLAB System',[m '/Observations'],...
 'System','CNSE2Monitor','SimulateUsing','Interpreted execution');
add_line(m,'Receiver/2','RTCP Reverse Path/1');
add_line(m,'RTCP Reverse Path/1','Observations/2');
add_block('simulink/Discrete/Unit Delay',[m '/Feedback tick'],'SampleTime','.001','InitialCondition','1');
add_block('sflib/Chart',[m '/AIMD']);
rt=sfroot;ch=rt.find('-isa','Stateflow.Chart','Path',[m '/AIMD']);
ch.ActionLanguage='MATLAB';ch.ChartUpdate='DISCRETE';ch.SampleTime='.001';
data(ch,'rr','Input',1,'[7 1]');data(ch,'enabled','Input',2,'1');
data(ch,'rate','Output',1,'1');data(ch,'clean','Local',0,'1');
s=Stateflow.State(ch);s.Position=[40 50 440 320];
s.LabelString=sprintf(['RUN\nentry: rate=1;clean=0;\nduring:\n' ...
 'if rr(1)>0 && enabled>0\n if rr(2)/256>0.02\n rate=max(0.15,0.8*rate);clean=0;\n' ...
 ' elseif rr(2)/256<=0.005\n clean=clean+1;\n if clean>=3\n rate=min(1.5,rate+0.05);clean=0;\n end\n' ...
 ' else\n clean=0;\n end\nend']);
tr=Stateflow.Transition(ch);tr.Destination=s;tr.DestinationOClock=0;
tr.SourceEndPoint=[260 20];tr.MidPoint=[260 35];
add_block('simulink/Sources/Constant',[m '/Adaptive enabled'],'Value','double(c.adaptive)');
add_line(m,'Observations/1','AIMD/1');add_line(m,'Adaptive enabled/1','AIMD/2');
add_line(m,'AIMD/1','Feedback tick/1');add_line(m,'Feedback tick/1','Observations/1');
add_line(m,'Feedback tick/1','Frames/1');
add_block('simulink/Signal Routing/Demux',[m '/Scope signals'],'Outputs','5');
add_block('simulink/Sinks/Scope',[m '/Dashboard'],'NumInputPorts','5');
scope=get_param([m '/Dashboard'],'ScopeConfiguration');
scope.LayoutDimensions=[5 1];scope.ShowLegend=true;scope.TimeUnits='Seconds';
add_line(m,'Observations/2','Scope signals/1');
labels={'Target payload (Mb/s)','Channel loss (fraction)','RFC jitter (ms)',...
 'Playout occupancy (frames)','AI-result AoI (ms)'};
for k=1:numel(labels)
 h=add_line(m,sprintf('Scope signals/%d',k),sprintf('Dashboard/%d',k));set_param(h,'Name',labels{k});
end
add_block('simulink/Sinks/To Workspace',[m '/Dashboard trace'],'VariableName','dashboard','SaveFormat','Timeseries');
add_line(m,'Observations/2','Dashboard trace/1');
topLayout(m,media,col);
save_system(m,fullfile(root,'generated',[m '.slx']));

 %% helpers ---------------------------------------------------------------
 function S=sub(name)
  S=[m '/' name];add_block('simulink/Ports & Subsystems/Subsystem',S);
  delete_line(S,'In1/1','Out1/1');delete_block([S '/In1']);delete_block([S '/Out1']);
 end
 function p=blk(S,lib,name,pos)
  p=[S '/' name];add_block(['sldelib/' lib],p,'Position',pos);
 end
 function p=gen(S,name,pos,period)
  p=blk(S,'Entity Generator',name,pos);
  set_param(p,'Period',period,'EntityType','Bus object','EntityTypeName','CNSE2Entity');
 end
 function p=server(S,name,pos,dt),p=blk(S,'Entity Server',name,pos);set_param(p,'ServiceTimeValue',dt);end
 function p=queue(S,name,pos,cap),p=blk(S,'Entity Queue',name,pos);set_param(p,'Capacity',cap);end
 function p=term(S,name,pos),p=blk(S,'Entity Terminator',name,pos);end
 function p=osw(S,name,pos)
  p=blk(S,sprintf('Entity\nOutput Switch'),name,pos);
  set_param(p,'SwitchingCriterion','From attribute','SwitchAttributeName','route');
 end
 function inp(S,name,pos),add_block('simulink/Sources/In1',[S '/' name],'Position',pos);end
 function outp(S,name,pos),add_block('simulink/Sinks/Out1',[S '/' name],'Position',pos);end
 function queueActions(p,kind)
  set_param(p,'EntryAction',txt(X,sprintf('cnse2_runtime(''%sQueue'', 1);   %% waiting count',kind)),...
   'ExitAction',txt(X,sprintf('cnse2_runtime(''%sQueue'', -1);',kind)));
 end
 function p=sfun(S,name,pos,proto)
  p=[S '/' name];add_block('simulink/User-Defined Functions/Simulink Function',p,'Position',pos);
  trig=find_system(p,'SearchDepth',1,'BlockType','TriggerPort');
  set_param(trig{1},'FunctionPrototype',proto);set_param(p,'ContentPreviewEnabled','off');
  delete_line(find_system(p,'FindAll','on','SearchDepth',1,'Type','line'));
  for a=find_system(p,'SearchDepth',1,'BlockType','ArgIn')'
   set_param(a{1},'OutDataTypeStr','double','PortDimensions','1');
  end
  for a=find_system(p,'SearchDepth',1,'BlockType','ArgOut')'
   set_param(a{1},'OutDataTypeStr','double','PortDimensions','1');
  end
 end
 function mfun(S,name,pos,proto,ins,out,formula,code)
  p=sfun(S,name,pos,proto);n=numel(ins);h=40*n;
  f=[p '/' name];add_block('simulink/User-Defined Functions/MATLAB Function',f,'Position',[200 60 340 60+h]);
  em=sfroot().find('-isa','Stateflow.EMChart','Path',f);em.Script=strjoin(code,newline);
  for i=1:n
   y=60+20*(2*i-1);
   set_param([p '/' ins{i}],'Position',[60 y-10 110 y+10]);
   add_line(p,[ins{i} '/1'],sprintf('%s/%d',name,i));
  end
  y=60+h/2;set_param([p '/' out],'Position',[410 y-10 460 y+10]);
  add_line(p,[name '/1'],[out '/1']);
  note(p,formula,[60 60+h+45]);
  note(p,'Double-click the MATLAB Function block to read the code.',[60 60+h+70]);
  set_param(p,'BackgroundColor','[0.93, 0.90, 0.98]','ContentPreviewEnabled','off');
 end
 function con(S,a,b,port)
  if nargin<4,port=1;end
  add_line(S,sprintf('%s/%d',a,port),[b '/1'],'autorouting','smart');
 end
end

function s=txt(varargin),s=strjoin(varargin,newline);end
function n=short(p),parts=strsplit(p,'/');n=parts{end};end
function d=data(ch,name,scope,port,sz)
d=Stateflow.Data(ch);d.Name=name;d.Scope=scope;d.DataType='double';d.Props.Array.Size=sz;
if port>0,d.Port=port;end
end
function area(S,pos,label,rgb)
% Same method as the M12 studio diagrams: a built-in Area annotation behind the blocks.
h=add_block('built-in/Area',[S '/' strrep(label,'/','//')],'Position',pos);
% For areas ForegroundColor is the fill as well, so set only BackgroundColor.
set_param(h,'BackgroundColor',sprintf('[%.2f, %.2f, %.2f]',rgb),'FontSize',11,'FontWeight','bold');
end
function note(S,label,xy)
a=Simulink.Annotation(S,label);a.Position=xy;a.FontSize=10;a.FontAngle='italic';
end
function tidy(S)
l=find_system(S,'FindAll','on','SearchDepth',1,'Type','line');
Simulink.BlockDiagram.routeLine(l);
end
function topLayout(m,media,col)
colors={col.source,col.source,col.source,col.link,col.link,col.sink,col.sink};
for k=1:numel(media)
 x=65+(k-1)*193;b=[m '/' media{k}];
 set_param(b,'Position',[x 95 x+141 163],'BackgroundColor',sprintf('[%.2f, %.2f, %.2f]',colors{k}),...
  'ContentPreviewEnabled','off');
end
set_param([m '/Receiver'],'Position',[1030 95 1171 175]);
set_param([m '/RTCP Reverse Path'],'Position',[860 235 1110 290],'Orientation','left',...
 'BackgroundColor',sprintf('[%.2f, %.2f, %.2f]',col.feedback),'ContentPreviewEnabled','off');
set_param([m '/Observations'],'Position',[430 360 580 440]);
set_param([m '/AIMD'],'Position',[700 330 830 395],'BackgroundColor',sprintf('[%.2f, %.2f, %.2f]',col.feedback),...
 'ContentPreviewEnabled','off');
set_param([m '/Adaptive enabled'],'Position',[540 470 640 495]);
set_param([m '/Feedback tick'],'Position',[300 520 360 555],'Orientation','left');
set_param([m '/Scope signals'],'Position',[930 405 935 505]);
set_param([m '/Dashboard'],'Position',[1060 400 1160 510]);
set_param([m '/Dashboard trace'],'Position',[1040 540 1180 575]);
tidy(m);
area(m,[45 50 1460 190],'RTP media path, left to right (each box opens to native SimEvents blocks)',col.source);
area(m,[700 205 1230 312],'RTCP receiver reports return to the sender',col.feedback);
area(m,[280 322 1230 595],'AIMD rate control (Stateflow) and dashboard',col.helper);
set_param(m,'ZoomFactor','FitSystem');
end
