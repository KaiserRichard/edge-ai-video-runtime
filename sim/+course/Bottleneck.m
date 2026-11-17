classdef Bottleneck < matlab.System
    methods
        function o=Bottleneck(varargin), setProperties(o,nargin,varargin{:}); end
    end
    % Byte capacity includes the packet in service. Tail drop, no preemption.
    properties (Nontunable)
        Rate = 100e6; Capacity = 256000; BitsPerByte = 8;
    end
    properties (Access=private)
        Jobs = zeros(0,2); Last = 0;
    end
    methods (Access=protected)
        function [departure,dropped,bytes]=stepImpl(o,t,n)
            assert(n>0 && o.Rate>0 && o.Capacity>0);
            o.Jobs(o.Jobs(:,1)<=t,:)=[];
            bytes=sum(o.Jobs(:,2)); dropped=bytes+n>o.Capacity;
            departure=Inf;
            if ~dropped
                departure=max(t,o.Last)+n*o.BitsPerByte/o.Rate;
                o.Last=departure; o.Jobs(end+1,:)=[departure,n]; bytes=bytes+n;
            end
        end
        function resetImpl(o), o.Jobs=zeros(0,2); o.Last=0; end
    end
end
