function summary=cnse2_run_shared_tests()
% v2 copy of study_simevents/cnse_run_shared_tests.m. The original suite
% rebuilds the shared SLX files during setup, so it runs on a scratch copy.
% The copy lives under study_simevents_v2/ and results are written there.
% Two extra v2 rows: a saved-model reload run of CN_simevents_v2 with all
% trace oracles, and a check that the v2 model contains no CNSEStage block.
root = fileparts(fileparts(mfilename('fullpath')));
v2 = fullfile(root,'study_simevents_v2');
scratch = tempname(v2);
mkdir(scratch);
originalPath = path;
originalFolder = pwd;
originalFileGen = Simulink.fileGenControl('getConfig');
cleanup = onCleanup(@()restore(scratch,v2,originalFolder,originalPath,originalFileGen)); %#ok<NASGU>
generated = fullfile(root,'generated');
if any(strcmpi(strsplit(path,pathsep),generated)), rmpath(generated); end
for name = ["+course","models","tests","data","app","run_tests.m", ...
    "setup_coursework.m","run_coursework.m"]
    copyfile(fullfile(root,name),fullfile(scratch,name));
end
mkdir(fullfile(scratch,'generated'));
mkdir(fullfile(scratch,'output'));
assert(~bdIsLoaded('CN_shared') && ~bdIsLoaded('OS_shared'), ...
    'CNSE2:SharedLoaded','Close the shared models before running isolated tests.');
cd(scratch);
addpath(scratch);
clear run_tests setup_coursework run_coursework build_models course_sfun
suite = run_tests(true,false);
assert(numel(suite)==29);
names = string({suite.Name})';
summary = table(names,[suite.Passed]',[suite.Failed]',[suite.Incomplete]',[suite.Duration]', ...
    'VariableNames',{'test','passed','failed','incomplete','duration_seconds'});
cd(originalFolder);path(originalPath);
Simulink.fileGenControl('setConfig','config',originalFileGen);
addpath(root,fullfile(root,'study_simevents'),v2,generated);

% v2 row 1: reload the saved model from disk and run the trace oracles.
tic;
if bdIsLoaded('CN_simevents_v2'), close_system('CN_simevents_v2',0); end
c=cnse_config();c.duration=5;c.warmup=1;c.loss=.05;c.delay=.02;c.jitter=.02;
r=cnse2_run(c,'test_reload',false);ok=all(r.validation.pass);
summary(end+1,:)={"CN_simevents_v2/reloadedModelPassesTraceOracles",ok,~ok,false,toc};
% v2 row 2: the mechanism is native, so no CNSEStage DES block may remain.
tic;
des=find_system('CN_simevents_v2','LookUnderMasks','all','FollowLinks','on','BlockType','MATLABDiscreteEventSystem');
sys=find_system('CN_simevents_v2','LookUnderMasks','all','FollowLinks','on','System','CNSEStage');
ok=isempty(des) && isempty(sys);
summary(end+1,:)={"CN_simevents_v2/noCNSEStageBlocks",ok,~ok,false,toc};
writetable(summary,fullfile(v2,'shared_test_results.csv'));
fprintf('Shared suite: %d/%d passed (29 original + 2 v2 checks)\n',sum(summary.passed),height(summary));
end

function restore(scratch,v2,originalFolder,originalPath,originalFileGen)
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
    parent = char(java.io.File(v2).getCanonicalPath());
    assert(strcmpi(fileparts(resolved),parent),'CNSE2:TestDirectory','Unexpected test scratch path.');
    if isfolder(resolved), rmdir(resolved,'s'); end
end
