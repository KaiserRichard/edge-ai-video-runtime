function frame=replayVideoFrame(video,time)
% Pure time selection, independently testable without creating a UI.
% Sparse unrelated CSV rows do not erase the last image or label.
frame=struct('file',"",'label',"No label yet",'confidence',NaN,'bad',false);
available=video.t<=time;
j=find(available & ~ismissing(video.file) & strlength(video.file)>0,1,'last');
if ~isempty(j),frame.file=video.file(j);frame.bad=video.bad(j);end
j=find(available & ~ismissing(video.label) & strlength(video.label)>0,1,'last');
if ~isempty(j),frame.label=video.label(j);frame.confidence=video.confidence(j);end
end
