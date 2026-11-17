/* No build step. Read-only lesson/evidence UI and the dashboard's shared panels. */
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const query = values => new URLSearchParams(values).toString();
  const evidenceLink = ref => "/evidence?" + query({root:ref.root,path:ref.path});
  const rawLink = ref => "/api/evidence/raw?" + query(ref);
  const api = async path => {
    const response = await fetch(path);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || response.statusText);
    return data;
  };
  const failure = (node, error) => { node.innerHTML = `<p class="error-note">${esc(error.message)}</p>`; };
  const title = {
    "01":"RTP header & khoảng trống sequence", "02":"Jitter: từng bước theo gói",
    "03":"Đổi D, nhìn deadline", "04":"RR: hai cách đếm loss",
    "05":"Cùng netem, khác mất frame", "06":"AIMD & bitrate đo thật",
    "07":"FIFO / latest: kết quả còn tươi?", "08":"Service time dưới contention",
    "09":"Ước lượng tuổi thông tin", "10":"Còn sống ≠ còn tươi"
  };
  const caption = {
    "01":"Nhìn vào đây: khoảng trống sequence được phát lại từ CSV, timestamp và marker thuộc gói đang chọn.",
    "02":"Nhìn vào đây: mỗi gói chỉ kéo J đi 1/16 về phía |D|; số tính lại đối chiếu với log.",
    "03":"Nhìn vào đây: tăng D giữ được nhiều frame hoàn chỉnh hơn, nhưng cộng thêm đúng D ms vào deadline.",
    "04":"Nhìn vào đây: fraction-lost thay đổi theo khoảng RR; cumulative-lost tích luỹ theo phiên.",
    "05":"Nhìn vào đây: mất frame khác mất gói, và loss theo cụm khác loss độc lập.",
    "06":"Nhìn vào đây: quality giảm mạnh khi loss cao rồi tăng từng bước; timeline này là MÔ PHỎNG.",
    "07":"Nhìn vào đây: khi service chậm hơn đầu vào, FIFO giữ kết quả cũ còn latest bỏ frame chờ cũ.",
    "08":"Nhìn vào đây: phân phối service time dời sang phải dưới memory stress ở cả P0 và P1.",
    "09":"Nhìn vào đây: L + Y/2 là INFERRED; giao không đều và dùng P50 khiến số này khác AoI đo.",
    "10":"Nhìn vào đây: heartbeat quá hạn chốt FAILSAFE; chỉ rearm hợp lệ mới đưa máy về INIT."
  };
  const panelId = {"01":"packets","02":"jitter","03":"playout","04":"rtcp","05":"loss-rr","06":"bitrate","07":"queues","08":"histogram","09":"aoi","10":"states"};
  const formulas = {
    "01":["\\mathrm{timestamp\\ step}=\\frac{\\mathrm{clock\\ rate}}{\\mathrm{fps}}","Timestamp step = clock rate / fps"],
    "02":["J_i=J_{i-1}+\\frac{|D_i|-J_{i-1}}{16}","J mới = J cũ + (|D| − J cũ) / 16"],
    "03":["t_{\\mathrm{deadline}}=t_{\\mathrm{anchor}}+\\frac{\\Delta\\mathrm{RTP}}{90000}+D","Deadline = mốc arrival + thời gian media + D"],
    "04":["\\mathrm{loss\\ (\\%)}=100\\frac{\\mathrm{fraction\\_lost}}{256}","Loss (%) = 100 × fraction_lost / 256"],
    "05":["p_{\\mathrm{frame}}=1-(1-p_{\\mathrm{packet}})^n","INFERRED · mất frame = 1 − (1 − mất gói)^n; giả thiết độc lập"],
    "06":["q_{\\mathrm{next}}=\\max(q_{\\min},\\lfloor 0.7q\\rfloor)","MÔ PHỎNG · loss cao: quality mới = max(quality tối thiểu, floor(0.7 × quality))"],
    "07":["\\Delta(t)=t-u(t)","AoI = thời điểm hiện tại − thời điểm tạo kết quả đang giữ"],
    "08":["S= t_{\\mathrm{done}}-t_{\\mathrm{input}}","Service = t_done − t_input (gồm cả chờ đầu vào)"],
    "09":["\\overline{\\Delta}\\approx L+\\frac{Y}{2}","INFERRED · Mean AoI ≈ latency + interval / 2"],
    "10":["\\mathrm{source\\ age}=\\mathrm{now}-\\mathrm{last\\ receive}+\\mathrm{age\\ at\\ send}+\\mathrm{transit\\ bound}","Tuổi nguồn = now − lần nhận cuối + tuổi lúc gửi + dự trù truyền"]
  };
  let theme = "dark";
  try { theme = localStorage.getItem("edge-observatory-theme") || theme; } catch {}
  if ($("learning-theme")) document.body.dataset.theme = theme === "light" ? "light" : "dark";
  $("learning-theme")?.addEventListener("click", () => {
    document.body.dataset.theme = document.body.dataset.theme === "light" ? "dark" : "light";
    try { localStorage.setItem("edge-observatory-theme", document.body.dataset.theme); } catch {}
    document.dispatchEvent(new Event("edge-theme"));
  });
  $("learning-present")?.addEventListener("click", async () => {
    const active = document.body.classList.toggle("presentation");
    $("learning-present").setAttribute("aria-pressed", String(active));
    try {
      if (active) await document.documentElement.requestFullscreen?.();
      else if (document.fullscreenElement) await document.exitFullscreen();
    } catch {} // The presentation layout also works when fullscreen is unavailable.
  });
  document.addEventListener("fullscreenchange", () => {
    if (!document.fullscreenElement) {
      document.body.classList.remove("presentation");
      $("learning-present")?.setAttribute("aria-pressed", "false");
    }
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape") {
      document.body.classList.remove("presentation");
      $("learning-present")?.setAttribute("aria-pressed","false");
    }
  });
  document.querySelectorAll(".site-nav a").forEach(a => a.classList.toggle("active", a.dataset.page === (document.body.dataset.page || "dashboard")));
  const done = new Set();
  try {
    const saved = JSON.parse(localStorage.getItem("edge-lessons-done") || "[]");
    if (Array.isArray(saved)) saved.filter(id => /^\d{2}$/.test(id)).forEach(id => done.add(id));
  } catch {}
  const progress = () => {
    if ($("study-progress")) $("study-progress").textContent = `${done.size} / 10 bài đã học`;
  };
  document.querySelectorAll("[data-done]").forEach(input => {
    input.checked = done.has(input.dataset.done);
    input.addEventListener("change", () => {
      input.checked ? done.add(input.dataset.done) : done.delete(input.dataset.done);
      try { localStorage.setItem("edge-lessons-done",JSON.stringify([...done])); } catch {}
      progress();
    });
  });
  progress();
  const sidebar=document.querySelector(".lesson-sidebar");
  if(sidebar) {
    const toggle=document.createElement("button");toggle.className="mobile-lesson-menu";
    toggle.textContent="Danh sách bài học";toggle.setAttribute("aria-expanded","false");
    toggle.onclick=()=>{const expanded=sidebar.classList.toggle("expanded");toggle.setAttribute("aria-expanded",String(expanded));};
    sidebar.prepend(toggle);
  }
  if ($("toc")) document.querySelectorAll(".prose > h2").forEach(heading => {
    const a = document.createElement("a");
    a.href = "#"+heading.id; a.textContent = heading.textContent; $("toc").append(a);
  });
  window.EdgeMath = () => {
    if (!window.katex) return;
    document.querySelectorAll("[data-katex]").forEach(node => {
      katex.render(node.dataset.katex, node, {throwOnError:false,trust:false});
    });
  };
  window.EdgeMermaid = () => {
    if (window.mermaid && document.querySelector("pre.mermaid")) {
      mermaid.initialize({startOnLoad:false,securityLevel:"strict",theme:"neutral"});
      mermaid.run({querySelector:"pre.mermaid"}).catch(() => {});
    }
  };
  window.EdgeMath(); window.EdgeMermaid();

  function plot(host, spec, name) {
    const label = document.createElement("div");
    label.className = "widget-axis";
    label.innerHTML = `<span>${esc(name || spec.labels.join(" / "))}</span><span>X: ${esc(spec.xunit)} · Y: ${esc(spec.yunit)}</span>`;
    const node = document.createElement("div"); node.className = "widget-chart";
    node.setAttribute("role","img"); node.setAttribute("aria-label",`${name || spec.labels.join(", ")}; X ${spec.xunit}; Y ${spec.yunit}`);
    host.append(label,node);
    const controller = EdgePanels.plot(node,spec);
    return {setData(data) { controller.spec = {...controller.spec,x:data[0],ys:data.slice(1)}; controller.setData(data); }};
  }
  function sources(node, refs) {
    const details = document.createElement("details"); details.className = "widget-source";
    details.open = refs.length <= 3;
    details.innerHTML = `<summary>Nguồn · ${refs.length} tệp (đường dẫn thật)</summary>` + refs.map(ref => {
      const label = esc(ref.source || ref.path);
      return ref.root ? `<a href="${esc(evidenceLink(ref))}">${label} ↗</a>` : `<a href="${esc(ref.url || "#")}">${label}</a>`;
    }).join("");
    node.append(details);
  }
  function controls(node, markup) {
    const element = document.createElement("div"); element.className = "widget-controls"; element.innerHTML = markup; node.append(element); return element;
  }
  function output(node) {
    const element = document.createElement("div"); element.className = "widget-output"; element.setAttribute("aria-live","polite"); node.append(element); return element;
  }
  function note(node, text) {
    const p = document.createElement("p"); p.className = "widget-note"; p.textContent = text; node.append(p);
  }
  async function widget(node, key) {
    try {
      const data = await api("/api/widgets/"+key);
      node.innerHTML = `<div class="eyebrow">THỬ TRỰC TIẾP · BÀI ${key}</div><div class="widget-topline"><h2>${title[key]}</h2><span class="badge ${data.kind === "measured" ? "good" : "warn"}">${esc(data.badge)}</span></div><p class="widget-caption">${caption[key]}</p>`;
      const formula=document.createElement("figure");formula.className="formula-figure";
      formula.dataset.katex=formulas[key][0];formula.textContent=formulas[key][1];node.append(formula);
      node.dataset.kind = data.kind;
      if (data.missing) note(node,data.missing);
      if (data.kind !== "missing") {
        if (key === "01") rtp(node,data);
        else if (key === "02") jitter(node,data);
        else if (key === "03") playout(node,data);
        else if (key === "06") abr(node,data);
        else if (key === "07") queues(node,data);
        else if (key === "09") age(node,data);
        else if (key === "10") supervisor(node,data);
        else {
          data.charts.forEach(spec => plot(node,spec));
          if (data.categories) note(node,data.categories.map((label,i)=>`${i}: ${label}`).join(" · "));
          if (data.table) {
            const table = document.createElement("div"); table.className="table-scroll";
            table.innerHTML="<table><thead><tr>"+data.table[0].map(c=>`<th>${esc(c)}</th>`).join("")+"</tr></thead><tbody>"+data.table.slice(1).map(row=>"<tr>"+row.map(c=>`<td>${esc(c)}</td>`).join("")+"</tr>").join("")+"</tbody></table>";
            node.append(table);
          }
        }
      }
      if (data.note) note(node,data.note);
      sources(node,data.sources || []);
      const actions = document.createElement("div"); actions.className="widget-actions";
      actions.innerHTML = `<a class="button-link" href="/?${query({lesson:key,profile:Number(key)>=8?"os":"cn",panel:panelId[key],view:"replay"})}">Xem trên dashboard ↗</a><a href="/lessons/${key}">Bài ${key} →</a>`;
      node.append(actions);
      node.dataset.ready = "true";
      window.EdgeMath();
    } catch (error) { failure(node,error); node.dataset.ready="error"; }
  }
  function rtp(node,data) {
    note(node,"SOURCE: sơ đồ bit theo Bài 01; V/PT và SSRC theo nguồn ghi trong bài. Bấm vào từng trường để xem nghĩa.");
    const fields=[["V",2,"Version: RTP v2; sơ đồ định dạng, không phải trường có trong CSV."],["P",1,"Padding: bit báo phần đệm; CSV không ghi trường này."],["X",1,"Extension: bit báo header mở rộng; CSV không ghi trường này."],["CC",4,"CSRC count: số nguồn đóng góp; CSV không ghi trường này."],["M",1,`Marker = ${data.header.marker}; đánh dấu mảnh cuối của frame.`],["PT",7,"Payload type 96: payload riêng của đề tài; SOURCE Bài 01."],["sequence",16,`Sequence number của gói đầu: ${data.header.seq}. Số này quay vòng sau 16 bit.`],["timestamp",32,`RTP timestamp của gói đầu: ${data.header.rtp_ts}; đồng hồ media, không phải giờ laptop.`],["SSRC",32,`SSRC trong sender_rtcp.csv: ${data.ssrc ?? "không có dữ liệu"}; định danh bên gửi.`]];
    const diagram=document.createElement("div"); diagram.className="rtp-bitfield";
    fields.forEach(([label,bits,description]) => {
      const button=document.createElement("button"); button.style.gridColumn="span "+bits; button.textContent=label;
      button.title=`${bits} bit`; button.onclick=()=>{detail.textContent=description;diagram.querySelectorAll("button").forEach(b=>b.classList.toggle("active",b===button));};
      diagram.append(button);
    });
    const picker=document.createElement("label");picker.className="rtp-mobile-fields";picker.textContent="Chọn trường RTP ";
    const select=document.createElement("select");select.setAttribute("aria-label","Chọn trường RTP");
    fields.forEach(([label,bits],i)=>select.add(new Option(`${label} · ${bits} bit`,i)));
    select.value="6";select.onchange=()=>diagram.querySelectorAll("button")[Number(select.value)].click();picker.append(select);
    const diagramScroll=document.createElement("div");diagramScroll.className="rtp-bitfield-wrap";diagramScroll.append(diagram);
    node.append(picker,diagramScroll);
    const detail=output(node); detail.textContent=fields[6][2];
    const control=controls(node,'<button type="button">Phát lại</button><label>Thời điểm <input aria-label="Thời điểm replay sequence" type="range" min="0" max="'+data.duration+'" step="0.02" value="'+data.duration+'"></label><span class="replay-position"></span>');
    const range=control.querySelector("input"),position=control.querySelector("span"),button=control.querySelector("button");
    const sequences=data.packets.map(p=>p[1]);
    const chart=plot(node,{x:[],ys:[[],[]],labels:["Gói nhận","Khoảng trống tạm thời"],colors:["cyan","red"],xunit:"s",yunit:"sequence",dots:true,range:[Math.min(...sequences)-1,Math.max(...sequences)+1]},"Sequence gaps · cửa sổ 2 giây");
    let timer=null;
    function draw() {
      const time=Number(range.value),packets=data.packets.filter(p=>p[0]<=time),recent=packets.filter(p=>p[0]>=time-2);
      const seen=new Set(packets.map(p=>p[1])), points=[];
      recent.forEach((p,i)=>{
        if(i) {
          const previous=recent[i-1][1],delta=(p[1]-previous+65536)%65536;
          if(delta>1 && delta<512) for(let gap=1;gap<delta;gap++) {
            const seq=(previous+gap)%65536; if(!seen.has(seq)) points.push([p[0],null,seq]);
          }
        }
        points.push([p[0],p[1],null]);
      });
      chart.setData([points.map(p=>p[0]),points.map(p=>p[1]),points.map(p=>p[2])]);
      position.textContent=time.toFixed(2)+" s";
    }
    range.oninput=draw;
    button.onclick=()=>{
      if(timer) {clearInterval(timer);timer=null;button.textContent="Phát lại";return;}
      range.value=0;button.textContent="Dừng";
      timer=setInterval(()=>{
        if(!node.isConnected || Number(range.value)+.025>=Number(range.max)) {clearInterval(timer);timer=null;button.textContent="Phát lại";return;}
        range.value=Number(range.value)+.05;draw();
      },50);
      draw();
    };
    draw();
  }
  function jitter(node,data) {
    data.charts.forEach(spec=>plot(node,spec));
    const control=controls(node,'<button type="button">Gói trước</button><button type="button">Gói tiếp</button><span class="calc-count"></span>');
    const result=output(node); let index=0;
    const draw=()=>{
      const row=data.calculator[index];
      if(!index) result.textContent=`Gói ${row.seq}: J = ${row.jitter_ts_units} tick (khởi tạo).`;
      else {
        const previous=data.calculator[index-1],j=Number(previous.jitter_ts_units),d=Number(row.transit_ts_units)-Number(previous.transit_ts_units);
        result.textContent=`Gói ${row.seq}: D = ${d} tick; J = ${j.toFixed(6)} + (${Math.abs(d)} − ${j.toFixed(6)}) / 16 = ${(j+(Math.abs(d)-j)/16).toFixed(6)} tick. Log: ${row.jitter_ts_units} tick.`;
      }
      control.querySelector("span").textContent=`${index+1} / ${data.calculator.length} gói từ ví dụ trong bài`;
      control.children[0].disabled=index===0;control.children[1].disabled=index===data.calculator.length-1;
    };
    control.children[0].onclick=()=>{index--;draw();};control.children[1].onclick=()=>{index++;draw();};draw();
  }
  function playout(node,data) {
    const control=controls(node,`<label for="delay-${node.id}">D (ms)</label><input id="delay-${node.id}" type="range" min="0" max="250" step="1" value="${Math.round(data.experiment_d)}"><strong class="delay-value"></strong>`);
    const result=output(node),xs=Array.from({length:251},(_,i)=>i);
    const percentage=d=>data.offsets.length?100*data.offsets.filter(v=>v>d).length/data.offsets.length:null;
    const spec={x:xs,ys:[xs.map(percentage),xs.map(d=>Math.abs(d-data.experiment_d)<.51?percentage(d):null)],labels:["Frame hoàn chỉnh muộn (%)","D thí nghiệm"],xunit:"D (ms)",yunit:"%",marker:true};
    plot(node,spec,"Deadline từ arrival CSV · INFERRED");
    const draw=()=>{
      const d=Number(control.querySelector("input").value);
      control.querySelector("strong").textContent=d+" ms";
      result.textContent=`Muộn: ${percentage(d)?.toFixed(2) ?? "—"}% / ${data.complete} frame hoàn chỉnh; thêm vào deadline: ${d} ms. D thí nghiệm: ${data.experiment_d} ms (marker). ${data.total-data.complete} frame không hoàn chỉnh nằm ngoài mẫu số; không phải capture→AI latency.`;
    };
    control.querySelector("input").oninput=draw;draw();
  }
  function abr(node,data) {
    const spec=data.simulation, x=[],qualities=[],losses=[];
    let quality=spec.initial_quality,clean=0;
    for(let t=0;t<=spec.seconds;t+=spec.rr_interval_s) {
      const loss=t>=spec.loss_step_start&&t<spec.loss_step_end?spec.loss:0;
      if(loss>spec.high_loss){quality=Math.max(spec.minimum_quality,Math.floor(quality*spec.decrease));clean=0;}
      else if(loss<spec.low_loss){clean++;if(clean>=spec.clean_reports){quality=Math.min(spec.maximum_quality,quality+spec.increase);clean=0;}}
      else clean=0;
      x.push(t);qualities.push(quality);losses.push(loss*100);
    }
    note(node,"MÔ PHỎNG · timeline quality; tham số minh hoạ trong widget_spec.json, quy tắc AIMD Bài 06. Không phải replay quyết định ABR.");
    plot(node,{x,ys:[qualities],labels:["Quality (mô phỏng)"],xunit:"s",yunit:"quality",stepped:true});
    plot(node,{x,ys:[losses],labels:["Loss đầu vào (mô phỏng)"],xunit:"s",yunit:"%",stepped:true});
    note(node,"ĐO THẬT · ba điểm bitrate tại q30 / q60 / q90; nguồn hw_tables.md CN-T5. Không phải kết quả ABR.");
    data.charts.forEach(spec=>plot(node,spec));
  }
  function queues(node,data) {
    const config=data.config;
    const control=controls(node,`<label>Service (ms) <input aria-label="Service time" type="range" min="${config.service_min_ms}" max="${config.service_max_ms}" step="${config.step_ms}" value="${config.service_ms}"></label><strong></strong>`);
    const result=output(node),chart=plot(node,{x:[],ys:[[],[]],labels:["FIFO AoI","Latest AoI"],xunit:"s",yunit:"ms"});
    function simulate(service,latest) {
      let nextArrival=0,nextDone=Infinity,generation=null,lastDelivered=null;const queue=[],deliveries=[];
      while(Math.min(nextArrival,nextDone)<=config.duration_s*1000) {
        const t=Math.min(nextArrival,nextDone);
        if(nextDone<=nextArrival) {
          lastDelivered=generation;deliveries.push([t,lastDelivered]);
          if(queue.length){generation=queue.shift();nextDone=t+service;}else nextDone=Infinity;
        } else {
          if(!Number.isFinite(nextDone)){generation=t;nextDone=t+service;}
          else if(latest){queue.length=0;queue.push(t);}
          else if(queue.length<config.fifo_capacity)queue.push(t);
          nextArrival+=1000/config.fps;
        }
      }
      return deliveries;
    }
    function draw() {
      const service=Number(control.querySelector("input").value),fifo=simulate(service,false),latest=simulate(service,true);
      const times=new Set([0,config.duration_s*1000]);
      for(let t=0;t<=config.duration_s*1000;t+=10)times.add(t);
      [...fifo,...latest].forEach(([t])=>{times.add(Math.max(0,t-.0001));times.add(t);});
      const x=[...times].sort((a,b)=>a-b), ages=deliveries=>{
        let index=-1;return x.map(t=>{while(index+1<deliveries.length&&deliveries[index+1][0]<=t)index++;return index>=0?t-deliveries[index][1]:null;});
      };
      chart.setData([x.map(t=>t/1000),ages(fifo),ages(latest)]);
      control.querySelector("strong").textContent=service+" ms";
      result.textContent=`Đầu vào ${config.fps} fps; service ${service} ms; FIFO tối đa ${config.fifo_capacity} frame chờ (đầy thì bỏ frame mới); latest chỉ giữ frame chờ mới nhất. Cùng service, không preempt. Kết quả trong ${config.duration_s} s: FIFO ${fifo.length}, latest ${latest.length}.`;
    }
    control.querySelector("input").oninput=draw;draw();
  }
  function age(node,data) {
    note(node,"INFERRED · L + Y/2, không phải một phép đo AoI mới.");
    const control=controls(node,'<label>Điều kiện <select aria-label="Chọn điều kiện AoI"></select></label>');
    const select=control.querySelector("select");
    data.cases.forEach((c,i)=>select.add(new Option(`${c.policy} · idle · dòng ${i+1}`,i)));
    const formula=output(node); formula.dataset.katex="\\overline{\\Delta}\\approx L+\\frac{Y}{2}";formula.textContent="Mean AoI ≈ latency + interval / 2";
    const result=output(node);
    const chart=plot(node,{x:[0,1],ys:[[0,0]],labels:["AoI (ms)"],xunit:"0=INFERRED · 1=đo",yunit:"ms",hist:true});
    select.onchange=()=>{
      const c=data.cases[Number(select.value)],inferred=c.latency+c.interval/2;
      result.textContent=`SOURCE: L = delivery P50 ${c.latency.toFixed(3)} ms; Y = initialized_seconds / rx_received = ${c.interval.toFixed(3)} ms. INFERRED L + Y/2 = ${inferred.toFixed(3)} ms. AoI đo (time average) = ${c.measured.toFixed(3)} ms.`;
      chart.setData([[0,1],[inferred,c.measured]]);
    };select.onchange();
  }
  function supervisor(node,data) {
    const control=controls(node,'<label>Kịch bản <select aria-label="Kịch bản supervisor"><option value="scenario">Missed heartbeat & rearm</option><option value="degrade">Degrade & recover</option></select></label><button type="button">Bước tiếp</button><button type="button">Chạy animation</button><button type="button">Về đầu</button>');
    const diagram=document.createElement("div");diagram.className="state-diagram";
    diagram.innerHTML=["INIT","FRESH","HOLD","FAILSAFE"].map((label,i)=>`<div class="state-node" data-state="${i}">${label}</div>`).join('<span aria-hidden="true">→</span>');
    node.append(diagram);
    note(node,"Mũi tên chỉ thứ tự hiển thị. Đường chuyển thực tế: FRESH ↔ HOLD; FRESH/HOLD → FAILSAFE; FAILSAFE → INIT sau rearm; INIT → FRESH.");
    const result=output(node),stage=output(node);
    const chart=plot(node,{x:[],ys:[[]],labels:["Stateflow state (0–3)"],xunit:"ms",yunit:"state",stepped:true,range:[0,3]});
    let index=0,timer=null;const select=control.querySelector("select"),buttons=control.querySelectorAll("button");
    const stop=()=>{clearInterval(timer);timer=null;buttons[1].textContent="Chạy animation";};
    const checkpoints=()=>{
      const scenario=data[select.value];
      const points=scenario.transition_ms.map((time,i)=>({time,state:scenario.state_sequence[i]}));
      // Show the last saved healthy sample before the watchdog expires, so
      // students can see missing heartbeats while FAILSAFE has not latched yet.
      if(select.value==="scenario") {
        const fault=points.findIndex(p=>p.state===3);
        const missed=data.traces.scenario.filter(row=>row.time_ms<points[fault]?.time&&row.state===1).at(-1);
        if(fault>0&&missed&&missed.time_ms>points[fault-1].time)
          points.splice(fault,0,{time:missed.time_ms,state:missed.state,miss:true});
      }
      return points;
    };
    function draw() {
      const scenario=data[select.value],points=checkpoints(),{state,time,miss}=points[index];
      diagram.querySelectorAll("[data-state]").forEach(n=>n.classList.toggle("active",Number(n.dataset.state)===state));
      result.textContent=`${scenario.scenario}: t = ${time} ms → ${["INIT","FRESH","HOLD","FAILSAFE"][state]}. Bước ${index+1}/${points.length}; JSON passed = ${scenario.passed}.`;
      const sample=data.traces[select.value].filter(row=>row.time_ms<=time).at(-1);
      stage.textContent=sample?`Heartbeat age: ${sample.heartbeat_age_ms} ms · source age: ${sample.source_age_ms} ms · reason ${sample.reason}. ${miss?"Heartbeat vắng: tuổi đang tăng, watchdog chưa hết hạn. Điểm này lấy từ CSV trước FAULT.":state===3?"FAULT: FAILSAFE bị chốt; heartbeat quay lại chưa đủ.":state===0&&index?"Rearm hợp lệ; chờ cả heartbeat và result mới.":state===2?"DEGRADE: kết quả đã cũ; heartbeat vẫn sống.":index===points.length-1?"Heartbeat OK / RECOVER khi có dữ liệu mới.":"Heartbeat OK / chờ dữ liệu."}`:"";
      chart.setData([points.slice(0,index+1).map(p=>p.time),points.slice(0,index+1).map(p=>p.state)]);
      buttons[0].disabled=index===points.length-1;
    }
    buttons[0].onclick=()=>{stop();index++;draw();};
    buttons[1].onclick=()=>{
      if(timer){stop();return;}index=0;draw();buttons[1].textContent="Dừng animation";
      timer=setInterval(()=>{
        if(!node.isConnected||index===checkpoints().length-1){stop();return;}index++;draw();
      },1000); // One transition per second for teaching; exact simulation times are printed.
    };
    buttons[2].onclick=()=>{stop();index=0;draw();};
    select.onchange=()=>{stop();index=0;draw();};
    note(node,`MÔ PHỎNG · ${data.report.completed}/${data.report.requested} kịch bản trong test_results.json; animation chậm mỗi chuyển trạng thái để dễ đọc, không theo thời gian thật.`);
    const images=document.createElement("details");images.className="simulation-images";images.open=true;
    images.innerHTML='<summary>Timeline PNG đã xuất từ Stateflow</summary>'+data.images.map(ref=>`<a href="${esc(evidenceLink(ref))}"><img loading="eager" src="${esc(rawLink(ref))}" alt="MÔ PHỎNG · ${esc(ref.path)}"></a>`).join("");
    node.append(images);draw();
  }

  async function evidence() {
    const app=$("evidence-app"),params=new URLSearchParams(location.search),root=params.get("root"),path=params.get("path")||"";
    try {
      const rootData=await api("/api/evidence/list");
      const intro='<p>Chỉ mở các thư mục nguồn đã khai báo trên server. Bản xem trước chỉ đọc; SHA-256 được tính khi bấm nút.</p>';
      if(!root) {
        app.innerHTML=intro+'<div class="root-list">'+rootData.roots.map(r=>`<a class="root-card" href="/evidence?${query({root:r.id})}">${esc(r.id)} · ${r.available?"Có nguồn":"Chưa có nguồn"}<small>${esc(r.path)}</small></a>`).join("")+'</div>';return;
      }
      app.innerHTML=intro+'<div class="evidence-layout"><aside class="evidence-folders"><a href="/evidence">← Tất cả nguồn</a><div class="evidence-path"></div><div id="file-list"></div></aside><section class="evidence-preview" id="file-preview"></section></div>';
      app.querySelector(".evidence-path").textContent=root;
      let folder=path;
      let preview=null;
      if(path) {
        // Try a file first; directories are shown using the directory endpoint.
        try { preview=await api("/api/evidence/preview?"+query({root,path,page:params.get("page")||1,...(params.get("column")?{column:params.get("column")}:{}),...(params.get("time")?{time:params.get("time")}:{})})); }
        catch { folder=path; }
        if(preview) folder=path.includes("/")?path.slice(0,path.lastIndexOf("/")):"";
      }
      const listing=await api("/api/evidence/list?"+query({root,path:folder,page:params.get("folder_page")||1}));
      const list=$("file-list");
      list.innerHTML=(folder?`<a class="file-row" href="/evidence?${query({root,path:folder.includes("/")?folder.slice(0,folder.lastIndexOf("/")):""})}">../</a>`:"")+listing.items.map(item=>`<a class="file-row" href="/evidence?${query({root,path:item.path})}">${item.directory?"▸ ":""}${esc(item.name)}${item.directory?"/":""}</a>`).join("");
      if(listing.pages>1) list.append(pager(listing.page,listing.pages,p=>"/evidence?"+query({root,path:folder,folder_page:p})));
      const view=$("file-preview");
      if(!preview){view.innerHTML='<h2>Chọn một tệp bằng chứng</h2><p>CSV: bảng, cột và biểu đồ. Log: 200 dòng cuối. PNG/SVG: ảnh trong trang.</p>';return;}
      view.innerHTML=`<div class="eyebrow">BẰNG CHỨNG / ${esc(preview.kind)}</div><span class="badge">${esc(preview.badge)}</span><h2 class="file-title">${esc(path.split("/").at(-1))}</h2><div class="evidence-path">${esc(preview.source)}</div><p>Được dùng trong bài: ${preview.lessons.length?preview.lessons.map(id=>`<a href="/lessons/${id}">${id}</a>`).join(", "):"Chưa gắn bài"}</p><button id="hash-source">Tính SHA-256 & provenance</button><div id="hash-result"></div>`;
      $("hash-source").onclick=async()=>{
        $("hash-source").disabled=true;$("hash-result").textContent="Đang đọc tệp và tính hash…";
        try {
          const value=await api("/api/evidence/provenance?"+query({root,path}));
          $("hash-result").className="provenance-result";
          $("hash-result").textContent=`${value.path}\nSize: ${value.size} bytes\nModified (UTC): ${value.modified}\nSHA-256: ${value.sha256}`;
        } catch(error){failure($("hash-result"),error);}finally{$("hash-source").disabled=false;}
      };
      if(preview.kind==="image") {
        const img=document.createElement("img");img.src=rawLink({root,path});img.alt=path;view.append(img);
      } else if(preview.kind==="log") {
        note(view,preview.note);const pre=document.createElement("pre");pre.textContent=preview.text;view.append(pre);
      } else {
        note(view,`${preview.total} dòng · ${preview.columns.length} cột. ${preview.time_note}`);
        const selected=params.get("column")||preview.numeric.find(c=>c!==preview.time_column),time=params.get("time")||preview.time_column;
        const control=controls(view,'<label>Cột số <select aria-label="Cột số"></select></label><label>Trục thời gian <select aria-label="Trục thời gian"></select></label>');
        const [ySelect,xSelect]=control.querySelectorAll("select");
        preview.numeric.forEach(c=>ySelect.add(new Option(c,c)));
        xSelect.add(new Option("Số dòng (không có thời gian)","__row__"));
        preview.numeric.forEach(c=>xSelect.add(new Option(c,c)));
        ySelect.value=selected||"";xSelect.value=time||"__row__";
        const chartHost=document.createElement("div");view.append(chartHost);
        async function drawPlot() {
          if(!ySelect.value) return;
          const plotData=await api("/api/evidence/preview?"+query({root,path,column:ySelect.value,...(xSelect.value?{time:xSelect.value}: {})}));
          chartHost.querySelectorAll(".widget-chart").forEach(n=>n._edgePanel?.destroy());chartHost.innerHTML="";
          plot(chartHost,{x:plotData.plot.map(p=>p[0]),ys:[plotData.plot.map(p=>p[1])],labels:[ySelect.value],xunit:plotData.plot_xunit,yunit:ySelect.value});
          note(chartHost,`${plotData.time_note} Lấy mẫu biểu đồ mỗi ${plotData.plot_stride} dòng; bảng vẫn giữ nguyên thứ tự.`);
        }
        ySelect.onchange=xSelect.onchange=()=>drawPlot().catch(error=>failure(chartHost,error));await drawPlot();
        const scroll=document.createElement("div");scroll.className="table-scroll";
        scroll.innerHTML="<table><thead><tr>"+preview.columns.map(c=>`<th>${esc(c)}</th>`).join("")+"</tr></thead><tbody>"+preview.rows.map(row=>"<tr>"+preview.columns.map(c=>`<td>${esc(row[c])}</td>`).join("")+"</tr>").join("")+"</tbody></table>";
        view.append(scroll,pager(preview.page,preview.pages,p=>"/evidence?"+query({root,path,page:p,...(ySelect.value?{column:ySelect.value}:{}),...(xSelect.value?{time:xSelect.value}:{})})));
      }
    } catch(error){failure(app,error);}
  }
  function pager(page,pages,href) {
    const node=document.createElement("nav");node.className="pager";node.setAttribute("aria-label","Phân trang");
    node.innerHTML=(page>1?`<a href="${esc(href(page-1))}">← Trước</a>`:"")+`<span>Trang ${page} / ${pages}</span>`+(page<pages?`<a href="${esc(href(page+1))}">Tiếp →</a>`:"");return node;
  }
  async function demo() {
    const app=$("demo-app");
    try {
      const data=await api("/api/demo"),status=await api("/api/status");
      let index=0,view="replay",timer=null,remaining=data.steps[0].seconds;
      app.innerHTML='<p>Kịch bản từ INDEX tiếng Việt · 600 giây. Replay hoạt động không cần Pi. Mỗi bước mở đúng panel trên cùng dashboard.</p><div class="demo-layout"><aside class="demo-step-list"></aside><section class="demo-stage"></section></div>';
      const list=app.querySelector(".demo-step-list"),stage=app.querySelector(".demo-stage");
      data.steps.forEach((step,i)=>{
        const button=document.createElement("button");button.innerHTML=`<b>${String(i+1).padStart(2,"0")}</b><span>${esc(step.title)}<br><small>${step.seconds} giây · Bài ${step.lesson}</small></span>`;
        button.onclick=()=>{index=i;draw();};list.append(button);
      });
      const stop=()=>{clearInterval(timer);timer=null;};
      function draw() {
        stop();
        const step=data.steps[index];remaining=step.seconds;
        [...list.children].forEach((b,i)=>b.classList.toggle("active",i===index));
        stage.innerHTML=`<div class="demo-topline"><span>BƯỚC ${index+1} / ${data.steps.length}</span><time class="demo-timer"></time></div><div class="demo-progress"><span style="width:${100*(index+1)/data.steps.length}%"></span></div><h2>${esc(step.title)}</h2><div class="speaker-note"><div class="eyebrow">GỢI Ý THUYẾT TRÌNH</div><p>Nói: ${esc(step.note)}</p></div><div class="demo-links"><button id="timer-start">Bắt đầu giờ</button><button id="demo-next">${index<data.steps.length-1?"Bước tiếp →":"Về bước 1"}</button><a href="/lessons/${step.lesson}">Bài ${step.lesson} chứng minh ↗</a><label>Panel <select id="demo-mode"><option value="replay">Replay / minh hoạ có nhãn</option><option value="live">Live từ hub hiện tại</option></select></label></div><p id="demo-mode-note"></p><iframe class="demo-dashboard" title="Dashboard · ${esc(step.title)}"></iframe><p><a id="demo-dashboard-link" target="_blank" rel="noopener">Mở dashboard toàn trang ↗</a> · <a href="/lessons/index">Kịch bản INDEX nguyên văn</a></p>`;
        const clock=stage.querySelector("time"),paintClock=()=>{clock.textContent=`${Math.floor(remaining/60).toString().padStart(2,"0")}:${(remaining%60).toString().padStart(2,"0")}`;};paintClock();
        $("timer-start").onclick=()=>{
          if(timer){stop();$("timer-start").textContent="Tiếp tục giờ";return;}
          if(!remaining)remaining=step.seconds;
          $("timer-start").textContent="Dừng giờ";
          timer=setInterval(()=>{remaining=Math.max(0,remaining-1);paintClock();if(!remaining){stop();$("timer-start").textContent="Chạy lại giờ";}},1000);
        };
        $("demo-next").onclick=()=>{index=(index+1)%data.steps.length;draw();};
        const mode=$("demo-mode");mode.value=view;
        const update=()=>{
          view=mode.value;
          const url="/?"+query({profile:step.profile,panel:panelId[step.lesson],lesson:step.lesson,view,embed:1});
          stage.querySelector("iframe").src=url;
          $("demo-dashboard-link").href=url.replace("&embed=1","");
          $("demo-mode-note").textContent=view==="replay"?`Nguồn panel: ${step.mode.toUpperCase()}. Giữ nhãn ĐO THẬT / MÔ PHỎNG trong màn hình.`:status.mode==="live"?`Hub LIVE · ${status.status}. Panel chỉ hiện telemetry thực sự đã nhận.`:`Hub hiện là ${status.mode.toUpperCase()}; chưa có nguồn LIVE. Khởi động hub --mode live rồi mở lại trang này.`;
        };
        mode.onchange=update;update();
      }
      draw();
    } catch(error){failure(app,error);}
  }
  const params=new URLSearchParams(location.search);
  if($("profile")) {
    const profile=params.get("profile");
    if(["cn","os"].includes(profile)){$("profile").value=profile;$("profile").dispatchEvent(new Event("change"));}
    const key=params.get("lesson"),view=params.get("view")||"replay";
    if(params.get("embed")==="1")document.body.classList.add("embedded-dashboard");
    if(key && title[key] && view!=="live") {
      const lab=document.createElement("div");lab.className="dashboard-lab";lab.id="dashboard-lesson";
      lab.innerHTML=`<section class="learning-widget panel full-widget" id="full-widget-${key}" data-widget="${key}"></section>`;
      document.querySelector(".session").after(lab);
      document.body.classList.add("has-dashboard-lab");
      if(params.get("embed")!=="1")lab.scrollIntoView();
    } else if(view==="live") {
      const desired=$(params.get("panel"));
      const panel=desired?.closest(".panel");
      if(panel){panel.classList.add("focused-panel");if(params.get("embed")==="1"){panel.classList.add("demo-live-panel");document.body.classList.add("has-live-panel");}panel.scrollIntoView();}
      const warning=document.createElement("p");warning.className="live-source-note";warning.textContent="LIVE yêu cầu hub --mode live. URL chỉ chọn panel; không đổi nguồn hub và không tạo telemetry.";
      document.querySelector(".session").after(warning);
      api("/api/status").then(status=>{
        warning.textContent=status.mode==="live"?`LIVE · ${status.status}. Dữ liệu thiếu giữ nguyên dấu —.`:`Chưa có dữ liệu LIVE: hub đang ở chế độ ${status.mode}. Chạy --mode live để nhận Pi / MCU; không dùng replay làm số đo live.`;
        if(status.mode!=="live")document.body.classList.add("live-unavailable");
      }).catch(error=>failure(warning,error));
    }
  }
  document.querySelectorAll("[data-widget]").forEach(node=>widget(node,node.dataset.widget));
  if($("evidence-app"))evidence();
  if($("demo-app"))demo();
})();
