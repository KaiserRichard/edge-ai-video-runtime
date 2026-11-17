classdef CourseworkReplayApp < matlab.apps.AppBase
% Programmatic App Designer-compatible app source (AppBase + uifigure).
% No binary .mlapp is fabricated. Launch CourseworkReplayApp(sim,measured).
properties (Access=public)
 UIFigure; Tabs; Slider; Status; Axes; Notes; Data; Clock; Time=0; Playing=false; Speed=1;
end
methods
 function app=CourseworkReplayApp(sim,measured)
  setup_coursework();app.Data={course.replayData(structEmpty()),course.replayData(structEmpty())};
  % Validate recordings before allocating a window or a timer.
  if nargin>=1 && ~isempty(sim),app.Data{1}=course.replayData(sim);end
  if nargin>=2 && ~isempty(measured),app.Data{2}=course.replayData(measured);end
  app.UIFigure=uifigure('Name','CN + OS replay | simulation and measurement','Position',[70 70 1400 850]);
  app.UIFigure.CloseRequestFcn=@(~,~)delete(app);
  grid=uigridlayout(app.UIFigure,[3 1]);grid.RowHeight={40,'1x',60};
  bar=uigridlayout(grid,[1 7]);bar.ColumnWidth={160,160,90,90,100,'1x',100};
  uibutton(bar,'Text','Load simulation','ButtonPushedFcn',@(~,~)app.choose(1));
  uibutton(bar,'Text','Load measured log','ButtonPushedFcn',@(~,~)app.choose(2));
  uibutton(bar,'Text','Play / pause','ButtonPushedFcn',@(~,~)app.toggle());
  uibutton(bar,'Text','Restart','ButtonPushedFcn',@(~,~)app.seek(0));
  uidropdown(bar,'Items',{'0.5x','1x','2x','5x'},'Value','1x','ValueChangedFcn',@(~,e)app.speed(e.Value));
  app.Status=uilabel(bar,'Text','Load a simulation MAT and measured CSV.');
  uibutton(bar,'Text','Refresh','ButtonPushedFcn',@(~,~)app.draw());
  app.Tabs=uitabgroup(grid);n=numel(app.Data{1}.panels);app.Axes=cell(n,2);app.Notes=cell(n,2);
  for k=1:n
   tab=uitab(app.Tabs,'Title',app.Data{1}.panels{k}.name);
   layout=uigridlayout(tab,[2 2]);layout.RowHeight={'1x',70};
   for side=1:2
    ax=uiaxes(layout);ax.Layout.Row=1;ax.Layout.Column=side;app.Axes{k,side}=ax;
    note=uilabel(layout,'WordWrap','on');note.Layout.Row=2;note.Layout.Column=side;app.Notes{k,side}=note;
   end
  end
  limit=max([1 app.Data{1}.duration app.Data{2}.duration]);
  app.Slider=uislider(grid,'Limits',[0 limit],'ValueChangedFcn',@(~,e)app.seek(e.Value));
  app.Clock=timer('ExecutionMode','fixedSpacing','Period',.2,'BusyMode','drop','TimerFcn',@(~,~)app.tick());
  registerApp(app,app.UIFigure);
  app.draw();start(app.Clock);if nargout==0,clear app;end
 end
 function choose(app,side)
  [f,p]=uigetfile({'*.mat;*.csv','Simulation MAT or measured CSV'});
  if isequal(f,0),return;end
  try,app.load(side,fullfile(p,f));catch e,uialert(app.UIFigure,e.message,'Cannot load replay');end
 end
 function load(app,side,file)
  app.Data{side}=course.replayData(file);
  limit=max([1 app.Data{1}.duration app.Data{2}.duration]);
  app.Time=min(app.Time,limit);app.Slider.Value=min(app.Slider.Value,limit);
  app.Slider.Limits=[0 limit];app.draw();
 end
 function speed(app,s),app.Speed=str2double(erase(s,'x'));end
 function toggle(app),app.Playing=~app.Playing;end
 function seek(app,t)
  validateattributes(t,{'numeric'},{'scalar','real','finite'});
  app.Time=max(0,min(app.Slider.Limits(2),t));app.draw();
 end
 function tick(app)
  if app.Playing
   app.Time=min(app.Slider.Limits(2),app.Time+.2*app.Speed);
   if app.Time>=app.Slider.Limits(2),app.Playing=false;end
   app.draw();
  end
 end
 function draw(app)
  app.Slider.Value=min(app.Slider.Limits(2),app.Time);
  app.Status.Text=sprintf('Replay %.2f s | left: %s | right: %s',app.Time,app.Data{1}.name,app.Data{2}.name);
  for k=1:size(app.Axes,1)
   for side=1:2
    p=app.Data{side}.panels{k};ax=app.Axes{k,side};
    cla(ax,'reset');legend(ax,'off');app.Notes{k,side}.Text=p.note;
    title(ax,app.Data{side}.name,'Interpreter','none');xlabel(ax,'Seconds since run origin');grid(ax,'on');
    if strcmp(p.mode,'video')
     frame=course.replayVideoFrame(p.video,app.Time);
     if strlength(frame.file)>0 && isfile(frame.file)
      image(ax,imread(frame.file));axis(ax,'image');
     else
      text(ax,.5,.5,'No image at this time','Units','normalized','HorizontalAlignment','center');
     end
     label=frame.label;
     if isfinite(frame.confidence),label=label+sprintf(' (%.1f%%)',100*frame.confidence);end
     title(ax,label,'Interpreter','none');
     if frame.bad,ax.XColor=[.85 .1 .1];ax.YColor=[.85 .1 .1];
     else,ax.XColor=[.15 .15 .15];ax.YColor=[.15 .15 .15];end
     ax.Box='on';ax.LineWidth=2;continue;
    end
    if isempty(p.t)
     text(ax,.5,.5,'Unavailable in this recording','Units','normalized','HorizontalAlignment','center');continue;
    end
    selected=p.t<=app.Time & p.t>=max(0,app.Time-10);
    if strcmp(p.mode,'hist')
     selected=p.t<=app.Time;histogram(ax,p.y(selected,1));xlabel(ax,'Latency (ms)');ylabel(ax,'Samples');
    elseif strcmp(p.mode,'packets')
     v=p.y(selected,:);colors=repmat([.45 .45 .45],size(v,1),1);
     colors(v(:,2)==1,:)=repmat([.85 .1 .1],sum(v(:,2)==1),1);
     colors(v(:,2)==2,:)=repmat([1 .5 0],sum(v(:,2)==2),1);
     scatter(ax,p.t(selected),v(:,1),12,colors,'filled');ylabel(ax,'RTP sequence');
    else
     plot(ax,p.t(selected),p.y(selected,:),'LineWidth',1.2);
     if ~isempty(p.labels),legend(ax,p.labels,'Interpreter','none','Location','best');end
    end
    if isfield(p,'secondary') && ~isempty(p.secondary)
     v=p.secondary;sel=v(:,1)<=app.Time & v(:,1)>=max(0,app.Time-10);
     yyaxis(ax,'right');stairs(ax,v(sel,1),v(sel,2),'--');ylabel(ax,'Waiting frames');yyaxis(ax,'left');
    end
   end
  end
  drawnow limitrate;
 end
 function delete(app)
  if ~isempty(app.Clock) && isvalid(app.Clock),stop(app.Clock);delete(app.Clock);end
  if ~isempty(app.UIFigure) && isvalid(app.UIFigure),delete(app.UIFigure);end
 end
end
end
function r=structEmpty()
c=course.defaults('CN');r=struct('config',c,'backend','no log loaded',...
 'Inference',struct('log',zeros(0,7),'aux',zeros(0,4)),'Netem',struct('log',zeros(0,7)),...
 'Receiver',struct('log',zeros(0,7),'aux',zeros(0,8),'frames',zeros(0,6)),...
 'Camera',struct('log',zeros(0,5)));
end
