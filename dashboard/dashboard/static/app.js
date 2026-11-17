/* uPlot 1.6.31. All displayed time series use hub-relative seconds. */
"use strict";
const $ = id => document.getElementById(id);
let colors = [];
let palette = {};
function readPalette() {
  const css=getComputedStyle(document.body);
  palette=Object.fromEntries(["cyan","amber","purple","green","red","blue","pink","olive","grid","dim","muted","text"].map(key=>[key,css.getPropertyValue("--"+key).trim()]));
  colors=["cyan","amber","purple","green","red","blue","pink","olive"].map(key=>palette[key]);
}
let profile = "cn", mode = "", now = 0, paused = false, connected = false, status = "", stats = {}, lastId = 0;
const charts = new Map();
function empty() { return {session:null, sources:new Set(), current:{}, samples:[], queue_samples:[], aoi_samples:[], packets:new Map(), frames:[], total:0, ontime:0, rtcp:[], latency:[], states:[], faults:[], decisions:[], hist:[], lastDecision:null, lastSample:-1, video:null, lastT:0}; }
const models = {cn:empty(), os:empty()};
function text(id, value) { $(id).textContent = value; }
function fmt(value, digits=1, unit="") { return Number.isFinite(value) ? value.toFixed(digits) + unit : "—"; }
function current(m, type, at=now, ttl=3) { const item=m.current[type]; return item && at-item.t<=ttl ? item.data : {}; }
function addBounded(list, item, limit) { list.push(item); if(list.length>limit) list.splice(0,list.length-limit); }

function ingest(e) {
  if (!models[e.profile] || !Number.isFinite(e.t) || e.id<=lastId) return;
  lastId=e.id;
  let m=models[e.profile];
  if(m.session!==e.session) { models[e.profile]=m=empty(); m.session=e.session; }
  m.lastT=e.t;
  m.sources.add(e.source);
  const d=e.data;
  m.current[e.type]=e;
  if(e.type==="packet") {
    if(d.gap_start!==null && d.gap_start!==undefined) {
      // Bound work after discontinuities. The loss count still retains the full gap.
      for(let seq=Math.max(d.gap_start,d.gap_end-511);seq<=d.gap_end;seq++) m.packets.set(seq,{t:e.t,status:"missing",seq});
    }
    if(d.packet_status!=="duplicate") {
      const previous=m.packets.get(d.extended_seq);
      m.packets.set(d.extended_seq,{t:previous?.t??e.t,status:d.packet_status,seq:d.extended_seq});
    }
    for(const [key,packet] of m.packets) { if(packet.t<e.t-10 || m.packets.size>6000) m.packets.delete(key); else break; }
  }
  if(e.type==="frame") { addBounded(m.frames,{t:e.t,...d},3000); m.total++; if(d.status==="ok") m.ontime++; }
  if(e.type==="rtcp") addBounded(m.rtcp,{t:e.t,source:e.source,...d},300);
  if(e.type==="result") addBounded(m.latency,{t:e.t,...d},1000);
  if(e.type==="queue") addBounded(m.queue_samples,{t:e.t,fifo:d.fifo_age_ms,latest:d.latest_age_ms,fifo_queue:d.fifo_queue,latest_queue:d.latest_queue},4800);
  if(e.type==="sender" && d.step!==undefined && d.step!==m.lastDecision) {
    if(m.lastDecision!==null) addBounded(m.decisions,{t:e.t,arrow:d.step>m.lastDecision?"↓":"↑",step:d.step,quality:d.quality},100);
    m.lastDecision=d.step;
  }
  if(e.type==="os") {
    if(d.fifo_age_ms!==undefined || d.latest_age_ms!==undefined) addBounded(m.aoi_samples,{t:e.t,fifo:d.fifo_age_ms??null,latest:d.latest_age_ms??null},4800);
    if(m.states.at(-1)?.state!==d.state) addBounded(m.states,{t:e.t,state:d.state},500);
    if(d.fault) addBounded(m.faults,{t:e.t,fault:d.fault},50);
    if(d.inference_ms!==undefined && d.condition) addBounded(m.hist,{t:e.t,value:d.inference_ms,condition:d.condition},500);
  }
  if(e.type==="video") {
    // Only JPEG data URLs constructed here; no arbitrary URL or HTML telemetry.
    if(/^[A-Za-z0-9+/]+={0,2}$/.test(d.jpeg_b64)) m.video={t:e.t,...d};
  }
  if(e.t-m.lastSample>=.099) sample(m,e.t);
}

function sample(m,t) {
  m.lastSample=t;
  const p=current(m,"packet",t), f=current(m,"frame",t), s=current(m,"sender",t), q=current(m,"queue",t), o=current(m,"os",t), h=current(m,"hardware",t);
  const frames=m.frames.filter(f=>f.t>=t-5 && f.t<=t);
  const ratio=frames.length ? 100*frames.filter(f=>f.status==="ok").length/frames.length : null;
  const row={t,packet_j:p.jitter_ms??null,frame_j:p.frame_jitter_ms??null,netem_j:h.netem_jitter_ms??s.netem_jitter_ms??null,
    occupancy:f.buffer_frames??null,arrival:f.arrival_offset_ms??null,zero:0,hit:ratio,cumulative:m.total?100*m.ontime/m.total:null,
    bitrate:s.bitrate_mbps??null,quality:s.quality??null,step:s.step??null,
    fifo:q.fifo_age_ms??o.fifo_age_ms??null,latest:q.latest_age_ms??o.latest_age_ms??null,
    fifo_queue:q.fifo_queue??null,latest_queue:q.latest_queue??null};
  (h.cpu_cores||[]).forEach((value,i)=>row["core"+i]=value);
  addBounded(m.samples,row,1200);
}

const definitions = {
  jitter:{profile:"cn",keys:["packet_j","frame_j","netem_j"],labels:["Packet J","Frame J","Netem"],dash:[2]},
  playout:{profile:"cn",keys:["arrival","zero","occupancy"],labels:["Arrival − deadline","Deadline","Frames waiting"],dots:[0],right:[2]},
  deadline:{profile:"cn",keys:["hit","cumulative"],labels:["5 s rolling","Cumulative"],range:[0,100]},
  latency:{profile:"cn",event:"latency",keys:["latency_ms"],labels:["Capture → result"],dots:[0]},
  bitrate:{profile:"cn",keys:["bitrate","quality","step"],labels:["Mb/s","Quality","Step"],right:[1,2]},
  queues:{profile:"cn",event:"queue_samples",keys:["fifo","latest","fifo_queue","latest_queue"],labels:["FIFO age","Latest age","FIFO queue","Latest queue"],right:[2,3]},
  aoi:{profile:"os",event:"aoi_samples",keys:["fifo","latest"],labels:["Input FIFO","Input latest-value"]},
  cpu:{profile:"os",keys:["core0","core1","core2","core3"],labels:["Core 0","Core 1","Core 2","Core 3"],range:[0,100]},
  histogram:{profile:"os",hist:true,keys:["idle-P0","stress-P0","idle-P1","stress-P1"],labels:["Idle P0","Stress P0","Idle P1","Stress P1"]}
};

function ensureChart(id,def) {
  const node=$(id);
  if(node.offsetWidth===0) return null;
  if(charts.has(id)) return charts.get(id);
  const axis={stroke:palette.muted,font:"10px Consolas, monospace",grid:{stroke:palette.grid,width:1},ticks:{stroke:palette.grid,width:1},size:38};
  const series=[{label:def.hist?"Latency":"Hub time",value:(_,v)=>fmt(v,1," s")},...def.labels.map((label,i)=>({label,stroke:colors[i%colors.length],width:1.6,
    scale:def.right?.includes(i)?"right":"y",dash:def.dash?.includes(i)?[5,4]:[],
    ...(def.dots?.includes(i)?{paths:()=>null}:{}),
    points:{show:!!def.dots?.includes(i),size:4,fill:colors[i%colors.length]},
    ...(def.hist&&window.uPlot?{paths:uPlot.paths.bars({size:[.8,40]}),fill:colors[i%colors.length]+"55"}:{})}))];
  const options={width:node.clientWidth,height:node.clientHeight,series,hist:!!def.hist,
    cursor:{...(!def.hist?{sync:{key:"hub-time"}}:{}),drag:{x:false,y:false}},
    legend:{live:false},scales:{x:{time:false},y:{auto:true,...(def.range?{range:()=>def.range}:{})},right:{auto:true}},
    axes:[{...axis,size:25,values:(_,ticks)=>ticks.map(x=>fmt(x,0,def.hist?"":"s"))},axis,...(def.right?[{...axis,scale:"right",side:1,size:30}]:[])]};
  const chart=window.EdgePanels.create(options,[[],...def.keys.map(()=>[])],node);
  charts.set(id,chart);
  chart.resizeObserver=new ResizeObserver(()=>{if(node.clientWidth) chart.setSize({width:node.clientWidth,height:node.clientHeight});});
  chart.resizeObserver.observe(node);
  return chart;
}

function renderCharts(t) {
  if(profile==="os") {
    const cores=current(models.os,"hardware",t).cpu_cores;
    if(cores && definitions.cpu.keys.length!==cores.length) {
      definitions.cpu.keys=cores.map((_,i)=>"core"+i);definitions.cpu.labels=cores.map((_,i)=>"Core "+i);
      if(charts.has("cpu")){charts.get("cpu").resizeObserver.disconnect();charts.get("cpu").destroy();charts.delete("cpu");}
    }
  }
  for(const [id,def] of Object.entries(definitions)) {
    if(def.profile!==profile) continue;
    const chart=ensureChart(id,def); if(!chart) continue;
    const m=models[def.profile];
    let data;
    if(def.hist) {
      const largest=Math.max(100,...m.hist.map(x=>x.value)), width=Math.max(5,Math.ceil(largest/20/5)*5);
      const centers=Array.from({length:20},(_,i)=>(i+.5)*width);
      data=[centers,...def.keys.map(key=>{
        if(!m.hist.some(x=>x.condition===key)) return centers.map(()=>null);
        const counts=centers.map(()=>0);
        m.hist.filter(x=>x.condition===key).forEach(x=>counts[Math.min(19,Math.floor(x.value/width))]++);
        return counts;
      })];
      chart.setData(data);
    } else {
      const rows=(def.event?m[def.event]:m.samples).filter(r=>r.t>=t-120);
      const rows2=rows.length===1?[{t:rows[0].t-.001},...rows]:rows;
      data=[rows2.map(r=>r.t),...def.keys.map(key=>rows2.map(r=>r[key]??null))];
      chart.setData(data);
      chart.setScale("x",{min:Math.max(0,t-120),max:Math.max(10,t)});
    }
  }
}

function canvasContext(id) {
  const canvas=$(id), rect=canvas.getBoundingClientRect(), dpr=window.devicePixelRatio||1;
  if(!rect.width) return null;
  canvas.width=Math.round(rect.width*dpr);canvas.height=Math.round(rect.height*dpr);
  const ctx=canvas.getContext("2d");ctx.scale(dpr,dpr);ctx.font="10px Consolas, monospace";
  return {canvas,ctx,w:rect.width,h:rect.height};
}
function timeAxis(ctx,w,h,t,window) {
  const low=window===10?t-10:Math.max(0,t-window), high=window===10?t:Math.max(10,t);
  ctx.strokeStyle=palette.grid;ctx.fillStyle=palette.dim;
  for(let i=0;i<=5;i++) { const x=36+(w-50)*i/5; ctx.beginPath();ctx.moveTo(x,10);ctx.lineTo(x,h-22);ctx.stroke();ctx.fillText(fmt(low+(high-low)*i/5,0,"s"),Math.max(0,x-12),h-5); }
  return time=>36+(time-low)/(high-low)*(w-50);
}
function renderPackets(t) {
  const info=canvasContext("packets");if(!info)return;
  const {ctx,w,h}=info, packets=[...models.cn.packets.values()].filter(p=>p.t>=t-10);
  timeAxis(ctx,w,h,t,10);
  const position=new Map();
  for(const packet of packets) {
    const x=36+(packet.t-t+10)/10*(w-50), col=Math.round(x), lane=(position.get(col)||0)%10;
    position.set(col,(position.get(col)||0)+1);
    ctx.strokeStyle=packet.status==="missing"?palette.red:packet.status==="reordered"?palette.amber:palette.dim;
    ctx.beginPath();ctx.moveTo(x,14+lane*(h-45)/10);ctx.lineTo(x,21+lane*(h-45)/10);ctx.stroke();
  }
  text("packet-count",`${packets.length} sequence ticks`);
}
let rtcpHitboxes=[];
function renderRTCP(t) {
  const info=canvasContext("rtcp");if(!info)return;
  const {ctx,w,h}=info, xAt=timeAxis(ctx,w,h,t,120);rtcpHitboxes=[];
  const kinds=["SR","RR","APP"];
  kinds.forEach((kind,i)=>{ctx.fillStyle=colors[i];ctx.fillText(kind,0,25+i*34);});
  for(const e of models.cn.rtcp.filter(e=>e.t>=t-120 && kinds.includes(e.kind))) {
    const index=kinds.indexOf(e.kind),x=xAt(e.t),y=22+index*34;
    ctx.fillStyle=colors[index];ctx.beginPath();ctx.arc(x,y,3.5,0,Math.PI*2);ctx.fill();rtcpHitboxes.push({x,y,e});
  }
}
$("rtcp").addEventListener("mousemove",ev=>{
  const r=$("rtcp").getBoundingClientRect(),hit=rtcpHitboxes.find(h=>Math.abs(h.x-(ev.clientX-r.left))<7 && Math.abs(h.y-(ev.clientY-r.top))<10);
  if(hit) { const e=hit.e;text("rtcp-detail",`${e.source} ${e.kind} ${e.direction} @ ${fmt(e.t,2)}s · loss ${fmt(e.fraction_lost/256*100,2,"%")} · J ${fmt(e.jitter_ms)} ms · RTT ${fmt(e.rtt_ms)} ms`); }
});

function renderStates(t) {
  const info=canvasContext("states");if(!info)return;
  const {ctx,w,h}=info, xAt=timeAxis(ctx,w,h,t,120);
  const states=models.os.states, tones={FRESH:palette.green,HOLD:palette.amber,FAILSAFE:palette.red};
  for(let i=0;i<states.length;i++) {
    const e=states[i],end=states[i+1]?.t??Math.min(t,models.os.lastT+3);
    if(end<t-120)continue;
    const x=xAt(Math.max(e.t,t-120)),right=xAt(end);
    ctx.fillStyle=tones[e.state];ctx.globalAlpha=.3;ctx.fillRect(x,22,Math.max(1,right-x),42);ctx.globalAlpha=1;
    if(right-x>55){ctx.fillStyle=tones[e.state];ctx.fillText(e.state,x+4,47);}
  }
  for(const e of models.os.faults.filter(x=>x.t>=t-120)) {const x=xAt(e.t);ctx.strokeStyle=palette.text;ctx.setLineDash([3,3]);ctx.beginPath();ctx.moveTo(x,12);ctx.lineTo(x,78);ctx.stroke();ctx.setLineDash([]);}
}

function hardware(prefix,m,t) {
  const h=current(m,"hardware",t),flag=h.throttled;
  text(prefix+"-temp",fmt(h.temperature_c,1," °C"));text(prefix+"-throttle",Number.isInteger(flag)?"0x"+flag.toString(16):"—");text(prefix+"-cpu",fmt(h.cpu_pct,0,"%"));
  const badge=$(prefix==="cn"?"hw-valid":"os-valid");
  badge.textContent=flag===undefined?"UNKNOWN / STALE":flag===0?"NO THROTTLE FLAGS":"THROTTLE FLAGS";
  badge.className="badge "+(flag===undefined?"warn":flag===0?"good":"bad");
  if(prefix==="cn") {text("cn-rssi",fmt(h.rssi_dbm,0," dBm"));text("cn-tx",fmt(h.tx_mbps,0," Mb/s"));text("netem",h.netem??current(m,"sender",t).netem??"No status received");}
}

function renderVideo(t) {
  const m=models.cn,ai=current(m,"ai",t),frame=current(m,"frame",t),video=m.video;
  text("ai-label",ai.label??(ai.class_id!==undefined?`ImageNet class ${ai.class_id}`:"No recent AI result"));text("confidence",fmt(ai.confidence*100,1,"%"));
  const stale=video && t-video.t>2;
  $("video-wrap").classList.toggle("damaged",frame.status!==undefined && frame.status!=="ok" || !!stale);
  text("frame-state",frame.status?.toUpperCase()??"NO FRAME");
  $("frame-state").className="badge "+(frame.status==="ok"?"good":frame.status?"bad":"");
  $("test-card").hidden=mode!=="synthetic";$("video").hidden=mode==="synthetic" || !video;$("no-video").hidden=mode==="synthetic" || !!video;
  if(mode==="synthetic") {
    const canvas=$("test-card"),ctx=canvas.getContext("2d");ctx.fillStyle="#0b1723";ctx.fillRect(0,0,640,300);
    ctx.strokeStyle="#294458";for(let i=0;i<640;i+=40){ctx.beginPath();ctx.moveTo(i,0);ctx.lineTo(i,300);ctx.stroke();}for(let i=0;i<300;i+=40){ctx.beginPath();ctx.moveTo(0,i);ctx.lineTo(640,i);ctx.stroke();}
    const x=120+(Math.sin(t*.6)+1)*170;ctx.strokeStyle="#5ad6e5";ctx.lineWidth=2;ctx.strokeRect(x,65,130,125);ctx.fillStyle="#5ad6e5";ctx.font="16px Consolas";ctx.fillText("SYNTHETIC TEST CARD",24,30);ctx.font="13px Consolas";ctx.fillText("Illustrative label · no camera / model attached",24,272);ctx.fillStyle="#7fe0ad";ctx.fillText("target 281",x,212);
    text("video-age","SYNTHETIC");
  } else if(video) {
    if($("video").dataset.frame!==String(video.t)) {$("video").src="data:image/jpeg;base64,"+video.jpeg_b64;$("video").dataset.frame=String(video.t);}
    text("video-age",stale?`STALE · ${fmt(t-video.t)} s`:"JPEG PREVIEW");
  } else text("video-age","");
}

function renderTiles(t) {
  const m=models[profile];
  if(profile==="cn") {
    const p=current(m,"packet",t),h=current(m,"hardware",t),s=current(m,"sender",t),f=current(m,"frame",t),q=current(m,"queue",t);
    // Last RR with a report block; empty compound RR wrappers cannot erase it.
    const rr=m.rtcp.filter(x=>x.kind==="RR" && x.fraction_lost!==undefined && t-x.t<5).at(-1);
    text("kernel",fmt(h.kernel_drops,0));text("seq-loss",fmt(p.sequence_lost,0));text("rr-loss",fmt(rr?rr.fraction_lost/256*100:undefined,2,"%"));
    text("occupancy",`BUFFER ${fmt(f.buffer_frames,0)} frames`);
    const frames=m.frames.filter(frame=>frame.t>=t-5 && frame.t<=t);
    text("hit",fmt(frames.length?100*frames.filter(frame=>frame.status==="ok").length/frames.length:undefined,1,"%"));text("hit-total",`Cumulative ${fmt(m.total?100*m.ontime/m.total:undefined,1,"%")}`);
    text("quality",`Q ${fmt(s.quality,0)} · FPS ${fmt(s.fps,0)} · STEP ${fmt(s.step,0)}`);
    text("queue-lengths",`QUEUES ${fmt(q.fifo_queue,0)} / ${fmt(q.latest_queue,0)}`);
    text("decisions",m.decisions.slice(-5).map(x=>`${x.arrow} ${fmt(x.t,1)}s Q${x.quality??"—"}`).join(" · ")||"No controller step observed");
    const result=m.latency.at(-1),keys=["capture_send_ms","network_playout_ms","queue_ms","inference_ms"];
    const stack=$("latency-stack");stack.replaceChildren();
    if(result && keys.every(k=>Number.isFinite(result[k]))) {
      const labels=["Capture→send","Network + playout + return","Queue","Inference"];
      keys.forEach((key,i)=>{const div=document.createElement("div");div.style.width=100*result[key]/Math.max(.001,result.latency_ms)+"%";div.style.background=colors[i];div.title=`${labels[i]}: ${fmt(result[key],2)} ms`;stack.append(div);});
      text("latency-detail",keys.map((key,i)=>`${labels[i]} ${fmt(result[key],1)} ms`).join(" / "));
    } else {const span=document.createElement("span");span.textContent="No complete breakdown in telemetry";stack.append(span);}
    hardware("cn",m,t);renderVideo(t);
  } else {
    const o=current(m,"os",t);text("led-state",o.state??"UNKNOWN / STALE");
    for(const state of ["fresh","hold","failsafe"]) $("led-"+state).classList.toggle("active",o.state===state.toUpperCase());
    $("led-link").classList.toggle("active",o.link_active===true);
    text("faults",m.faults.slice(-4).map(e=>`${fmt(e.t,1)}s · ${e.fault}`).join(" / ")||"No fault marker received");hardware("os",m,t);
  }
}

function quantile(values, fraction) {
  const sorted=values.filter(Number.isFinite).sort((a,b)=>a-b);
  return sorted.length?sorted[Math.max(0,Math.ceil(sorted.length*fraction)-1)]:undefined;
}
function kpi(id,value,digits,unit) {
  const node=$(id);node.replaceChildren(document.createTextNode(fmt(value,digits)));
  if(Number.isFinite(value)) {const small=document.createElement("small");small.textContent=unit;node.append(small);}
}
function renderSummary(t) {
  const m=models[profile],p=current(m,"packet",t),q=current(m,"queue",t),o=current(m,"os",t);
  const frames=m.frames.filter(f=>f.t>=t-5 && f.t<=t);
  kpi("kpi-loss",p.sequence_loss_pct,2,"%");
  kpi("kpi-jitter",p.jitter_ms,2,"ms");
  kpi("kpi-ontime",frames.length?100*frames.filter(f=>f.status==="ok").length/frames.length:undefined,1,"%");
  const durations=profile==="cn"?m.latency.filter(r=>r.t>=t-120 && r.t<=t).map(r=>r.latency_ms):m.hist.filter(r=>r.t>=t-120 && r.t<=t).map(r=>r.value);
  const fresh=profile==="cn"?current(m,"result",t).latency_ms!==undefined:m.hist.some(r=>r.t>=t-3 && r.t<=t);
  kpi("kpi-p50",fresh?quantile(durations,.5):undefined,1,"ms");
  kpi("kpi-p95",fresh?quantile(durations,.95):undefined,1,"ms");
  for(const id of ["kpi-p50-note","kpi-p95-note"])text(id,profile==="cn"?"Capture → result · last 120 s":"Inference only · last 120 s");
  document.querySelectorAll(".kpi:nth-child(4) .kpi-label>span,.kpi:nth-child(5) .kpi-label>span").forEach(node=>node.textContent=profile==="cn"?"PI":"OS");
  let age=q.latest_age_ms??o.latest_age_ms;
  let ageNote="Latest-value result AoI";
  if(age===undefined && m.current.ai && t-m.current.ai.t<=3) {age=Math.max(0,t-m.current.ai.t)*1000;ageNote="Since AI event · hub receipt";}
  if(age===undefined) ageNote="No recent result-age telemetry";
  kpi("kpi-age",age,0,"ms");text("kpi-age-note",ageNote);
  text("session-id",m.session??"No active session for this profile");
  text("source-producers",[...m.sources].sort().join(" / ")||"None observed for this profile");
  if(mode==="synthetic") {
    text("source-title","SYNTHETIC DATA · NOT MEASURED");
    text("notice","Seeded simulation of the Pi → laptop pipeline. No camera, model or hardware measurement is attached.");
    text("source-evidence","Illustrative seeded generator. FIFO/latest use identical inputs and equal service time. These values do not validate hardware performance.");
  } else if(mode==="replay") {
    const sample=/^cn-loss5-\d+$/.test(m.session??""),osDemo=/^os-demo-\d+$/.test(m.session??"");
    text("source-title",osDemo?"CSV REPLAY · ILLUSTRATIVE SYNTHETIC EXPORT":sample?"CSV REPLAY · CN-LOSS5 HARDWARE EXCERPT":"CSV REPLAY · RECORDED INPUT");
    text("notice",osDemo?"The OS demo CSV is synthetic. It is not MCU or hardware evidence.":sample?"Included 5% loss run · first 8 seconds of original hardware CSVs. Playback is not a live hardware connection.":"Playback of supplied CSV observations. Original provenance must be checked separately; replay alone does not establish measured data.");
    text("source-evidence",sample?"Sample identity from session name: cn-loss5. Manifest: samples/cn-loss5/provenance.json. Contains original paths, selection rule and source/excerpt SHA-256 hashes. The browser does not independently verify these hashes.":osDemo?"samples/os-demo.csv: illustrative synthetic OS export, not measured MCU data.":"Supplied CSV replay. Session name and producers are shown above; no provenance manifest is transmitted by protocol v1.");
  } else if(mode==="live") {
    text("source-title","LIVE TELEMETRY · UDP INGESTION");
    text("notice","Producer-reported observations from the Pi / receiver. Check producer identity and instrument provenance before drawing conclusions.");
    text("source-evidence","Live UDP envelopes. The hub validates the schema; it does not authenticate producers or independently validate physical measurements.");
  }
}

let viewT=0;
function render(force=false) {
  if(paused&&!force)return;
  const t=paused?viewT:status==="replay complete"?Math.max(models.cn.lastT,models.os.lastT):now;
  viewT=t;
  if(models[profile].lastSample<t-.099 && status!=="replay complete") sample(models[profile],t);
  const seconds=Math.floor(t);
  text("clock",[Math.floor(seconds/3600),Math.floor(seconds/60)%60,seconds%60].map(v=>String(v).padStart(2,"0")).join(":"));
  $("clock").setAttribute("datetime",`PT${seconds}S`);$("clock").title="Elapsed hub display time";
  text("mode",mode?mode.toUpperCase():"—");text("source-status",paused?"View paused · ingestion continues":status);
  text("health",`${stats.accepted??0} events · ${stats.invalid??0} invalid · ${stats.client_drops??0} client drops`);
  renderSummary(t);renderTiles(t);renderCharts(t);
  if(profile==="cn"){renderPackets(t);renderRTCP(t);}else renderStates(t);
  document.body.dataset.profile=profile;document.body.dataset.mode=mode;document.body.dataset.events=String(stats.accepted??0);
}

$("profile").addEventListener("change",()=>{profile=$("profile").value;$("cn").hidden=profile!=="cn";$("os").hidden=profile!=="os";document.querySelector("h1").firstChild.textContent=profile==="cn"?"Network observability":"Runtime observability";document.querySelector("h1 span").textContent=profile==="cn"?" / RTP & RTCP":" / Operating Systems";text("overview-description",profile==="cn"?"From capture to inference. A clear view of the entire feedback loop.":"Supervision, scheduling and result freshness. Observe the runtime under load.");text("section-title",profile==="cn"?"TRANSPORT & INFERENCE":"SUPERVISOR & RUNTIME");render(true);});
$("pause").addEventListener("click",()=>{paused=!paused;$("pause").textContent=paused?"Resume view":"Pause view";$("pause").setAttribute("aria-pressed",String(paused));document.body.dataset.paused=String(paused);render(true);});

function setTheme(theme) {
  document.body.dataset.theme=theme;readPalette();
  text("theme-label",theme==="dark"?"Light":"Dark");$("theme").setAttribute("aria-label",theme==="dark"?"Switch to light theme":"Switch to dark theme");
  try{localStorage.setItem("edge-observatory-theme",theme);}catch(_){} // Storage can be disabled in a lab browser.
  for(const chart of charts.values()){chart.resizeObserver.disconnect();chart.destroy();}charts.clear();render(true);
  document.dispatchEvent(new Event("edge-theme"));
}
let savedTheme="dark";try{savedTheme=localStorage.getItem("edge-observatory-theme")==="light"?"light":"dark";}catch(_){}
setTheme(savedTheme);
$("theme").addEventListener("click",()=>setTheme(document.body.dataset.theme==="dark"?"light":"dark"));
function presentation(active) {
  document.body.classList.toggle("presentation",active);$("present").setAttribute("aria-pressed",String(active));text("present-label",active?"Exit present":"Present");
  requestAnimationFrame(()=>render(true));
}
$("present").addEventListener("click",async()=>{
  const active=!document.body.classList.contains("presentation");presentation(active);
  try{if(active && document.documentElement.requestFullscreen)await document.documentElement.requestFullscreen();else if(!active && document.fullscreenElement)await document.exitFullscreen();}catch(error){$("present").title="Presentation layout active; browser fullscreen unavailable";document.body.dataset.fullscreenError=error.message;}
});
document.addEventListener("fullscreenchange",()=>presentation(!!document.fullscreenElement));
document.addEventListener("keydown",event=>{if(event.key==="Escape" && document.body.classList.contains("presentation")){presentation(false);if(document.fullscreenElement)document.exitFullscreen().catch(()=>{});}});

function connect() {
  const socket=new WebSocket(`${location.protocol==="https:"?"wss":"ws"}://${location.host}/ws`);
  socket.onopen=()=>{connected=true;document.body.dataset.connected="true";text("connection","CONNECTED");$("connection").className="badge good";};
  socket.onmessage=ev=>{
    const msg=JSON.parse(ev.data);now=msg.t;stats=msg.stats||stats;status=msg.status||status;
    if(msg.type==="hello") {mode=msg.mode;lastId=0;models.cn=empty();models.os=empty();msg.history.sort((a,b)=>a.id-b.id).forEach(ingest);}
    else (msg.events||[]).forEach(ingest);
    render();
  };
  socket.onclose=()=>{connected=false;document.body.dataset.connected="false";text("connection","DISCONNECTED · RETRYING");$("connection").className="badge bad";setTimeout(connect,1500);};
  socket.onerror=()=>socket.close();
}
if(!window.uPlot) {$("chart-error").hidden=false;text("renderer","Local canvas · offline ready");}
connect();
const focusQuery=new URLSearchParams(location.search);
if(focusQuery.get("profile")==="os") {$("profile").value="os";$("profile").dispatchEvent(new Event("change"));}
const focusId=focusQuery.get("panel");
if(focusId&&$(focusId)) {
  const panel=$(focusId).closest(".panel");
  if(panel)panel.classList.add("focused-panel");
  if(focusQuery.get("view")==="live")setTimeout(()=>panel?.scrollIntoView({block:"start"}),300);
}
setInterval(()=>{if(!connected&&!paused){now+=.5;render();}},500);
