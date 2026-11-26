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
  function init() {
    document.querySelectorAll('.quiz').forEach(setupQuiz);
    document.querySelectorAll('[data-oscn-deadline]').forEach(setupDeadline);
  }
  if (typeof document$ !== 'undefined') document$.subscribe(init);
  else if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
