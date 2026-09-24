/* 기업 리서치 화면 — dart_today.js 와 disclosure_research/*.json 을 읽어 네 화면을 그린다.
   읽는 순서(소유자 지시 2026-09-24): 무슨 일이 있었어? → 왜 볼 필요가 있어? → 아직 모르는 건? → 다음에 확인할 건? → DART에서 직접 보기.
   원칙: 공시 사실만. 매수·매도·저평가 같은 판단 어휘를 만들지 않는다.
   결측은 0이 아니다: NOT_COLLECTED(아직 못 받음) · NOT_APPLICABLE(그 회사에 없는 항목) · 못 찾음은 '안 함(미실행)'이 아니다. */
(function () {
  'use strict';
  var G = window.Gaeo;
  var esc = G.esc;
  var DIR = '/disclosure_research/';
  var SCHEMA = 'gaeo_disclosure_research_v1', CONTRACT = 'disclosure-research-public-v1';
  var cache = {}, contract = null, current = { tab: 'today', code: '' };
  var $ = function (id) { return document.getElementById(id); };

  function link(u, label) {
    return (typeof u === 'string' && u.indexOf('https://') === 0)
      ? '<a href="' + esc(u) + '" target="_blank" rel="noopener">' + esc(label || 'DART에서 직접 보기') + '</a>'
      : '<span class="meta">원문 링크 없음</span>';
  }
  function eok(v) {
    if (typeof v !== 'number') return '<span class="meta">' + esc(v === 'NOT_COLLECTED' ? '아직 못 받음' : v === 'NOT_APPLICABLE' ? '해당 없음' : v) + '</span>';
    var e = v / 1e8, s = Math.abs(e) >= 100 ? Math.round(e).toLocaleString('ko-KR') : (Math.round(e * 10) / 10).toLocaleString('ko-KR');
    return (v < 0 ? '<span class="neg">' : '<span>') + s + '억</span>';
  }
  function pct(c) {
    if (!c) return '';
    if (typeof c.pct === 'number') return (c.pct > 0 ? '+' : '') + c.pct + '%';
    return c.pctReason === 'prior_zero_or_negative' ? '전년이 0 이하라 증감률 안 셈' : '—';
  }
  function load(kind) {
    if (cache[kind]) return Promise.resolve(cache[kind]);
    return fetch(DIR + kind + '.json', { cache: 'no-cache' })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function (d) {
        if (!d || d.schemaVersion !== SCHEMA || d.contractVersion !== CONTRACT || (kind !== 'contract' && d.kind !== kind)) throw new Error('자료 형식이 약속과 다름');
        cache[kind] = d; return d;
      });
  }
  function fail(el, err) {
    el.innerHTML = '<p class="note">자료를 받지 못했습니다(' + esc(err && err.message) + '). 없는 자료를 0이나 "이상 없음"으로 채우지 않습니다.</p>';
  }
  function nameOf(code) { return (contract && contract.companyNames && contract.companyNames[code]) || code; }
  function resolveCode(q) {
    q = String(q || '').trim(); if (!q) return '';
    if (/^\d{6}$/.test(q)) return q;
    var names = (contract && contract.companyNames) || {}, hit = '';
    Object.keys(names).forEach(function (c) { if (!hit && names[c] === q) hit = c; });
    Object.keys(names).forEach(function (c) { if (!hit && names[c] && names[c].indexOf(q) >= 0) hit = c; });
    return hit || q;
  }
  function qa(parts) {
    return '<dl class="qa">' + parts.filter(function (p) { return p[1]; }).map(function (p) {
      return '<dt>' + esc(p[0]) + '</dt><dd>' + p[1] + '</dd>';
    }).join('') + '</dl>';
  }
  function ul(items) { return items.length ? '<ul>' + items.map(function (x) { return '<li>' + x + '</li>'; }).join('') + '</ul>' : ''; }
  function openCompany(el) {
    Array.prototype.forEach.call(el.querySelectorAll('[data-code]'), function (li) {
      li.addEventListener('click', function (e) { e.preventDefault(); $('q').value = li.getAttribute('data-code'); show(); window.scrollTo(0, 0); });
    });
  }

  /* 오늘의 공시 */
  function renderToday(code) {
    var el = $('view-today');
    if (typeof DART_TODAY === 'undefined' || !DART_TODAY || !Array.isArray(DART_TODAY.items)) { fail(el, new Error('오늘의 공시 파일 없음')); return; }
    var items = DART_TODAY.items.filter(function (it) { return !code || it.code === code; });
    var head = '<p class="meta">모은 시각 ' + esc(DART_TODAY.generatedAt) + ' · ' + esc(DART_TODAY.priceLabel || '') + '</p>';
    if (code && !items.length) {
      el.innerHTML = head + '<p class="note">' + esc(nameOf(code)) + '(' + esc(code) + '): 최근 며칠 사이 모은 공시 목록에 없습니다. 공시가 없었다는 확정은 아닙니다 — 「공시 변화」 탭에서 더 긴 기간을 보세요.</p>';
      return;
    }
    el.innerHTML = head + '<ul class="list">' + items.slice(0, 120).map(function (it) {
      return '<li><a href="?code=' + esc(it.code) + '" data-code="' + esc(it.code) + '"><b>' + esc(it.name) + '</b></a> ' +
        (it.isCorrection ? '<span class="tag">정정</span>' : '') + esc(it.title) +
        ' <span class="meta">' + esc(G.ymd(it.receiptDate)) + ' · ' + link(G.dartUrl(it.rceptNo)) + '</span></li>';
    }).join('') + '</ul>' + (items.length > 120 ? '<p class="meta">이 밖에 ' + (items.length - 120) + '건은 회사를 골라 보세요.</p>' : '');
    openCompany(el);
  }

  /* 공시 변화 */
  function renderChanges(d, code) {
    var el = $('view-changes'), cats = d.categories || {}, w = d.windows || {};
    var head = '<p class="meta">최근 ' + esc(w.recent && w.recent.days) + '일(' + esc(w.recent && w.recent.from) + '~' + esc(w.recent && w.recent.to) + ')과 그 전 같은 기간을 견줍니다' +
      (w.prior && w.prior.fullyCovered === false ? ' · 그 전 기간은 자료가 모자라 견주지 않음' : '') + ' · 자료 시작 ' + esc(w.coverageFrom) + '</p>';
    if (!code) {
      var rows = Object.keys(d.companies || {}).map(function (k) { return { code: k, c: d.companies[k] }; })
        .sort(function (a, b) { return String(b.c.latestReceivedOn).localeCompare(String(a.c.latestReceivedOn)) || a.code.localeCompare(b.code); }).slice(0, 80);
      el.innerHTML = head + '<p class="small">최근에 공시를 낸 회사 순서(80곳). 회사를 누르면 자세히 봅니다.</p><ul class="list">' + rows.map(function (r) {
        var ch = (r.c.changes || []).slice(0, 2).map(function (x) { return esc(x.text); }).join(' / ');
        return '<li><a href="?code=' + esc(r.code) + '" data-code="' + esc(r.code) + '"><b>' + esc(r.c.name || r.code) + '</b></a> <span class="meta">최근 ' + esc(r.c.latestReceivedOn) + ' · 공시 ' + esc(r.c.filingCount) + '건</span>' + (ch ? '<br><span class="small">' + ch + '</span>' : '') + '</li>';
      }).join('') + '</ul>';
      openCompany(el); return;
    }
    var c = d.companies && d.companies[code];
    if (!c) { el.innerHTML = head + '<p class="note">' + esc(nameOf(code)) + '(' + esc(code) + '): 이 자료 기간에 모은 공시가 없습니다. 공시가 없었다는 확정은 아닙니다(아직 못 모았을 수 있음).</p>'; return; }
    var seen = {}, why = [], unknown = [], next = [];
    (c.changes || []).forEach(function (x) {
      var cat = cats[x.category];
      if (cat && cat.howToRead && !seen[x.category]) {
        seen[x.category] = 1;
        why.push('<b>' + esc(cat.label) + '</b>: ' + esc(cat.howToRead.why));
        unknown.push('<b>' + esc(cat.label) + '</b>: ' + esc(cat.howToRead.counter));
        next.push('<b>' + esc(cat.label) + '</b>: ' + esc(cat.howToRead.next));
      }
    });
    var happened = (c.changes || []).map(function (x) { return esc(x.text); });
    if (!happened.length) happened = ['최근 기간과 그 전 기간 사이에 공시 종류·건수 변화가 없었습니다(공시가 없다는 뜻은 아닙니다).'];
    var filings = (c.filings || []).map(function (f) {
      var label = cats[f.category] ? cats[f.category].label : f.category;
      return (f.isCorrection ? '<span class="tag">정정 · ' + esc(f.correctionKind || '정정') + '</span>' : '') + (label ? '<span class="tag">' + esc(label) + '</span>' : '') +
        esc(f.title) + ' <span class="meta">' + esc(f.receivedOn) + '</span> · ' + link(f.url);
    });
    el.innerHTML = head + '<div class="card"><h3>' + esc(c.name || code) + ' <span class="meta">' + esc(code) + '</span></h3>' +
      '<p class="meta">모은 공시 ' + esc(c.filingCount) + '건 · 가장 최근 ' + esc(c.latestReceivedOn) + ' · 최근 기간 ' + esc(c.recentCount) + '건 · 그 전 기간 ' + (c.priorCount == null ? '견주지 않음' : esc(c.priorCount) + '건') + '</p>' +
      qa([['무슨 일이 있었어?', ul(happened)], ['왜 볼 필요가 있어?', ul(why)], ['아직 모르는 건?', ul(unknown.length ? unknown : ['공시 제목만으로는 금액·수량·일정을 모릅니다. 원문에서 확인해야 합니다.'])],
          ['다음에 확인할 건?', ul(next.length ? next : ['원문에서 결정 내용과 일정을 읽고, 뒤이어 나오는 결과 공시를 확인합니다.'])],
          ['DART에서 직접 보기', ul(filings) + (c.filingsTruncated ? '<p class="meta">이 밖에 ' + esc(c.filingsTruncated) + '건은 DART에서 회사 이름으로 찾아보세요.</p>' : '')]]) +
      '<p class="meta">출처: OpenDART 공시 목록 · 접수일 기준 · ' + esc(G.kst(d.generatedAt)) + ' 생성</p></div>';
  }

  /* 재무 변화 */
  function renderFinancial(d, code) {
    var el = $('view-financial');
    var head = '<p class="meta">사업보고서(1년치)의 표준 계정 · 단위 억원 · 자료 받은 회사 ' + esc(d.coverage.companiesCollected) + '곳 / 추적 ' + esc(d.coverage.trackedCompanies) + '곳</p>';
    var h = d.howToRead || {};
    if (!code) {
      el.innerHTML = head + '<p class="small">위 검색창에 회사 이름이나 종목코드를 넣고 「보기」를 누르세요.</p>' +
        qa([['무엇을 보여 주나요?', esc(h.why)], ['아직 모르는 건?', esc(h.counter)], ['다음에 확인할 건?', esc(h.next)],
            ['표를 읽는 규칙', ul((d.method || []).map(esc))]]);
      return;
    }
    var c = d.companies && d.companies[code];
    if (!c) {
      var nc = (d.notCollectedTickers || []).indexOf(code) >= 0;
      el.innerHTML = head + '<p class="note">' + esc(nameOf(code)) + '(' + esc(code) + '): ' + (nc ? '아직 재무 자료를 받지 못했습니다(NOT_COLLECTED). 재무가 없다는 뜻이 아닙니다.' : '이 자료에 기록이 없습니다.') + '</p>';
      return;
    }
    var years = (c.periods || []).map(function (p) { return p.year; });
    var pairs = c.comparablePairs || [], lastPair = pairs[pairs.length - 1];
    var table = '<div class="tbl"><table><thead><tr><th>항목</th>' + years.map(function (y) { return '<th>' + esc(y) + '</th>'; }).join('') + '<th>바뀐 정도</th></tr></thead><tbody>';
    var happened = [];
    (c.rows || []).forEach(function (r) {
      var ch = lastPair && r.changes && r.changes[lastPair.to];
      if (ch && typeof ch.pct === 'number' && Math.abs(ch.pct) >= 20) happened.push(esc(r.label) + '이(가) ' + esc(lastPair.from) + '년보다 ' + esc(lastPair.to) + '년에 ' + (ch.pct > 0 ? '늘었습니다' : '줄었습니다') + ' (' + esc(pct(ch)) + ').');
      table += '<tr><td>' + esc(r.label) + '</td>' + years.map(function (y) {
        if (r.values && y in r.values) return '<td>' + eok(r.values[y]) + '</td>';
        return '<td class="meta">' + ((r.missing || []).indexOf(y) >= 0 ? '항목 못 찾음' : '—') + '</td>';
      }).join('') + '<td>' + (ch ? eok(ch.abs) + ' (' + esc(pct(ch)) + ')' : '<span class="meta">견주지 않음</span>') + '</td></tr>';
    });
    table += '</tbody></table></div>';
    if (!happened.length) happened.push(lastPair ? '가장 최근 두 해 사이에 20% 넘게 바뀐 항목은 없습니다.' : '같은 기준(연결/별도)으로 견줄 수 있는 두 해가 없습니다.');
    el.innerHTML = head + '<div class="card"><h3>' + esc(c.name || code) + ' <span class="meta">' + esc(code) + ' · ' + esc(c.fsDivLabel || c.fsDiv) + '</span></h3>' +
      qa([['무슨 일이 있었어?', ul(happened)], ['왜 볼 필요가 있어?', esc(h.why)], ['아직 모르는 건?', esc(h.counter) + (c.notes && c.notes.length ? ul(c.notes.map(esc)) : '')],
          ['다음에 확인할 건?', esc(h.next)], ['DART에서 직접 보기', 'DART에서 회사 이름으로 「사업보고서」를 찾아 재무제표와 주석을 읽어 보세요. ' + link('https://dart.fss.or.kr/', 'DART 열기')]]) +
      table + '<p class="meta">출처: OpenDART 단일회사 전체 재무제표 · ' + esc(G.kst(d.generatedAt)) + ' 생성</p></div>';
  }

  /* 사건 흐름 */
  var STAGE = { PLANNED: '발표', FILED: '진행 자료', IN_PROGRESS: '진행 자료', REPORTED: '결과 보고', COMPLETED: '완료' };
  function renderTimeline(d, code) {
    var el = $('view-timeline');
    var head = '<p class="meta">공시 제목으로 「결정 → 진행 → 결과 → 완료」를 잇습니다 · 흐름이 있는 회사 ' + esc(d.coverage.companiesWithTimelines) + '곳</p>';
    if (!code) {
      var rows = Object.keys(d.companies || {}).map(function (k) {
        var t = d.companies[k].timelines || [];
        return { code: k, name: d.companies[k].name, n: t.length, latest: t.map(function (x) { return x.latestReceivedOn; }).sort().pop() };
      }).sort(function (a, b) { return String(b.latest).localeCompare(String(a.latest)); }).slice(0, 80);
      el.innerHTML = head + qa([['읽을 때 주의', ul((d.limits || []).map(esc))]]) + '<ul class="list">' + rows.map(function (r) {
        return '<li><a href="?code=' + esc(r.code) + '" data-code="' + esc(r.code) + '"><b>' + esc(r.name || r.code) + '</b></a> <span class="meta">흐름 ' + r.n + '개 · 최근 ' + esc(r.latest) + '</span></li>';
      }).join('') + '</ul>';
      openCompany(el); return;
    }
    var c = d.companies && d.companies[code];
    if (!c) { el.innerHTML = head + '<p class="note">' + esc(nameOf(code)) + '(' + esc(code) + '): 이 자료 기간에 이어지는 공시를 찾지 못했습니다. 사건이 없었다는 뜻은 아닙니다.</p>'; return; }
    var html = head + '<div class="card"><h3>' + esc(c.name || code) + ' <span class="meta">' + esc(code) + '</span></h3>';
    (c.timelines || []).forEach(function (t) {
      var chain = (d.chains || {})[t.chain] || {}, h = chain.howToRead || {};
      var happened = (t.items || []).map(function (i) {
        return esc(i.receivedOn) + ' — ' + esc(i.stageLabel) + ' 공시가 나왔습니다' + (i.isCorrection ? ' <span class="tag">정정</span>' : '') + '. <span class="small">(' + esc(i.title) + ')</span>';
      });
      var unknown = (t.stagesNotFound || []).map(function (s) { return esc(s.stageLabel) + '은(는) 아직 확인되지 않았습니다. 안 했다는 뜻(미실행)이 아니라 못 찾은 것입니다.'; });
      if (h.counter) unknown.push(esc(h.counter));
      html += '<h3>' + esc(t.label) + '</h3><p class="meta">지금 확인된 단계: <span class="tag strong">' + esc(STAGE[t.latestStage] || t.latestStage) + '</span> 최근 ' + esc(t.latestReceivedOn) + '</p>' +
        qa([['무슨 일이 있었어?', ul(happened)], ['왜 볼 필요가 있어?', esc(h.why)], ['아직 모르는 건?', ul(unknown)], ['다음에 확인할 건?', esc(h.next)],
            ['DART에서 직접 보기', ul((t.items || []).map(function (i) { return esc(i.stageLabel) + ' · ' + link(i.url); }))]]);
    });
    el.innerHTML = html + '<p class="meta">출처: OpenDART 공시 목록 제목·접수번호·접수일 · ' + esc(G.kst(d.generatedAt)) + ' 생성</p></div>';
  }

  function show() {
    current.code = resolveCode($('q').value);
    ['today', 'changes', 'financial', 'timeline'].forEach(function (t) { $('view-' + t).classList.toggle('hidden', t !== current.tab); });
    if (current.tab === 'today') { renderToday(current.code); return; }
    var kind = { changes: 'disclosure_changes', financial: 'financial_changes', timeline: 'event_timelines' }[current.tab];
    var el = $('view-' + current.tab);
    el.innerHTML = '<p class="meta">불러오는 중…</p>';
    load(kind).then(function (d) {
      if (current.tab === 'changes') renderChanges(d, current.code);
      else if (current.tab === 'financial') renderFinancial(d, current.code);
      else renderTimeline(d, current.code);
    }).catch(function (e) { fail(el, e); });
  }
  Array.prototype.forEach.call(document.querySelectorAll('.tabs [role="tab"]'), function (b) {
    b.addEventListener('click', function () {
      Array.prototype.forEach.call(document.querySelectorAll('.tabs [role="tab"]'), function (x) { x.setAttribute('aria-selected', x === b ? 'true' : 'false'); });
      current.tab = b.getAttribute('data-tab'); show();
    });
  });
  $('go').addEventListener('click', show);
  $('clear').addEventListener('click', function () { $('q').value = ''; show(); });
  $('q').addEventListener('keydown', function (e) { if (e.key === 'Enter') show(); });

  var initial = G.param('code');
  if (initial) $('q').value = initial;
  load('contract').then(function (c) {
    contract = c;
    $('asOf').textContent = '기준일 ' + c.asOf + ' · 만든 시각 ' + G.kst(c.generatedAt) + ' (한국시간) · 추적 회사 ' + Object.keys(c.companyNames || {}).length + '곳';
    var dl = $('companies'), names = c.companyNames || {};
    Object.keys(names).sort().forEach(function (code) { var o = document.createElement('option'); o.value = names[code]; o.label = code; dl.appendChild(o); });
    if (initial) {  // 회사를 골라 들어오면 공시 변화부터 보여 준다
      current.tab = 'changes';
      Array.prototype.forEach.call(document.querySelectorAll('.tabs [role="tab"]'), function (x) { x.setAttribute('aria-selected', x.getAttribute('data-tab') === 'changes' ? 'true' : 'false'); });
    }
    show();
  }).catch(function (e) {
    $('asOf').textContent = '자료 약속 파일을 받지 못했습니다(' + (e && e.message) + ') — 자료 없이 화면을 채우지 않습니다.';
    show();
  });
})();
