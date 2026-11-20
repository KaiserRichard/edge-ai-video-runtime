classdef CNSE2Monitor < matlab.System
    % Sample entity observations for the AIMD controller and the five-panel scope.
    methods (Access=protected)
        function [rr,y]=stepImpl(~,rate,received)
            coder.extrinsic('cnse2_runtime');
            rr=zeros(7,1);y=zeros(5,1);
            [rr,y]=cnse2_runtime('poll',rate,received);
        end
        function [a,b]=getOutputSizeImpl(~),a=[7 1];b=[5 1];end
        function [a,b]=getOutputDataTypeImpl(~),a='double';b='double';end
        function [a,b]=isOutputComplexImpl(~),a=false;b=false;end
        function [a,b]=isOutputFixedSizeImpl(~),a=true;b=true;end
        function s=getSampleTimeImpl(o),s=createSampleTime(o,'Type','Discrete','SampleTime',.001);end
    end
end
