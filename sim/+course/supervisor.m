function [s,reason,h,epoch]=supervisor(s,reason,h,epoch,u,c)
% Tick-level oracle, transition-before-during semantics match generated chart.
t=u(1);healthy=t-u(2)<c.heartbeatTimeout && u(4)<c.holdTimeout;
switch s
 case 0
  if u(3)>epoch && u(4)>=c.failsafeTimeout,s=3;reason=10;
  elseif u(2)>epoch && u(3)>epoch && healthy,s=1;reason=1;end
 case {1,2}
  if t-u(2)>=c.heartbeatTimeout,s=3;reason=3;
  elseif u(4)>=c.failsafeTimeout,s=3;reason=10;
  elseif u(4)>=c.holdTimeout,s=2;reason=9;
  elseif healthy,s=1;reason=1;end
 case 3
  if u(5)>0 && h>=0 && t-h>=c.healthyRearm && healthy
   s=0;reason=0;epoch=t;h=-1;return;
  end
end
if healthy,if h<0,h=t;end;else,h=-1;end
end
