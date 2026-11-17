classdef Depacketizer < matlab.System
    % Per-frame duplicate suppression; caller expires entries after late window.
    properties (Access=private)
        Frames;
    end
    methods
        function expire(o,frame)
            key=sprintf('%.0f',frame);
            if ~isempty(o.Frames) && isKey(o.Frames,key), remove(o.Frames,key); end
        end
    end
    methods (Access=protected)
        function setupImpl(o), o.Frames=containers.Map('KeyType','char','ValueType','any'); end
        function [complete,duplicate]=stepImpl(o,p)
            key=sprintf('%.0f',p(3));
            if isKey(o.Frames,key), f=o.Frames(key);
            else, f=struct('seen',false(1,p(5)),'ts',p(2)); end
            assert(numel(f.seen)==p(5) && f.ts==p(2),'Conflicting RTP frame');
            duplicate=f.seen(p(4)); f.seen(p(4))=true;
            complete=all(f.seen) && ~duplicate; o.Frames(key)=f;
        end
        function resetImpl(o), setupImpl(o); end
    end
end
