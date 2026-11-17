classdef TestLibrary < matlab.unittest.TestCase
methods (Test)
 function packetWrapAndReassembly(t)
  p=course.Packetizer('Payload',100,'InitialSequence',65535,'InitialTimestamp',2^32-100);
  rows=p(1,0,250);t.verifyEqual(rows(:,1),[65535;0;1]);t.verifyEqual(rows(:,7),[0;0;1]);
  next=p(2,1/15,100);t.verifyEqual(next(2),5900);
  d=course.Depacketizer;[ok,dup]=d(rows(3,:));t.verifyFalse(ok);t.verifyFalse(dup);
  [ok,dup]=d(rows(3,:));t.verifyFalse(ok);t.verifyTrue(dup);
  d(rows(1,:));[ok,~]=d(rows(2,:));t.verifyTrue(ok);
 end
 function jitterAndRollover(t)
  j=course.RFCJitter;j(0,2^32-900);[ms,ticks]=j(.010,0);
  t.verifyEqual(ms,0,'AbsTol',1e-10);t.verifyEqual(ticks,0,'AbsTol',1e-8);
  [ms,~]=j(.030,900);t.verifyEqual(ms,.625,'AbsTol',1e-10);
 end
 function rrSequenceReorderAndIntervals(t)
  r=course.ReceiverReport;
  r([65534 0],0,false);r([0 900],.01,false);r([65535 0],.02,false);
  [rr,~,~,~]=r([],.5,true);t.verifyEqual(rr(2),0);t.verifyEqual(rr(5),65536);
  r([2 1800],.03,false);[rr,~,~,~]=r([],1,true);t.verifyEqual(rr(2),128);
  r([1 900],.04,false);[rr,~,~,~]=r([],2,true);t.verifyEqual(rr(4),0);t.verifyEqual(rr(2),0);
 end
 function losses(t)
  b=course.Loss('Seed',2);t.verifyFalse(b(0));t.verifyTrue(b(1));
  a=course.Loss('Mode','ge','Seed',12);b=course.Loss('Mode','ge','Seed',12);
  x=false(1,30000);y=x;for k=1:numel(x),x(k)=a(.05);y(k)=b(.05);end
  t.verifyEqual(x,y);
  t.verifyLessThan(abs(mean(x)-.05),.015);
  starts=find(diff([false x])==1);ends=find(diff([x false])==-1);
  t.verifyLessThan(abs(mean(ends-starts+1)-4),.5);
 end
 function queuePolicies(t)
  f=course.FrameQueue('Policy','fifo','Capacity',2);
  f([1 0 0],false);f([2 0 0],false);[~,n,d]=f([3 0 0],false);
  t.verifyEqual(n,2);t.verifyEqual(d,1);[r,~,~]=f([],true);t.verifyEqual(r(1),1);
  q=course.FrameQueue('Policy','latest');q([1 0 0],false);q([2 0 0],false);
  [r,n,~]=q([],true);t.verifyEqual(r(1),2);t.verifyEqual(n,0);
 end
 function linkSerializationAndDelay(t)
  b=course.Bottleneck('Rate',8000,'Capacity',200);
  [a,d,~]=b(0,100);t.verifyEqual(a,.1,'AbsTol',1e-12);t.verifyFalse(d);
  [a,~,~]=b(0,100);t.verifyEqual(a,.2,'AbsTol',1e-12);
  [a,d,~]=b(0,1);t.verifyTrue(d);t.verifyEqual(a,Inf);
  [a,d,~]=b(.2,100);t.verifyFalse(d);t.verifyEqual(a,.3,'AbsTol',1e-12);
  u=course.Bottleneck('Rate',921600,'Capacity',100,'BitsPerByte',10);
  [a,~,~]=u(0,35);t.verifyEqual(a,350/921600,'AbsTol',1e-12);
  delay=course.Delay('Base',.02,'Jitter',.05,'PreserveOrder',true);last=0;
  for k=1:100,a=delay(k*.001);t.verifyGreaterThanOrEqual(a,max(last,k*.001));last=a;end
 end
 function samplerAndAge(t)
  inf=course.Inference('Samples',[.01 .02 .04],'Seed',4);a=zeros(100,1);
  for k=1:100,[~,a(k)]=inf(0);end
  t.verifyTrue(all(ismember(a,[.01 .02 .04])));reset(inf);
  for k=1:100,[~,b]=inf(0);t.verifyEqual(b,a(k));end
  t.verifyEqual(course.aoi([0;1],[0;.5],0,2),.75,'AbsTol',1e-12);
  t.verifyTrue(isnan(course.aoi(1,0,0,2)));
  t.verifyEqual(course.percentile([1 2 3 4],[0 50 100]),[1 2.5 4]);
 end
 function playoutAnchor(t)
  b=course.PlayoutBuffer('Depth',.05);
  t.verifyEqual(b(.020,2^32-6000),.070,'AbsTol',1e-12);
  t.verifyEqual(b(.100,0),.070+1/15,'AbsTol',1e-12);
 end
 function aimdThresholds(t)
  rr=zeros(7,1);rr(1)=1;rr(2)=floor(.15*256);
  [r,n]=course.aimd(1,2,rr,true);t.verifyEqual(r,.8);t.verifyEqual(n,0);
  rr(2)=0;rr(3)=90000;
  for k=1:3,[r,n]=course.aimd(r,n,rr,true);end
  t.verifyEqual(r,.85,'AbsTol',1e-12);t.verifyEqual(n,0);
 end
 function supervisorBoundariesAndLatch(t)
  c=course.defaults('OS');s=1;reason=1;h=-1;e=0;
  [s,reason,h,e]=course.supervisor(s,reason,h,e,[1;.99;.9;.200;0],c);
  t.verifyEqual(s,2);t.verifyEqual(reason,9);
  [s,reason,h,e]=course.supervisor(s,reason,h,e,[1.001;.99;.9;.500;0],c);
  t.verifyEqual(s,3);t.verifyEqual(reason,10);
  [s,reason,h,e]=course.supervisor(s,reason,h,e,[2;2;2;.01;0],c);t.verifyEqual(s,3);
  [s,reason,h,e]=course.supervisor(s,reason,h,e,[3.001;3;3;.01;1],c); %#ok<ASGLU>
  t.verifyEqual(s,0);t.verifyEqual(e,3.001);
  [s,reason,~,~]=course.supervisor(1,1,-1,0,[1;0;.9;.6;0],c);
  t.verifyEqual(s,3);t.verifyEqual(reason,3); % heartbeat has priority
 end
 function noLossAndPolicyFreshness(t)
  c=course.defaults('CN');c.duration=1;c.warmup=.1;c.drain=.5;
  r=run_coursework(c,'matlab');t.verifyEqual(r.metrics.frame_loss,0);t.verifyEqual(r.metrics.on_time,1);
  c=course.defaults('OS');c.samples=.05;c.duration=4;c.warmup=1;c.queueCapacity=5;
  c.policy='fifo';a=run_coursework(c,'matlab');c.policy='latest';b=run_coursework(c,'matlab');
  t.verifyGreaterThan(a.metrics.aoi_ms,b.metrics.aoi_ms+50);
 end
 function wholeFrameLossAndAllMissing(t)
  c=course.defaults('CN');c.duration=.5;c.warmup=.05;c.drain=.2;c.loss=1;
  r=run_coursework(c,'matlab');t.verifyEqual(r.metrics.frame_loss,1);
  t.verifyEqual(r.metrics.on_time,0);t.verifyTrue(isnan(r.metrics.aoi_ms));
 end
 function sourceAndReplayContract(t)
  root=setup_coursework();
  d=course.replayData(fullfile(root,'data','source','os_measured_bridge.csv'));
  t.verifyGreaterThan(d.duration,1);t.verifyNotEmpty(d.panels{7}.y);
  t.verifyEmpty(d.panels{11}.y); % no invented temperature or throttle readings
  targets=readtable(fullfile(root,'data','cn_targets.csv'),'TextType','string');
  configs=course.cnConfigs();names=string({configs.name});
  t.verifyTrue(all(ismember(targets.config,names)));
 end
end
end
