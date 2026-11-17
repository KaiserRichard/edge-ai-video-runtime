classdef Delay < matlab.System
    methods
        function o=Delay(varargin), setProperties(o,nargin,varargin{:}); end
    end
    properties (Nontunable)
        Base = 0; Jitter = 0; Distribution = 'normal'; PreserveOrder = false; Seed = 2;
    end
    properties (Access=private)
        Stream; Last = -Inf;
    end
    methods (Access=protected)
        function setupImpl(o)
            assert(o.Base>=0 && o.Jitter>=0);
            o.Stream=RandStream('mt19937ar','Seed',o.Seed); o.Last=-Inf;
        end
        function arrival=stepImpl(o,t)
            if strcmp(o.Distribution,'normal'), z=randn(o.Stream);
            else, z=2*rand(o.Stream)-1; end
            arrival=t+max(0,o.Base+o.Jitter*z);
            if o.PreserveOrder, arrival=max(arrival,o.Last); end
            o.Last=arrival;
        end
        function resetImpl(o), setupImpl(o); end
    end
end
