function [rate,clean]=aimd(rate,clean,rr,enabled)
% MATLAB oracle for Stateflow chart tests. Jitter does not reset clean count.
if ~enabled || rr(1)==0,return;end
if rr(2)/256>.02,rate=max(.15,.8*rate);clean=0;
elseif rr(2)/256<=.005
 clean=clean+1;if clean>=3,rate=min(1.5,rate+.05);clean=0;end
else,clean=0;
end
end
