/* 글 모음 화면(종목 공부 · 투자 공부 · 계산기) — 목록(분류·검색·쪽). 글 한 편은 정적 쪽(/snap/…)으로 잇는다. 네트워크 0(데이터는 같은 사이트 js). */
(function () {
  'use strict';
  var G = window.Gaeo, esc = G.esc;
  var PAGE = 12;
  function render(opt) {
    var root = document.getElementById(opt.el);
    var data = Array.isArray(opt.data) ? opt.data : null;
    if (!data) { root.innerHTML = G.state('error', '글 목록 파일을 받지 못했어요', '잠시 뒤 다시 열어 보세요. 없는 글을 빈 목록으로 채우지 않아요.'); return; }
    /* 글 한 편은 빌드가 만든 정적 쪽(/snap/<묶음>/<번호>.html)에서 읽는다 — 검색엔진이 읽는 주소와 같다.
       옛 주소(?id=)로 들어오면 그 쪽으로 옮긴다. */
    var id = Number(G.param('id'));
    if (id) {
      var found = data.filter(function (x) { return x.id === id; })[0];
      if (found) { root.innerHTML = G.loading('글을 여는 중이에요'); location.replace(opt.staticBase + id + '.html'); return; }
      root.innerHTML = '<p class="note">이 글을 찾지 못했습니다. <a href="' + opt.base + '">목록으로</a></p>';
      return;
    }
    var state = { cat: G.param('cat'), q: '', page: 1 };
    var byId = {};
    data.forEach(function (x) { byId[x.id] = x; });
    function catLabel(key) { var c = (opt.cats || []).filter(function (x) { return x.key === key; })[0]; return c ? c.label : ''; }
    function href(x) { return opt.staticBase + x.id + '.html'; }
    /* 한 문장 요약 — 요약의 첫 문장만(길면 줄임). 본문은 바꾸지 않는다. */
    function oneLine(s) {
      s = String(s || ''); var m = /^(.+?[.!?])(\s|$)/.exec(s), t = m ? m[1] : s;
      return t.length > 92 ? t.slice(0, 90) + '…' : t;
    }
    function card(x) {
      var label = catLabel(x.cat);
      return '<article class="card art-card"><p class="ac-meta">' + (label ? G.chip('neutral', label) : '') + '<time datetime="' + esc(x.date) + '">' + esc(x.date) + '</time></p>' +
        '<a class="ac-title" href="' + href(x) + '">' + esc(x.name) + '</a><p class="ac-sub">' + esc(oneLine(x.summary)) + '</p>' +
        (/^\d{6}$/.test(x.code || '') ? '<a class="ac-link" href="/company/' + esc(x.code) + '/">이 회사의 공시·재무 변화 보기 →</a>' : '') + '</article>';
    }
    /* 처음이라면 여기부터 — 페이지마다 사람이 고른 글 번호(opt.start.ids)나 링크(opt.start.links)만 보여 준다. */
    function startHere() {
      var s = opt.start;
      if (!s) return '';
      var items = (s.ids || []).map(function (id) { return byId[id]; }).filter(Boolean)
        .map(function (x) { return '<li><a href="' + href(x) + '">' + esc(x.name) + '</a></li>'; })
        .concat((s.links || []).map(function (l) { return '<li><a href="' + esc(l[0]) + '">' + esc(l[1]) + '</a></li>'; }));
      return '<section class="start-here" aria-labelledby="start-h"><h2 id="start-h">처음이라면 여기부터</h2><p>' + esc(s.note || '') + '</p>' +
        (items.length ? '<ol>' + items.join('') + '</ol>' : '') + '</section>';
    }
    function draw() {
      var q = state.q.trim();
      var list = data.filter(function (x) { return (!state.cat || x.cat === state.cat) && (!q || (x.name + ' ' + (x.tag || '') + ' ' + (x.summary || '')).indexOf(q) >= 0); });
      var pages = Math.max(1, Math.ceil(list.length / PAGE));
      if (state.page > pages) state.page = pages;
      var catsHtml = (opt.cats || []).length ? '<div class="tabs" role="group" aria-label="분야 고르기">' + [{ key: '', label: '전체' }].concat(opt.cats).map(function (c) {
        return '<button type="button" aria-pressed="' + (state.cat === c.key) + '" data-cat="' + esc(c.key) + '">' + esc(c.label) + '</button>';
      }).join('') + '</div>' : '';
      var fresh = !state.cat && !q && state.page === 1;
      root.innerHTML = (fresh ? startHere() : '') + catsHtml +
        '<div class="search" role="search"><input id="art-q" placeholder="제목·내용 검색" aria-label="글 검색" value="' + esc(state.q) + '"></div>' +
        '<p class="meta" aria-live="polite">' + (list.length ? list.length + '개' : '찾는 글이 없어요. 다른 낱말로 찾거나 분야를 「전체」로 바꿔 보세요.') + '</p>' +
        '<div class="grid two">' + list.slice((state.page - 1) * PAGE, state.page * PAGE).map(card).join('') + '</div>' +
        (pages > 1 ? '<div class="pager"><button type="button" data-p="-1"' + (state.page <= 1 ? ' disabled' : '') + '>이전</button><span class="meta">' + state.page + ' / ' + pages + '</span><button type="button" data-p="1"' + (state.page >= pages ? ' disabled' : '') + '>다음</button></div>' : '');
      Array.prototype.forEach.call(root.querySelectorAll('[data-cat]'), function (b) { b.onclick = function () { state.cat = b.getAttribute('data-cat'); state.page = 1; draw(); }; });
      Array.prototype.forEach.call(root.querySelectorAll('[data-p]'), function (b) { b.onclick = function () { state.page += Number(b.getAttribute('data-p')); draw(); window.scrollTo(0, 0); }; });
      var input = document.getElementById('art-q');
      input.oninput = function () { state.q = input.value; state.page = 1; var pos = input.selectionStart; draw(); var again = document.getElementById('art-q'); again.focus(); again.setSelectionRange(pos, pos); };
    }
    draw();
  }
  window.GaeoArticles = { render: render };
})();
