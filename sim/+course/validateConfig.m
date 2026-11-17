function validateConfig(c)
assert(ismember(upper(c.project),{'CN','OS'}),'Unknown project');
assert(c.dt==.001,'This model uses a 1 kHz scheduling tick');
assert(c.duration>c.warmup && c.warmup>=0 && c.drain>=0,'Invalid observation window');
assert(c.fps>0 && c.fps<=1/c.dt,'Frame rate must not exceed one source event per tick');
assert(c.payload>0 && c.payload==floor(c.payload),'Payload must be positive integer bytes');
assert(c.meanPackets>=1 && c.maxBatch>=ceil(c.meanPackets),'Packet batch too small');
assert(c.maxBatch==floor(c.maxBatch) && c.maxBatch>0,'Invalid batch bound');
assert(c.loss>=0 && c.loss<=1 && c.seed>=0 && c.seed==floor(c.seed),'Invalid loss or seed');
assert(c.rate>0 && c.linkBytes>0 && c.baud>0,'Invalid link parameters');
assert(c.delay>=0 && c.jitter>=0 && c.depth>=0,'Negative delay');
assert(c.queueCapacity>=1 && c.queueCapacity==floor(c.queueCapacity),'Invalid queue capacity');
assert(ismember(c.policy,{'fifo','latest'}) && ismember(c.bridgePolicy,{'fifo','latest'}),'Unknown policy');
assert(ismember(c.lossMode,{'bernoulli','ge'}) && ismember(c.distribution,{'normal','uniform'}),'Unknown channel law');
assert(all(isfinite(c.samples(:))) && all(c.samples(:)>0) && ~isempty(c.samples),'Invalid service samples');
assert(c.heartbeatTimeout>0 && c.holdTimeout>0 && c.failsafeTimeout>c.holdTimeout && c.healthyRearm>0,'Invalid supervisor limits');
if ~isempty(c.lossSteps)
 assert(size(c.lossSteps,2)==2 && all(diff(c.lossSteps(:,1))>=0),'Invalid step schedule');
 assert(all(c.lossSteps(:,2)>=0 & c.lossSteps(:,2)<=1),'Invalid scheduled loss');
end
end
