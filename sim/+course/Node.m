classdef Node < handle
% Interpreted stage shared by MATLAB runner and connected Simulink blocks.
% Fixed-size ports carry zero-padded batches; id=0 means no event.
properties
 Kind; C; LastTick=-Inf; Cached; Log=zeros(0,1); Aux=zeros(0,1);
 Stream; P; L; D; B; R; J; PB; Q; I;
 NextFrame=0; Frame=0; Pending=zeros(0,9); Frames=zeros(0,6);
 LastRR=0; Jms=0; Jframe=0; SeenFrame=[]; Ready=zeros(0,3); MediaOffset=NaN;
 BusyUntil=Inf; Active=zeros(1,3); Service=0; Started=0;
 NextHeartbeat=0; LastHB=-Inf; LastRX=-Inf; AgeAtSend=0;
 LastFrame=0; NextBridge=0; BridgeRows=zeros(0,6);
end
methods
 function o=Node(kind,c)
  o.Kind=kind;o.C=c;o.Stream=RandStream('mt19937ar','Seed',c.seed+100);
  switch kind
   case 'camera',o.Log=zeros(0,5);
   case 'packetizer',o.P=course.Packetizer('Payload',c.payload);o.Log=zeros(0,9);
   case 'channel'
    o.L=course.Loss('Mode',c.lossMode,'Pgb',c.pGB,'Pbg',c.pBG,'Seed',c.seed+200);
    o.D=course.Delay('Base',c.delay,'Jitter',c.jitter,'Distribution',c.distribution,...
     'PreserveOrder',c.preserveOrder,'Seed',c.seed+300);
    o.B=course.Bottleneck('Rate',c.rate,'Capacity',c.linkBytes);o.Log=zeros(0,7);
   case 'receiver'
    o.P=course.Depacketizer;o.R=course.ReceiverReport;o.J=course.RFCJitter;
    o.PB=course.PlayoutBuffer('Depth',c.depth);o.Log=zeros(0,7);o.Aux=zeros(0,8);
   case 'ai'
    o.Q=course.FrameQueue('Policy',c.policy,'Capacity',c.queueCapacity);
    o.I=course.Inference('Samples',c.samples,'Seed',c.seed+400);
    o.Log=zeros(0,7);o.Aux=zeros(0,4);
   case 'uart'
    o.B=course.Bottleneck('Rate',c.baud,'Capacity',4096,'BitsPerByte',10);
    o.Log=zeros(0,6);o.Aux=zeros(0,4);
  end
 end
 function out=step(o,t,varargin)
  % Idempotent Outputs callback: Simulink may request it twice at a tick.
  if t==o.LastTick,out=o.Cached;return;end
  switch o.Kind
   case 'camera',out=o.camera(t,varargin{1});
   case 'packetizer',out=o.packetizer(t,varargin{1});
   case 'channel',out=o.channel(t,varargin{1});
   case 'receiver',out=o.receiver(t,varargin{1},varargin{2});
   case 'ai',out=o.ai(t,varargin{1});
   case 'uart',out=o.uart(t,varargin{1});
   otherwise,error('course:Kind','Unknown stage');
  end
  o.LastTick=t;o.Cached=out;
 end
 function out=camera(o,t,rate)
  row=zeros(3,1);c=o.C;
  if t+1e-10>=o.NextFrame && o.NextFrame<c.duration
   capture=o.NextFrame;o.NextFrame=o.NextFrame+1/c.fps;o.Frame=o.Frame+1;
   % Two-point packet-count law preserves measured mean; size variance ASSUMED.
   n=floor(c.meanPackets)+(rand(o.Stream)<mod(c.meanPackets,1));
   tail=.8*c.payload;
   if isfinite(c.meanBytes),tail=c.meanBytes-(c.meanPackets-1)*c.payload;end
   tail=min(c.payload,max(1,tail));bytes=max(1,round(((n-1)*c.payload+tail)*rate));
   row=[o.Frame;capture;bytes];
   if strcmpi(c.project,'OS'),row(3)=capture;end
   o.Log(end+1,:)=[t o.Frame capture bytes rate];
  end
  out={row};
 end
 function out=packetizer(o,t,row)
  packets=zeros(o.C.maxBatch,8);
  if row(1)>0
   p=o.P(row(1),row(2),row(3));assert(size(p,1)<=o.C.maxBatch,'course:Batch','Increase maxBatch');
   packets(1:size(p,1),:)=p;o.Log=[o.Log;[repmat(t,size(p,1),1) p]];
  end
  out={packets(:)};
 end
 function out=channel(o,t,batch)
  c=o.C;packets=reshape(batch,c.maxBatch,8);prob=c.loss;
  for k=1:size(c.lossSteps,1),if t>=c.lossSteps(k,1),prob=c.lossSteps(k,2);end,end
  for k=find(packets(:,3)>0)'
   p=packets(k,:);drop=false;
   % netem loss applies per IP fragment, including the shorter final packet.
   fragments=ceil((p(6)+28)/1480);
   for f=1:fragments,drop=o.L(prob)||drop;end
   arrival=Inf;qd=false;bytes=0;
   if ~drop
    [dep,qd,bytes]=o.B(t,p(6)+48);
    if ~qd,arrival=o.D(dep);o.Pending(end+1,:)=[p arrival];end
   end
   o.Log(end+1,:)=[t p(1) p(3) drop qd arrival bytes];
  end
  due=o.Pending(:,9)<=t+1e-10;arrivals=sortrows(o.Pending(due,:),9);o.Pending(due,:)=[];
  assert(size(arrivals,1)<=c.maxBatch,'course:Batch','Receive batch overflow; increase maxBatch');
  y=zeros(c.maxBatch,9);y(1:size(arrivals,1),:)=arrivals;out={y(:)};
 end
 function out=receiver(o,t,batch,source)
  c=o.C;packets=reshape(batch,c.maxBatch,9);row=zeros(3,1);rr=zeros(7,1);
  % Sender side-channel is for denominator accounting only, never reassembly.
  if source(1)>0
   deadline=Inf;
   if isfinite(o.MediaOffset),deadline=source(2)+o.MediaOffset;end
   o.Frames(end+1,:)=[source(1) source(2) deadline Inf 0 0];
  end
  for k=find(packets(:,3)>0)'
   p=packets(k,1:8);arrival=packets(k,9);ix=find(o.Frames(:,1)==p(3),1);
   [~,duplicate,reordered,j]=o.R(p,arrival,false);o.Jms=j;
   if ~ismember(p(3),o.SeenFrame)
    o.Jframe=o.J(arrival,p(2));o.SeenFrame(end+1)=p(3);
   end
   deadline=o.PB(arrival,p(2));
   if isnan(o.MediaOffset),o.MediaOffset=deadline-p(8);end
   % First received packet anchors every generated frame's media deadline.
   unset=isinf(o.Frames(:,3));
   o.Frames(unset,3)=deadline+o.Frames(unset,2)-p(8);
   if ~isempty(ix) && arrival<=deadline+c.lateWindow
    [complete,~]=o.P(p);
    if complete,o.Frames(ix,4)=arrival;end
   end
   o.Log(end+1,:)=[arrival p(1) p(3) duplicate reordered o.Jms o.Jframe];
  end
  for ix=find(o.Frames(:,5)==0 & o.Frames(:,3)<=t+1e-10)'
   o.Frames(ix,5)=1;
   if o.Frames(ix,4)<=o.Frames(ix,3)
    o.Ready(end+1,:)=[o.Frames(ix,1:2) o.Frames(ix,3)];o.Frames(ix,6)=1;
   end
  end
  if ~isempty(o.Ready),row=o.Ready(1,:)';o.Ready(1,:)=[];end
  if t+1e-10>=o.LastRR+1
   [r,~,~,~]=o.R([],t,true);rr=r';o.LastRR=t;
   % LSR/DLSR are zero: no SR synchronization emulated; RTT unavailable.
   o.Aux(end+1,:)=[t r];
  end
  out={row,rr};
 end
 function out=ai(o,t,row)
  y=zeros(6,1);c=o.C;
  if t+1e-10>=o.BusyUntil
   y=[o.Active(1:2) o.BusyUntil o.Service o.Started-o.Active(3) o.Active(3)]';
   o.Log(end+1,:)=[o.BusyUntil o.Active(1:2) o.Service o.Started-o.Active(3) o.Active(3) o.Started];
   o.BusyUntil=Inf;
  end
  item=zeros(0,3);if row(1)>0,item=row(:)';end
  [next,n,drops]=o.Q(item,isinf(o.BusyUntil));
  if ~isempty(next)
   o.Active=next;o.Started=t;[o.BusyUntil,o.Service]=o.I(t);
  end
  o.Aux(end+1,:)=[t n drops double(~isinf(o.BusyUntil))];out={y};
 end
 function out=uart(o,t,row)
  c=o.C;active=t>=c.faultTime && t<c.recoverTime;
  bridgeDead=active && ismember(c.fault,{'F1','F2','F4','unplug'});
  resultDead=active && ismember(c.fault,{'F3','F5','stale'});
  if row(1)>0 && ~resultDead && ~bridgeDead
   if strcmp(c.bridgePolicy,'latest'),o.BridgeRows=row(:)';
   elseif size(o.BridgeRows,1)<c.bridgeCapacity,o.BridgeRows(end+1,:)=row(:)';end
  end
  if t+1e-10>=o.NextHeartbeat
   o.NextHeartbeat=o.NextHeartbeat+c.heartbeatPeriod;
   if ~bridgeDead
    [dep,drop,~]=o.B(t,c.heartbeatBytes);
    if ~drop,o.Pending(end+1,:)=[0 0 0 0 0 0 0 0 dep];end
   end
  end
  if t+1e-10>=o.NextBridge
   o.NextBridge=t+c.bridgePeriod;
   if ~bridgeDead && ~resultDead && ~isempty(o.BridgeRows)
    r=o.BridgeRows(1,:);o.BridgeRows(1,:)=[];
    [dep,drop,~]=o.B(t,35);
    if ~drop,o.Pending(end+1,:)=[r(1) r(2) t-r(2) t zeros(1,4) dep];end
   end
  end
  due=o.Pending(:,9)<=t+1e-10;p=sortrows(o.Pending(due,:),9);o.Pending(due,:)=[];
  for k=1:size(p,1)
   if strcmp(c.fault,'unplug') && active,continue;end
   if p(k,1)==0,o.LastHB=p(k,9);
   elseif p(k,1)>o.LastFrame
    o.LastFrame=p(k,1);o.LastRX=p(k,9);o.AgeAtSend=p(k,3);
    o.Log(end+1,:)=[p(k,9) p(k,1:4) p(k,9)-p(k,2)];
   end
  end
  age=t-o.LastRX+o.AgeAtSend+c.transitBound;
  rearm=double(t>=c.rearmTime && t<c.rearmTime+c.dt);
  o.Aux(end+1,:)=[t t-o.LastHB age active];
  out={[t;o.LastHB;o.LastRX;age;rearm]};
 end
end
methods (Static)
 function [ins,outs]=ports(kind,c)
  switch kind
   case 'camera',ins=1;outs=3;
   case 'packetizer',ins=3;outs=c.maxBatch*8;
   case 'channel',ins=c.maxBatch*8;outs=c.maxBatch*9;
   case 'receiver',ins=[c.maxBatch*9 3];outs=[3 7];
   case 'ai',ins=3;outs=6;
   case 'uart',ins=6;outs=5;
   otherwise,error('course:Kind','Unknown stage');
  end
 end
end
end
