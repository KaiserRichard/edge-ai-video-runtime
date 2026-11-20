function build_cn_simevents()
% Rebuild only the new model. Never call models/build_models here.
root=fileparts(fileparts(mfilename('fullpath')));addpath(root,fullfile(root,'study_simevents'),fullfile(root,'generated'));
assert(~isempty(ver('slde')) && ~isempty(ver('comm')));
Simulink.fileGenControl('set','CacheFolder',fullfile(root,'generated','se_cache'),...
 'CodeGenFolder',fullfile(root,'generated','se_codegen'),'createDir',true);
load_system('simulink');load_system('sldelib');load_system('sflib');
names={'seq','rtpTimestamp','size','SSRC','frame','fragment','count','marker','capture','route','rr','reverseDelay','forwardDelay','sentAt'};
elements=Simulink.BusElement.empty;
for k=1:numel(names)
 e=Simulink.BusElement;e.Name=names{k};e.DataType='double';
 if strcmp(e.Name,'rr'),e.Dimensions=[1 7];else,e.Dimensions=1;end
 elements(k)=e;
end
b=Simulink.Bus;b.Elements=elements;
c=cnse_config();m='CN_simevents';
if bdIsLoaded(m),close_system(m,0);end
dictionaryName=[m '.sldd'];
dictionaryFile=fullfile(root,'generated',dictionaryName);
if isfile(dictionaryFile)
 dictionary=Simulink.data.dictionary.open(dictionaryFile);
else
 dictionary=Simulink.data.dictionary.create(dictionaryFile);
end
design=getSection(dictionary,'Design Data');
if exist(design,'CNSEEntity')
 setValue(getEntry(design,'CNSEEntity'),b);
else
 addEntry(design,'CNSEEntity',b);
end
saveChanges(dictionary);
close(dictionary);
new_system(m);
set_param(m,'DataDictionary',dictionaryName);
ws=get_param(m,'ModelWorkspace');assignin(ws,'c',c);
set_param(m,'SolverType','Variable-step','Solver','ode45','MaxStep','.001',...
 'StopTime','c.duration+c.drain','ReturnWorkspaceOutputs','on','SaveOutput','off',...
 'InitFcn','cnse_runtime(''init'',evalin(get_param(''CN_simevents'',''ModelWorkspace''),''c''));','ZoomFactor','FitSystem');

% Frames and frame queue (overwrite affects waiting work, never active service).
g=blk('Entity Generator','Frame clock',[35 105 105 160]);
set_param(g,'Period','1/c.fps','EntityType','Bus object','EntityTypeName','CNSEEntity');
frame=des('Size new frame','frame',[175 105 270 160]);
wire(g,frame);
ad=blk(sprintf('Entity\nOutput Switch'),'Sender admission',[115 90 145 145]);
set_param(ad,'SwitchingCriterion','From attribute','SwitchAttributeName','route');
ds=blk('Entity Terminator','Sender overflow',[150 200 220 240]);
q=blk('Entity Queue','Frame FIFO or latest',[155 90 225 145]);
set_param(q,'Capacity','max(1,c.queueCapacity*strcmp(c.policy,''fifo''))','OverwriteOldest','on');
queueActions(q,'sender');
pace=blk('Entity Server','Sender processing',[275 90 345 145]);
set_param(pace,'ServiceTimeValue','c.senderService');
p=des('RTP fragment fanout','packetizer',[395 85 495 150]);
set_param(ad,'Position',[320 105 350 160]);
set_param(q,'Position',[405 105 475 160]);
set_param(pace,'Position',[530 105 600 160]);
set_param(ds,'Position',[405 205 475 245]);
set_param(p,'Position',[650 105 750 160]);
wire(frame,ad);wire(ad,q);add_line(m,[short(ad) '/2'],[short(ds) '/1'],'autorouting','on');wire(q,pace);wire(pace,p);
group({g,frame},'Frames');group({ad,ds,q,pace},'Sender Queue');group({p},'RTP Packetizer');
set_param([m '/Frames/In1'],'Name','AIMD size scale','Position',[45 215 75 235]);

q=blk('Entity Queue','Packet FIFO',[555 90 625 145]);set_param(q,'Capacity','Inf');
sv=blk('Entity Server','Bits divided by link bitrate',[675 90 755 145]);
set_param(sv,'ServiceTimeSource','MATLAB action','ServiceTimeAction',sprintf('coder.extrinsic(''cnse_runtime'');\ndt=0;dt=cnse_runtime(''serialize'',entity.size);'));
set_param(sv,'ExitAction',sprintf('coder.extrinsic(''cnse_runtime'');\ncnse_runtime(''serialized'',entity);'));
wire([m '/RTP Packetizer'],q);wire(q,sv);group({q,sv},'Serialization');

j=des('Seeded delay and loss draw','channel',[815 95 920 150]);
sw=blk(sprintf('Entity\nOutput Switch'),'Loss route',[970 95 1030 150]);
set_param(sw,'SwitchingCriterion','From attribute','SwitchAttributeName','route');
drop=blk('Entity Terminator','Netem drops',[1090 205 1165 250]);
td=add_block('simulink/Continuous/Entity Transport Delay',[m '/Entity Transport Delay'],...
 'Position',[1100 95 1180 150]);td=getfullname(td);
co=add_block('simulink/Sources/Constant',[m '/Guaranteed delay (s)'],...
 'Value','c.transportBase+c.transportFloor','Position',[960 25 1045 55]);co=getfullname(co);
prop=blk('Entity Server','Per-packet delay remainder',[1235 95 1320 150]);
set_param(prop,'Capacity','Inf','ServiceTimeSource','MATLAB action','ServiceTimeAction',...
 sprintf('coder.extrinsic(''cnse_runtime'');\ndt=0;dt=cnse_runtime(''propagation'',entity);'));
wire([m '/Serialization'],j);wire(j,sw);wire(sw,td);wire(td,prop);
add_line(m,[short(co) '/1'],[short(td) '/2'],'autorouting','on');
add_line(m,[short(sw) '/2'],[short(drop) '/1'],'autorouting','on');
group({j,sw,drop,td,co,prop},'Channel');

r=des('Reorder reassemble and deadline','receiver',[1330 85 1450 150]);
g=blk('Entity Generator','RR clock',[1300 260 1370 315]);
set_param(g,'Period','1','GenerateEntityAtSimulationStart','off','EntityType','Bus object','EntityTypeName','CNSEEntity');
add_line(m,[short(g) '/1'],[short(r) '/2']);
wire([m '/Channel'],r);group({r,g},'Receiver');
ad=blk(sprintf('Entity\nOutput Switch'),'AI admission',[1470 90 1500 145]);
set_param(ad,'SwitchingCriterion','From attribute','SwitchAttributeName','route');
ds=blk('Entity Terminator','AI overflow',[1480 200 1550 240]);
q=blk('Entity Queue','AI waiting frames',[1510 90 1580 145]);
set_param(q,'Capacity','max(1,c.queueCapacity*strcmp(c.policy,''fifo''))','OverwriteOldest','on');
queueActions(q,'ai');
sv=blk('Entity Server','Inference service',[1630 90 1700 145]);set_param(sv,'ServiceTimeValue','c.samples(1)');
done=blk('Entity Terminator','AI result',[1750 90 1820 145]);
set_param(done,'EntryAction',sprintf('coder.extrinsic(''cnse_runtime'');\ncnse_runtime(''result'',entity);'));
wire([m '/Receiver'],ad);wire(ad,q);add_line(m,[short(ad) '/2'],[short(ds) '/1']);wire(q,sv);wire(sv,done);group({ad,ds,q,sv,done},'Inference');

sw=blk(sprintf('Entity\nOutput Switch'),'Reverse loss',[1190 390 1260 445]);
set_param(sw,'SwitchingCriterion','From attribute','SwitchAttributeName','route');
drop=blk('Entity Terminator','RR drops',[1190 500 1260 545]);
sv=blk('Entity Server','Reverse propagation',[1000 390 1080 445]);
set_param(sv,'Capacity','Inf','ServiceTimeSource','MATLAB action','ServiceTimeAction','dt=entity.reverseDelay;');
done=blk('Entity Terminator','RR at sender',[820 390 900 445]);
set_param(done,'NumberEntitiesArrived','on',...
 'EntryAction',sprintf('coder.extrinsic(''cnse_runtime'');\ncnse_runtime(''feedback'',entity);'));
add_block('simulink/User-Defined Functions/MATLAB System',[m '/Observations'],...
 'System','CNSEMonitor','SimulateUsing','Interpreted execution','Position',[600 650 730 720]);
add_line(m,'Receiver/2',[short(sw) '/1']);wire(sw,sv);wire(sv,done);add_line(m,[short(sw) '/2'],[short(drop) '/1']);
add_line(m,[short(done) '/1'],'Observations/2','autorouting','on');
group({sw,drop,sv,done},'RTCP Reverse Path');
rrPorts=get_param([m '/RTCP Reverse Path'],'PortHandles');
set_param(get_param(rrPorts.Outport,'Line'),'Name','Delivered RR count');
add_block('simulink/Discrete/Unit Delay',[m '/Feedback tick'],...
 'SampleTime','.001','InitialCondition','1','Position',[370 660 430 700]);
add_block('sflib/Chart',[m '/AIMD'],'Position',[820 645 960 730]);
rt=sfroot;ch=rt.find('-isa','Stateflow.Chart','Path',[m '/AIMD']);
ch.ActionLanguage='MATLAB';ch.ChartUpdate='DISCRETE';ch.SampleTime='.001';
data(ch,'rr','Input',1,'[7 1]');data(ch,'enabled','Input',2,'1');
data(ch,'rate','Output',1,'1');data(ch,'clean','Local',0,'1');
s=Stateflow.State(ch);s.Position=[40 50 440 320];
s.LabelString=sprintf(['RUN\nentry: rate=1;clean=0;\nduring:\n' ...
 'if rr(1)>0 && enabled>0\n if rr(2)/256>0.02\n rate=max(0.15,0.8*rate);clean=0;\n' ...
 ' elseif rr(2)/256<=0.005\n clean=clean+1;\n if clean>=3\n rate=min(1.5,rate+0.05);clean=0;\n end\n' ...
 ' else\n clean=0;\n end\nend']);
t=Stateflow.Transition(ch);t.Destination=s;t.DestinationOClock=0;
t.SourceEndPoint=[260 20];t.MidPoint=[260 35];
add_block('simulink/Sources/Constant',[m '/Adaptive enabled'],'Value','double(c.adaptive)','Position',[600 780 700 810]);
add_line(m,'Observations/1','AIMD/1');add_line(m,'Adaptive enabled/1','AIMD/2');
add_line(m,'AIMD/1','Feedback tick/1');add_line(m,'Feedback tick/1','Observations/1');
add_block('simulink/Signal Routing/Demux',[m '/Scope signals'],'Outputs','5',...
 'Position',[1055 667 1060 749]);
add_block('simulink/Sinks/Scope',[m '/Dashboard'],'NumInputPorts','5','Position',[1300 670 1380 747]);
scope=get_param([m '/Dashboard'],'ScopeConfiguration');
scope.LayoutDimensions=[5 1];
scope.ShowLegend=true;
scope.TimeUnits='Seconds';
add_line(m,'Observations/2','Scope signals/1','autorouting','on');
labels={'Target payload (Mb/s)','Channel loss (fraction)','RFC jitter (ms)',...
 'Playout occupancy (frames)','AI-result AoI (ms)'};
for k=1:numel(labels)
 line=add_line(m,sprintf('Scope signals/%d',k),sprintf('Dashboard/%d',k),'autorouting','on');
 set_param(line,'Name',labels{k});
end
add_block('simulink/Sinks/To Workspace',[m '/Dashboard trace'],'VariableName','dashboard',...
 'SaveFormat','Timeseries','Position',[1280 800 1400 840]);
add_line(m,'Observations/2','Dashboard trace/1','autorouting','on');
add_line(m,'Feedback tick/1','Frames/1','autorouting','on');
cnse_layout(m);
save_system(m,fullfile(root,'generated',[m '.slx']));

 function p=blk(lib,name,pos)
  p=[m '/' name];add_block(['sldelib/' lib],p,'Position',pos);
 end
 function p=des(name,mode,pos)
  p=blk(sprintf('MATLAB\nDiscrete-Event System'),name,pos);
  set_param(p,'System','CNSEStage');set_param(p,'Mode',mode,'SimulateUsing','Interpreted execution');
 end
 function group(paths,name)
  h=cellfun(@getSimulinkBlockHandle,paths);
  Simulink.BlockDiagram.createSubSystem(h);
  % createSubSystem moves blocks; locate newest default Subsystem.
  all=find_system(m,'SearchDepth',1,'BlockType','SubSystem','Name','Subsystem');
  set_param(all{1},'Name',name);
 end
 function wire(a,b),add_line(m,[short(a) '/1'],[short(b) '/1'],'autorouting','on');end
 function queueActions(p,kind)
  set_param(p,'EntryAction',sprintf('coder.extrinsic(''cnse_runtime'');\ncnse_runtime(''%sQueue'',1);',kind),...
   'ExitAction',sprintf('coder.extrinsic(''cnse_runtime'');\ncnse_runtime(''%sQueue'',-1);',kind));
 end
end
function n=short(p),parts=strsplit(p,'/');n=parts{end};end
function d=data(ch,name,scope,port,sz)
d=Stateflow.Data(ch);d.Name=name;d.Scope=scope;d.DataType='double';d.Props.Array.Size=sz;
if port>0,d.Port=port;end
end

