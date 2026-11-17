classdef Loss < matlab.System
    methods
        function o=Loss(varargin), setProperties(o,nargin,varargin{:}); end
    end
    % GE emits in current state, then transitions; start in stationarity.
    properties (Nontunable)
        Mode = 'bernoulli'; Probability = 0; Pgb = .01316; Pbg = .25; Seed = 1;
    end
    properties (Access=private)
        Stream; Bad = false;
    end
    methods (Access=protected)
        function setupImpl(o)
            assert(o.Probability>=0 && o.Probability<=1);
            assert(o.Pgb>=0 && o.Pbg>0 && o.Pgb<=1 && o.Pbg<=1);
            o.Stream=RandStream('mt19937ar','Seed',o.Seed);
            o.Bad=rand(o.Stream)<o.Pgb/(o.Pgb+o.Pbg);
        end
        function drop=stepImpl(o,p)
            if strcmp(o.Mode,'ge')
                drop=o.Bad;
                u=rand(o.Stream);
                if o.Bad, o.Bad=~(u<o.Pbg); else, o.Bad=u<o.Pgb; end
            else
                assert(p>=0 && p<=1); drop=rand(o.Stream)<p;
            end
        end
        function resetImpl(o), setupImpl(o); end
    end
end
