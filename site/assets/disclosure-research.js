/* 기업 리서치 화면 — dart_today.js · assets/research-summary.json(빌드가 만든 작은 요약) · disclosure_research/*.json 을 읽는다.
   회사를 고르면: 회사 한눈에 보기(요약 파일만) → 탭을 누를 때 그 탭 자료만 받는다(큰 파일을 한꺼번에 받지 않는다).
   읽는 순서(소유자 지시 2026-09-24): 무슨 일이 있었어? → 왜 볼 필요가 있어? → 아직 모르는 건? → 다음에 확인할 건? → DART에서 직접 보기.
   원칙: 공시 사실만. 매수·매도·저평가 같은 판단 어휘를 만들지 않는다. 색으로 좋고 나쁨을 말하지 않는다.
   결측은 0이 아니다: NOT_COLLECTED(아직 못 받음) · NOT_APPLICABLE(그 회사에 없는 항목) · 못 찾음은 '안 함(미실행)'이 아니다. */
(function () {
  'use strict';
  var G = window.Gaeo;
  var esc = G.esc;
  var DIR = '/disclosure_research/', SUMMARY = '/assets/research-summary.json';
  var SCHEMA = 'gaeo_disclosure_research_v1', CONTRACT = 'disclosure-research-public-v1';
  var TABS = ['today', 'changes', 'financial', 'timeline'];
  var KIND = { changes: 'disclosure_changes', financial: 'financial_changes', timeline: 'event_timelines' };
  var KEY_ACCOUNTS = ['revenue', 'operatingIncome', 'netIncome', 'operatingCashFlow'];
  var cache = {}, contract = null, summary = null, summaryFailed = false, current = { tab: 'today', code: '' };
  var $ = function (id) { return document.getElementById(id); };
  var dartOk = typeof DART_TODAY !== 'undefined' && DART_TODAY && Array.isArray(DART_TODAY.items);

  function link(u, label) {
    return (typeof u === 'string' && u.indexOf('https://') === 0)
      ? '<a href="' + esc(u) + '" target="_blank" rel="noopener">' + esc(label || 'DART에서 직접 보기') + ' ↗</a>'
      : '<span class="meta">원문 링크 없음</span>';
  }
  function dartSearch(name) { return 'https://dart.fss.or.kr/dsab007/main.do?option=corp&textCrpNm=' + encodeURIComponent(name || ''); }
  /* 금액: 조·억·만 원 단위를 칸마다 적는다. 음수는 빨강이 아니라 "−" 기호로. */
  function krw(v) {
    if (typeof v !== 'number') return v === 'NOT_COLLECTED' ? '아직 못 받음' : v === 'NOT_APPLICABLE' ? '해당 없음' : '—';
    var a = Math.abs(v), s = v < 0 ? '−' : '';
    if (a >= 1e12) return s + (a / 1e12).toLocaleString('ko-KR', { maximumFractionDigits: 1 }) + '조';
    if (a >= 1e8) return s + Math.round(a / 1e8).toLocaleString('ko-KR') + '억';
    if (a >= 1e4) return s + Math.round(a / 1e4).toLocaleString('ko-KR') + '만';
    return s + a.toLocaleString('ko-KR') + '원';
  }
  function pct(c) {
    if (!c) return '';
    if (typeof c.pct === 'number') return (c.pct > 0 ? '+' : c.pct < 0 ? '−' : '') + Math.abs(c.pct) + '%';
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
  function loadSummary() {
    return fetch(SUMMARY, { cache: 'no-cache' })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function (d) { if (!d || d.schema !== 'gaeo-research-summary-v1') throw new Error('요약 형식이 약속과 다름'); summary = d; })
      .catch(function () { summaryFailed = true; });
  }
  function fail(el, err) {
    el.innerHTML = G.state('error', '자료 파일을 받지 못했어요', '받지 못한 이유: ' + esc(err && err.message) + '. 없는 자료를 0이나 "이상 없음"으로 채우지 않아요. 잠시 뒤 다시 열어 보세요.');
  }
  function nameOf(code) { return (contract && contract.companyNames && contract.companyNames[code]) || code; }
  function tracked(code) { return !!(contract && contract.companyNames && contract.companyNames[code]); }
  function resolveCode(q) {
    q = String(q || '').trim(); if (!q) return '';
    if (/^\d{6}$/.test(q)) return q;
    var names = (contract && contract.companyNames) || {}, hit = '';
    Object.keys(names).forEach(function (c) { if (!hit && names[c] === q) hit = c; });
    Object.keys(names).forEach(function (c) { if (!hit && names[c] && names[c].indexOf(q) >= 0) hit = c; });
    return hit || q;
  }
  /* 읽는 순서 사다리. parts: [질문, html, 종류(fact|why|unknown|next|source)] */
  function ladder(parts) {
    return '<ol class="ladder">' + parts.filter(function (p) { return p[1]; }).map(function (p) {
      return '<li class="rung-' + p[2] + '"><p class="rung-q">' + esc(p[0]) + '</p><div class="rung-body">' + p[1] + '</div></li>';
    }).join('') + '</ol>';
  }
  function ul(items) { return items.length ? '<ul>' + items.map(function (x) { return '<li>' + x + '</li>'; }).join('') + '</ul>' : ''; }
  function panelHead(code, extra) {
    return '<div class="panel-title"><h3>' + esc(nameOf(code)) + '</h3><span class="meta">' + esc(code) + (extra ? ' · ' + extra : '') + '</span></div>';
  }
  function todayPeriod() {
    var ds = dartOk ? DART_TODAY.items.map(function (it) { return G.ymd(it.receiptDate); }).sort() : [];
    return ds.length ? ds[0] + ' ~ ' + ds[ds.length - 1] : '';
  }
  function openCompany(el) {
    Array.prototype.forEach.call(el.querySelectorAll('[data-code]'), function (a) {
      a.addEventListener('click', function (e) { e.preventDefault(); $('q').value = a.getAttribute('data-code'); search(); });
    });
  }

  /* 회사 한눈에 보기 — 요약 파일과 오늘의 공시만 쓴다 */
  function sumCard(key, title, tab, chipHtml, lines) {
    return '<article class="card summary-card"><h3><span class="sc-key" aria-hidden="true">' + key + '</span>' + esc(title) + ' ' + chipHtml + '</h3>' +
      lines.map(function (p) { return '<p>' + p + '</p>'; }).join('') +
      '<button type="button" class="btn btn-outline" data-open-tab="' + tab + '">자세히 보기</button></article>';
  }
  function changeText(c) { return c ? pct(c) : '견주지 않음'; }
  function renderOverview(code) {
    var el = $('overview');
    if (!code) { el.classList.add('hidden'); el.innerHTML = ''; return; }
    el.classList.remove('hidden');
    if (!/^\d{6}$/.test(code) || !tracked(code)) {
      el.innerHTML = G.state('na', '「' + code + '」에 맞는 회사를 추적 목록에서 찾지 못했어요',
        'GAEO는 지금 ' + Object.keys((contract && contract.companyNames) || {}).length + '개 회사의 공시를 모아요. 이름을 다시 확인하거나 ' + link(dartSearch(code), 'DART에서 직접 찾아보기') + '.');
      return;
    }
    var name = nameOf(code), s = summary && summary.companies && summary.companies[code];
    var cards = [];
    /* A 최근 공시 */
    var mine = dartOk ? DART_TODAY.items.filter(function (it) { return it.code === code; }) : [];
    if (!dartOk) cards.push(sumCard('A', '최근 공시', 'today', G.chip('unknown', '못 받음'), ['최근 공시 목록 파일을 받지 못했어요.']));
    else if (mine.length) cards.push(sumCard('A', '최근 공시', 'today', G.chip('fact', '확인됨'),
      ['최근 접수분(' + esc(todayPeriod()) + ')에 ' + mine.length + '건', '가장 최근 ' + esc(G.ymd(mine[0].receiptDate)) + ' · 「' + esc(mine[0].title) + '」']));
    else cards.push(sumCard('A', '최근 공시', 'today', G.chip('na', '목록에 없음'),
      ['최근 접수분(' + esc(todayPeriod()) + ') 목록에 이 회사 공시가 없어요.', '공시가 없었다는 확정은 아니에요 — 「공시 변화」에서 더 긴 기간을 보세요.']));
    /* B 공시 변화 · C 재무 변화 · D 사건 흐름 — 요약 파일 */
    if (summaryFailed || !summary) {
      var msg = summaryFailed ? ['요약 파일을 받지 못했어요. 「자세히 보기」로 원래 자료를 열 수 있어요.'] : ['요약을 불러오고 있어요.'];
      var ch = summaryFailed ? G.chip('unknown', '못 받음') : G.chip('info', '불러오는 중');
      cards.push(sumCard('B', '공시 변화', 'changes', ch, msg), sumCard('C', '재무 변화', 'financial', ch, msg), sumCard('D', '사건 흐름', 'timeline', ch, msg));
    } else {
      var c = s && s.changes;
      cards.push(c ? sumCard('B', '공시 변화', 'changes', G.chip('fact', '확인됨'),
        ['모은 공시 ' + esc(c.filingCount) + '건 · 가장 최근 ' + esc(c.latestReceivedOn), esc((c.lines && c.lines[0]) || '최근 기간과 그 전 기간 사이에 공시 종류·건수 변화가 없었어요.')])
        : sumCard('B', '공시 변화', 'changes', G.chip('na', '모은 공시 없음'), ['이 자료 기간에 모은 공시가 없어요.', '공시가 없었다는 확정은 아니에요(아직 못 모았을 수 있어요).']));
      var f = s && s.financial;
      if (!f) cards.push(sumCard('C', '재무 변화', 'financial', G.chip('na', '기록 없음'), ['이 자료에 재무 기록이 없어요.']));
      else if (f.state === 'NOT_COLLECTED') cards.push(sumCard('C', '재무 변화', 'financial', G.chip('unknown', '아직 못 받음'),
        ['재무 자료를 아직 받지 못했어요(NOT_COLLECTED).', '재무가 없다는 뜻이 아니에요. 하루에 몇십 곳씩 차례로 채워요.']));
      else cards.push(sumCard('C', '재무 변화', 'financial', G.chip('fact', '확인됨'), f.from
        ? [esc(f.basis || '') + ' · ' + esc(f.from) + '년 → ' + esc(f.to) + '년', (f.rows || []).map(function (r) { return esc(r.label) + ' ' + esc(changeText(r.change)); }).join(' · ')]
        : ['같은 기준(연결/별도)으로 견줄 수 있는 두 해가 없어요.']));
      var t = s && s.timelines;
      cards.push(t ? sumCard('D', '사건 흐름', 'timeline', G.chip('fact', '확인됨'),
        ['이어진 흐름 ' + esc(t.count) + '개', esc(t.items[0].label) + ' — 지금 확인된 단계 「' + esc(t.items[0].stageLabel) + '」(' + esc(t.items[0].latestReceivedOn) + ')'])
        : sumCard('D', '사건 흐름', 'timeline', G.chip('na', '흐름 없음'), ['이어지는 공시 흐름을 찾지 못했어요.', '사건이 없었다는 뜻은 아니에요.']));
    }
    el.innerHTML = '<div class="card"><div class="overview-head"><h2 id="ov-title">' + esc(name) + '</h2>' + G.chip('neutral', code) + '</div>' +
      '<p class="overview-meta"><span>자료 기준일 ' + esc((summary && summary.asOf) || (contract && contract.asOf) || '') + '</span>' + link(dartSearch(name), 'DART에서 이 회사 공시 검색') + '</p>' +
      '<p class="meta">DART 검색 화면이 회사 이름이 입력된 채로 열려요. 검색을 누르면 원문 목록이 나와요.</p></div>' +
      '<div class="grid two">' + cards.join('') + '</div>';
    Array.prototype.forEach.call(el.querySelectorAll('[data-open-tab]'), function (b) {
      b.addEventListener('click', function () { selectTab(b.getAttribute('data-open-tab'), true); });
    });
  }

  /* 오늘의 공시 · 최근 공시 */
  function renderToday(code) {
    var el = $('view-today');
    if (!dartOk) { fail(el, new Error('오늘의 공시 파일 없음')); return; }
    var items = DART_TODAY.items.filter(function (it) { return !code || it.code === code; });
    var head = '<p class="meta">공시 접수 ' + esc(todayPeriod()) + ' · 모은 시각 ' + esc(DART_TODAY.generatedAt) + ' · 하루 두 번 갱신</p>';
    if (code && !items.length) {
      el.innerHTML = head + G.state('na', '최근 접수분 목록에 이 회사 공시가 없어요', esc(nameOf(code)) + '(' + esc(code) + ') — 공시가 없었다는 확정은 아니에요. 「공시 변화」 탭에서 더 긴 기간을 보세요.');
      return;
    }
    el.innerHTML = head + '<ul class="list list-card">' + items.slice(0, 120).map(function (it) {
      return '<li><a href="?code=' + esc(it.code) + '" data-code="' + esc(it.code) + '"><b>' + esc(it.name) + '</b></a> ' +
        (it.isCorrection ? G.chip('neutral', '정정') : '') + esc(it.title) +
        '<br><span class="meta">' + esc(G.ymd(it.receiptDate)) + ' · ' + link(G.dartUrl(it.rceptNo), 'DART 원문') + '</span></li>';
    }).join('') + '</ul>' + (items.length > 120 ? '<p class="meta">이 밖에 ' + (items.length - 120) + '건은 회사를 골라 보세요.</p>' : '') +
      G.sourceBar('공시 목록(list.json) · 접수일 기준', '', 'https://dart.fss.or.kr/', 'DART 열기');
    openCompany(el);
  }

  /* 공시 변화 */
  function renderChanges(d, code) {
    var el = $('view-changes'), cats = d.categories || {}, w = d.windows || {};
    var head = '<p class="meta">최근 ' + esc(w.recent && w.recent.days) + '일(' + esc(w.recent && w.recent.from) + '~' + esc(w.recent && w.recent.to) + ')과 그 전 같은 기간을 견줘요' +
      (w.prior && w.prior.fullyCovered === false ? ' · 그 전 기간은 자료가 모자라 견주지 않음' : '') + ' · 자료 시작 ' + esc(w.coverageFrom) + '</p>';
    if (!code) {
      var rows = Object.keys(d.companies || {}).map(function (k) { return { code: k, c: d.companies[k] }; })
        .sort(function (a, b) { return String(b.c.latestReceivedOn).localeCompare(String(a.c.latestReceivedOn)) || a.code.localeCompare(b.code); }).slice(0, 80);
      el.innerHTML = head + '<p class="small">최근에 공시를 낸 회사 순서(80곳). 회사를 누르면 자세히 봅니다.</p><ul class="list list-card">' + rows.map(function (r) {
        var ch = (r.c.changes || []).slice(0, 2).map(function (x) { return esc(x.text); }).join(' / ');
        return '<li><a href="?code=' + esc(r.code) + '" data-code="' + esc(r.code) + '"><b>' + esc(r.c.name || r.code) + '</b></a> <span class="meta">최근 ' + esc(r.c.latestReceivedOn) + ' · 공시 ' + esc(r.c.filingCount) + '건</span>' + (ch ? '<br><span class="small">' + ch + '</span>' : '') + '</li>';
      }).join('') + '</ul>';
      openCompany(el); return;
    }
    var c = d.companies && d.companies[code];
    if (!c) {
      el.innerHTML = head + G.state('na', '이 자료 기간에 모은 공시가 없어요', esc(nameOf(code)) + '(' + esc(code) + ') — 공시가 없었다는 확정은 아니에요(아직 못 모았을 수 있어요).');
      return;
    }
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
    if (!happened.length) happened = ['최근 기간과 그 전 기간 사이에 공시 종류·건수 변화가 없었어요(공시가 없다는 뜻은 아니에요).'];
    var filings = (c.filings || []).map(function (f) {
      var label = cats[f.category] ? cats[f.category].label : f.category;
      return (f.isCorrection ? G.chip('neutral', '정정 · ' + (f.correctionKind || '정정')) : '') + (label ? G.chip('info', label) : '') +
        esc(f.title) + ' <span class="meta">' + esc(f.receivedOn) + '</span> · ' + link(f.url, 'DART 원문');
    });
    el.innerHTML = head + '<div class="card">' + panelHead(code, '모은 공시 ' + esc(c.filingCount) + '건 · 가장 최근 ' + esc(c.latestReceivedOn) + ' · 최근 기간 ' + esc(c.recentCount) + '건 · 그 전 기간 ' + (c.priorCount == null ? '견주지 않음' : esc(c.priorCount) + '건')) +
      ladder([['무슨 일이 있었어?', ul(happened), 'fact'], ['왜 볼 필요가 있어?', ul(why), 'why'],
              ['아직 모르는 건?', ul(unknown.length ? unknown : ['공시 제목만으로는 금액·수량·일정을 몰라요. 원문에서 확인해야 해요.']), 'unknown'],
              ['다음에 확인할 건?', ul(next.length ? next : ['원문에서 결정 내용과 일정을 읽고, 뒤이어 나오는 결과 공시를 확인해요.']), 'next'],
              ['DART에서 직접 보기', ul(filings) + (c.filingsTruncated ? '<p class="meta">이 밖에 ' + esc(c.filingsTruncated) + '건은 DART에서 회사 이름으로 찾아보세요.</p>' : ''), 'source']]) +
      G.sourceBar('공시 목록 · 접수일 기준', d.generatedAt, dartSearch(nameOf(code)), 'DART에서 원문 확인') + '</div>';
  }

  /* 재무 변화 — 핵심 변화 카드(크기 막대) 먼저, 숫자 표는 「숫자 자세히 보기」 */
  function finCard(r, periods, lastPair) {
    var labels = {}, mixed = false, first = null;
    periods.forEach(function (p) { labels[p.year] = p.fsDivLabel; if (first === null) first = p.fsDivLabel; else if (p.fsDivLabel !== first) mixed = true; });
    var years = periods.map(function (p) { return p.year; });
    var nums = years.map(function (y) { return r.values && (y in r.values) ? r.values[y] : undefined; });
    var max = 0;
    nums.forEach(function (v) { if (typeof v === 'number' && Math.abs(v) > max) max = Math.abs(v); });
    var ch = lastPair && r.changes && r.changes[lastPair.to];
    var rows = years.map(function (y, i) {
      var v = nums[i], bar = '', val;
      if (typeof v === 'number') {
        var width = max > 0 ? Math.max(v === 0 ? 0 : 2, Math.round(Math.abs(v) / max * 100)) : 0;
        bar = '<span class="bar-fill' + (v < 0 ? ' neg' : '') + '" style="width:' + width + '%"></span>';
        val = '<span class="bar-val">' + esc(krw(v)) + '</span>';
      } else {
        val = '<span class="bar-val none">' + esc(v === undefined ? ((r.missing || []).indexOf(y) >= 0 ? '항목 못 찾음' : '—') : krw(v)) + '</span>';
      }
      return '<div class="bar-row"><span class="bar-year">' + esc(y) + (mixed ? ' ' + esc(labels[y] || '') : '') + '</span><span class="bar-track" aria-hidden="true">' + bar + '</span>' + val + '</div>';
    }).join('');
    return '<div class="fin-card"><h4>' + esc(r.label) + '</h4><p class="fin-change">' +
      (ch ? esc(lastPair.from) + '년 → ' + esc(lastPair.to) + '년: ' + esc(krw(ch.abs)) + ' (' + esc(pct(ch)) + ')' : '견줄 수 있는 두 해가 없어요') + '</p>' + rows + '</div>';
  }
  function renderFinancial(d, code) {
    var el = $('view-financial');
    var head = '<p class="meta">사업보고서(1년치)의 표준 계정 · 자료 받은 회사 ' + esc(d.coverage.companiesCollected) + '곳 / 추적 ' + esc(d.coverage.trackedCompanies) + '곳</p>';
    var h = d.howToRead || {};
    if (!code) {
      el.innerHTML = head + '<div class="card"><p class="small">위 검색창에 회사 이름이나 종목코드를 넣고 「보기」를 누르세요.</p>' +
        ladder([['무엇을 보여 주나요?', esc(h.why), 'why'], ['아직 모르는 건?', esc(h.counter), 'unknown'], ['다음에 확인할 건?', esc(h.next), 'next'],
                ['표를 읽는 규칙', ul((d.method || []).map(esc)), 'source']]) + '</div>';
      return;
    }
    var c = d.companies && d.companies[code];
    if (!c) {
      var nc = (d.notCollectedTickers || []).indexOf(code) >= 0;
      el.innerHTML = head + (nc
        ? G.state('unknown', '재무 자료를 아직 받지 못했어요', esc(nameOf(code)) + '(' + esc(code) + ') — NOT_COLLECTED. 재무가 없다는 뜻이 아니에요. 하루에 몇십 곳씩 차례로 채워요.')
        : G.state('na', '이 자료에 재무 기록이 없어요', esc(nameOf(code)) + '(' + esc(code) + ')'));
      return;
    }
    var periods = c.periods || [], years = periods.map(function (p) { return p.year; });
    var pairs = c.comparablePairs || [], lastPair = pairs[pairs.length - 1];
    var byAccount = {};
    (c.rows || []).forEach(function (r) { byAccount[r.account] = r; });
    var cards = KEY_ACCOUNTS.filter(function (k) { return byAccount[k]; }).map(function (k) { return finCard(byAccount[k], periods, lastPair); }).join('');
    var table = '<div class="tbl"><table><thead><tr><th>항목</th>' + years.map(function (y) { return '<th>' + esc(y) + '</th>'; }).join('') + '<th>바뀐 정도</th></tr></thead><tbody>';
    var happened = [];
    (c.rows || []).forEach(function (r) {
      var ch = lastPair && r.changes && r.changes[lastPair.to];
      if (ch && typeof ch.pct === 'number' && Math.abs(ch.pct) >= 20) happened.push(esc(r.label) + '이(가) ' + esc(lastPair.from) + '년보다 ' + esc(lastPair.to) + '년에 ' + (ch.pct > 0 ? '늘었어요' : '줄었어요') + ' (' + esc(pct(ch)) + ').');
      table += '<tr><td>' + esc(r.label) + '</td>' + years.map(function (y) {
        if (r.values && y in r.values) return '<td>' + esc(krw(r.values[y])) + '</td>';
        return '<td class="meta">' + ((r.missing || []).indexOf(y) >= 0 ? '항목 못 찾음' : '—') + '</td>';
      }).join('') + '<td>' + (ch ? esc(krw(ch.abs)) + ' (' + esc(pct(ch)) + ')' : '<span class="meta">견주지 않음</span>') + '</td></tr>';
    });
    table += '</tbody></table></div>';
    if (!happened.length) happened.push(lastPair ? '가장 최근 두 해 사이에 20% 넘게 바뀐 항목은 없어요.' : '같은 기준(연결/별도)으로 견줄 수 있는 두 해가 없어요.');
    el.innerHTML = head + '<div class="card">' + panelHead(code, esc(c.fsDivLabel || c.fsDiv)) +
      '<p class="small">막대는 금액의 크기만 보여 줘요. 색으로 좋고 나쁨을 말하지 않아요 — 음수는 테두리만 있는 막대와 「−」로 적어요.</p>' +
      '<div class="fin-cards">' + cards + '</div>' +
      ladder([['무슨 일이 있었어?', ul(happened), 'fact'], ['왜 볼 필요가 있어?', esc(h.why), 'why'],
              ['아직 모르는 건?', esc(h.counter) + (c.notes && c.notes.length ? ul(c.notes.map(esc)) : ''), 'unknown'],
              ['다음에 확인할 건?', esc(h.next), 'next'],
              ['DART에서 직접 보기', 'DART에서 회사 이름으로 「사업보고서」를 찾아 재무제표와 주석을 읽어 보세요. ' + link(dartSearch(nameOf(code)), 'DART에서 이 회사 공시 검색'), 'source']]) +
      '<details class="numbers"><summary>숫자 자세히 보기(표)</summary><p class="meta">금액 단위는 칸마다 조·억·만 원으로 적었어요. 결측은 0이 아니에요.</p>' + table + '</details>' +
      G.sourceBar('단일회사 전체 재무제표(사업보고서)', d.generatedAt, dartSearch(nameOf(code)), 'DART에서 원문 확인') + '</div>';
  }

  /* 사건 흐름 — 세로 타임라인. 못 찾은 단계는 빈 점 + "안 했다는 뜻이 아님" */
  var STAGE = { PLANNED: '결정·계획', FILED: '신고·확정', IN_PROGRESS: '진행 절차', REPORTED: '결과 보고', COMPLETED: '완료' };
  function tlFound(i) {
    return '<li><p class="tl-date"><time datetime="' + esc(i.receivedOn) + '">' + esc(i.receivedOn) + '</time></p>' +
      '<p class="tl-stage">' + esc(i.stageLabel) + (i.isCorrection ? ' ' + G.chip('neutral', '정정') : '') + '</p>' +
      '<p class="tl-title">' + esc(i.title) + '</p>' + link(i.url, 'DART 원문') + '</li>';
  }
  function tlMissing(label) {
    return '<li class="tl-missing"><p class="tl-stage">' + esc(label) + ' ' + G.chip('na', '아직 확인 못 함') + '</p>' +
      '<p class="tl-why">안 했다는 뜻(미실행)이 아니라 GAEO가 아직 확인하지 못했다는 뜻입니다.</p></li>';
  }
  function renderTimeline(d, code) {
    var el = $('view-timeline');
    var head = '<p class="meta">공시 제목으로 「결정 → 진행 → 결과 → 완료」를 이어요 · 흐름이 있는 회사 ' + esc(d.coverage.companiesWithTimelines) + '곳</p>';
    if (!code) {
      var rows = Object.keys(d.companies || {}).map(function (k) {
        var t = d.companies[k].timelines || [];
        return { code: k, name: d.companies[k].name, n: t.length, latest: t.map(function (x) { return x.latestReceivedOn; }).sort().pop() };
      }).sort(function (a, b) { return String(b.latest).localeCompare(String(a.latest)); }).slice(0, 80);
      el.innerHTML = head + '<div class="card">' + ladder([['읽을 때 주의', ul((d.limits || []).map(esc)), 'unknown']]) + '</div><ul class="list list-card">' + rows.map(function (r) {
        return '<li><a href="?code=' + esc(r.code) + '" data-code="' + esc(r.code) + '"><b>' + esc(r.name || r.code) + '</b></a> <span class="meta">흐름 ' + r.n + '개 · 최근 ' + esc(r.latest) + '</span></li>';
      }).join('') + '</ul>';
      openCompany(el); return;
    }
    var c = d.companies && d.companies[code];
    if (!c) { el.innerHTML = head + G.state('na', '이어지는 공시 흐름을 찾지 못했어요', esc(nameOf(code)) + '(' + esc(code) + ') — 사건이 없었다는 뜻은 아니에요.'); return; }
    var html = head + '<div class="card">' + panelHead(code, '흐름 ' + (c.timelines || []).length + '개');
    (c.timelines || []).forEach(function (t) {
      var chain = (d.chains || {})[t.chain] || {}, h = chain.howToRead || {};
      var byStage = {}, known = {}, nodes = [];
      (t.items || []).slice().sort(function (a, b) { return String(a.receivedOn).localeCompare(String(b.receivedOn)); })
        .forEach(function (i) { (byStage[i.stage] = byStage[i.stage] || []).push(i); });
      (chain.stages || []).forEach(function (st) {
        known[st.stage] = 1;
        if (byStage[st.stage]) byStage[st.stage].forEach(function (i) { nodes.push(tlFound(i)); });
        else nodes.push(tlMissing(st.label));
      });
      Object.keys(byStage).forEach(function (sg) { if (!known[sg]) byStage[sg].forEach(function (i) { nodes.push(tlFound(i)); }); });
      var unknown = (t.stagesNotFound || []).map(function (s) { return esc(s.stageLabel) + '은(는) 아직 확인되지 않았어요. 안 했다는 뜻(미실행)이 아니라 못 찾은 거예요.'; });
      if (h.counter) unknown.push(esc(h.counter));
      html += '<div class="tl-block"><h4>' + esc(t.label) + '</h4><p class="meta">지금 확인된 단계 ' + G.chip('info', STAGE[t.latestStage] || t.latestStage) + ' 최근 ' + esc(t.latestReceivedOn) + '</p>' +
        ladder([['무슨 일이 있었어?', '<ol class="tl" aria-label="' + esc(t.label) + ' 단계">' + nodes.join('') + '</ol>', 'fact'], ['왜 볼 필요가 있어?', esc(h.why), 'why'],
                ['아직 모르는 건?', ul(unknown), 'unknown'], ['다음에 확인할 건?', esc(h.next), 'next']]) + '</div>';
    });
    el.innerHTML = html + G.sourceBar('공시 목록 제목·접수번호·접수일', d.generatedAt, dartSearch(nameOf(code)), 'DART에서 원문 확인') + '</div>';
  }

  /* 이 공시가 어렵다면 — 사람이 고른 연결표(tools/build_site.py LESSONS_BY_CATEGORY)로만 잇는다 */
  function renderRelated(code) {
    var el = $('related'), s = code && summary && summary.companies && summary.companies[code];
    if (!s) { el.classList.add('hidden'); el.innerHTML = ''; return; }
    var picks = [], seen = {}, labels = summary.categoryLabels || {};
    (s.categories || []).forEach(function (cat) {
      (summary.lessons[cat] || []).forEach(function (l) {
        if (!seen[l[0]] && picks.length < 3) { seen[l[0]] = 1; picks.push({ id: l[0], name: l[1], why: '관련 공시 · ' + (labels[cat] || cat) }); }
      });
    });
    (summary.basicLessons || []).forEach(function (l) { if (!seen[l[0]] && picks.length < 3) { seen[l[0]] = 1; picks.push({ id: l[0], name: l[1], why: '공시 읽는 법 기초' }); } });
    el.innerHTML = '<div class="section-head"><h2 id="rel-title">이 공시가 어렵다면</h2></div>' +
      '<p class="section-sub">이 회사 공시에 나온 종류와 이어지는 기초 공부예요.</p><div class="grid three">' + picks.map(function (p) {
        return '<a class="card link-card" href="/learn.html?t=stock&id=' + esc(p.id) + '">' + G.chip('info', p.why) + '<span class="lc-title">' + esc(p.name) + '</span></a>';
      }).join('') + '</div>';
    el.classList.remove('hidden');
  }

  function show() {
    TABS.forEach(function (t) { $('view-' + t).classList.toggle('hidden', t !== current.tab); });
    $('tab-today').textContent = current.code ? '최근 공시' : '오늘의 공시';
    var code = /^\d{6}$/.test(current.code) && tracked(current.code) ? current.code : '';
    renderOverview(current.code);
    renderRelated(code);
    if (current.code && !code) { $('view-' + current.tab).innerHTML = ''; return; }
    if (current.tab === 'today') { renderToday(code); return; }
    var el = $('view-' + current.tab);
    el.innerHTML = G.loading();
    load(KIND[current.tab]).then(function (d) {
      if (current.tab === 'changes') renderChanges(d, code);
      else if (current.tab === 'financial') renderFinancial(d, code);
      else renderTimeline(d, code);
    }).catch(function (e) { fail(el, e); });
  }
  function selectTab(tab, focusPanel) {
    current.tab = tab;
    try {  /* 지금 보는 회사·탭을 주소에 남긴다(공유·새로고침). 실패해도 화면에는 영향 없음 */
      history.replaceState(null, '', current.code ? '?code=' + encodeURIComponent(current.code) + (tab !== 'changes' ? '&tab=' + tab : '') : (tab !== 'today' ? '?tab=' + tab : location.pathname));
    } catch (e) { /* 무시 */ }
    Array.prototype.forEach.call(document.querySelectorAll('.tabs [role="tab"]'), function (x) {
      var on = x.getAttribute('data-tab') === tab;
      x.setAttribute('aria-selected', on ? 'true' : 'false');
      x.tabIndex = on ? 0 : -1;
    });
    show();
    if (focusPanel) { $('view-' + tab).focus(); }
  }
  function search() {
    current.code = resolveCode($('q').value);
    if (current.code && current.tab === 'today') current.tab = 'changes';
    if (!current.code) current.tab = 'today';
    selectTab(current.tab, false);
    if (current.code) $('overview').focus();
  }
  var tabs = Array.prototype.slice.call(document.querySelectorAll('.tabs [role="tab"]'));
  tabs.forEach(function (b, i) {
    b.addEventListener('click', function () { selectTab(b.getAttribute('data-tab'), false); });
    b.addEventListener('keydown', function (e) {
      var to = e.key === 'ArrowRight' ? i + 1 : e.key === 'ArrowLeft' ? i - 1 : e.key === 'Home' ? 0 : e.key === 'End' ? tabs.length - 1 : null;
      if (to === null) return;
      e.preventDefault();
      var next = tabs[(to + tabs.length) % tabs.length];
      next.focus(); selectTab(next.getAttribute('data-tab'), false);
    });
  });
  $('search-form').addEventListener('submit', function (e) { e.preventDefault(); search(); });
  $('clear').addEventListener('click', function () { $('q').value = ''; search(); });

  var initial = G.param('code');
  if (initial) $('q').value = initial;
  $('view-today').innerHTML = G.loading();
  var summaryReady = loadSummary();
  load('contract').then(function (c) {
    contract = c;
    $('asOf').textContent = '자료 기준일 ' + c.asOf + ' · 자료 생성 ' + G.kst(c.generatedAt) + ' (한국시간) · 추적 회사 ' + Object.keys(c.companyNames || {}).length + '곳 · 하루 2회 갱신';
    var dl = $('companies'), names = c.companyNames || {};
    Object.keys(names).sort().forEach(function (code) { var o = document.createElement('option'); o.value = names[code]; o.label = code; dl.appendChild(o); });
    current.code = resolveCode(initial);
    var wanted = G.param('tab');
    current.tab = TABS.indexOf(wanted) >= 0 ? wanted : (current.code ? 'changes' : 'today');
    selectTab(current.tab, false);
    summaryReady.then(function () { if (current.code) { renderOverview(current.code); renderRelated(/^\d{6}$/.test(current.code) && tracked(current.code) ? current.code : ''); } });
  }).catch(function (e) {
    $('asOf').textContent = '자료 기준 파일을 받지 못했어요(' + (e && e.message) + ') — 자료 없이 화면을 채우지 않아요.';
    selectTab('today', false);
  });
})();
