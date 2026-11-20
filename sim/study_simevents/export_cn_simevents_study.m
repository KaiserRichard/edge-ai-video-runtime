function export_cn_simevents_study()
% Export the actual Simulink subsystems and a dashboard from the logged signals.
root = fileparts(fileparts(mfilename('fullpath')));
folder = fullfile(root,'study_simevents');
figures = fullfile(folder,'figures');
if ~isfolder(figures), mkdir(figures); end
model = 'CN_simevents';
if ~bdIsLoaded(model), load_system(fullfile(root,'generated',[model '.slx'])); end

subsystems = find_system(model,'SearchDepth',1,'BlockType','SubSystem');
subsystems = setdiff(subsystems,{[model '/AIMD']},'stable');
systems = [{model};subsystems(:)];
for k = 1:numel(systems)
    system = systems{k};
    filename = fullfile(figures,[strrep(strrep(system,'/','__'),' ','_') '.png']);
    set_param(system,'PaperOrientation','landscape','PaperType','A3');
    print(['-s' system],'-dpng','-r200',filename);
    cropDiagram(filename);
end
chart = fullfile(figures,'CN_simevents__AIMD.png');
sfprint([model '/AIMD'],'png',chart);
cropDiagram(chart);

fixed = load(fullfile(folder,'B_adaptive0.mat'),'r');
adaptive = load(fullfile(folder,'B_adaptive1.mat'),'r');
fig = figure('Visible','off','Color','w','Position',[30 30 1250 1040]);
cleanup = onCleanup(@()close(fig)); %#ok<NASGU>
layout = tiledlayout(fig,5,1,'TileSpacing','compact','Padding','compact');
ink=[.12 .18 .24];
title(layout,'Stage B | Fixed versus AIMD during a 15% forward-loss step','Color',ink);
xlabel(layout,'Simulation time (s)','Color',ink);
labels = {'Target payload (Mb/s)','Cumulative loss (%)','RFC 3550 jitter (ms)', ...
    'Playout buffer (1 s mean)','AI-result AoI (ms)'};
fixedData = squeeze(fixed.r.dashboard.Data)';
adaptiveData = squeeze(adaptive.r.dashboard.Data)';
if size(fixedData,1)~=numel(fixed.r.dashboard.Time)
    fixedData=fixedData';
    adaptiveData=adaptiveData';
end
fixedData(:,2)=100*fixedData(:,2);
adaptiveData(:,2)=100*adaptiveData(:,2);
fixedData(:,4)=movmean(fixedData(:,4),[999 0]);
adaptiveData(:,4)=movmean(adaptiveData(:,4),[999 0]);
for k = 1:5
    ax = nexttile(layout);
    series = plot(ax,fixed.r.dashboard.Time,fixedData(:,k),'Color',[.24 .34 .47],'LineWidth',1.0);
    hold(ax,'on');
    series(2) = plot(ax,adaptive.r.dashboard.Time,adaptiveData(:,k),'Color',[.03 .54 .49],'LineWidth',1.0);
    xline(ax,15,'--','Color',[.50 .39 .29]);
    xline(ax,35,'--','Color',[.50 .39 .29]);
    ax.Color='white'; ax.XColor=ink; ax.YColor=ink;
    ax.GridColor=[.44 .51 .59]; ax.GridAlpha=.23;
    ylabel(ax,labels{k},'Color',ink);
    xlim(ax,[0 adaptive.r.c.duration]);
    grid(ax,'on');
    if k==1
        lg=legend(ax,series,{'Fixed','AIMD'},'Location','northeast');
        lg.Color='white'; lg.TextColor=ink; lg.EdgeColor=[.70 .75 .80];
    end
    if k<5, ax.XTickLabel={}; end
end
exportgraphics(fig,fullfile(figures,'Stage_B_Dashboard.png'),'Resolution',135);
end

function cropDiagram(filename)
[pixels,map,alpha] = imread(filename);
if ~isempty(map)
    pixels = uint8(round(255*ind2rgb(pixels,map)));
end
if size(pixels,3)==1
    pixels = repmat(pixels,1,1,3);
end
if ~isempty(alpha)
    weight = double(alpha)/double(intmax(class(alpha)));
    pixels = uint8(double(pixels).*weight + 255*(1-weight));
end
ink = any(pixels<248,3);
rows = find(any(ink,2));
columns = find(any(ink,1));
assert(~isempty(rows) && ~isempty(columns),'CNSE:Figure','Empty diagram export.');
y = max(1,rows(1)-30):min(size(pixels,1),rows(end)+30);
x = max(1,columns(1)-30):min(size(pixels,2),columns(end)+30);
imwrite(pixels(y,x,:),filename);
end
