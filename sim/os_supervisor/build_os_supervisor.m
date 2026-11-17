function modelPath = build_os_supervisor()
%BUILD_OS_SUPERVISOR Build the STM32/FreeRTOS timing abstraction in Stateflow.
% Inputs are accepted UART reception timestamps, not raw UART frames.
% No other model, figure, base variable, worker, or MATLAB process is closed.
[~, systemMemory] = memory;
assert(systemMemory.PhysicalMemory.Available>5*1024^3, 'codex_e:LowRAM', ...
    'Available physical RAM must be strictly above 5 GiB before building.');
root = fileparts(mfilename('fullpath'));
model = 'codex_e_os_supervisor';
assert(~bdIsLoaded(model), 'codex_e:ModelBusy', ...
    'The model name is already loaded. Save/rename it before rebuilding.');
load_system('simulink');
load_system('sflib');
oldFileGen = Simulink.fileGenControl('getConfig');
fileGenCleanup = onCleanup(@() Simulink.fileGenControl('setConfig', 'config', oldFileGen));
Simulink.fileGenControl('set', 'CacheFolder', fullfile(root, 'cache'), ...
    'CodeGenFolder', fullfile(root, 'codegen'), 'createDir', true);
new_system(model);
modelCleanup = onCleanup(@() closeOwnedModel(model));
set_param(model, 'SolverType', 'Fixed-step', 'Solver', 'FixedStepDiscrete', ...
    'FixedStep', '0.001', 'StopTime', '2', 'SimulationMode', 'normal', ...
    'ReturnWorkspaceOutputs', 'on', 'SaveOutput', 'off', 'SaveTime', 'on');
ws = get_param(model, 'ModelWorkspace');
% HB timeout, source-age HOLD/FAILSAFE, healthy rearm, transit, activity LED.
assignin(ws, 'limits', [100; 200; 500; 1000; 5; 20]);
cases = os_supervisor_scenarios();
assignin(ws, 'stimulus', cases(1).stimulus);
add_block('simulink/Sources/From Workspace', [model '/Accepted_UART'], ...
    'VariableName', 'stimulus', 'Interpolate', 'off', 'SampleTime', '0.001', ...
    'OutputAfterFinalValue', 'Holding final value', ...
    'Position', [40 80 195 135]);
add_block('simulink/Sources/Constant', [model '/Limits_ms'], ...
    'Value', 'limits', 'Position', [50 210 185 250]);
add_block('sflib/Chart', [model '/Supervisor_1kHz'], 'Position', [290 65 530 265]);
rt = sfroot;
chart = rt.find('-isa', 'Stateflow.Chart', 'Path', [model '/Supervisor_1kHz']);
chart.ActionLanguage = 'MATLAB';
chart.ChartUpdate = 'DISCRETE';
chart.SampleTime = '0.001';
chart.Description = ['Timing abstraction of OS_PLAN and retained firmware: ' ...
    'pre-reception deadline checks; explicit healthy rearm; new receptions after rearm.'];
data(chart, 'u', 'Input', 1, '[5 1]', 'double');
data(chart, 'lim', 'Input', 2, '[6 1]', 'double');
data(chart, 'state_id', 'Output', 1, '1', 'double');
data(chart, 'reason', 'Output', 2, '1', 'double');
data(chart, 'leds', 'Output', 3, '[4 1]', 'double');
data(chart, 'ages_ms', 'Output', 4, '[2 1]', 'double');
locals = {'lastHB','lastResult','ageAtSend','epoch','healthySince', ...
    'nowMs','sourceAge','heartbeatAge','activityUntil'};
for k = 1:numel(locals)
    data(chart, locals{k}, 'Local', 0, '1', 'double');
end
flags = {'hasHB','hasResult','hbExpired','sourceExpired','healthy'};
for k = 1:numel(flags)
    data(chart, flags{k}, 'Local', 0, '1', 'boolean');
end
parent = Stateflow.State(chart);
parent.Position = [20 25 2200 1000];
parent.FontSize = 10;
parent.LabelString = sprintf(['SUPERVISOR\nentry:\n' ...
    'nowMs=u(1); lastHB=0; lastResult=0; ageAtSend=0; epoch=nowMs;\n' ...
    'hasHB=false; hasResult=false; healthySince=-1; activityUntil=-1;\n' ...
    'hbExpired=true; sourceExpired=false; healthy=false;\n' ...
    'heartbeatAge=0; sourceAge=0; leds=zeros(4,1); ages_ms=zeros(2,1);\n' ...
    'during:\n' ...
    'nowMs=u(1);\n' ...
    'heartbeatAge=nowMs-lastHB; sourceAge=nowMs-lastResult+ageAtSend+lim(5);\n' ...
    'hbExpired=~hasHB || heartbeatAge>=lim(1);\n' ...
    'sourceExpired=hasResult && sourceAge>=lim(3);\n' ...
    'if hbExpired || ~hasResult || sourceAge>=lim(2)\n healthySince=-1;\nend\n' ...
    'if u(2)>epoch && u(2)<=nowMs && (~hasHB || u(2)>lastHB)\n' ...
    ' lastHB=u(2); hasHB=true; activityUntil=nowMs+lim(6);\nend\n' ...
    'if u(3)>epoch && u(3)<=nowMs && (~hasResult || u(3)>lastResult)\n' ...
    ' lastResult=u(3); ageAtSend=u(4); hasResult=true; activityUntil=nowMs+lim(6);\nend\n' ...
    'heartbeatAge=nowMs-lastHB; sourceAge=nowMs-lastResult+ageAtSend+lim(5);\n' ...
    'hbExpired=hbExpired || ~hasHB || heartbeatAge>=lim(1);\n' ...
    'sourceExpired=sourceExpired || (hasResult && sourceAge>=lim(3));\n' ...
    'healthy=hasHB && hasResult && heartbeatAge<lim(1) && sourceAge<lim(2);\n' ...
    'if healthy\n if healthySince<0\n healthySince=nowMs;\n end\n' ...
    'else\n healthySince=-1;\nend\n' ...
    'leds(4)=double(nowMs<activityUntil);\n' ...
    'ages_ms=[heartbeatAge;sourceAge];']);
init = state(parent, 'INIT', [1050 250 250 190], sprintf(['entry:\n' ...
    'state_id=0; reason=0; epoch=nowMs;\n' ...
    'hasHB=false; hasResult=false; healthy=false; healthySince=-1;\n' ...
    'leds(1)=0; leds(2)=0; leds(3)=0;']));
fresh = state(parent, 'FRESH', [1450 250 250 190], sprintf(['entry:\n' ...
    'state_id=1; reason=1;\nleds(1)=1; leds(2)=0; leds(3)=0;']));
hold = state(parent, 'HOLD', [1450 650 250 190], sprintf(['entry:\n' ...
    'state_id=2; reason=9;\nleds(1)=0; leds(2)=1; leds(3)=0;']));
fail = state(parent, 'FAILSAFE', [1870 450 300 240], sprintf(['entry:\n' ...
    'state_id=3;\nleds(1)=0; leds(2)=0; leds(3)=1;']));
initial(chart, parent);
initial(parent, init);
transition(parent, init, fail, '[sourceExpired]{reason=10;}', 1);
transition(parent, init, fresh, '[healthy && lastHB>epoch && lastResult>epoch]', 2);
transition(parent, fresh, fail, '[hbExpired]{reason=3;}', 1);
transition(parent, fresh, fail, '[sourceExpired]{reason=10;}', 2);
transition(parent, fresh, hold, '[hasResult && sourceAge>=lim(2)]', 3);
transition(parent, hold, fail, '[hbExpired]{reason=3;}', 1);
transition(parent, hold, fail, '[sourceExpired]{reason=10;}', 2);
transition(parent, hold, fresh, '[healthy]', 3);
transition(parent, fail, init, ...
    '[u(5)>0 && healthy && healthySince>=0 && nowMs-healthySince>=lim(4)]', 1);
add_line(model, 'Accepted_UART/1', 'Supervisor_1kHz/1', 'autorouting', 'on');
add_line(model, 'Limits_ms/1', 'Supervisor_1kHz/2', 'autorouting', 'on');
names = {'state_log','reason_log','led_log','age_log'};
for k = 1:numel(names)
    block = [model '/' names{k}];
    add_block('simulink/Sinks/To Workspace', block, 'VariableName', names{k}, ...
        'SaveFormat', 'Timeseries', 'Position', [650 50+75*k 800 80+75*k]);
    add_line(model, sprintf('Supervisor_1kHz/%d', k), [names{k} '/1'], 'autorouting', 'on');
end
Simulink.Annotation(model, sprintf(['STM32 FreeRTOS supervisor, 1 ms tick\n' ...
    'u = [now_ms; accepted_HB_timestamp_or_-1; accepted_result_timestamp_or_-1; age_at_send_ms; rearm]\n' ...
    'LEDs = [D4 FRESH; D5 HOLD; D6 FAILSAFE; D9 recent link activity]\n' ...
    'Accepted UART metadata only: CRC/session/generation validation and Linux scheduling are outside this model.']));
modelPath = fullfile(root, [model '.slx']);
save_system(model, modelPath);
fprintf('Built %s\n', modelPath);
end

function d = data(chart, name, scope, port, sizeText, type)
d = Stateflow.Data(chart);
d.Name = name;
d.Scope = scope;
d.DataType = type;
d.Props.Array.Size = sizeText;
if port > 0
    d.Port = port;
end
end

function s = state(parent, name, position, body)
s = Stateflow.State(parent);
s.Position = position;
s.LabelString = sprintf('%s\n%s', name, body);
end

function initial(parent, target)
t = Stateflow.Transition(parent);
t.Destination = target;
t.DestinationOClock = 0;
x = target.Position(1) + target.Position(3)/2;
y = target.Position(2);
t.SourceEndPoint = [x y-35];
t.MidPoint = [x y-15];
end

function transition(parent, source, target, label, order)
t = Stateflow.Transition(parent);
t.Source = source;
t.Destination = target;
t.SourceOClock = 3;
t.DestinationOClock = 9;
t.LabelString = label;
t.ExecutionOrder = order;
if strcmp(source.Name, 'FAILSAFE') && strcmp(target.Name, 'INIT')
    % Keep the rearm route inside SUPERVISOR: an external route resets it.
    t.SourceOClock = 0;
    t.DestinationOClock = 0;
    t.MidPoint = [1600 160];
    t.LabelPosition = [1130 105 950 50];
end
end

function closeOwnedModel(model)
if bdIsLoaded(model)
    close_system(model, 0);
end
end
