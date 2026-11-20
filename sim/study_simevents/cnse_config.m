function c=cnse_config(c)
% Seconds, bytes, bits/s. No Wireless Network Toolbox dependencies.
if nargin==0,c=course.defaults('CN');end
if ~isfield(c,'senderService'),c.senderService=0;end
if ~isfield(c,'reverseDelay'),c.reverseDelay=.010;end
if ~isfield(c,'reverseJitter'),c.reverseJitter=.002;end
if ~isfield(c,'reverseLoss'),c.reverseLoss=0;end
c.transportFloor=1e-6;
c.transportBase=0;
if c.jitter==0
    c.transportBase=c.delay;
elseif strcmp(c.distribution,'uniform')
    c.transportBase=max(0,c.delay-c.jitter);
end
end
