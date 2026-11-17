classdef ReceiverReport < matlab.System
    % Single validated SSRC, extended sequence and RFC 3550 interval loss.
    % No probation/restart detection; duplicates count in RFC received count.
    properties (Access=private)
        Highest=NaN; Base=0; Received=0; ExpectedPrior=0; ReceivedPrior=0;
        Seen; Jitter; JitterTicks=0;
    end
    methods (Access=protected)
        function setupImpl(o)
            o.Seen=containers.Map('KeyType','double','ValueType','logical');
            o.Jitter=course.RFCJitter;
        end
        function [rr,duplicate,reordered,jms]=stepImpl(o,packet,t,report)
            duplicate=false;reordered=false;jms=NaN;
            if ~isempty(packet)
                seq=packet(1);
                if isnan(o.Highest),ext=seq;o.Base=ext;o.Highest=ext;
                else,ext=o.Highest+mod(seq-mod(o.Highest,65536)+32768,65536)-32768;end
                duplicate=isKey(o.Seen,ext);reordered=ext<o.Highest;
                o.Seen(ext)=true;o.Highest=max(o.Highest,ext);o.Received=o.Received+1;
                [jms,o.JitterTicks]=o.Jitter(t,packet(2));
            end
            rr=zeros(1,7);
            if report && ~isnan(o.Highest)
                expected=o.Highest-o.Base+1;lost=expected-o.Received;
                ei=expected-o.ExpectedPrior;ri=o.Received-o.ReceivedPrior;
                fraction=0;if ei>0,fraction=min(255,max(0,floor(256*(ei-ri)/ei)));end
                rr=[1 fraction floor(o.JitterTicks) max(-2^23,min(2^23-1,lost)) o.Highest 0 0];
                o.ExpectedPrior=expected;o.ReceivedPrior=o.Received;
            end
        end
        function flag=isInputSizeMutableImpl(~,~),flag=true;end
        function resetImpl(o)
            o.Highest=NaN;o.Base=0;o.Received=0;o.ExpectedPrior=0;o.ReceivedPrior=0;o.JitterTicks=0;setupImpl(o);
        end
    end
end
