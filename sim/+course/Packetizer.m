classdef Packetizer < matlab.System
    methods
        function o=Packetizer(varargin), setProperties(o,nargin,varargin{:}); end
    end
    % Metadata RTP model (not JPEG encoding or a wire serializer).
    % columns: seq, ts, frame, fragment, count, JPEG bytes, marker, capture.
    properties (Nontunable)
        Payload = 1200; ClockRate = 90000; InitialSequence = 0; InitialTimestamp = 0;
    end
    properties (Access=private)
        Sequence = 0;
    end
    methods (Access=protected)
        function setupImpl(o), o.Sequence=o.InitialSequence; end
        function p=stepImpl(o,frame,capture,bytes)
            assert(bytes>0 && bytes==floor(bytes) && o.Payload>0);
            n=ceil(bytes/o.Payload); p=zeros(n,8);
            ts=mod(o.InitialTimestamp+round(capture*o.ClockRate),2^32);
            for k=1:n
                p(k,:)=[mod(o.Sequence,65536),ts,frame,k,n,...
                    min(o.Payload,bytes-(k-1)*o.Payload),double(k==n),capture];
                o.Sequence=o.Sequence+1;
            end
        end
        function resetImpl(o), o.Sequence=o.InitialSequence; end
    end
end
