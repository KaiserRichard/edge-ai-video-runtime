classdef FrameQueue < matlab.System
    methods
        function o=FrameQueue(varargin), setProperties(o,nargin,varargin{:}); end
    end
    % step(row,pop): push first, then pop. Empty row means no enqueue.
    % FIFO drops newest on overflow; latest overwrites the waiting slot only.
    properties (Nontunable), Policy='fifo'; Capacity=8; end
    properties (Access=private), Rows=zeros(0,3); end
    methods (Access=protected)
        function flag=isInputSizeMutableImpl(~,~), flag=true; end
        function [row,count,dropped]=stepImpl(o,item,pop)
            dropped=0; row=zeros(0,3);
            if ~isempty(item)
                if strcmp(o.Policy,'latest')
                    dropped=size(o.Rows,1); o.Rows=item;
                elseif size(o.Rows,1)<o.Capacity
                    o.Rows(end+1,:)=item;
                else, dropped=1;
                end
            end
            if pop && ~isempty(o.Rows), row=o.Rows(1,:); o.Rows(1,:)=[]; end
            count=size(o.Rows,1);
        end
        function resetImpl(o), o.Rows=zeros(0,3); end
    end
end
