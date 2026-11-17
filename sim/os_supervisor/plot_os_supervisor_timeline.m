function plot_os_supervisor_timeline(scenario, recording, output)
fig = figure('Visible', 'off', 'Color', 'w', 'Position', [80 80 1200 800]);
figCleanup = onCleanup(@() close(fig));
layout = tiledlayout(fig, 3, 1, 'TileSpacing', 'compact');
ax = nexttile(layout);
stairs(ax, recording.time_ms, recording.state, 'LineWidth', 1.8);
yticks(ax, 0:3);
yticklabels(ax, {'INIT','FRESH','HOLD','FAILSAFE'});
ylim(ax, [-0.25 3.4]);
grid(ax, 'on');
ylabel(ax, 'Supervisor');
title(ax, strrep(scenario.name, '_', ' '));
markEvents(ax, scenario);
ax = nexttile(layout);
hold(ax, 'on');
colors = [0.1 0.65 0.2; 0.85 0.62 0; 0.85 0.1 0.1; 0.1 0.35 0.85];
for led = 1:4
    stairs(ax, recording.time_ms, (4-led)*1.5+recording{:, 3+led}, ...
        'Color', colors(led,:), 'LineWidth', 1.3);
end
yticks(ax, [0.5 2 3.5 5]);
yticklabels(ax, {'D9 activity','D6 FAILSAFE','D5 HOLD','D4 FRESH'});
ylim(ax, [-0.2 6]);
grid(ax, 'on');
ylabel(ax, 'LED levels, offset');
ax = nexttile(layout);
plot(ax, recording.time_ms, recording.heartbeat_age_ms, ...
    recording.time_ms, recording.source_age_ms, 'LineWidth', 1.1);
hold(ax, 'on');
yline(ax, 100, '--', 'HB 100 ms', 'Color', [0.35 0.35 0.35]);
yline(ax, 200, '--', 'HOLD 200 ms', 'Color', [0.35 0.35 0.35]);
yline(ax, 500, '--', 'FAILSAFE 500 ms', 'Color', [0.35 0.35 0.35]);
xlabel(ax, 'Supervisor clock (ms)');
ylabel(ax, 'Age (ms)');
legendHandle = legend(ax, {'Heartbeat silence','Source age (includes send age + transit)'}, ...
    'Location', 'northwest');
legendHandle.AutoUpdate = 'off';
grid(ax, 'on');
markEvents(ax, scenario);
superTitle = sgtitle(layout, 'Stateflow simulation / accepted UART metadata / 1 kHz tick');
superTitle.Color = 'k';
set(findall(fig, 'Type', 'axes'), 'Color', 'w', 'XColor', 'k', 'YColor', 'k', ...
    'GridColor', [0.5 0.5 0.5], 'XLim', [0 recording.time_ms(end)]);
set(findall(fig, 'Type', 'text'), 'Color', 'k');
set(findall(fig, 'Type', 'legend'), 'Color', 'w', 'TextColor', 'k');
exportgraphics(fig, fullfile(output, [scenario.name '_timeline.png']), ...
    'Resolution', 150, 'BackgroundColor', 'white');
end

function markEvents(ax, scenario)
if ~isnan(scenario.faultMs)
    xline(ax, scenario.faultMs, ':r', 'Injection');
end
if ~isnan(scenario.resumeMs)
    xline(ax, scenario.resumeMs, ':b', 'Traffic returns');
end
for ms = scenario.rearmMs
    xline(ax, ms, ':k', 'Rearm pulse');
end
end

