/* GAEO 기업 리서치 — 공통 머리말·꼬리말·도우미. 외부 추적·광고·서비스워커 없음. 네트워크: 같은 사이트 파일뿐. */
(function () {
  'use strict';
  var NAV = [
    ['/', '홈', 'home'],
    ['/disclosure-research.html', '기업 리서치', 'research'],
    ['/past-analysis/', '과거 정밀분석', 'past'],
    ['/study.html', '종목 공부', 'study'],
    ['/learn.html', '투자 공부', 'learn'],
    ['/calculators.html', '계산기', 'calc']
  ];
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function inline(s) {
    return esc(s)
      .replace(/\[([^\]]+)\]\((https:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
      .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>');
  }
  /* 아주 작은 마크다운: ## 소제목 · - 목록 · 문단 · **굵게** · [링크](https://) */
  function md(text) {
    var lines = String(text || '').split('\n'), html = '', para = [], list = null;
    function flushP() { if (para.length) { html += '<p>' + para.map(inline).join('<br>') + '</p>'; para = []; } }
    function flushL() { if (list) { html += '<ul>' + list.map(function (x) { return '<li>' + inline(x) + '</li>'; }).join('') + '</ul>'; list = null; } }
    lines.forEach(function (ln) {
      var t = ln.trim();
      if (!t) { flushP(); flushL(); return; }
      if (t.indexOf('## ') === 0 || t.indexOf('### ') === 0) { flushP(); flushL(); html += '<h4>' + inline(t.replace(/^#+\s*/, '')) + '</h4>'; return; }
      if (/^[-·*]\s+/.test(t)) { flushP(); if (!list) list = []; list.push(t.replace(/^[-·*]\s+/, '')); return; }
      flushL(); para.push(t);
    });
    flushP(); flushL();
    return html;
  }
  /* 머리말·꼬리말은 빌드(tools/build_site.py)가 미리 그린다 — 자바스크립트가 꺼져도 보인다. 비어 있을 때만 여기서 그린다. */
  function header(active) {
    var el = document.getElementById('site-head');
    if (!el || el.children.length) return;
    el.className = 'site-head';
    el.innerHTML = '<a class="skip" href="#main">본문 바로가기</a><div class="wrap head-row"><a class="brand" href="/">GAEO<small>기업 리서치</small></a>' +
      '<nav class="nav" aria-label="주 메뉴">' + NAV.map(function (n) {
        return '<a href="' + n[0] + '"' + (n[2] === active ? ' aria-current="page"' : '') + '>' + n[1] + '</a>';
      }).join('') + '</nav></div>';
  }
  function footer() {
    var el = document.getElementById('site-foot');
    if (!el || el.children.length) return;
    el.className = 'site-foot';
    el.innerHTML = '<div class="wrap"><p>GAEO는 공시·기업 공부를 돕는 개인 리서치 노트입니다. 투자 권유가 아니며, 판단과 책임은 읽는 분에게 있습니다. 매수·매도 추천, 1:1 종목 상담, 유료 리딩을 하지 않습니다.</p>' +
      '<p>공시 자료 출처: 금융감독원 전자공시시스템(DART) · OpenDART</p>' +
      '<p class="foot-links"><a href="/about.html">사이트 소개</a><a href="/disclaimer.html">자료 출처·면책</a><a href="/privacy.html">개인정보처리방침</a><a href="/contact.html">문의</a></p></div>';
  }
  /* 화면 상태 — 불러오는 중 · 아직 못 받음 · 해당 없음 · 오류를 서로 다른 말로 보여 준다(없는 자료를 0 으로 채우지 않는다). */
  var CHIP = { fact: '확인됨', unknown: '아직 못 받음', na: '해당 없음', error: '오류', info: '안내' };
  function chip(kind, label) { return '<span class="chip ' + kind + '">' + esc(label || CHIP[kind] || '') + '</span>'; }
  function loading(text) {
    return '<div class="loading" role="status" aria-live="polite"><span class="sk" aria-hidden="true"></span><span class="sk w70" aria-hidden="true"></span><span class="sk w40" aria-hidden="true"></span><p>' + esc(text || '자료를 불러오고 있어요') + '</p></div>';
  }
  function state(kind, title, body) {
    return '<div class="state state-' + kind + '" role="' + (kind === 'error' ? 'alert' : 'note') + '"><p class="state-title">' + esc(title) + '</p>' + (body ? '<p>' + body + '</p>' : '') + '</div>';
  }
  function sourceBar(what, generatedAt, url, urlLabel) {
    return '<p class="source-bar"><span>출처: 금융감독원 OpenDART' + (what ? ' · ' + esc(what) : '') + '</span>' +
      (generatedAt ? '<span>자료 생성 ' + esc(kst(generatedAt)) + '</span>' : '') +
      (url ? '<a href="' + esc(url) + '" target="_blank" rel="noopener">' + esc(urlLabel || '원문 확인') + ' ↗</a>' : '') + '</p>';
  }
  function param(name) {
    var m = new RegExp('[?&]' + name + '=([^&#]*)').exec(location.search);
    return m ? decodeURIComponent(m[1].replace(/\+/g, ' ')) : '';
  }
  function dartUrl(rceptNo) {
    return /^\d{14}$/.test(String(rceptNo || '')) ? 'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=' + rceptNo : '';
  }
  function ymd(s) {
    s = String(s || '');
    return /^\d{8}$/.test(s) ? s.slice(0, 4) + '-' + s.slice(4, 6) + '-' + s.slice(6) : s;
  }
  /* ISO 시각(UTC) → 'YYYY-MM-DD HH:MM' 한국시간. 이미 한국시간 문자열이면 그대로. */
  function kst(iso) {
    var d = new Date(iso);
    if (!/T/.test(String(iso || '')) || isNaN(d)) return String(iso || '');
    var k = new Date(d.getTime() + 9 * 3600 * 1000).toISOString();
    return k.slice(0, 10) + ' ' + k.slice(11, 16);
  }
  window.Gaeo = { kst: kst, esc: esc, md: md, inline: inline, header: header, footer: footer, param: param, dartUrl: dartUrl, ymd: ymd,
    chip: chip, loading: loading, state: state, sourceBar: sourceBar };
  document.addEventListener('DOMContentLoaded', function () {
    header(document.body.getAttribute('data-page') || '');
    footer();
  });
})();
