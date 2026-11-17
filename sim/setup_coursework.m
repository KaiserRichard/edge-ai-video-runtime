function root = setup_coursework()
% Add this project only. Never start a parallel pool or touch another session.
root = fileparts(mfilename('fullpath'));
addpath(root,fullfile(root,'models'),fullfile(root,'app'));
for name = {'generated','output'}
    p = fullfile(root,name{1});
    if ~isfolder(p), mkdir(p); end
end
end
