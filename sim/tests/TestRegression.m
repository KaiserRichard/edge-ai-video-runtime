classdef TestRegression < matlab.unittest.TestCase
% Boundary and analytic checks, ready for the owner's later MATLAB session.
methods (Test)
 function rrOwnsIntegerJitter(t)
  r=course.ReceiverReport;
  r([0 0],0,false);r([1 900],.020,false);
  [rr,~,~,~]=r([],.1,true);
  t.verifyEqual(rr(3),56); % (1800-900)/16 = 56.25 timestamp ticks
  reset(r);r([10 0],0,false);r([10 0],0,false);
  [rr,~,~,~]=r([],.1,true);
  t.verifyEqual(rr(4),-1); % RFC cumulative loss can be negative with duplicates
  t.verifyEqual(rr(3),0);
 end
 function bernoulliFrameLossMatchesFormula(t)
  loss=course.Loss('Seed',903);frames=5000;n=5;p=.05;missing=false(frames,1);
  for i=1:frames
   for k=1:n,missing(i)=loss(p) || missing(i);end
  end
  t.verifyLessThan(abs(mean(missing)-(1-(1-p)^n)),.025);
 end
 function resetRestoresPacketAndLinkState(t)
  p=course.Packetizer('InitialSequence',23);a=p(1,0,2401);p(2,1,200);
  reset(p);t.verifyEqual(p(1,0,2401),a);
  b=course.Bottleneck('Rate',8000,'Capacity',1000);b(0,100);
  reset(b);[departure,drop,bytes]=b(0,100);
  t.verifyEqual(departure,.1);t.verifyFalse(drop);t.verifyEqual(bytes,100);
 end
 function receiverDeadlineBoundary(t)
  c=course.defaults('CN');c.maxBatch=2;c.depth=.05;
  for lag=[0 .0001]
   n=course.Node('receiver',c);
   batch=zeros(2,9);batch(1,:)=[0 0 1 1 2 10 0 0 0];
   n.step(0,batch(:),[1;0;20]);
   batch=zeros(2,9);batch(1,:)=[1 0 1 2 2 10 1 0 .05+lag];
   output=n.step(.051,batch(:),zeros(3,1));
   t.verifyEqual(n.Frames(1,6),double(lag==0));
   t.verifyEqual(output{1}(1),double(lag==0));
   count=size(n.Log,1);again=n.step(.051,batch(:),zeros(3,1));
   t.verifyEqual(again,output);t.verifyEqual(size(n.Log,1),count);
  end
 end
 function timeoutCrossingWithinOneTick(t)
  for fault={'F1','F3','unplug'}
   c=course.defaults('OS');c.samples=.02;c.fps=10;c.duration=2;c.warmup=.1;
   c.fault=fault{1};c.faultTime=.9134;c.recoverTime=Inf;
   r=run_coursework(c,'matlab');rows=course.faultTransitions(r);
   t.verifyTrue(any([rows.state]==3));
   t.verifyGreaterThanOrEqual([rows.quantization_ms],-1e-8);
   t.verifyLessThanOrEqual([rows.quantization_ms],1+1e-8);
   t.verifyEqual([rows.tick_error_ms],zeros(1,numel(rows)),'AbsTol',1e-8);
   ix=r.state(:,1)>=1.5;t.verifyTrue(all(r.state(ix,2)==3));
  end
 end
 function canonicalReplayUsesTimeAndReorder(t)
  root=setup_coursework();file=[tempname(fullfile(root,'output')) '.csv'];
  cleanup=onCleanup(@()delete(file)); %#ok<NASGU>
  T=table([0;1;2],[2;1;3],[0;2;1],["a.png";"";"b.png"],...
   ["cat";"";"dog"],[.8;NaN;.9],[0;0;1],...
   'VariableNames',{'t','seq','packet_status','image_file','ai_label','ai_confidence','frame_bad'});
  writetable(T,file);d=course.replayData(file);
  t.verifyEqual(d.panels{2}.mode,'packets');t.verifyEqual(d.panels{2}.y(:,2),[0;2;1]);
  before=course.replayVideoFrame(d.panels{1}.video,-1);t.verifyEqual(before.file,"");
  first=course.replayVideoFrame(d.panels{1}.video,1.5);t.verifyEqual(first.label,"cat");
  last=course.replayVideoFrame(d.panels{1}.video,2);t.verifyEqual(last.label,"dog");
  t.verifyTrue(last.bad);t.verifyEqual(last.confidence,.9);
 end
 function osReplayMatchesMetricEndpoint(t)
  c=course.defaults('OS');c.duration=1;c.warmup=.1;c.samples=.02;
  r=run_coursework(c,'matlab');d=course.replayData(r);u=r.UART.log;
  [~,time,age]=course.aoi(u(:,1),u(:,3),c.warmup,c.duration);
  t.verifyEqual(d.panels{10}.t,time);t.verifyEqual(d.panels{10}.y,age*1000);
 end
 function replayDoesNotMoveWarmup(t)
  for project={'CN','OS'}
   c=course.defaults(project{1});c.duration=.3;c.warmup=0;c.drain=.2;c.samples=.02;
   r=run_coursework(c,'matlab');d=course.replayData(r);
   t.verifyTrue(isnan(r.metrics.aoi_ms));
   t.verifyEmpty(d.panels{10}.t);t.verifyEmpty(d.panels{10}.y);
  end
 end
 function noUARTDeliveryHasNoMCUAge(t)
  c=course.defaults('OS');c.duration=.3;c.warmup=.1;c.samples=.02;
  c.fault='unplug';c.faultTime=0;
  r=run_coursework(c,'matlab');d=course.replayData(r);
  t.verifyNotEmpty(r.Inference.log);t.verifyEmpty(r.UART.log);
  t.verifyTrue(isnan(r.metrics.aoi_ms));t.verifyEmpty(d.panels{10}.y);
 end
 function whollyLostFrameRetainsDeadline(t)
  c=course.defaults('CN');c.maxBatch=2;c.depth=.05;
  n=course.Node('receiver',c);batch=zeros(2,9);
  batch(1,:)=[0 0 1 1 1 10 1 0 0];n.step(0,batch(:),[1;0;10]);
  n.step(.1,zeros(18,1),[2;.1;10]);n.step(.151,zeros(18,1),zeros(3,1));
  t.verifyEqual(n.Frames(2,3),.15,'AbsTol',1e-12);
  t.verifyEqual(n.Frames(2,4),Inf);t.verifyEqual(n.Frames(2,5:6),[1 0]);
 end
 function faultRowsRequireNewTransition(t)
  c=course.defaults('OS');c.fault='F1';c.faultTime=1;
  r=struct('config',c,'state',[.9 3 3;1 3 3;1.1 3 3],...
   'UART',struct('log',zeros(0,6),'aux',zeros(0,4)));
  rows=course.faultTransitions(r);
  t.verifyEmpty(rows);t.verifyTrue(isfield(rows,'reference'));
  r.state=[.9 1 1;1.1 3 3];rows=course.faultTransitions(r);
  t.verifyEmpty(rows); % No accepted heartbeat exists to define a reference.
 end
 function sparseTextReplayStaysUnavailable(t)
  root=setup_coursework();file=[tempname(fullfile(root,'output')) '.csv'];
  cleanup=onCleanup(@()delete(file)); %#ok<NASGU>
  T=table([0;1],["";""],["";""],...
   'VariableNames',{'t','image_file','ai_label'});
  writetable(T,file);d=course.replayData(file);
  frame=course.replayVideoFrame(d.panels{1}.video,1);
  t.verifyEqual(frame.file,"");t.verifyEqual(frame.label,"No label yet");
  T.t=[1;0];writetable(T,file);
  t.verifyError(@()course.replayData(file),'course:LogTime');
 end
 function stagePortsMatchRuntimeBatches(t)
  c=course.defaults('CN');
  kinds={'camera','packetizer','channel','receiver','ai','uart'};
  inputs={1,3,512,[576 3],3,6};outputs={3,512,576,[3 7],6,5};
  for k=1:numel(kinds)
   [ins,outs]=course.Node.ports(kinds{k},c);
   t.verifyEqual(ins,inputs{k});t.verifyEqual(outs,outputs{k});
   n=course.Node(kinds{k},c);u=arrayfun(@(width)zeros(width,1),ins,'UniformOutput',false);
   y=n.step(0,u{:});t.verifyEqual(numel(y),numel(outs));
   for j=1:numel(outs),t.verifySize(y{j},[outs(j) 1]);end
  end
  t.verifyError(@()course.Node.ports('unknown',c),'course:Kind');
 end
end
end
