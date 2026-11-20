classdef CNSEStage < matlab.DiscreteEventSystem
    % Small entity adapters; queues, servers and routing remain native blocks.
    properties (Nontunable)
        Mode = 'packetizer';
    end
    methods (Access=protected)
        function n=getNumInputsImpl(o), n=1+ismember(o.Mode,{'receiver','frame'}); end
        function n=getNumOutputsImpl(o), n=1+strcmp(o.Mode,'receiver'); end
        function t=getEntityTypesImpl(o), t=o.entityType('entity','CNSEEntity'); end
        function [i,u]=getEntityPortsImpl(o)
            i={'entity'};u={'entity'};
            if strcmp(o.Mode,'receiver'),i={'entity','entity'};u={'entity','entity'};end
            if strcmp(o.Mode,'frame'),i={'entity',''};end
        end
        function [s,i,u]=getEntityStorageImpl(o)
            s=[o.queueFIFO('entity',Inf) o.queueFIFO('entity',Inf)];i={1};u={[1 2]};
            if strcmp(o.Mode,'frame'),i={1,0};end
            if strcmp(o.Mode,'receiver')
                s=[s o.queueFIFO('entity',Inf)];i={1,3};u={[1 2],3};
            end
        end
    end
    methods
        function o=CNSEStage(varargin),setProperties(o,nargin,varargin{:});end
        function [entity,events]=entry(o,storage,entity,~,varargin)
            coder.extrinsic('cnse_runtime');
            t=0;t=cnse_runtime('time');
            switch o.Mode
                case 'frame'
                    row=zeros(1,3);row=cnse_runtime('frame',varargin{1});
                    if row(1)==0
                        events=o.eventDestroy();
                        return;
                    end
                    entity.data.frame=row(1);entity.data.capture=row(2);entity.data.size=row(3);
                    route=1;route=cnse_runtime('admitSender');entity.data.route=route;
                    events=o.eventForward('output',1,0);
                case 'packetizer'
                    n=0;n=cnse_runtime('packetize',entity.data,t);
                    events=o.eventDestroy();
                    for k=1:n
                        tag=sprintf('%d:%d',entity.data.frame,k);
                        events=[events o.eventGenerate(2,tag,0,300)]; %#ok<AGROW>
                    end
                case 'channel'
                    delay=0;route=1;
                    [delay,route]=cnse_runtime('channel',entity.data,t);
                    entity.data.route=route;
                    entity.data.forwardDelay=delay;
                    entity.data.sentAt=t;
                    events=o.eventForward('output',1,0);
                case 'receiver'
                    if storage==3
                        rr=zeros(1,7);route=1;d=0;
                        [rr,route,d]=cnse_runtime('report');
                        entity.data.rr=rr;entity.data.route=route;entity.data.reverseDelay=d;
                        events=o.eventForward('output',2,0);return;
                    end
                    wait=-1;wait=cnse_runtime('receive',entity.data,t);
                    events=o.eventDestroy();
                    if wait>=0
                        events=[events o.eventGenerate(2,sprintf('%d',entity.data.frame),wait,300)];
                    end
                otherwise
                    events=o.eventForward('output',1,0);
            end
        end
        function [entity,events]=generate(o,~,entity,tag,varargin)
            coder.extrinsic('cnse_runtime');
            row=zeros(1,8);t=0;t=cnse_runtime('time');
            if strcmp(o.Mode,'packetizer')
                row=cnse_runtime('packet',tag,t);
                entity.data.seq=row(1);entity.data.rtpTimestamp=row(2);
                entity.data.frame=row(3);entity.data.fragment=row(4);
                entity.data.count=row(5);entity.data.size=row(6);
                entity.data.marker=row(7);entity.data.capture=row(8);
                entity.data.SSRC=20261119;
            else
                row=cnse_runtime('playout',tag,t);
                entity.data.frame=row(3);entity.data.capture=row(8);
                route=1;route=cnse_runtime('admitAI');entity.data.route=route;
            end
            events=o.eventForward('output',1,0);
        end
    end
end

