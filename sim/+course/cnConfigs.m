function configs=cnConfigs()
% Transcribed measured conditions. No fit to measured output metrics.
b=course.defaults('CN'); configs=b; configs.name='eth_q75_640x480_15fps';
names={'ge5_b4','loss0','loss1','loss10','loss5'};
ps=[.05 0 .01 .10 .05]; np=[5.121 5.607 5.096 5.107 5.106];
for i=1:numel(names)
 c=b;c.name=names{i};c.loss=ps(i);c.meanPackets=np(i);c.depth=.100;
 if i==1,c.lossMode='ge';end
 configs(end+1)=c; %#ok<AGROW>
end
for j=[20 5]
 for d=[100 20 200 50]
  c=b;c.name=sprintf('d20j%d%s_D%d',j,ternary(j==20,'n',''),d);
  c.delay=.020;c.jitter=j/1000;c.depth=d/1000;c.meanPackets=5;
  if j==5,c.distribution='uniform';end
  configs(end+1)=c; %#ok<AGROW>
 end
end
names={'payload1200_loss2','payload1400_loss2','payload3000_frag_loss2','payload500_loss2','q30','q60','q90'};
payload=[1200 1400 3000 500 1200 1200 1200];
np=[5.232 5.002 2.318 12.307 5.003 5.024 9.211];
bytes=[6071 5945.1 5860.9 6131.2 5650.4 5777.2 10537.4];
for i=1:numel(names)
 c=b;c.name=names{i};c.payload=payload(i);c.meanPackets=np(i);c.meanBytes=bytes(i);
 if i<=4,c.loss=.02;end
 configs(end+1)=c; %#ok<AGROW>
end
c=b;c.name='wifi_D50';c.delay=.035;c.jitter=.020;c.meanPackets=5.1;
configs(end+1)=c; % ASSUMED Wi-Fi delay law; descriptive sensitivity only.
for policy={'fifo','latest'}
 c=b;c.name=['T7_' policy{1}];c.policy=policy{1};c.fps=30;
 c.samples=.05;c.depth=.100;configs(end+1)=c; %#ok<AGROW>
end
for p=[0 .05]
 c=b;c.meanPackets=5.1;c.loss=p;
 if p==0,c.name='noloss_D50';else,c.name='loss5_D50';end
 configs(end+1)=c; %#ok<AGROW>
end
for abr=[false true]
 c=b;c.name=['T8_' ternary(abr,'AIMD','fixed')];c.adaptive=abr;
 c.lossSteps=[0 0;15 .15;35 0];configs(end+1)=c; %#ok<AGROW>
end
end
function s=ternary(q,a,b)
if q,s=a;else,s=b;end
end
