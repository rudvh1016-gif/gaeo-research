/* content/*.js 글 자료를 브라우저와 똑같이 실행해 JSON 으로 내보낸다(tools/build_site.py 가 부른다).
   글 파일 끝의 본문 보강(LESSON_DETAIL_UPDATES 등)까지 적용된 최종 모습을 쓰기 위해 정규식 대신 실제로 실행한다.
   네트워크 0 · 외부 모듈 0(node 기본 vm 만). 사용: node tools/content_dump.js */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const ROOT = path.join(__dirname, '..');
const FILES = [['content/stock_study.js', 'STOCK_STUDY'], ['content/stock_lessons.js', 'STOCK_LESSONS'],
  ['content/estate_lessons.js', 'ESTATE_LESSONS'], ['content/calculators.js', 'CALCULATORS']];
const out = {};
for (const [rel, name] of FILES) {
  const ctx = vm.createContext({});
  vm.runInContext(fs.readFileSync(path.join(ROOT, rel), 'utf8') + '\n;this.__out = ' + name + ';', ctx, { filename: rel, timeout: 5000 });
  if (!Array.isArray(ctx.__out)) throw new Error(rel + ': ' + name + ' 배열이 아니다');
  out[name] = JSON.parse(JSON.stringify(ctx.__out));
}
process.stdout.write(JSON.stringify(out));
