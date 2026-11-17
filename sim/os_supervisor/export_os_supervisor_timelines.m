function export_os_supervisor_timelines()
%EXPORT_OS_SUPERVISOR_TIMELINES Replot saved actual runs without resimulation.
[~, systemMemory] = memory;
assert(systemMemory.PhysicalMemory.Available>5*1024^3, 'codex_e:LowRAM', ...
    'Available physical RAM must be strictly above 5 GiB before export.');
root = fileparts(mfilename('fullpath'));
output = fullfile(root, 'output');
files = dir(fullfile(output, '*.mat'));
count = 0;
for k = 1:numel(files)
    if strcmp(files(k).name, 'test_results.mat')
        continue
    end
    saved = load(fullfile(files(k).folder, files(k).name), 'scenario', 'recording');
    if isfield(saved, 'scenario') && isfield(saved, 'recording')
        plot_os_supervisor_timeline(saved.scenario, saved.recording, output);
        count = count+1;
    end
end
fprintf('Exported %d lesson timelines from saved actual Stateflow recordings.\n', count);
end
