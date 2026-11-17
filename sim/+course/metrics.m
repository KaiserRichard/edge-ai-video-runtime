function m=metrics(r)
c=r.config;ai=r.Inference.log;w=c.warmup;stop=c.duration;
if isempty(ai),done=[];capture=[];else,done=ai(:,1);capture=ai(:,3);end
use=capture>=w & capture<stop & done<=stop;
m=struct('frame_loss',NaN,'on_time',NaN,'late',NaN,'sequence_loss',NaN,...
 'jitter_ms',NaN,'latency_p50_ms',course.percentile(1000*(done(use)-capture(use)),50),...
 'latency_p95_ms',course.percentile(1000*(done(use)-capture(use)),95),...
 'aoi_ms',1000*course.aoi(done,capture,w,stop),'results_s',sum(done>=w & done<stop)/(stop-w));
m.payload_bitrate_mbps=NaN;m.packets_per_frame=NaN;
m.queue_wait_p50_ms=NaN;m.queue_wait_p95_ms=NaN;m.inference_p50_ms=NaN;m.inference_p95_ms=NaN;
if ~isempty(ai)
 m.queue_wait_p50_ms=course.percentile(ai(use,5)*1000,50);
 m.queue_wait_p95_ms=course.percentile(ai(use,5)*1000,95);
 m.inference_p50_ms=course.percentile(ai(use,4)*1000,50);
 m.inference_p95_ms=course.percentile(ai(use,4)*1000,95);
end
if strcmpi(c.project,'CN')
 cam=r.Camera.log;select=cam(:,3)>=w & cam(:,3)<stop;
 m.payload_bitrate_mbps=sum(cam(select,4))*8/(stop-w)/1e6;
 m.packets_per_frame=mean(ceil(cam(select,4)/c.payload));
 f=r.Receiver.frames;select=f(:,2)>=w & f(:,2)<stop;f=f(select,:);
 m.frame_loss=mean(isinf(f(:,4)));m.on_time=mean(f(:,6)==1);
 m.late=mean(isfinite(f(:,4)) & f(:,4)>f(:,3));
 p=r.Netem.log;select=p(:,1)>=w & p(:,1)<stop;
 m.sequence_loss=mean(any(p(select,4:5)>0,2));
 p=r.Receiver.log;select=p(:,1)>=w & p(:,1)<stop;m.jitter_ms=mean(p(select,6));
else
 p=r.UART.log;
 m.aoi_ms=1000*course.aoi(p(:,1),p(:,3),w,stop);
end
end
