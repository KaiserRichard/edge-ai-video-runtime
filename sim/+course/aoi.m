function [value,t,age]=aoi(done,capture,start,stop)
% Exact integral of freshest-delivered age. Require an observation at start.
assert(stop>start,'Observation stop must exceed start');
capture=capture(:);assert(numel(done)==numel(capture),'Mismatched delivery/capture vectors');
[done,k]=sort(done(:)); capture=capture(k); good=isfinite(done)&isfinite(capture);
done=done(good); capture=capture(good);
idx=find(done<=start,1,'last');
if isempty(idx), value=NaN; t=[]; age=[]; return; end
fresh=max(capture(1:idx)); last=start; area=0; t=start; age=start-fresh;
for k=idx+1:numel(done)
    if done(k)>stop, break; end
    dt=done(k)-last; area=area+(last-fresh)*dt+dt^2/2;
    t=[t;done(k);done(k)]; age=[age;done(k)-fresh;done(k)-max(fresh,capture(k))]; %#ok<AGROW>
    fresh=max(fresh,capture(k)); last=done(k);
end
dt=stop-last; area=area+(last-fresh)*dt+dt^2/2;
t=[t;stop]; age=[age;stop-fresh]; value=area/(stop-start);
end
