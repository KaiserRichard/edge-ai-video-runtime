function rows=faultTransitions(result)
% Reference-clock and fault-clock timing for first HOLD/FAILSAFE in a fault.
% Analytic crossing assumes no further accepted message of that type.
c=result.config;s=result.state;u=result.UART;
rows=struct('fault',{},'seed',{},'state',{},'reason',{},'reference',{},...
 'local_ms',{},'fault_to_state_ms',{},'predicted_fault_ms',{},...
 'quantization_ms',{},'tick_error_ms',{});
if isempty(s),return;end
entered=[true;diff(s(:,2))~=0];
for target=[2 3]
 ix=find(entered & s(:,1)>=c.faultTime & s(:,1)<c.recoverTime & s(:,2)==target,1);
 if isempty(ix),continue;end
 time=s(ix,1);reason=s(ix,3);
 if reason==3
  j=find(u.aux(:,1)<=time & isfinite(u.aux(:,2)),1,'last');
  if isempty(j),continue;end
  reference=u.aux(j,1)-u.aux(j,2);
  kind="last_heartbeat";remaining=c.heartbeatTimeout;
 elseif reason==9 || reason==10
  j=find(u.log(:,1)<=time,1,'last');
  if isempty(j),continue;end
  reference=u.log(j,1);kind="last_inference";
  if target==2,limit=c.holdTimeout;else,limit=c.failsafeTimeout;end
  remaining=limit-u.log(j,4)-c.transitBound;
 else
  continue;
 end
 crossing=reference+remaining;
 predictedTick=ceil((crossing-1e-12)/c.dt)*c.dt;
 rows(end+1)=struct('fault',string(c.fault),'seed',c.seed,'state',target,...
  'reason',reason,'reference',kind,'local_ms',1000*(time-reference),...
  'fault_to_state_ms',1000*(time-c.faultTime),...
  'predicted_fault_ms',1000*(predictedTick-c.faultTime),...
  'quantization_ms',1000*(time-crossing),'tick_error_ms',1000*(time-predictedTick)); %#ok<AGROW>
end
end
