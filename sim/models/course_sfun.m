function course_sfun(block)
% Normal-mode Level-2 adapter; no code generation, acceleration or SimEvents.
block.NumDialogPrms=2;
block.DialogPrmsTunable={'Nontunable','Nontunable'};
kind=block.DialogPrm(1).Data;c=block.DialogPrm(2).Data;
[ins,outs]=course.Node.ports(kind,c);
block.NumInputPorts=numel(ins);block.NumOutputPorts=numel(outs);
block.SetPreCompInpPortInfoToDynamic;block.SetPreCompOutPortInfoToDynamic;
for k=1:numel(ins)
 block.InputPort(k).Dimensions=ins(k);block.InputPort(k).DatatypeID=0;
 block.InputPort(k).Complexity='Real';block.InputPort(k).DirectFeedthrough=true;
end
for k=1:numel(outs)
 block.OutputPort(k).Dimensions=outs(k);block.OutputPort(k).DatatypeID=0;
 block.OutputPort(k).Complexity='Real';
end
block.SampleTimes=[c.dt 0];block.SimStateCompliance='DisallowSimState';
block.RegBlockMethod('Start',@start);
block.RegBlockMethod('Outputs',@outputs);
end
function start(block)
n=course.Node(block.DialogPrm(1).Data,block.DialogPrm(2).Data);
set_param(block.BlockHandle,'UserData',n,'UserDataPersistent','off');
end
function outputs(block)
n=get_param(block.BlockHandle,'UserData');u=cell(1,block.NumInputPorts);
for k=1:numel(u),u{k}=block.InputPort(k).Data;end
y=n.step(block.CurrentTime,u{:});
for k=1:numel(y),block.OutputPort(k).Data=y{k};end
end
