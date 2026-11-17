function tests = test_os_supervisor()
%TEST_OS_SUPERVISOR MATLAB unit-test entry point for the complete SLX harness.
tests = functiontests(localfunctions);
end

function testChartSequencesAndTiming(testCase)
report = run_os_supervisor_tests();
verifyEqual(testCase, numel(report), 8);
verifyTrue(testCase, all([report.passed]));
end
