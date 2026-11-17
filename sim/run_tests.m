function results=run_tests(includeSimulink,includeApp)
% Explicit invocation only. Nothing invokes MATLAB from the shell.
if nargin<1,includeSimulink=true;end
if nargin<2,includeApp=false;end
root=setup_coursework();addpath(fullfile(root,'tests'));
suite=[matlab.unittest.TestSuite.fromClass(?TestLibrary) matlab.unittest.TestSuite.fromClass(?TestRegression)];
if includeSimulink,suite=[suite matlab.unittest.TestSuite.fromClass(?TestSimulink)];end
if includeApp,suite=[suite matlab.unittest.TestSuite.fromClass(?TestApp)];end
results=run(suite);assertSuccess(results);
end
