function varargout=cnse_runtime(action,varargin)
% Interpreted event bookkeeping, not a scheduler. SimEvents schedules transport.
% Exposes all packet, report, frame and result traces for independent checks.
persistent s
switch action
 case 'time'
  varargout={get_param('CN_simevents','SimulationTime')};
 case 'init'
  c=varargin{1};s=struct('c',c,'rate',1,'frame',0,'packets',{{}},...
   'camera',zeros(0,5),'tx',zeros(0,11),'serialized',zeros(0,4),'rx',zeros(0,13),'frames',zeros(0,6),...
   'results',zeros(0,3),'reports',zeros(0,8),'feedback',zeros(0,8),...
   'pending',zeros(0,7),'sampledRR',0,'fresh',NaN,'jms',0,...
   'anchor',NaN,'rateLog',zeros(0,2),'qLog',zeros(0,3),...
   'senderWaiting',0,'aiWaiting',0,'senderDrops',0,'aiDrops',0,...
   'channelDropped',0,'playoutWaiting',0);
  s.cameraRng=RandStream('mt19937ar','Seed',c.seed+100);
  s.P=course.Packetizer('Payload',c.payload);
  s.L=course.Loss('Mode',c.lossMode,'Pgb',c.pGB,'Pbg',c.pBG,'Seed',c.seed+200);
  s.D=course.Delay('Base',c.delay,'Jitter',c.jitter,'Distribution',c.distribution,...
   'PreserveOrder',c.preserveOrder,'Seed',c.seed+300);
  s.R=course.ReceiverReport;s.PB=course.PlayoutBuffer('Depth',c.depth);
  s.DP=course.Depacketizer;
  s.RL=course.Loss('Seed',c.seed+600);
  s.RD=course.Delay('Base',c.reverseDelay,'Jitter',c.reverseJitter,'Seed',c.seed+700);
 case 'frame'
  t=get_param('CN_simevents','SimulationTime');v=zeros(1,3);
  rate=varargin{1};
  if rate<=0,rate=1;end
  if t<s.c.duration-1e-10
   s.frame=s.frame+1;n=floor(s.c.meanPackets)+(rand(s.cameraRng)<mod(s.c.meanPackets,1));
   tail=.8*s.c.payload;
   if isfinite(s.c.meanBytes),tail=s.c.meanBytes-(s.c.meanPackets-1)*s.c.payload;end
   bytes=max(1,round(((n-1)*s.c.payload+min(s.c.payload,max(1,tail)))*rate));
   v=[s.frame t bytes];s.camera(end+1,:)=[t s.frame t bytes rate];
   s.frames(end+1,:)=[s.frame t Inf Inf 0 0];
   if isfinite(s.anchor),s.frames(end,3)=t+s.anchor;end
  end
  varargout={v};
 case 'packetize'
  e=varargin{1};t=varargin{2};n=0;
  if e.frame>0
   p=s.P(e.frame,e.capture,e.size);s.packets{e.frame}=p;n=size(p,1);
   s.qLog(end+1,:)=[t e.frame t-e.capture];
  end
  varargout={n};
 case 'packet'
  ix=sscanf(varargin{1},'%d:%d');varargout={s.packets{ix(1)}(ix(2),:)};
 case 'serialize'
  varargout={8*(varargin{1}+48)/s.c.rate};
 case 'serialized'
  e=varargin{1};t=get_param('CN_simevents','SimulationTime');
  s.serialized(end+1,:)=[t e.seq e.frame e.size];
 case 'senderQueue'
  s.senderWaiting=s.senderWaiting+varargin{1};
 case 'aiQueue'
  s.aiWaiting=s.aiWaiting+varargin{1};
 case 'admitSender'
  route=1;
  if strcmp(s.c.policy,'fifo') && s.senderWaiting>=s.c.queueCapacity
   route=2;s.senderDrops=s.senderDrops+1;
  end
  varargout={route};
 case 'admitAI'
  route=1;
  if strcmp(s.c.policy,'fifo') && s.aiWaiting>=s.c.queueCapacity
   route=2;s.aiDrops=s.aiDrops+1;
  end
  varargout={route};
 case 'channel'
  e=varargin{1};t=varargin{2};p=s.c.loss;
  for k=1:size(s.c.lossSteps,1),if t>=s.c.lossSteps(k,1),p=s.c.lossSteps(k,2);end,end
  drop=false;for k=1:ceil((e.size+28)/1480),drop=s.L(p)||drop;end
  delay=0;if ~drop,delay=s.D(t)-t;end
  s.tx(end+1,:)=[t e.seq e.rtpTimestamp e.frame e.fragment e.count e.size e.marker e.capture drop delay];
  s.channelDropped=s.channelDropped+drop;
  varargout={delay,1+double(drop)};
 case 'propagation'
  e=varargin{1};t=get_param('CN_simevents','SimulationTime');
  varargout={max(0,e.forwardDelay-(t-e.sentAt))};
 case 'receive'
  e=varargin{1};t=varargin{2};p=[e.seq e.rtpTimestamp e.frame e.fragment e.count e.size e.marker e.capture];
  [~,dup,reorder,s.jms]=s.R(p,t,false);deadline=s.PB(t,e.rtpTimestamp);
  if isnan(s.anchor)
   s.anchor=deadline-e.capture;s.frames(:,3)=s.frames(:,2)+s.anchor;
  end
  s.rx(end+1,:)=[t p dup reorder s.jms deadline];
  [complete,~]=s.DP(p);wait=-1;
  if complete
   s.frames(e.frame,4)=t;s.frames(e.frame,5)=1;
   if t<=deadline+1e-12
    wait=max(0,deadline-t);
    s.playoutWaiting=s.playoutWaiting+1;
   end
  end
  varargout={wait};
 case 'playout'
  id=str2double(varargin{1});s.frames(id,6)=1;
  s.playoutWaiting=s.playoutWaiting-1;
  row=zeros(1,8);row(3)=id;row(8)=s.frames(id,2);
  varargout={row};
 case 'result'
  e=varargin{1};t=get_param('CN_simevents','SimulationTime');s.results(end+1,:)=[t e.frame e.capture];
  if isnan(s.fresh),s.fresh=e.capture;else,s.fresh=max(s.fresh,e.capture);end
 case 'report'
  t=get_param('CN_simevents','SimulationTime');[rr,~,~,~]=s.R([],t,true);s.reports(end+1,:)=[t rr];
  drop=s.RL(s.c.reverseLoss);d=s.RD(t)-t;
  varargout={rr,1+double(drop),d};
 case 'feedback'
  e=varargin{1};t=get_param('CN_simevents','SimulationTime');s.feedback(end+1,:)=[t e.rr];
  s.pending(end+1,:)=e.rr;
 case 'poll'
  s.rate=varargin{1};t=get_param('CN_simevents','SimulationTime');rr=zeros(7,1);
  if varargin{2}>s.sampledRR && ~isempty(s.pending)
   rr=s.pending(1,:)';
   s.pending(1,:)=[];
   s.sampledRR=s.sampledRR+1;
  end
  if isempty(s.rateLog)||s.rateLog(end,2)~=s.rate,s.rateLog(end+1,:)=[t s.rate];end
  loss=s.channelDropped/max(1,size(s.tx,1));
  age=NaN;if isfinite(s.fresh),age=1000*(t-s.fresh);end
  occupancy=s.playoutWaiting;
  meanBytes=(s.c.meanPackets-.2)*s.c.payload;
  if isfinite(s.c.meanBytes),meanBytes=s.c.meanBytes;end
  target=s.rate*s.c.fps*meanBytes*8/1e6;
  varargout={rr,[target;loss;s.jms;occupancy;age]};
 case 'get'
  varargout={s};
 otherwise,error('CNSE:Action','Unknown action %s',action);
end
end
