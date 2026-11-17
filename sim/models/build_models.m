function build_models()
% Generate reviewable SLX diagrams later, in this workspace only.
root=setup_coursework();load_system('simulink');load_system('sflib');
Simulink.fileGenControl('set','CacheFolder',fullfile(root,'generated','cache'),...
 'CodeGenFolder',fullfile(root,'generated','codegen'),'createDir',true);
make('CN_shared',course.defaults('CN'),root);
make('OS_shared',course.defaults('OS'),root);
end
function make(m,c,root)
if bdIsLoaded(m),close_system(m,0);end
new_system(m);ws=get_param(m,'ModelWorkspace');assignin(ws,'c',c);
set_param(m,'SolverType','Fixed-step','Solver','FixedStepDiscrete',...
 'FixedStep','c.dt','StopTime','c.duration+c.drain','SimulationMode','normal',...
 'ReturnWorkspaceOutputs','on','SaveTime','on','SaveOutput','off');
node(m,'Camera','camera',[35 100 125 155]);
node(m,'Inference','ai',[765 100 875 155]);
if strcmp(c.project,'CN')
 node(m,'RTP','packetizer',[165 100 255 155]);
 node(m,'Netem','channel',[300 100 420 155]);
 node(m,'Receiver','receiver',[475 100 635 170]);
 wire(m,'Camera/1','RTP/1');wire(m,'RTP/1','Netem/1');wire(m,'Netem/1','Receiver/1');
 wire(m,'Camera/1','Receiver/2');wire(m,'Receiver/1','Inference/1');
 ch=chart(m,'AIMD',[480 285 650 375]);
 data(ch,'rr','Input',1,'[7 1]');data(ch,'enabled','Input',2,'1');
 data(ch,'rate','Output',1,'1');data(ch,'clean','Local',0,'1');
 s=Stateflow.State(ch);s.Position=[40 40 300 240];
 s.LabelString=sprintf(['RUN\nentry: rate=1; clean=0;\nduring:\n' ...
 'if rr(1)>0 && enabled>0\n' ...
 ' if rr(2)/256>0.02\n rate=max(0.15,rate*0.8); clean=0;\n' ...
 ' elseif rr(2)/256<=0.005\n clean=clean+1;\n' ...
 ' if clean>=3\n rate=min(1.5,rate+0.05); clean=0;\n end\n' ...
 ' else\n clean=0;\n end\nend']);
 initial(ch,s);
 add_block('simulink/Sources/Constant',[m '/AdaptiveEnabled'],'Value','double(c.adaptive)','Position',[295 325 380 350]);
 add_block('simulink/Discrete/Unit Delay',[m '/FeedbackTick'],'InitialCondition','1',...
  'SampleTime','c.dt','Position',[195 275 260 310]);
 wire(m,'Receiver/2','AIMD/1');wire(m,'AdaptiveEnabled/1','AIMD/2');
 wire(m,'AIMD/1','FeedbackTick/1');wire(m,'FeedbackTick/1','Camera/1');
 sink(m,'Inference/1','AI_results',[940 110 1040 140]);
 sink(m,'AIMD/1','rate_log',[740 300 835 330]);
 Simulink.Annotation(m,'RTP metadata, 90 kHz clock; first-arrival playout; RR every 1 s; one-tick feedback delay');
else
 add_block('simulink/Sources/Constant',[m '/Rate'],'Value','1','Position',[35 30 85 55]);
 wire(m,'Rate/1','Camera/1');wire(m,'Camera/1','Inference/1');
 set_param([m '/Inference'],'Position',[180 100 310 155]);
 node(m,'UART','uart',[365 100 495 155]);wire(m,'Inference/1','UART/1');
 ch=chart(m,'Supervisor',[570 100 770 205]);
 data(ch,'u','Input',1,'[5 1]');data(ch,'lim','Input',2,'[4 1]');
 data(ch,'state','Output',1,'1');data(ch,'reason','Output',2,'1');
 data(ch,'healthySince','Local',0,'1');data(ch,'epoch','Local',0,'1');
 % u=[now,last heartbeat receive,last result receive,source age,rearm pulse].
 healthy='u(1)-u(2)<lim(1) && u(4)<lim(2)';
 during=sprintf(['during:\nif %s\n if healthySince<0\n healthySince=u(1);\n end\n' ...
 'else\n healthySince=-1;\nend'],healthy);
 init=state(ch,'INIT',[30 30 150 110],sprintf('entry: state=0; reason=0; epoch=u(1); healthySince=-1;\n%s',during));
 fresh=state(ch,'FRESH',[260 30 190 160],sprintf('entry: state=1; reason=1;\n%s',during));
 hold=state(ch,'HOLD',[260 250 190 160],sprintf('entry: state=2;\n%s',during));
 fail=state(ch,'FAILSAFE',[540 120 240 200],sprintf('entry: state=3;\n%s',during));
 initial(ch,init);
 transition(ch,init,fail,'[u(3)>epoch && u(4)>=lim(3)]{reason=10;}',1);
 transition(ch,init,fresh,['[u(2)>epoch && u(3)>epoch && ' healthy ']'],2);
 transition(ch,fresh,fail,'[u(1)-u(2)>=lim(1)]{reason=3;}',1);
 transition(ch,fresh,fail,'[u(4)>=lim(3)]{reason=10;}',2);
 transition(ch,fresh,hold,'[u(4)>=lim(2)]{reason=9;}',3);
 transition(ch,hold,fail,'[u(1)-u(2)>=lim(1)]{reason=3;}',1);
 transition(ch,hold,fail,'[u(4)>=lim(3)]{reason=10;}',2);
 transition(ch,hold,fresh,['[' healthy ']'],3);
 transition(ch,fail,init,['[u(5)>0 && healthySince>=0 && u(1)-healthySince>=lim(4) && ' healthy ']'],1);
 add_block('simulink/Sources/Constant',[m '/Timeouts'],'Value',...
  '[c.heartbeatTimeout;c.holdTimeout;c.failsafeTimeout;c.healthyRearm]','Position',[355 260 500 300]);
 wire(m,'UART/1','Supervisor/1');wire(m,'Timeouts/1','Supervisor/2');
 sink(m,'Supervisor/1','state_log',[845 105 965 135]);
 sink(m,'Supervisor/2','reason_log',[845 175 965 205]);
 Simulink.Annotation(m,'1 kHz supervisor; source-age arithmetic; heartbeat priority; FAILSAFE requires explicit healthy rearm');
end
save_system(m,fullfile(root,'generated',[m '.slx']));close_system(m,0);
end
function node(m,name,kind,pos)
add_block('simulink/User-Defined Functions/Level-2 MATLAB S-Function',[m '/' name],...
 'FunctionName','course_sfun','Parameters',['''' kind ''', c'],'Position',pos);
end
function wire(m,a,b),add_line(m,a,b,'autorouting','on');end
function sink(m,source,name,pos)
add_block('simulink/Sinks/To Workspace',[m '/' name],'VariableName',name,...
 'SaveFormat','Timeseries','Position',pos);wire(m,source,[name '/1']);
end
function ch=chart(m,name,pos)
add_block('sflib/Chart',[m '/' name],'Position',pos);
r=sfroot;ch=r.find('-isa','Stateflow.Chart','Path',[m '/' name]);
ch.ActionLanguage='MATLAB';ch.ChartUpdate='DISCRETE';ch.SampleTime='0.001';
end
function d=data(ch,name,scope,port,sz)
d=Stateflow.Data(ch);d.Name=name;d.Scope=scope;d.DataType='double';
d.Props.Array.Size=sz;if port>0,d.Port=port;end
end
function s=state(ch,name,pos,body)
s=Stateflow.State(ch);s.Position=pos;s.LabelString=sprintf('%s\n%s',name,body);
end
function initial(ch,s)
t=Stateflow.Transition(ch);t.Destination=s;t.DestinationOClock=0;
t.SourceEndPoint=[s.Position(1)+s.Position(3)/2 s.Position(2)-20];
t.MidPoint=[s.Position(1)+s.Position(3)/2 s.Position(2)-10];
end
function transition(ch,a,b,label,order)
t=Stateflow.Transition(ch);t.Source=a;t.Destination=b;
t.SourceOClock=6;t.DestinationOClock=0;t.LabelString=label;t.ExecutionOrder=order;
end
