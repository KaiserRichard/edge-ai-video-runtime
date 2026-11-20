function cnse_layout(m)
% Arrange the media, RTCP and signal paths after grouping the native blocks.
media={'Frames','Sender Queue','RTP Packetizer','Serialization','Channel','Receiver','Inference'};
source='[0.82, 0.91, 0.97]';
link='[0.83, 0.94, 0.95]';
sink='[0.88, 0.95, 0.85]';
feedback='[0.99, 0.94, 0.81]';
colors={source,source,source,link,link,sink,sink};
for k=1:numel(media)
    x=65+(k-1)*193;
    block=[m '/' media{k}];
    set_param(block,'Position',[x 95 x+141 163], ...
        'BackgroundColor',colors{k},'ContentPreviewEnabled','off','ShowPortLabels','none');
end
set_param([m '/Receiver'],'ShowPortLabels','FromPortBlockName');
set_param([m '/RTCP Reverse Path'],'Position',[805 230 1060 290], ...
    'Orientation','left','BackgroundColor',feedback, ...
    'ContentPreviewEnabled','off','ShowPortLabels','none');
set_param([m '/Feedback tick'],'Position',[280 218 342 256],'Orientation','left');
set_param([m '/Observations'],'Position',[455 355 605 420]);
set_param([m '/AIMD'],'Position',[700 337 823 403],'BackgroundColor',feedback, ...
    'ContentPreviewEnabled','off');
set_param([m '/Adaptive enabled'],'Position',[459 468 605 495]);
set_param([m '/Scope signals'],'Position',[935 421 940 522]);
set_param([m '/Dashboard'],'Position',[1190 420 1290 523]);
set_param([m '/Dashboard trace'],'Position',[1160 561 1300 596]);

layout('Frames',{
    'Frame clock',[45 45 128 102]
    'AIMD size scale',[45 128 75 150]
    'Size new frame',[217 49 350 115]
    'Out1',[435 71 465 93]});
layout('Sender Queue',{
    'In1',[35 77 65 99]
    'Sender admission',[136 61 176 115]
    'Frame FIFO or latest',[250 61 335 115]
    'Sender processing',[417 61 502 115]
    'Out1',[565 77 595 99]
    'Sender overflow',[251 172 332 215]});
layout('RTP Packetizer',{
    'In1',[35 70 65 92]
    'RTP fragment fanout',[152 49 283 112]
    'Out1',[372 70 402 92]});
layout('Serialization',{
    'In1',[35 77 65 99]
    'Packet FIFO',[145 60 218 116]
    'Bits divided by link bitrate',[333 60 430 116]
    'Out1',[530 77 560 99]});
layout('Channel',{
    'In1',[35 123 65 145]
    'Seeded delay and loss draw',[135 103 265 165]
    'Loss route',[345 104 408 164]
    'Guaranteed delay (s)',[487 32 585 61]
    'Entity Transport Delay',[520 102 614 166]
    'Per-packet delay remainder',[724 103 828 165]
    'Netem drops',[503 230 583 278]
    'Out1',[903 123 933 145]});
set_param([m '/Channel/Entity Transport Delay'],'ShowName','on');
layout('Receiver',{
    'In1',[39 57 69 79]
    'RR clock',[40 125 118 174]
    'Reorder reassemble and deadline',[230 44 404 124]
    'Out1',[520 55 550 77]
    'Out2',[520 95 550 117]});
set_param([m '/Receiver/In1'],'Name','RTP');
set_param([m '/Receiver/Out1'],'Name','Playout');
set_param([m '/Receiver/Out2'],'Name','RTCP RR');
layout('Inference',{
    'In1',[35 77 65 99]
    'AI admission',[137 61 177 115]
    'AI waiting frames',[255 61 335 115]
    'Inference service',[413 61 493 115]
    'AI result',[578 61 658 115]
    'AI overflow',[254 175 335 224]});
reverse=[m '/RTCP Reverse Path/'];
for name={'In1','Reverse loss','Reverse propagation','RR at sender','RR drops','Out1'}
    set_param([reverse name{1}],'Orientation','left');
end
layout('RTCP Reverse Path',{
    'In1',[620 110 650 132]
    'Reverse loss',[501 89 565 149]
    'Reverse propagation',[329 89 421 149]
    'RR at sender',[153 89 242 149]
    'RR drops',[331 206 420 257]
    'Out1',[35 56 65 78]});
set_param([reverse 'In1'],'Name','From receiver');
set_param([reverse 'Out1'],'Name','Delivered RR count');
heading=Simulink.Annotation(m,'RTP media moves right. RTCP reports return below the receiver.');
heading.Position=[342 49];
details=Simulink.Annotation(m,'Receiver reports sampled at 1 kHz');
details.Position=[698 291];

reroute(m);
set_param(m,'ZoomFactor','FitSystem');

    function layout(system,blocks)
        sys=[m '/' system];
        for i=1:size(blocks,1)
            set_param([sys '/' blocks{i,1}],'Position',blocks{i,2});
        end
        reroute(sys);
    end
end

function reroute(system)
lines=find_system(system,'FindAll','on','SearchDepth',1,'Type','line');
Simulink.BlockDiagram.routeLine(lines);
end
