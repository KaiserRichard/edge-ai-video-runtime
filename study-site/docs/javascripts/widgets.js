/* Interactive teaching widgets. Usage in Markdown: <div class="widget" data-widget="NAME"></div>
   NAME: serialization | framesize | fragments | jitter | aimd | framesuccess | deadline | aoi | queue | clocks
   All are teaching calculators built from the model's own equations; none is a new simulation. */
(() => {
  const el = (tag, cls, txt) => { const e = document.createElement(tag); if (cls) e.className = cls; if (txt !== undefined) e.textContent = txt; return e; };
  const slider = (label, min, max, step, val, fmt) => {
    const wrap = el('label', 'w-slider'); const name = el('span', 'w-label', label);
    const input = el('input'); Object.assign(input, { type: 'range', min, max, step, value: val });
    const out = el('span', 'w-val'); const show = () => { out.textContent = fmt(Number(input.value)); };
    input.addEventListener('input', show); show(); wrap.append(name, input, out); return { wrap, input };
  };
  const stat = (label) => { const s = el('div', 'w-stat'); const v = el('div', 'w-num', '–'); s.append(el('div', 'w-cap', label), v); return { s, v }; };
  const note = (t) => el('p', 'w-note', t);
  const fmt = (x, d = 2) => Number(x).toLocaleString('vi-VN', { maximumFractionDigits: d, minimumFractionDigits: 0 });

  const W = {
    serialization(h) {
      const sz = slider('Payload (B)', 200, 1400, 100, 1200, v => v + ' B');
      const c = slider('Link (Mb/s)', 0.25, 100, 0.25, 100, v => fmt(v) + ' Mb/s');
      const a = stat('Thời gian đẩy 1 gói'), b = stat('Số gói tối đa mỗi giây');
      const grid = el('div', 'w-grid'); grid.append(a.s, b.s);
      const up = () => { const bits = 8 * (Number(sz.input.value) + 48); const t = bits / (Number(c.input.value) * 1e6);
        a.v.textContent = fmt(t * 1000, 3) + ' ms'; b.v.textContent = fmt(1 / t, 0) + ' gói/s'; };
      [sz, c].forEach(x => x.input.addEventListener('input', up)); up();
      h.append(sz.wrap, c.wrap, grid, note('T_ser = 8·(payload + 48 B header) / C. Thử 0,55 Mb/s: một gói 1200 B mất khoảng 18 ms. CALCULATED.'));
    },
    framesize(h) {
      const base = Number(h.dataset.base || 6960), payload = Number(h.dataset.payload || 1200);
      const r = slider('AIMD scale r', 0.15, 1.5, 0.05, 1, v => fmt(v));
      const a = stat('Kích thước ảnh'), b = stat('Số gói cần'), grid = el('div', 'w-grid'); grid.append(a.s, b.s);
      const up = () => { const s = Math.round(Number(r.input.value) * base); a.v.textContent = fmt(s, 0) + ' B'; b.v.textContent = Math.ceil(s / payload); };
      r.input.addEventListener('input', up); up();
      h.append(r.wrap, grid, note(`Ảnh gốc ${base} B, payload ${payload} B/gói. FPS không đổi: AIMD chỉ đổi số byte mỗi ảnh. CALCULATED.`));
    },
    fragments(h) {
      const n = Number(h.dataset.count || 6); const got = new Array(n).fill(true); got[n - 1] = false;
      const row = el('div', 'w-frags'); const a = stat('Đã nhận'), b = stat('Cờ hoàn thành'), grid = el('div', 'w-grid'); grid.append(a.s, b.s);
      const msg = el('p', 'w-msg');
      const up = () => { const k = got.filter(Boolean).length; a.v.textContent = `${k}/${n}`; b.v.textContent = k === n ? '1' : '0';
        msg.textContent = k === n ? 'Ảnh đủ mảnh: có thể phát nếu kịp deadline.' : 'Thiếu mảnh: ảnh không ghép được, dù gói marker đã tới.'; msg.className = 'w-msg ' + (k === n ? 'ok' : 'no'); };
      for (let i = 0; i < n; i++) { const btn = el('button', 'w-frag', 'P' + (i + 1) + (i === n - 1 ? ' ★' : '')); btn.type = 'button';
        const paint = () => btn.classList.toggle('on', got[i]); paint();
        btn.addEventListener('click', () => { got[i] = !got[i]; paint(); up(); }); row.append(btn); }
      up(); h.append(note('Bấm vào từng gói để bật/tắt. ★ là gói có marker bit.'), row, grid, msg);
    },
    jitter(h) {
      const d = slider('|D| mỗi gói (ms)', 0, 40, 1, 10, v => v + ' ms');
      const canvas = el('canvas', 'w-canvas'); canvas.width = 640; canvas.height = 200;
      const a = stat('J sau 1 gói'), b = stat('J sau 16 gói'), c = stat('J sau 64 gói'), grid = el('div', 'w-grid'); grid.append(a.s, b.s, c.s);
      const up = () => { const D = Number(d.input.value); let J = 0; const ys = [];
        for (let k = 1; k <= 64; k++) { J += (D - J) / 16; ys.push(J); }
        a.v.textContent = fmt(ys[0], 3) + ' ms'; b.v.textContent = fmt(ys[15], 2) + ' ms'; c.v.textContent = fmt(ys[63], 2) + ' ms';
        drawLine(canvas, ys, Math.max(40, D), D, 'Số gói k'); };
      d.input.addEventListener('input', up); up();
      h.append(d.wrap, canvas, grid, note('J_k = J_{k−1} + (|D_k| − J_{k−1})/16: bộ lọc làm mượt bậc 1, đường nét đứt là |D|. Đầu vào hằng là giả định đơn giản hoá. CALCULATED.'));
    },
    aimd(h) {
      let rate = 1, clean = 0, hist = [1];
      const losses = [['15% loss', 0.15], ['1% loss', 0.01], ['0% loss', 0]]; let loss = 0.15;
      const pick = el('div', 'w-btns'); losses.forEach(([t, v], i) => { const b = el('button', 'w-btn' + (i === 0 ? ' on' : ''), t); b.type = 'button';
        b.onclick = () => { loss = v; pick.querySelectorAll('button').forEach(x => x.classList.remove('on')); b.classList.add('on'); }; pick.append(b); });
      const go = el('button', 'w-btn primary', 'Gửi 1 RR hợp lệ'); go.type = 'button';
      const reset = el('button', 'w-btn', 'Đặt lại'); reset.type = 'button';
      const a = stat('Scale r'), b = stat('Bộ đếm clean'), grid = el('div', 'w-grid'); grid.append(a.s, b.s);
      const canvas = el('canvas', 'w-canvas'); canvas.width = 640; canvas.height = 180; const log = el('p', 'w-msg');
      const show = (m) => { a.v.textContent = fmt(rate, 3); b.v.textContent = clean + '/3'; log.textContent = m || ''; drawSteps(canvas, hist); };
      go.onclick = () => { const q = Math.floor(256 * loss) / 256; let m;
        if (q > 0.02) { rate = Math.max(0.15, 0.8 * rate); clean = 0; m = `Loss ${fmt(q * 100, 1)}% > 2%: giảm nhân r ← max(0,15; 0,8·r).`; }
        else if (q <= 0.005) { clean++; m = `Loss ≤ 0,5%: clean = ${clean}.`; if (clean >= 3) { rate = Math.min(1.5, rate + 0.05); clean = 0; m += ' Đủ 3 lần: tăng cộng r ← min(1,5; r + 0,05).'; } }
        else { clean = 0; m = 'Loss ở giữa 0,5% và 2%: giữ r, xoá bộ đếm clean.'; }
        hist.push(rate); show(m); };
      reset.onclick = () => { rate = 1; clean = 0; hist = [1]; show('Đã đặt lại.'); };
      const ctl = el('div', 'w-btns'); ctl.append(go, reset);
      show(); h.append(note('Chọn mức loss, rồi gửi từng receiver report. Thử nhiều lần 15% rồi chuyển 0%.'), pick, ctl, grid, canvas, log,
        note('Đúng luật của chart RUN trong mô hình v2: ngưỡng 2% / 0,5%, giảm ×0,8, tăng +0,05 sau 3 RR sạch, giới hạn [0,15; 1,5]. Đây là mô hình dạy học, không phải mô phỏng MATLAB mới.'));
    },
    framesuccess(h) {
      const p = slider('Xác suất mất gói p', 0, 0.4, 0.01, 0.15, v => fmt(v * 100, 0) + '%');
      const list = el('div', 'w-bars'); const Ns = [1, 2, 4, 6, 8, 11];
      const up = () => { const pv = Number(p.input.value); list.innerHTML = '';
        Ns.forEach(N => { const s = Math.pow(1 - pv, N); const row = el('div', 'w-bar');
          const bar = el('div', 'w-fill'); bar.style.width = (s * 100).toFixed(1) + '%';
          row.append(el('span', 'w-bl', N + ' gói'), Object.assign(el('div', 'w-track'), {}), el('span', 'w-bv', fmt(s * 100, 1) + '%'));
          row.children[1].append(bar); list.append(row); }); };
      p.input.addEventListener('input', up); up();
      h.append(p.wrap, list, note('P(ảnh đủ) = (1 − p)^N khi mất gói độc lập và cần mọi mảnh. CALCULATED.'));
    },
    deadline(h) {
      const first = slider('Gói đầu tới lúc (ms)', 0, 100, 5, 20, v => v + ' ms');
      const fps = slider('FPS', 5, 30, 1, 15, v => v + ' FPS');
      const B = slider('Độ sâu buffer B (ms)', 0, 200, 10, 50, v => v + ' ms');
      const tbl = el('table', 'w-table');
      const up = () => { const a = Number(first.input.value), f = Number(fps.input.value), b = Number(B.input.value);
        tbl.innerHTML = '<tr><th>Ảnh i</th><th>(TS_i − TS_0)/90000</th><th>Deadline d_i</th></tr>' +
          [0, 1, 2, 3].map(i => `<tr><td>${i}</td><td>${fmt(i * 1000 / f, 2)} ms</td><td><b>${fmt(a + i * 1000 / f + b, 2)} ms</b></td></tr>`).join(''); };
      [first, fps, B].forEach(x => x.input.addEventListener('input', up)); up();
      h.append(first.wrap, fps.wrap, B.wrap, tbl, note('d_i = t_anchor + (TS_i − TS_0)/90000 + B. Deadline đi theo lịch media, không theo giờ đến của từng gói. CALCULATED.'));
    },
    aoi(h) {
      const T = slider('Chu kỳ có kết quả mới (ms)', 20, 600, 10, 100, v => v + ' ms');
      const L = slider('Độ trễ mỗi kết quả (ms)', 0, 600, 10, 150, v => v + ' ms');
      const canvas = el('canvas', 'w-canvas'); canvas.width = 640; canvas.height = 200; const a = stat('AoI trung bình'), grid = el('div', 'w-grid'); grid.append(a.s);
      const up = () => { const t = Number(T.input.value), l = Number(L.input.value); const ys = [];
        for (let x = 0; x <= 4 * t; x += t / 20) ys.push(l + (x % t)); a.v.textContent = fmt(l + t / 2, 1) + ' ms'; drawLine(canvas, ys, Math.max(...ys) * 1.1, null, 'thời gian'); };
      [T, L].forEach(x => x.input.addEventListener('input', up)); up();
      h.append(T.wrap, L.wrap, canvas, grid, note('A(t) = t − u(t). Với kết quả đều đặn: AoI trung bình ≈ độ trễ + chu kỳ/2. Răng cưa đơn giản hoá. CALCULATED.'));
    },
    queue(h) {
      const lam = slider('Tốc độ đến λ (ảnh/s)', 5, 40, 1, 30, v => v + '/s');
      const svc = slider('Thời gian xử lý (ms)', 10, 100, 5, 50, v => v + ' ms');
      const a = stat('Năng lực μ'), b = stat('Tải ρ = λ/μ'), c = stat('Trạng thái'), grid = el('div', 'w-grid'); grid.append(a.s, b.s, c.s);
      const up = () => { const l = Number(lam.input.value), mu = 1000 / Number(svc.input.value), rho = l / mu;
        a.v.textContent = fmt(mu, 1) + '/s'; b.v.textContent = fmt(rho, 2); c.v.textContent = rho > 1 ? 'Quá tải' : 'Ổn định'; c.v.className = 'w-num ' + (rho > 1 ? 'bad' : 'good'); };
      [lam, svc].forEach(x => x.input.addEventListener('input', up)); up();
      h.append(lam.wrap, svc.wrap, grid, note('Khi ρ > 1, FIFO luôn đầy dần và ảnh chờ càng lâu càng cũ; latest-value bỏ ảnh cũ để xử lý ảnh mới nhất. CALCULATED.'));
    },
    clocks(h) {
      // CN-T9 measured per-frame breakdown (cn/rtp/report/hw_tables.md), mean of per-run P50 / P95, ms.
      const D = {
        noloss_D50: { cap: [0.07, 0.09], s2r: [67.84, 72.95], tot: [67.91, 73.03], play: [50.26, 50.54], q: [0.12, 0.13], inf: [12.51, 12.93] },
        loss5_D50: { cap: [0.07, 0.09], s2r: [67.93, 73.58], tot: [68.01, 73.66], play: [50.16, 50.42], q: [0.12, 0.14], inf: [12.52, 13.08] } };
      const INFO = {
        cap: ['Capture → first send', 'pi', 'Nén xong ảnh tới lúc gói đầu tiên rời socket. Rất ngắn.'],
        out: ['Mạng chiều đi', 'none', 'Không đo riêng được: gửi theo đồng hồ Pi, nhận theo đồng hồ laptop. Hai đồng hồ không đồng bộ nên không trừ chéo.'],
        play: ['Playout wait', 'lap', 'Laptop cố ý giữ frame tới hạn phát (độ sâu bộ đệm 50 ms). Đây là phần lớn nhất của độ trễ.'],
        q: ['AI queue wait', 'lap', 'Frame chờ trong hàng đợi AI trước khi được xử lý. Gần như bằng 0 vì AI không quá tải.'],
        inf: ['Inference', 'lap', 'Thời gian MobileNetV2 xử lý một frame trên laptop.'],
        back: ['Kết quả chiều về (AIRS)', 'none', 'Gói kết quả AI đi từ laptop về Pi. Cũng không đo riêng được vì khác đồng hồ.'],
        tot: ['Tổng capture → result receipt', 'pi', 'Đo hoàn toàn trên đồng hồ Pi: từ lúc chụp tới lúc Pi nhận kết quả. Hợp lệ vì cả hai mốc cùng một đồng hồ.'] };
      let cfg = 'noloss_D50', k = 0, sel = 'tot';
      const bar = el('div', 'w-btns');
      const mk = (txt, on) => { const b = el('button', 'w-btn', txt); b.type = 'button'; b.addEventListener('click', on); bar.append(b); return b; };
      const b1 = mk('noloss_D50', () => { cfg = 'noloss_D50'; draw(); }), b2 = mk('loss5_D50', () => { cfg = 'loss5_D50'; draw(); });
      const b3 = mk('P50', () => { k = 0; draw(); }), b4 = mk('P95', () => { k = 1; draw(); });
      const box = el('div', 'w-clocks'); const info = el('div', 'w-clock-info');
      const draw = () => {
        [b1, b2].forEach(b => b.classList.toggle('on', b.textContent === cfg)); b3.classList.toggle('on', k === 0); b4.classList.toggle('on', k === 1);
        const d = D[cfg], v = x => d[x][k];
        const PX = 120, LX = 520, top = 70, s = 4.2;              // 4.2 px per ms on the laptop axis
        const yCap = top, ySend = top + 22, yRecv = ySend + 40;
        const yPlay = yRecv + v('play') * s, yQ = yPlay + Math.max(6, v('q') * s), yInf = yQ + v('inf') * s, yRes = yInf + 40;
        const seg = (id, x, y1, y2, col) => `<rect data-k="${id}" x="${x - 9}" y="${y1}" width="18" height="${Math.max(4, y2 - y1)}" rx="3" fill="${col}" class="w-hot${sel === id ? ' sel' : ''}"/>`;
        const dot = (x, y, col) => `<circle cx="${x}" cy="${y}" r="7" fill="${col}"/>`;
        const lab = (x, y, t, a) => `<text x="${x}" y="${y + 4}" text-anchor="${a}" fill="currentColor" font-size="13">${t}</text>`;
        const arrow = (id, x1, y1, x2, y2) => `<g data-k="${id}" class="w-hot${sel === id ? ' sel' : ''}"><line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#3B82F6" stroke-width="3" stroke-dasharray="${sel === id ? '0' : '7 5'}"/><line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="transparent" stroke-width="18"/></g>`;
        const H = yRes + 50;
        box.innerHTML = `<svg viewBox="0 0 680 ${H}" width="100%" role="img" aria-label="Kiến trúc đo CN-T9: đồng hồ Pi và đồng hồ laptop">
          <text x="${PX}" y="30" text-anchor="middle" fill="currentColor" font-size="16" font-weight="700">Đồng hồ Pi</text>
          <text x="${LX}" y="30" text-anchor="middle" fill="currentColor" font-size="16" font-weight="700">Đồng hồ laptop</text>
          <line x1="${PX}" y1="45" x2="${PX}" y2="${H - 10}" stroke="currentColor" stroke-opacity=".35" stroke-width="2"/>
          <line x1="${LX}" y1="45" x2="${LX}" y2="${H - 10}" stroke="currentColor" stroke-opacity=".35" stroke-width="2"/>
          <g data-k="tot" class="w-hot${sel === 'tot' ? ' sel' : ''}"><path d="M ${PX - 30} ${yCap} H ${PX - 50} V ${yRes} H ${PX - 30}" fill="none" stroke="#16A34A" stroke-width="3"/><rect x="${PX - 62}" y="${yCap}" width="30" height="${yRes - yCap}" fill="transparent"/>
          <text x="${PX - 62}" y="${(yCap + yRes) / 2}" transform="rotate(-90 ${PX - 62} ${(yCap + yRes) / 2})" text-anchor="middle" fill="#16A34A" font-size="13">tổng ${fmt(v('tot'))} ms</text></g>
          ${seg('cap', PX, yCap, ySend, '#16A34A')}
          ${arrow('out', PX, ySend, LX, yRecv)} ${arrow('back', LX, yInf, PX, yRes)}
          ${seg('play', LX, yRecv, yPlay, '#B45309')} ${seg('q', LX, yPlay, yQ, '#6B7280')} ${seg('inf', LX, yQ, yInf, '#15803D')}
          ${dot(PX, yCap, '#16A34A')}${dot(PX, ySend, '#16A34A')}${dot(PX, yRes, '#16A34A')}${dot(LX, yRecv, '#3B82F6')}${dot(LX, yPlay, '#3B82F6')}${dot(LX, yInf, '#3B82F6')}
          ${lab(PX + 16, yCap, 'Chụp ảnh', 'start')}${lab(PX + 16, ySend, 'Gửi gói đầu', 'start')}${lab(PX + 16, yRes, 'Nhận kết quả AI', 'start')}
          ${lab(LX - 16, yRecv, 'Nhận gói', 'end')}${lab(LX - 16, yPlay, 'Hạn phát (playout)', 'end')}${lab(LX - 16, yInf, 'AI xong', 'end')}
          ${lab(LX + 16, (yRecv + yPlay) / 2, 'playout ' + fmt(v('play')), 'start')}${lab(LX + 16, yQ - 2, 'hàng đợi ' + fmt(v('q')), 'start')}${lab(LX + 16, (yQ + yInf) / 2, 'AI ' + fmt(v('inf')), 'start')}
        </svg>`;
        box.querySelectorAll('[data-k]').forEach(n => n.addEventListener('click', () => { sel = n.dataset.k; draw(); }));
        const [name, clk, txt] = INFO[sel], val = d[sel] ? `${fmt(d[sel][k])} ms (${k ? 'P95' : 'P50'}, MEASURED)` : 'không đo riêng';
        const ck = { pi: 'Đồng hồ Pi', lap: 'Đồng hồ laptop', none: 'Hai đồng hồ khác nhau' }[clk];
        info.innerHTML = `<div class="w-cap">${name} · ${ck}</div><div class="w-num">${val}</div><p class="w-note">${txt}</p>`;
      };
      draw();
      h.append(bar, box, info, note('Bấm vào từng đoạn trên hình. Khoảng trên cùng một đồng hồ thì đo được; mũi tên đi qua mạng nối hai đồng hồ khác nhau nên không tách được độ trễ một chiều. Số liệu CN-T9, trung bình 5 lần chạy, MEASURED.'));
    },
  };

  function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
  function drawLine(cv, ys, ymax, ref, xlabel) {
    const g = cv.getContext('2d'), w = cv.width, hh = cv.height, pad = 30; g.clearRect(0, 0, w, hh);
    g.strokeStyle = css('--md-default-fg-color--lighter') || '#999'; g.beginPath(); g.moveTo(pad, 8); g.lineTo(pad, hh - pad); g.lineTo(w - 8, hh - pad); g.stroke();
    const X = i => pad + (w - pad - 8) * i / (ys.length - 1), Y = v => hh - pad - (hh - pad - 8) * v / ymax;
    if (ref !== null && ref !== undefined) { g.setLineDash([5, 4]); g.strokeStyle = '#F59E0B'; g.beginPath(); g.moveTo(pad, Y(ref)); g.lineTo(w - 8, Y(ref)); g.stroke(); g.setLineDash([]); }
    g.strokeStyle = '#14B8A6'; g.lineWidth = 2.5; g.beginPath(); ys.forEach((v, i) => i ? g.lineTo(X(i), Y(v)) : g.moveTo(X(i), Y(v))); g.stroke(); g.lineWidth = 1;
    g.fillStyle = css('--md-default-fg-color--light') || '#666'; g.font = '12px sans-serif'; g.fillText(xlabel, w - 70, hh - 10);
  }
  function drawSteps(cv, hist) {
    const ys = hist.length > 1 ? hist : [hist[0], hist[0]]; drawLine(cv, ys, 1.6, 1, 'số RR');
  }
  function init() { document.querySelectorAll('.widget[data-widget]').forEach(h => {
    if (h.dataset.ready) return; const f = W[h.dataset.widget]; if (!f) return; h.dataset.ready = '1';
    const t = h.dataset.title; if (t) h.append(el('div', 'w-title', t)); f(h); }); }
  if (typeof document$ !== 'undefined') document$.subscribe(init);
  else if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
