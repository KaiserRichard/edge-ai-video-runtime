classdef TestApp < matlab.unittest.TestCase
% Optional desktop smoke test: run_tests(false,true). Creates then closes UI.
methods (Test)
 function opensSeeksAndCleansUp(t)
  root=setup_coursework();app=CourseworkReplayApp([],fullfile(root,'data','source','os_measured_bridge.csv'));
  cleanup=onCleanup(@()delete(app)); %#ok<NASGU>
  stop(app.Clock);app.seek(1);drawnow;
  t.verifyTrue(isvalid(app.UIFigure));t.verifySize(app.Axes,[16 2]);
  t.verifyEqual(app.Slider.Value,1);t.verifyNotEmpty(app.Data{2}.panels{7}.y);
  app.seek(0);t.verifyEqual(app.Slider.Value,0);
  app.seek(-1);t.verifyEqual(app.Time,0);
  app.seek(app.Slider.Limits(2)+1);t.verifyEqual(app.Time,app.Slider.Limits(2));
 end
end
end
