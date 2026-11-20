function T=cnse2_validate(r)
% v1 trace oracles (cnse_validate) plus checks that the native v2 blocks
% (replicator packetizer, RFC 3550 MATLAB Function, playout deadline,
% fragment counter, deadline gate) reproduce the +course reference objects.
c=r.c;x=r.rx;reports=r.reports;names=strings(0,1);errors=zeros(0,1);tol=errors;
% Native packetizer (replicator + header stamp) vs course.Packetizer on the
% frames that actually reached the packetizer, in the same order.
P=course.Packetizer('Payload',c.payload);ref=zeros(0,8);
for k=1:size(r.qLog,1)
 f=r.qLog(k,2);cam=r.camera(r.camera(:,2)==f,:);
 ref=[ref;P(f,cam(3),cam(4))]; %#ok<AGROW>
end
add('Native packetizer fields vs course.Packetizer',err(ref,r.tx(:,2:9)),0);
add('Native RFC 3550 block vs course.ReceiverReport jitter',err(x(:,12),r.libraryJitter),1e-9);
add('Native fragment counter vs course.Depacketizer',...
 err(r.nativeComplete(:,1),r.nativeComplete(:,2)),0);
onTime=find(isfinite(r.frames(:,4)) & r.frames(:,4)<=r.frames(:,3)+1e-12);
add('Deadline gate releases exactly the complete on-time frames',...
 err(sort(r.released(:,2)),onTime),0);
rr=course.ReceiverReport;j=course.RFCJitter;pb=course.PlayoutBuffer('Depth',c.depth);
dep=course.Depacketizer;arrival=course.Delay('Base',c.delay,'Jitter',c.jitter,...
 'Distribution',c.distribution,'PreserveOrder',c.preserveOrder,'Seed',c.seed+300);
loss=course.Loss('Mode',c.lossMode,'Pgb',c.pGB,'Pbg',c.pBG,'Seed',c.seed+200);
maxJ=0;maxD=0;maxRR=0;idx=1;formula=0;last=NaN;lastTs=0;maxFormula=0;
complete=Inf(size(r.frames,1),1);
for k=1:size(reports,1)+1
 time=Inf;if k<=size(reports,1),time=reports(k,1);end
 while idx<=size(x,1) && x(idx,1)<=time
  row=x(idx,:);p=row(2:9);t=row(1);[~,~,~,jm]=rr(p,t,false);
  v=j(t,p(2));maxJ=max(maxJ,max(abs([v-jm jm-row(12)])));
  deadline=pb(t,p(2));maxD=max(maxD,abs(deadline-row(13)));
  [done,~]=dep(p);if done,complete(p(3))=t;end
  if isfinite(last)
   ds=mod(p(2)-lastTs+2^31,2^32)-2^31;
   formula=formula+(abs((t-last)*90000-ds)-formula)/16;
  end
  maxFormula=max(maxFormula,abs(formula/90-row(12)));last=t;lastTs=p(2);idx=idx+1;
 end
 if k<=size(reports,1)
  [v,~,~,~]=rr([],time,true);maxRR=max(maxRR,max(abs(v-reports(k,2:8))));
 end
end
add('RFC jitter vs course.RFCJitter and RR',maxJ,1e-8);
add('RFC jitter independent recurrence',maxFormula,1e-8);
add('RTCP fraction cumulative loss jitter',maxRR,0);
reverseLoss=course.Loss('Seed',c.seed+600);
reverseDelay=course.Delay('Base',c.reverseDelay,'Jitter',c.reverseJitter,'Seed',c.seed+700);
reverse=zeros(0,8);
for k=1:size(reports,1)
 departure=reports(k,1);
 dropped=reverseLoss(c.reverseLoss);due=reverseDelay(departure);
 if ~dropped && due<=c.duration+c.drain
  reverse(end+1,:)=[due reports(k,2:8)]; %#ok<AGROW>
 end
end
add('Seeded RTCP reverse delivery vs course.Delay and course.Loss',err(sortrows(reverse,1),r.feedback),1e-9);
add('Playout deadline vs course.PlayoutBuffer',maxD,1e-9);
add('Reassembly vs course.Depacketizer',err(complete,r.frames(:,4)),1e-9);
% Replay the seeded channel on exactly the transmitted packet order.
eLoss=0;eDelay=0;
for k=1:size(r.tx,1)
 p=r.tx(k,:);prob=c.loss;
 for h=1:size(c.lossSteps,1),if p(1)>=c.lossSteps(h,1),prob=c.lossSteps(h,2);end,end
 drop=false;for h=1:ceil((p(7)+28)/1480),drop=loss(prob)||drop;end
 eLoss=max(eLoss,abs(drop-p(10)));
 if ~drop,eDelay=max(eDelay,abs(arrival(p(1))-p(1)-p(11)));end
end
add('Seeded packet and fragment loss vs course.Loss',eLoss,0);
add('Seeded propagation vs course.Delay',eDelay,1e-9);
% Native serialization server uses all packets, including later channel losses.
last=0;eSerial=0;
for k=1:size(r.serialized,1)
 p=r.serialized(k,:);ix=find(r.qLog(:,2)==p(3),1);enq=r.qLog(ix,1);
 last=max(last,enq)+8*(p(4)+48)/c.rate;
 eSerial=max(eSerial,abs(p(1)-last));
end
add('Native serialization independent workload equation',eSerial,1e-7);
add('Channel timestamps equal serialized departures',err(r.tx(:,1:2),r.serialized(:,1:2)),1e-9);
% Match each received fragment to its actual transmission despite reordering.
[matched,origin]=ismember(x(:,[2 4 5]),r.tx(:,[2 4 5]),'rows');
if all(matched) && numel(unique(origin))==size(x,1)
 delivered=r.tx(origin,:);
 add('Only surviving fragments reach the receiver',sum(delivered(:,10)),0);
 add('Native delay matches each seeded arrival within 1 ms',...
  max([0;abs(x(:,1)-delivered(:,1)-delivered(:,11))]),.00101);
else
 add('Only surviving fragments reach the receiver',Inf,0);
 add('Native delay matches each seeded arrival within 1 ms',Inf,0);
end
a=r.results;oracle=course.aoi(a(:,1),a(:,3),c.warmup,c.duration);
independent=independentAge(a(:,1),a(:,3),c.warmup,c.duration);
add('AI-result AoI exact integral vs course.aoi',err(oracle,independent),1e-9);
add('Reported AoI vs independent integral (ms)',err(r.metrics.aoi_ms,1000*independent),1e-6);
window=r.tx(:,1)>=c.warmup & r.tx(:,1)<c.duration;
add('Reported sequence loss vs unique received fragments',...
 err(r.metrics.sequence_loss,1-sum(ismember(find(window),origin))/nnz(window)),1e-12);
% Check each state change against the delivered RR oracle, allowing 2 ticks
% for the sampled input and the explicit feedback Unit Delay.
rate=1;clean=0;expected=[0 1];
for k=1:size(r.feedback,1)
 [rate,clean]=course.aimd(rate,clean,r.feedback(k,2:8),c.adaptive);
 if rate~=expected(end,2),expected(end+1,:)=[r.feedback(k,1) rate];end %#ok<AGROW>
end
actual=r.rateLog;
if size(actual,1)==size(expected,1)
 add('AIMD Stateflow rate vs course.aimd',max(abs(actual(:,2)-expected(:,2))),1e-10);
 add('AIMD feedback scheduling within two ticks',max(abs(actual(:,1)-expected(:,1))),.00201);
else
 add('AIMD Stateflow rate vs course.aimd',Inf,0);
 add('AIMD feedback scheduling within two ticks',Inf,0);
end
add('Every received packet passed the native loss switch',...
 size(x,1)-sum(r.tx(:,10)==0),0);
add('Every result came from an on-time frame',sum(r.frames(a(:,2),6)~=1),0);
% Test endpoint definitions and nonnegative latency as well as trace parity.
add('Causal result timestamps',max([0;a(:,3)-a(:,1)]),0);
T=table(names,errors,tol,errors<=tol,'VariableNames',{'check','error','tolerance','pass'});
 function add(n,e,t),names(end+1,1)=n;errors(end+1,1)=abs(e);tol(end+1,1)=t;end
end
function e=err(a,b)
if isequaln(a,b),e=0;elseif isequal(size(a),size(b)) && all(isfinite(a(:))==isfinite(b(:)))
 finite=isfinite(a)&isfinite(b);e=max([0;abs(a(finite)-b(finite))]);
else,e=Inf;end
end
function age=independentAge(t,cap,start,stop)
[t,k]=sort(t);cap=cap(k);ok=t<=start;
if ~any(ok),age=NaN;return;end
fresh=max(cap(ok));cursor=start;area=0;
for k=find(t>start & t<=stop)'
 interval=t(k)-cursor;area=area+interval*((cursor+t(k))/2-fresh);
 fresh=max(fresh,cap(k));cursor=t(k);
end
area=area+(stop-cursor)*((cursor+stop)/2-fresh);age=area/(stop-start);
end
