classdef TestSimulink < matlab.unittest.TestCase
methods (TestClassSetup)
 function build(~),build_models();end
end
methods (Test)
 function cnConnectedLoop(t)
  c=course.defaults('CN');c.duration=4;c.warmup=.1;c.drain=.2;c.loss=.15;c.adaptive=true;
  a=run_coursework(c,'matlab');b=run_coursework(c,'simulink');
  t.verifyEqual(b.Camera.log,a.Camera.log,'AbsTol',1e-9);
  t.verifyEqual(b.Receiver.log,a.Receiver.log,'AbsTol',1e-9);
  t.verifyEqual(b.Receiver.aux,a.Receiver.aux,'AbsTol',1e-9);
  t.verifyEqual(b.Inference.log,a.Inference.log,'AbsTol',1e-9);
  t.verifyEqual(b.metrics.on_time,a.metrics.on_time,'AbsTol',1e-12);
  t.verifyLessThan(min(b.rate(:,2)),1);
 end
 function stateflowMatchesOracle(t)
  for fault={'F1','F3'}
   c=course.defaults('OS');c.duration=4;c.warmup=.1;c.samples=.02;c.fps=10;
   c.fault=fault{1};c.faultTime=1.0134;c.recoverTime=2;c.rearmTime=3.5;
   a=run_coursework(c,'matlab');b=run_coursework(c,'simulink');
   t.verifyEqual(b.state(:,2:3),a.state(:,2:3));
   t.verifyEqual(b.UART.log,a.UART.log,'AbsTol',1e-9);
   fail=find(b.state(:,2)==3,1);t.verifyNotEmpty(fail);
   if strcmp(fault{1},'F1'),t.verifyLessThan(b.state(fail,1)-c.faultTime,.101);end
   latched=b.state(:,1)>=c.recoverTime & b.state(:,1)<c.rearmTime;
   t.verifyTrue(all(b.state(latched,2)==3));
   rearm=find(abs(b.state(:,1)-c.rearmTime)<1e-9,1);
   t.assertNotEmpty(rearm);t.verifyEqual(b.state(rearm,2),0);
   ready=find(b.state(:,1)>c.rearmTime & b.state(:,2)==1,1);
   t.verifyNotEmpty(ready);
  end
 end
 function graphContainsControllersAtOneKHz(t)
  root=setup_coursework();
  models={'CN_shared','OS_shared'};controllers={'AIMD','Supervisor'};
  for k=1:numel(models)
   model=models{k};
   load_system(fullfile(root,'generated',[model '.slx']));
   cleanup=onCleanup(@()close_system(model,0));
   charts=sfroot;chart=charts.find('-isa','Stateflow.Chart','Path',...
    [model '/' controllers{k}]);
   t.assertNumElements(chart,1);t.verifyEqual(chart.SampleTime,'0.001');
   t.verifyEqual(chart.ChartUpdate,'DISCRETE');clear cleanup;
  end
 end
end
end
