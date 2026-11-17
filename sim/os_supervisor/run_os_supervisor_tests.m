function report = run_os_supervisor_tests(selectedNames)
%RUN_OS_SUPERVISOR_TESTS Execute the actual SLX chart and export lesson figures.
if nargin<1
    selectedNames = {};
end
root = fileparts(mfilename('fullpath'));
output = fullfile(root, 'output');
if ~isfolder(output)
    mkdir(output);
end
assertFreeMemory();
modelPath = build_os_supervisor();
model = 'codex_e_os_supervisor';
assert(~bdIsLoaded(model), 'codex_e:ModelBusy', 'Model name is already in use.');
oldFileGen = Simulink.fileGenControl('getConfig');
fileGenCleanup = onCleanup(@() Simulink.fileGenControl('setConfig', 'config', oldFileGen));
Simulink.fileGenControl('set', 'CacheFolder', fullfile(root, 'cache'), ...
    'CodeGenFolder', fullfile(root, 'codegen'), 'createDir', true);
load_system(modelPath);
modelCleanup = onCleanup(@() closeOwnedModel(model));
cases = os_supervisor_scenarios();
if ~isempty(selectedNames)
    if ischar(selectedNames) || isstring(selectedNames)
        selectedNames = cellstr(selectedNames);
    end
    allNames = {cases.name};
    assert(all(ismember(selectedNames, allNames)), 'Unknown scenario name.');
    cases = cases(ismember(allNames, selectedNames));
end
report = struct([]);
for c = 1:numel(cases)
    assertFreeMemory();
    scenario = cases(c);
    input = Simulink.SimulationInput(model);
    input = input.setVariable('stimulus', scenario.stimulus, 'Workspace', model);
    input = input.setModelParameter('StopTime', '2.1');
    out = sim(input);
    timeMs = double(out.state_log.Time(:))*1000;
    state = samples(out.state_log, 1);
    reason = samples(out.reason_log, 1);
    leds = samples(out.led_log, 4);
    ages = samples(out.age_log, 2);
    indices = [1; find(diff(state)~=0)+1];
    sequence = state(indices)';
    transitionMs = timeMs(indices)';
    assert(isequal(sequence, scenario.expected), 'codex_e:StateSequence', ...
        '%s: actual sequence %s, expected %s', scenario.name, mat2str(sequence), mat2str(scenario.expected));
    assert(all(abs(transitionMs-scenario.expectedMs)<1e-6), 'codex_e:TransitionTime', ...
        '%s: transition ms %s, expected %s', scenario.name, mat2str(transitionMs), mat2str(scenario.expectedMs));
    assert(isequal(leds(:,1), double(state==1)), 'D4 must mean FRESH.');
    assert(isequal(leds(:,2), double(state==2)), 'D5 must mean HOLD.');
    assert(isequal(leds(:,3), double(state==3)), 'D6 must mean FAILSAFE.');
    expectedActivity = zeros(size(timeMs));
    activityUntil = -1;
    u = scenario.stimulus.Data;
    for k = 1:numel(timeMs)
        if u(k,2)>=0 || u(k,3)>=0
            activityUntil = timeMs(k)+20;
        end
        expectedActivity(k) = double(timeMs(k)<activityUntil-1e-8);
    end
    assert(isequal(leds(:,4), expectedActivity), 'D9 must show the documented 20 ms activity window.');
    failIndex = find(state==3, 1);
    if ~isempty(failIndex)
        assert(reason(failIndex)==scenario.failReason, 'Wrong fault reason or priority.');
    end
    holdIndex = find(state==2, 1);
    hbDelay = NaN;
    holdDelay = NaN;
    sourceDelay = NaN;
    if ~isnan(scenario.lastHB) && ~isempty(failIndex) && scenario.failReason==3
        hbDelay = timeMs(failIndex)-scenario.lastHB;
        assert(hbDelay>=100-1e-8 && hbDelay<101+1e-8, 'Watchdog must react in timeout + one tick.');
    end
    if ~isnan(scenario.lastResult) && ~isempty(holdIndex)
        holdDelay = timeMs(holdIndex)-scenario.lastResult;
        assert(holdDelay>=175-1e-8 && holdDelay<176+1e-8, 'Wrong source-age HOLD timing.');
    end
    if ~isnan(scenario.lastResult) && ~isempty(failIndex) && scenario.failReason==10
        sourceDelay = timeMs(failIndex)-scenario.lastResult;
        assert(sourceDelay>=475-1e-8 && sourceDelay<476+1e-8, 'Wrong source-age FAILSAFE timing.');
    end
    if ~isempty(scenario.rearmMs)
        healthyRearm = scenario.rearmMs(end);
        recoveryTick = ceil(scenario.resumeMs);
        assert(all(state(timeMs>=recoveryTick & timeMs<healthyRearm)==3), ...
            'Traffic return or early rearm cleared the FAILSAFE latch.');
        initIndex = find(timeMs>=healthyRearm-1e-6, 1);
        assert(state(initIndex)==0, 'Healthy explicit rearm must enter INIT.');
        nextHB = min(u(u(:,2)>healthyRearm, 2));
        nextResult = min(u(u(:,3)>healthyRearm, 3));
        readyTick = ceil(max(nextHB, nextResult));
        assert(all(state(timeMs>=healthyRearm & timeMs<readyTick)==0), ...
            'Pre-rearm receptions were reused.');
    end
    recording = table(timeMs, state, reason, leds(:,1), leds(:,2), leds(:,3), leds(:,4), ...
        ages(:,1), ages(:,2), 'VariableNames', ...
        {'time_ms','state','reason','D4','D5','D6','D9','heartbeat_age_ms','source_age_ms'});
    writetable(recording, fullfile(output, [scenario.name '.csv']));
    save(fullfile(output, [scenario.name '.mat']), 'scenario', 'recording');
    plot_os_supervisor_timeline(scenario, recording, output);
    report(c).scenario = scenario.name;
    report(c).passed = true;
    report(c).state_sequence = sequence;
    report(c).transition_ms = transitionMs;
    report(c).heartbeat_delay_ms = hbDelay;
    report(c).hold_delay_ms = holdDelay;
    report(c).source_failsafe_delay_ms = sourceDelay;
    writeJson(fullfile(output, [scenario.name '_result.json']), report(c));
    writeJson(fullfile(output, 'test_results.json'), struct('complete', c==numel(cases), ...
        'requested', numel(cases), 'completed', c, 'results', report));
    fprintf('PASS %-32s states=%s at ms=%s\n', scenario.name, mat2str(sequence), mat2str(transitionMs));
end
save(fullfile(output, 'test_results.mat'), 'report');
fprintf('All %d actual Stateflow scenarios passed; PNG/CSV/MAT artifacts: %s\n', numel(report), output);
end

function values = samples(series, channels)
values = double(squeeze(series.Data));
if channels==1
    values = values(:);
elseif size(values,1)~=numel(series.Time)
    values = values';
end
assert(isequal(size(values), [numel(series.Time) channels]), 'Unexpected signal dimensions.');
end

function writeJson(path, value)
handle = fopen(path, 'w');
assert(handle>=0, 'Could not create test report.');
fileCleanup = onCleanup(@() fclose(handle));
fprintf(handle, '%s', jsonencode(value, 'PrettyPrint', true));
end

function assertFreeMemory()
[~, systemMemory] = memory;
assert(systemMemory.PhysicalMemory.Available>5*1024^3, 'codex_e:LowRAM', ...
    'Available physical RAM must be strictly above 5 GiB; no model is run.');
end

function closeOwnedModel(model)
if bdIsLoaded(model)
    close_system(model, 0);
end
end
