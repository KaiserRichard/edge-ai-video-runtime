classdef RFCJitter < matlab.System
    methods
        function o=RFCJitter(varargin), setProperties(o,nargin,varargin{:}); end
    end
    properties (Nontunable), ClockRate=90000; end
    properties (Access=private)
        LastArrival=NaN; LastTimestamp=0; J=0;
    end
    methods (Access=protected)
        function [ms,ticks]=stepImpl(o,arrival,ts)
            if ~isnan(o.LastArrival)
                ds=mod(ts-o.LastTimestamp+2^31,2^32)-2^31;
                d=(arrival-o.LastArrival)*o.ClockRate-ds;
                o.J=o.J+(abs(d)-o.J)/16;
            end
            o.LastArrival=arrival; o.LastTimestamp=ts;
            ticks=o.J; ms=1000*o.J/o.ClockRate;
        end
        function resetImpl(o), o.LastArrival=NaN; o.LastTimestamp=0; o.J=0; end
    end
end
