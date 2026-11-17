function result=run_coursework(c,backend)
% Run one configured experiment. Default backend executes the SLX charts.
if nargin<1,c=course.defaults('CN');end
if nargin<2,backend='simulink';end
root=setup_coursework();course.validateConfig(c);
if strcmpi(c.project,'CN'),names={'Camera','RTP','Netem','Receiver','Inference'};
 kinds={'camera','packetizer','channel','receiver','ai'};
else,names={'Camera','Inference','UART'};kinds={'camera','ai','uart'};end
nodes=cell(size(names));stateLog=zeros(0,3);rateLog=zeros(0,2);
if strcmpi(backend,'simulink')
 Simulink.fileGenControl('set','CacheFolder',fullfile(root,'generated','cache'),...
  'CodeGenFolder',fullfile(root,'generated','codegen'),'createDir',true);
 model=[upper(c.project) '_shared'];file=fullfile(root,'generated',[model '.slx']);
 if ~isfile(file),build_models();end
 load_system(file);ws=get_param(model,'ModelWorkspace');assignin(ws,'c',c);
 out=sim(model,'StopTime',num2str(c.duration+c.drain,17),'SimulationMode','normal');
 for k=1:numel(names),nodes{k}=get_param([model '/' names{k}],'UserData');end
 if strcmpi(c.project,'OS')
  st=out.get('state_log');re=out.get('reason_log');stateLog=[st.Time st.Data(:) re.Data(:)];
 else,r=out.get('rate_log');rateLog=[r.Time r.Data(:)];end
else
 assert(strcmpi(backend,'matlab'),'Unknown backend');
 for k=1:numel(names),nodes{k}=course.Node(kinds{k},c);end
 rate=1;clean=0;s=0;reason=0;h=-1;epoch=0;
 for tick=0:round((c.duration+c.drain)/c.dt)
  t=tick*c.dt;
  cam=nodes{1}.step(t,rate);
  if strcmpi(c.project,'CN')
   pkt=nodes{2}.step(t,cam{1});net=nodes{3}.step(t,pkt{1});
   rx=nodes{4}.step(t,net{1},cam{1});nodes{5}.step(t,rx{1});
   [rate,clean]=course.aimd(rate,clean,rx{2},c.adaptive);rateLog(end+1,:)=[t rate]; %#ok<AGROW>
  else
   ai=nodes{2}.step(t,cam{1});u=nodes{3}.step(t,ai{1});
   [s,reason,h,epoch]=course.supervisor(s,reason,h,epoch,u{1},c);
   stateLog(end+1,:)=[t s reason]; %#ok<AGROW>
  end
 end
end
result=struct('config',c,'backend',backend,'state',stateLog,'rate',rateLog);
for k=1:numel(names)
 n=nodes{k};result.(names{k})=struct('log',n.Log,'aux',n.Aux,'frames',n.Frames);
end
result.metrics=course.metrics(result);
if strcmpi(backend,'simulink'),close_system(model,0);end
end
