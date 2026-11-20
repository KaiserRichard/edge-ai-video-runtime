function cnse_run_shared_tests()
% Test setup rebuilds both shared SLX files, so run the untouched suite in a copy.
root = fileparts(fileparts(mfilename('fullpath')));
generated = fullfile(root,'generated');
scratch = tempname(generated);
mkdir(scratch);
originalPath = path;
originalFolder = pwd;
originalFileGen = Simulink.fileGenControl('getConfig');
cleanup = onCleanup(@()restore(scratch,generated,originalFolder,originalPath,originalFileGen)); %#ok<NASGU>
if any(strcmpi(strsplit(path,pathsep),generated)), rmpath(generated); end

for name = ["+course","models","tests","data","app","run_tests.m", ...
    "setup_coursework.m","run_coursework.m"]
    copyfile(fullfile(root,name),fullfile(scratch,name));
end
mkdir(fullfile(scratch,'generated'));
mkdir(fullfile(scratch,'output'));

assert(~bdIsLoaded('CN_shared') && ~bdIsLoaded('OS_shared'), ...
    'CNSE:SharedLoaded','Close the shared models before running isolated tests.');
cd(scratch);
addpath(scratch);
clear run_tests setup_coursework run_coursework build_models course_sfun
suite = run_tests(true,false);
assert(numel(suite)==29);
names = string({suite.Name})';
summary = table(names,[suite.Passed]',[suite.Failed]',[suite.Incomplete]',[suite.Duration]', ...
    'VariableNames',{'test','passed','failed','incomplete','duration_seconds'});
writetable(summary,fullfile(root,'study_simevents','shared_test_results.csv'));

end

function restore(scratch,generated,originalFolder,originalPath,originalFileGen)
    for model = {'CN_shared','OS_shared'}
        if bdIsLoaded(model{1}) && startsWith(get_param(model{1},'FileName'),scratch)
            close_system(model{1},0);
        end
    end
    Simulink.fileGenControl('setConfig','config',originalFileGen);
    cd(originalFolder);
    path(originalPath);
    clear run_tests setup_coursework run_coursework build_models course_sfun
    resolved = char(java.io.File(scratch).getCanonicalPath());
    parent = char(java.io.File(generated).getCanonicalPath());
    assert(strcmpi(fileparts(resolved),parent),'CNSE:TestDirectory','Unexpected test scratch path.');
    if isfolder(resolved), rmdir(resolved,'s'); end
end
