function cases = os_supervisor_scenarios()
%OS_SUPERVISOR_SCENARIOS Deterministic accepted-UART fault injections.
% A reception at x.25 ms reaches the next 1 ms supervisor observation.
names = {'healthy','single_missed_heartbeat','late_within_timeout', ...
    'missed_heartbeat_recovery','late_heartbeat_at_deadline', ...
    'degrade_and_recover','stale_result_failsafe_rearm','heartbeat_priority'};
cases = struct([]);
for c = 1:numel(names)
    name = names{c};
    ms = (0:2100)';
    hb = (0.25:20:2100)';
    result = (0.25:50:2100)';
    rearm = [];
    expected = [0 1];
    expectedMs = [0 1];
    faultMs = NaN;
    resumeMs = NaN;
    refHB = NaN;
    refResult = NaN;
    failReason = NaN;
    switch name
        case 'single_missed_heartbeat'
            hb(hb==200.25) = [];
            faultMs = 200.25;
        case 'late_within_timeout'
            hb(hb>=220.25 & hb<280.25) = [];
            faultMs = 220.25;
            resumeMs = 280.25;
        case 'missed_heartbeat_recovery'
            hb(hb>=220.25 & hb<700.25) = [];
            faultMs = 220.25;
            resumeMs = 700.25;
            refHB = 200.25;
            rearm = [900 1701]; % First pulse is too early.
            expected = [0 1 3 0 1];
            expectedMs = [0 1 301 1701 1751];
            failReason = 3;
        case 'late_heartbeat_at_deadline'
            hb(hb>=220.25 & hb<300.25) = [];
            faultMs = 220.25;
            resumeMs = 300.25; % Exactly 100 ms since the last HB, so expired.
            refHB = 200.25;
            rearm = [600 1301];
            expected = [0 1 3 0 1];
            expectedMs = [0 1 301 1301 1351];
            failReason = 3;
        case 'degrade_and_recover'
            result(result>=200.25 & result<450.25) = [];
            faultMs = 200.25;
            resumeMs = 450.25;
            refResult = 150.25;
            expected = [0 1 2 1];
            expectedMs = [0 1 326 451];
        case 'stale_result_failsafe_rearm'
            result(result>=200.25 & result<700.25) = [];
            faultMs = 200.25;
            resumeMs = 700.25;
            refResult = 150.25;
            rearm = [900 1701];
            expected = [0 1 2 3 0 1];
            expectedMs = [0 1 326 626 1701 1751];
            failReason = 10;
        case 'heartbeat_priority'
            result(result>=200.25) = [];
            hb(hb>526) = [];
            hb(end+1) = 526; % HB expiry and source-age FAILSAFE both at 626 ms.
            faultMs = 200.25;
            refResult = 150.25;
            refHB = 526;
            expected = [0 1 2 3];
            expectedMs = [0 1 326 626];
            failReason = 3;
    end
    u = [ms -ones(size(ms)) -ones(size(ms)) 20*ones(size(ms)) zeros(size(ms))];
    for k = 1:numel(hb)
        u(ceil(hb(k))+1, 2) = hb(k);
    end
    for k = 1:numel(result)
        u(ceil(result(k))+1, 3) = result(k);
    end
    u(rearm+1, 5) = 1;
    cases(c).name = name;
    cases(c).stimulus = timeseries(u, ms/1000);
    cases(c).expected = expected;
    cases(c).expectedMs = expectedMs;
    cases(c).faultMs = faultMs;
    cases(c).resumeMs = resumeMs;
    cases(c).rearmMs = rearm;
    cases(c).lastHB = refHB;
    cases(c).lastResult = refResult;
    cases(c).failReason = failReason;
end
end
