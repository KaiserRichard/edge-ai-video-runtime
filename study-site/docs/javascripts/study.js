/* OS+CN team site: picture multiple-choice quizzes + an illustrative deadline slider. No network, no storage.
   Quiz markup in Markdown (md_in_html):

   <div class="quiz" markdown>
   <p class="quiz-q">Câu hỏi?</p>
   ![mô tả](../../assets/img/x.webp)
   - [ ] phương án sai
   - [x] phương án đúng
   <div class="quiz-why" markdown>Giải thích hiện ra sau khi chọn.</div>
   </div>
*/
(() => {
  const MARK = /^\s*\[([ xX])\]\s*/;
  function stripMark(li) {
    const walker = document.createTreeWalker(li, NodeFilter.SHOW_TEXT);
    let node; while ((node = walker.nextNode())) {
      if (!node.nodeValue.trim()) continue;
      const m = node.nodeValue.match(MARK);
      if (m) node.nodeValue = node.nodeValue.replace(MARK, '');
      return !!m && m[1].toLowerCase() === 'x';
    }
    return false;
  }
  function setupQuiz(q) {
    if (q.dataset.ready) return; q.dataset.ready = '1';
    const items = Array.from(q.querySelectorAll(':scope > ul > li, :scope > ol > li'));
    const why = q.querySelector('.quiz-why');
    if (why) why.hidden = true;
    items.forEach((li, i) => {
      li.dataset.correct = stripMark(li) ? '1' : '0';
      li.classList.add('quiz-opt'); li.setAttribute('role', 'button'); li.tabIndex = 0;
      const tag = document.createElement('span'); tag.className = 'quiz-letter'; tag.textContent = 'ABCDEFGH'[i] || '';
      li.prepend(tag);
    });
    function reset() {
      q.classList.remove('answered'); if (why) why.hidden = true;
      q.querySelectorAll('.quiz-result, .quiz-again').forEach(n => n.remove());
      items.forEach(o => o.classList.remove('is-right', 'is-dim', 'picked-right', 'picked-wrong'));
    }
    function pick(li) {
      if (q.classList.contains('answered')) return;
      q.classList.add('answered');
      const ok = li.dataset.correct === '1';
      items.forEach(o => o.classList.add(o.dataset.correct === '1' ? 'is-right' : 'is-dim'));
      li.classList.add(ok ? 'picked-right' : 'picked-wrong');
      const res = document.createElement('p'); res.className = 'quiz-result ' + (ok ? 'ok' : 'no'); res.setAttribute('role', 'status');
      res.textContent = ok ? '✓ Chính xác!' : '✗ Chưa đúng. Đáp án đúng được tô xanh.';
      const list = li.parentElement; list.after(res);
      if (why) { why.hidden = false; res.after(why); }
      const again = document.createElement('button'); again.type = 'button'; again.className = 'quiz-again'; again.textContent = 'Làm lại';
      again.addEventListener('click', reset); q.append(again);
    }
    items.forEach(li => {
      li.addEventListener('click', () => pick(li));
      li.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(li); } });
    });
  }
  function setupDeadline(host) {
    if (host.dataset.ready) return; host.dataset.ready = '1';
    const range = document.createElement('input'); range.type = 'range'; range.min = '0'; range.max = '200'; range.value = '140'; range.step = '10';
    range.setAttribute('aria-label', 'Thời điểm ảnh hoàn thành, ms');
    const result = document.createElement('p'); result.setAttribute('role', 'status');
    const update = () => { const t = Number(range.value);
      result.textContent = `Hoàn thành ${t} ms; deadline 100 ms: ${t <= 100 ? 'đúng hạn, được phát' : 'muộn, bị loại'}. Ví dụ minh họa.`; };
    range.addEventListener('input', update); host.append(range, result); update();
  }
  // --- Persona: the "Bạn là ai?" choice selects a reading roadmap (not a login). ---
  const PEOPLE = { hieu: 'Hiếu', vinh: 'Vinh', manh: 'Mạnh', truong: 'Trường', khanh: 'Khánh' };
  const CN_ONLY = ['manh', 'truong'];
  const OS_PATH = /\/(sessions\/0[34]-[^/]+|defence\/os|demo\/os)\/?(index\.html)?$/;
  function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } }
  function homeHref() { const a = document.querySelector('.md-header__button.md-logo'); return a ? a.getAttribute('href') : '/'; }
  function setupPersona() {
    const m = location.pathname.match(/\/roadmap\/(hieu|vinh|manh|truong|khanh)\/?/);
    if (m) store('oscn-persona', m[1]);
    const who = store('oscn-persona');
    if (!who || !PEOPLE[who]) return;
    if (CN_ONLY.includes(who)) {
      document.querySelectorAll('.md-nav a[href]').forEach(a => {
        if (OS_PATH.test(new URL(a.href, location.href).pathname)) {
          const top = a.closest('.md-nav--primary > .md-nav__list > .md-nav__item') || a.closest('.md-nav__item');
          if (top) top.style.display = 'none';
        }
      });
      document.querySelectorAll('.md-footer__link').forEach(a => {
        if (OS_PATH.test(new URL(a.href, location.href).pathname)) a.style.display = 'none';
      });
    }
    const inner = document.querySelector('.md-content__inner');
    if (inner && !inner.querySelector('.persona-bar')) {
      const bar = document.createElement('div'); bar.className = 'persona-bar';
      const scope = CN_ONLY.includes(who) ? ' · chỉ môn Mạng máy tính' : '';
      bar.innerHTML = `Lộ trình đang xem: <strong>${PEOPLE[who]}</strong>${scope} · <a href="${homeHref()}">Đổi người</a>`;
      inner.prepend(bar);
    }
  }
  // --- Click a figure to see it at full size (no resizing of technical screenshots). ---
  function setupZoom() {
    document.querySelectorAll('.md-content article img').forEach(img => {
      if (img.dataset.zoom || img.closest('a')) return; img.dataset.zoom = '1';
      img.classList.add('zoomable'); img.title = 'Bấm để phóng to';
      img.addEventListener('click', () => {
        const ov = document.createElement('div'); ov.className = 'zoom-overlay'; ov.setAttribute('role', 'dialog');
        const big = document.createElement('img'); big.src = img.currentSrc || img.src; big.alt = img.alt;
        const hint = document.createElement('p'); hint.textContent = 'Bấm hoặc nhấn Esc để đóng';
        ov.append(big, hint); document.body.append(ov);
        const close = () => { ov.remove(); document.removeEventListener('keydown', esc); };
        const esc = e => { if (e.key === 'Escape') close(); };
        ov.addEventListener('click', close); document.addEventListener('keydown', esc);
      });
    });
  }
  function init() {
    document.querySelectorAll('.quiz').forEach(setupQuiz);
    document.querySelectorAll('[data-oscn-deadline]').forEach(setupDeadline);
    setupPersona(); setupZoom();
  }
  if (typeof document$ !== 'undefined') document$.subscribe(init);
  else if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
