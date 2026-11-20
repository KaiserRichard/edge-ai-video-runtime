function files=export_cn_simevents_v2()
% Export the top level, every subsystem (including Simulink Function blocks)
% and the AIMD chart of CN_simevents_v2 to study_simevents_v2/figures.
root=fileparts(fileparts(mfilename('fullpath')));
figures=fullfile(root,'study_simevents_v2','figures');
if ~isfolder(figures),mkdir(figures);end
model='CN_simevents_v2';
if ~bdIsLoaded(model),load_system(fullfile(root,'generated',[model '.slx']));end
subsystems=find_system(model,'LookUnderMasks','none','BlockType','SubSystem');
subsystems=setdiff(subsystems,{[model '/AIMD']},'stable');
% MATLAB Function blocks are SubSystems too; the parent Simulink Function figure shows them.
subsystems=subsystems(~strcmp(get_param(subsystems,'SFBlockType'),'MATLAB Function'));
systems=[{model};subsystems(:)];files={};
for k=1:numel(systems)
 system=systems{k};
 name=regexprep(strrep(system,'/','__'),'[^\w]+','_');
 filename=fullfile(figures,[name '.png']);
 set_param(system,'PaperOrientation','landscape','PaperType','A3','ZoomFactor','FitSystem');
 print(['-s' system],'-dpng','-r170',filename);
 cropDiagram(filename);files{end+1}=filename; %#ok<AGROW>
end
chart=fullfile(figures,'CN_simevents_v2__AIMD.png');
sfprint([model '/AIMD'],'png',chart);cropDiagram(chart);files{end+1}=chart;
end

function cropDiagram(filename)
[pixels,map,alpha]=imread(filename);
if ~isempty(map),pixels=uint8(round(255*ind2rgb(pixels,map)));end
if size(pixels,3)==1,pixels=repmat(pixels,1,1,3);end
if ~isempty(alpha)
 weight=double(alpha)/double(intmax(class(alpha)));
 pixels=uint8(double(pixels).*weight+255*(1-weight));
end
ink=any(pixels<248,3);rows=find(any(ink,2));columns=find(any(ink,1));
assert(~isempty(rows) && ~isempty(columns),'CNSE2:Figure','Empty diagram export.');
y=max(1,rows(1)-30):min(size(pixels,1),rows(end)+30);
x=max(1,columns(1)-30):min(size(pixels,2),columns(end)+30);
imwrite(pixels(y,x,:),filename);
end
