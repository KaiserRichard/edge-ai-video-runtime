classdef PlayoutBuffer < matlab.System
    methods
        function o=PlayoutBuffer(varargin), setProperties(o,nargin,varargin{:}); end
    end
    properties (Nontunable), Depth=.05; ClockRate=90000; end
    properties (Access=private), Anchor=NaN; Timestamp=0; end
    methods (Access=protected)
        function deadline=stepImpl(o,arrival,ts)
            if isnan(o.Anchor), o.Anchor=arrival; o.Timestamp=ts; end
            delta=mod(ts-o.Timestamp+2^31,2^32)-2^31;
            deadline=o.Anchor+delta/o.ClockRate+o.Depth;
        end
        function resetImpl(o), o.Anchor=NaN; o.Timestamp=0; end
    end
end
