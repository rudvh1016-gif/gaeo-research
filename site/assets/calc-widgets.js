/* 계산기 위젯 — 옛 사이트 app.js 의 calcWidgetHTML/wireCalcWidget 를 그대로 옮겼다(계산식 변경 없음).
   바꾼 것: 이용 통계 호출 2줄 삭제, 제목 이모지 삭제. 외부 전송 없음 — 입력값은 이 브라우저에서만 계산한다. */
(function(){
  const n0=v=>{ const x=parseFloat(v); return isFinite(x)?x:0; };
  const fmtWon=v=>Math.round(v).toLocaleString('ko-KR')+'원';

  // 계산기별 입력 폼 HTML — id는 CALCULATORS 항목의 id를 접두로 써서 여러 계산기가 동시에 있어도 겹치지 않게 함
  function calcWidgetHTML(item){
    const p=k=>`c${item.id}-${k}`;
    if(item.calcType==='stockbreakeven'){
      return `<div class="calc-wrap">
        <div class="calc-title">주식 손익분기·순손익 계산</div>
        <div class="calc-row"><label>시장</label><select id="${p('market')}"><option value="kospi">KOSPI 주식</option><option value="kosdaq">KOSDAQ 주식</option><option value="etf">ETF·ETN</option><option value="custom">직접 설정</option></select></div>
        <div class="calc-row"><label>평균 매수가</label><input type="number" id="${p('buyPrice')}" value="50000" min="0" step="1"><span class="calc-unit">원</span></div>
        <div class="calc-row"><label>보유수량</label><input type="number" id="${p('qty')}" value="100" min="1" step="1"><span class="calc-unit">주</span></div>
        <div class="calc-row"><label>예상 매도가</label><input type="number" id="${p('sellPrice')}" value="52000" min="0" step="1"><span class="calc-unit">원</span></div>
        <div class="calc-row"><label>매수 수수료율</label><input type="number" id="${p('buyFee')}" value="0.015" min="0" max="100" step="0.001"><span class="calc-unit">%</span></div>
        <div class="calc-row"><label>매도 수수료율</label><input type="number" id="${p('sellFee')}" value="0.015" min="0" max="100" step="0.001"><span class="calc-unit">%</span></div>
        <div class="calc-row"><label>매도 세율</label><input type="number" id="${p('sellTax')}" value="0.20" min="0" max="100" step="0.01"><span class="calc-unit">%</span></div>
        <div class="calc-row"><label>기타 왕복 비용</label><input type="number" id="${p('fixedCost')}" value="0" min="0" step="1"><span class="calc-unit">원</span></div>
        <div class="calc-row"><label>목표 순수익률</label><input type="number" id="${p('targetReturn')}" value="10" min="-99" max="10000" step="0.1"><span class="calc-unit">%</span></div>
        <button type="button" class="calc-btn" id="${p('btn')}">비용 포함 가격 계산하기</button>
        <div class="calc-result" id="${p('result')}" style="display:none"></div>
        <div class="calc-note">2026년 7월 기준 기본값이에요. 실제 증권사 수수료와 종목별 세율을 확인해 수정하세요. KRX 호가단위로 올림한 주문 가능 가격도 함께 표시합니다.</div>
      </div>`;
    }
    if(item.calcType==='ipoallocation'){
      return `<div class="calc-wrap">
        <div class="calc-title">공모주 균등·비례 배정 계산</div>
        <div class="calc-row"><label>공모가</label><input type="number" id="${p('offerPrice')}" value="20000" min="1" step="1"><span class="calc-unit">원</span></div>
        <div class="calc-row"><label>내 청약주수</label><input type="number" id="${p('appliedShares')}" value="1000" min="1" step="1"><span class="calc-unit">주</span></div>
        <div class="calc-row"><label>청약 증거금률</label><input type="number" id="${p('marginRate')}" value="50" min="0.01" max="100" step="0.1"><span class="calc-unit">%</span></div>
        <div class="calc-row"><label>최소 청약주수</label><input type="number" id="${p('minimumShares')}" value="10" min="1" step="1"><span class="calc-unit">주</span></div>
        <div class="calc-row"><label>균등배정 물량</label><input type="number" id="${p('equalPool')}" value="100000" min="0" step="1"><span class="calc-unit">주</span></div>
        <div class="calc-row"><label>균등 대상 계좌 수</label><input type="number" id="${p('accountCount')}" value="150000" min="1" step="1"><span class="calc-unit">계좌</span></div>
        <div class="calc-row"><label>비례배정 물량</label><input type="number" id="${p('proportionalPool')}" value="100000" min="0" step="1"><span class="calc-unit">주</span></div>
        <div class="calc-row"><label>총 유효 청약주수</label><input type="number" id="${p('totalAppliedShares')}" value="200000000" min="1" step="1"><span class="calc-unit">주</span></div>
        <div class="calc-row"><label>청약수수료</label><input type="number" id="${p('subscriptionFee')}" value="2000" min="0" step="1"><span class="calc-unit">원</span></div>
        <button type="button" class="calc-btn" id="${p('btn')}">증거금·예상 배정 계산하기</button>
        <div class="calc-result" id="${p('result')}" style="display:none"></div>
        <div class="calc-note">해당 증권사의 최종 청약자료를 넣어야 의미가 있어요. 소수점 결과는 기대값이며 실제 배정은 인수회사의 단수주·추첨 기준에 따라 달라집니다.</div>
      </div>`;
    }
    if(item.calcType==='avgprice'){
      return `<div class="calc-wrap">
        <div class="calc-title">평단가 계산기</div>
        <div class="calc-row"><label>기존 보유수량</label><input type="number" id="${p('q1')}" placeholder="10" min="0"><span class="calc-unit">주</span></div>
        <div class="calc-row"><label>기존 평단가</label><input type="number" id="${p('p1')}" placeholder="50000" min="0"><span class="calc-unit">원</span></div>
        <div class="calc-row"><label>추가매수 수량</label><input type="number" id="${p('q2')}" placeholder="10" min="0"><span class="calc-unit">주</span></div>
        <div class="calc-row"><label>추가매수 단가</label><input type="number" id="${p('p2')}" placeholder="40000" min="0"><span class="calc-unit">원</span></div>
        <div class="calc-row"><label>목표 수익률</label><input type="number" id="${p('target')}" placeholder="10" min="-100" max="1000" step="0.1"><span class="calc-unit">%</span></div>
        <button type="button" class="calc-btn" id="${p('btn')}">계산하기</button>
        <div class="calc-result" id="${p('result')}" style="display:none"></div>
        <div class="calc-note">목표 수익률에 0을 넣으면 손익분기점(본전) 가격을 알 수 있어요</div>
      </div>`;
    }
    if(item.calcType==='capitalgainstax'){
      return `<div class="calc-wrap">
        <div class="calc-title">해외주식 양도소득세 계산기</div>
        <div class="calc-row"><label>총 매도금액</label><input type="number" id="${p('sell')}" placeholder="15000000" min="0"><span class="calc-unit">원</span></div>
        <div class="calc-row"><label>총 매수금액</label><input type="number" id="${p('buy')}" placeholder="10000000" min="0"><span class="calc-unit">원</span></div>
        <button type="button" class="calc-btn" id="${p('btn')}">계산하기</button>
        <div class="calc-result" id="${p('result')}" style="display:none"></div>
        <div class="calc-note">연 기본공제 250만원, 세율 22%(지방소득세 포함) 적용 · 국내 상장주식(대주주 제외)은 대부분 비과세예요</div>
      </div>`;
    }
    if(item.calcType==='compound'){
      return `<div class="calc-wrap">
        <div class="calc-title">복리 계산기</div>
        <div class="calc-row"><label>원금</label><input type="number" id="${p('principal')}" placeholder="5000000" min="0"><span class="calc-unit">원</span></div>
        <div class="calc-row"><label>매월 추가납입</label><input type="number" id="${p('monthly')}" placeholder="300000" min="0"><span class="calc-unit">원</span></div>
        <div class="calc-row"><label>연 수익률</label><input type="number" id="${p('rate')}" placeholder="7" min="-50" max="100" step="0.1"><span class="calc-unit">%</span></div>
        <div class="calc-row"><label>투자 기간</label><input type="number" id="${p('years')}" placeholder="10" min="1" max="80"><span class="calc-unit">년</span></div>
        <button type="button" class="calc-btn" id="${p('btn')}">계산하기</button>
        <div class="calc-result" id="${p('result')}" style="display:none"></div>
      </div>`;
    }
    if(item.calcType==='loanpayment'){
      return `<div class="calc-wrap">
        <div class="calc-title">대출 원리금상환 계산기</div>
        <div class="calc-row"><label>대출원금</label><input type="number" id="${p('principal')}" placeholder="300000000" min="0"><span class="calc-unit">원</span></div>
        <div class="calc-row"><label>연이자율</label><input type="number" id="${p('rate')}" placeholder="4.5" min="0" max="30" step="0.01"><span class="calc-unit">%</span></div>
        <div class="calc-row"><label>대출기간</label><input type="number" id="${p('years')}" placeholder="30" min="1" max="50"><span class="calc-unit">년</span></div>
        <button type="button" class="calc-btn" id="${p('btn')}">계산하기</button>
        <div class="calc-result" id="${p('result')}" style="display:none"></div>
        <div class="calc-note">원리금균등상환 방식 기준 · 중도상환수수료·인지세 등 부대비용은 포함하지 않아요 · 부동산 매매 잔금용 대출이면 잔금 계산까지 되는 부동산 잔금·대출 계산기가 더 편해요</div>
      </div>`;
    }
    if(item.calcType==='balancepayment'){
      return `<div class="calc-wrap">
        <div class="calc-title">부동산 잔금·대출 계산기</div>
        <div class="calc-row"><label>매매가</label><input type="number" id="${p('price')}" placeholder="500000000" min="0"><span class="calc-unit">원</span></div>
        <div class="calc-row"><label>계약금</label><input type="number" id="${p('down')}" placeholder="50000000" min="0"><span class="calc-unit">원</span></div>
        <div class="calc-row"><label>중도금</label><input type="number" id="${p('interim')}" placeholder="0" min="0"><span class="calc-unit">원</span></div>
        <div class="calc-row"><label>대출희망금액</label><input type="number" id="${p('loan')}" placeholder="300000000" min="0"><span class="calc-unit">원</span></div>
        <div class="calc-row"><label>연이자율</label><input type="number" id="${p('rate')}" placeholder="4.5" min="0" max="30" step="0.01"><span class="calc-unit">%</span></div>
        <div class="calc-row"><label>대출기간</label><input type="number" id="${p('years')}" placeholder="30" min="1" max="50"><span class="calc-unit">년</span></div>
        <button type="button" class="calc-btn" id="${p('btn')}">계산하기</button>
        <div class="calc-result" id="${p('result')}" style="display:none"></div>
        <div class="calc-note">잔금(매매가−계약금−중도금) 중 대출희망금액만큼을 원리금균등상환으로 계산해요 · 대출 한도 자체가 궁금하면 DSR·LTV 계산기를 함께 확인해보세요</div>
      </div>`;
    }
    if(item.calcType==='dividendtax'){
      return `<div class="calc-wrap">
        <div class="calc-title">배당소득세 계산기</div>
        <div class="calc-row"><label>세전 배당금</label><input type="number" id="${p('div')}" placeholder="1000000" min="0"><span class="calc-unit">원</span></div>
        <button type="button" class="calc-btn" id="${p('btn')}">계산하기</button>
        <div class="calc-result" id="${p('result')}" style="display:none"></div>
        <div class="calc-note">국내주식 기본 원천징수세율 15.4%(소득세14%+지방소득세1.4%) 적용 · 금융소득 연 2,000만원 초과 시 종합과세 대상일 수 있어요</div>
      </div>`;
    }
    if(item.calcType==='dsrltv'){
      return `<div class="calc-wrap">
        <div class="calc-title">DSR·LTV 계산기</div>
        <div class="calc-row"><label>주택가격</label><input type="number" id="${p('house')}" placeholder="1000000000" min="0"><span class="calc-unit">원</span></div>
        <div class="calc-row"><label>대출희망금액</label><input type="number" id="${p('loan')}" placeholder="600000000" min="0"><span class="calc-unit">원</span></div>
        <div class="calc-row"><label>연이자율</label><input type="number" id="${p('rate')}" placeholder="4.5" min="0" max="30" step="0.01"><span class="calc-unit">%</span></div>
        <div class="calc-row"><label>대출기간</label><input type="number" id="${p('years')}" placeholder="30" min="1" max="50"><span class="calc-unit">년</span></div>
        <div class="calc-row"><label>연소득</label><input type="number" id="${p('income')}" placeholder="60000000" min="0"><span class="calc-unit">원</span></div>
        <div class="calc-row"><label>기타 대출 연상환액</label><input type="number" id="${p('other')}" placeholder="0" min="0"><span class="calc-unit">원</span></div>
        <button type="button" class="calc-btn" id="${p('btn')}">계산하기</button>
        <div class="calc-result" id="${p('result')}" style="display:none"></div>
        <div class="calc-note">대략적인 참고용 계산이에요 · 실제 한도는 규제지역·스트레스 DSR·은행별 기준에 따라 달라져요</div>
      </div>`;
    }
    if(item.calcType==='etfplan') return `<div class="calc-wrap"><div class="calc-title">ETF 적립식·분배금</div><div class="calc-row"><label>초기 투자금</label><input type="number" id="${p('principal')}" placeholder="5000000" min="0"><span class="calc-unit">원</span></div><div class="calc-row"><label>월 적립금</label><input type="number" id="${p('monthly')}" placeholder="300000" min="0"><span class="calc-unit">원</span></div><div class="calc-row"><label>연 기대수익률</label><input type="number" id="${p('rate')}" placeholder="7" step="0.1"><span class="calc-unit">%</span></div><div class="calc-row"><label>연 분배율</label><input type="number" id="${p('yield')}" placeholder="4" step="0.1"><span class="calc-unit">%</span></div><div class="calc-row"><label>세율 가정</label><input type="number" id="${p('tax')}" value="15.4" step="0.1"><span class="calc-unit">%</span></div><div class="calc-row"><label>기간</label><input type="number" id="${p('years')}" placeholder="10" min="1"><span class="calc-unit">년</span></div><button type="button" class="calc-btn" id="${p('btn')}">계산하기</button><div class="calc-result" id="${p('result')}" style="display:none"></div><div class="calc-note">수익률은 분배금을 포함한 총수익률 가정입니다. 분배금은 현재 평가액 기준의 참고 추정치예요.</div></div>`;
    if(item.calcType==='taxsavings') return `<div class="calc-wrap"><div class="calc-title">ISA·연금저축 절세 예상</div><div class="calc-row"><label>연금저축·IRP 납입액</label><input type="number" id="${p('pension')}" placeholder="6000000" min="0"><span class="calc-unit">원</span></div><div class="calc-row"><label>세액공제 대상 한도</label><input type="number" id="${p('pensionLimit')}" placeholder="공식 한도 입력" min="0"><span class="calc-unit">원</span></div><div class="calc-row"><label>내 적용 공제율</label><input type="number" id="${p('credit')}" placeholder="공식 공제율" min="0" max="100" step="0.1"><span class="calc-unit">%</span></div><div class="calc-row"><label>ISA 예상 순이익</label><input type="number" id="${p('isaGain')}" placeholder="3000000" min="0"><span class="calc-unit">원</span></div><div class="calc-row"><label>ISA 비과세 한도</label><input type="number" id="${p('isaFree')}" placeholder="공식 한도 입력" min="0"><span class="calc-unit">원</span></div><div class="calc-row"><label>ISA 초과분 세율</label><input type="number" id="${p('isaReduced')}" placeholder="공식 세율" min="0" max="100" step="0.1"><span class="calc-unit">%</span></div><div class="calc-row"><label>일반계좌 비교 세율</label><input type="number" id="${p('isaTax')}" value="15.4" min="0" max="100" step="0.1"><span class="calc-unit">%</span></div><button type="button" class="calc-btn" id="${p('btn')}">계산하기</button><div class="calc-result" id="${p('result')}" style="display:none"></div><div class="calc-note">한도·세율은 자동 확정하지 않습니다. 올해 공식 자료에서 확인한 본인 적용값을 입력하세요.</div></div>`;
    if(item.calcType==='youthasset') return `<div class="calc-wrap"><div class="calc-title">청년 자산형성 만기 예상</div><div class="calc-row"><label>월 납입액</label><input type="number" id="${p('monthly')}" placeholder="500000" min="0"><span class="calc-unit">원</span></div><div class="calc-row"><label>월 지원금/기여금</label><input type="number" id="${p('support')}" placeholder="0" min="0"><span class="calc-unit">원</span></div><div class="calc-row"><label>연 금리 가정</label><input type="number" id="${p('rate')}" placeholder="4" step="0.1"><span class="calc-unit">%</span></div><div class="calc-row"><label>가입 기간</label><input type="number" id="${p('months')}" placeholder="60" min="1"><span class="calc-unit">개월</span></div><button type="button" class="calc-btn" id="${p('btn')}">계산하기</button><div class="calc-result" id="${p('result')}" style="display:none"></div><div class="calc-note">지원금·금리는 공식 공고의 본인 적용값을 넣으세요.</div></div>`;
    if(item.calcType==='rentvsjeonse') return `<div class="calc-wrap"><div class="calc-title">전세 vs 월세</div><div class="calc-row"><label>전세 보증금</label><input type="number" id="${p('jeonse')}" placeholder="200000000" min="0"><span class="calc-unit">원</span></div><div class="calc-row"><label>전세 대출금</label><input type="number" id="${p('loan')}" placeholder="100000000" min="0"><span class="calc-unit">원</span></div><div class="calc-row"><label>전세대출 금리</label><input type="number" id="${p('loanRate')}" placeholder="4" min="0" max="100" step="0.1"><span class="calc-unit">%</span></div><div class="calc-row"><label>월세 보증금</label><input type="number" id="${p('deposit')}" placeholder="10000000" min="0"><span class="calc-unit">원</span></div><div class="calc-row"><label>월세</label><input type="number" id="${p('rent')}" placeholder="800000" min="0"><span class="calc-unit">원</span></div><div class="calc-row"><label>내 돈 기회비용률</label><input type="number" id="${p('opp')}" value="3" min="0" max="100" step="0.1"><span class="calc-unit">%</span></div><div class="calc-row"><label>전세 월 관리비</label><input type="number" id="${p('jMgmt')}" value="0" min="0"><span class="calc-unit">원</span></div><div class="calc-row"><label>월세 월 관리비</label><input type="number" id="${p('rMgmt')}" value="0" min="0"><span class="calc-unit">원</span></div><div class="calc-row"><label>전세 일회성 비용</label><input type="number" id="${p('jCost')}" value="0" min="0"><span class="calc-unit">원</span></div><div class="calc-row"><label>월세 일회성 비용</label><input type="number" id="${p('rCost')}" value="0" min="0"><span class="calc-unit">원</span></div><div class="calc-row"><label>계약기간</label><input type="number" id="${p('months')}" value="24" min="1"><span class="calc-unit">개월</span></div><button type="button" class="calc-btn" id="${p('btn')}">비교하기</button><div class="calc-result" id="${p('result')}" style="display:none"></div><div class="calc-note">대출 원금상환은 비용이 아니라 자산 이동으로 보고 제외했어요. 보증금 반환 위험·세액공제는 별도 판단이 필요해요.</div></div>`;
    if(item.calcType==='severance') return `<div class="calc-wrap"><div class="calc-title">퇴직금·퇴사 후 현금흐름</div><div class="calc-row"><label>최근 3개월 임금 합계</label><input type="number" id="${p('wage')}" placeholder="9000000" min="0"><span class="calc-unit">원</span></div><div class="calc-row"><label>산정기간 총일수</label><input type="number" id="${p('days')}" value="92" min="1"><span class="calc-unit">일</span></div><div class="calc-row"><label>계속 근로일수</label><input type="number" id="${p('workdays')}" placeholder="730" min="1"><span class="calc-unit">일</span></div><div class="calc-row"><label>주 평균 근로시간</label><input type="number" id="${p('weeklyHours')}" value="40" min="0" max="168" step="0.5"><span class="calc-unit">시간</span></div><div class="calc-row"><label>연차수당 등 추가 정산</label><input type="number" id="${p('extra')}" value="0" min="0"><span class="calc-unit">원</span></div><div class="calc-row"><label>보유 현금</label><input type="number" id="${p('cash')}" placeholder="10000000" min="0"><span class="calc-unit">원</span></div><div class="calc-row"><label>월 필수지출</label><input type="number" id="${p('expense')}" placeholder="2000000" min="1"><span class="calc-unit">원</span></div><button type="button" class="calc-btn" id="${p('btn')}">계산하기</button><div class="calc-result" id="${p('result')}" style="display:none"></div><div class="calc-note">세전 추정치입니다. 퇴직연금·세금·평균임금 포함항목은 반영하지 않았어요.</div></div>`;
    return '';
  }
  // 계산기별 이벤트 연결 + 실제 계산 로직
  function wireCalcWidget(item){
    const p=k=>document.getElementById(`c${item.id}-${k}`);
    const btn=p('btn'); if(!btn) return;
    const widget=btn.closest('.calc-wrap');
    const result=p('result');
    if(widget){
      widget.querySelectorAll('.calc-row').forEach((row,index)=>{
        const control=row.querySelector('input,select,textarea');
        const label=row.querySelector('label');
        const unit=row.querySelector('.calc-unit');
        if(control&&label){ label.htmlFor=control.id; }
        if(control&&unit){
          if(!unit.id) unit.id=`${control.id}-unit`;
          const described=(control.getAttribute('aria-describedby')||'').split(/\s+/).filter(Boolean);
          if(!described.includes(unit.id)) described.push(unit.id);
          control.setAttribute('aria-describedby',described.join(' '));
        }
        if(control&&!control.id) control.id=`calc-${item.id}-field-${index}`;
      });
    }
    if(result){ result.setAttribute('role','status'); result.setAttribute('aria-live','polite'); result.tabIndex=-1; }
    if(item.calcType==='stockbreakeven'){
      const market=p('market');
      market.onchange=()=>{
        if(market.value==='kospi'||market.value==='kosdaq') p('sellTax').value='0.20';
        if(market.value==='etf') p('sellTax').value='0';
      };
      btn.onclick=()=>{
        const marketType=market.value;
        const buyPrice=n0(p('buyPrice').value), qty=Math.floor(n0(p('qty').value));
        const sellPrice=n0(p('sellPrice').value), buyFeeRate=n0(p('buyFee').value)/100;
        const sellFeeRate=n0(p('sellFee').value)/100, sellTaxRate=n0(p('sellTax').value)/100;
        const fixedCost=n0(p('fixedCost').value), targetReturn=n0(p('targetReturn').value)/100;
        const res=p('result'); res.style.display='block';
        if(buyPrice<=0||qty<=0){
          res.innerHTML='<div class="cr-sub">0보다 큰 평균 매수가와 보유수량을 입력해주세요.</div>'; return;
        }
        if([buyFeeRate,sellFeeRate,sellTaxRate].some(v=>v<0||v>1)||sellFeeRate+sellTaxRate>=1||fixedCost<0||targetReturn<=-1){
          res.innerHTML='<div class="cr-sub">수수료·세율은 0~100% 범위에서 입력하고, 매도 수수료와 세금의 합은 100%보다 작아야 해요.</div>'; return;
        }
        const tickAt=price=>{
          if(marketType==='etf') return 5;
          if(marketType==='custom') return 1;
          if(price<1000) return 1;
          if(price<5000) return 5;
          if(price<10000) return 10;
          if(price<50000) return 50;
          if(price<100000) return 100;
          if(price<500000) return marketType==='kospi'?500:100;
          return marketType==='kospi'?1000:100;
        };
        const roundToOrderPrice=price=>{
          let rounded=price;
          for(let i=0;i<3;i+=1){
            const tick=tickAt(rounded);
            rounded=Math.ceil(price/tick)*tick;
          }
          return rounded;
        };
        const buyAmount=buyPrice*qty;
        const buyCommission=buyAmount*buyFeeRate;
        const acquisitionCost=buyAmount+buyCommission+fixedCost;
        const netSellFactor=1-sellFeeRate-sellTaxRate;
        const breakEvenRaw=acquisitionCost/(qty*netSellFactor);
        const breakEvenOrder=roundToOrderPrice(breakEvenRaw);
        const targetRaw=acquisitionCost*(1+targetReturn)/(qty*netSellFactor);
        const targetOrder=roundToOrderPrice(targetRaw);
        let sellHtml='<span style="color:var(--t3)">예상 매도가를 입력하면 그 가격의 세후 손익도 계산해요.</span>';
        if(sellPrice>0){
          const sellAmount=sellPrice*qty;
          const sellCommission=sellAmount*sellFeeRate;
          const sellTax=sellAmount*sellTaxRate;
          const netProceeds=sellAmount-sellCommission-sellTax;
          const netProfit=netProceeds-acquisitionCost;
          const netReturn=acquisitionCost>0?netProfit/acquisitionCost*100:0;
          sellHtml=`예상 매도대금 ${fmtWon(sellAmount)}<br>매도 수수료 ${fmtWon(sellCommission)} · 매도세금 ${fmtWon(sellTax)}<br><strong>세후 순손익 ${netProfit>=0?'+':''}${fmtWon(netProfit)} (${netReturn>=0?'+':''}${netReturn.toFixed(2)}%)</strong>`;
        }
        res.innerHTML=`<div class="cr-main">손익분기 주문가 ${fmtWon(breakEvenOrder)}</div>
          <div class="cr-sub">이론 손익분기 ${fmtWon(breakEvenRaw)} · 적용 호가단위 ${fmtWon(tickAt(breakEvenOrder))}<br>
          매수원금 ${fmtWon(buyAmount)} · 매수수수료 ${fmtWon(buyCommission)} · 기타비용 ${fmtWon(fixedCost)}<br>
          목표 순수익률 ${(targetReturn*100).toFixed(1)}% 주문가 ${fmtWon(targetOrder)} (이론 ${fmtWon(targetRaw)})<br><br>${sellHtml}<br>
          <span style="color:var(--t3)">원 미만 처리와 체결별 수수료 합산 방식에 따라 증권사 정산액과 소액 차이가 날 수 있어요.</span></div>`;
      };
    }
    if(item.calcType==='ipoallocation'){
      btn.onclick=()=>{
        const offerPrice=n0(p('offerPrice').value);
        const appliedShares=Math.floor(n0(p('appliedShares').value));
        const marginRate=n0(p('marginRate').value)/100;
        const minimumShares=Math.floor(n0(p('minimumShares').value));
        const equalPool=Math.floor(n0(p('equalPool').value));
        const accountCount=Math.floor(n0(p('accountCount').value));
        const proportionalPool=Math.floor(n0(p('proportionalPool').value));
        const totalAppliedShares=Math.floor(n0(p('totalAppliedShares').value));
        const subscriptionFee=n0(p('subscriptionFee').value);
        const res=p('result'); res.style.display='block';
        if(offerPrice<=0||appliedShares<=0||minimumShares<=0||marginRate<=0||marginRate>1||accountCount<=0||totalAppliedShares<=0||equalPool<0||proportionalPool<0||subscriptionFee<0){
          res.innerHTML='<div class="cr-sub">공모가·청약주수·대상 계좌·총 유효 청약주수를 확인하고, 증거금률은 0% 초과 100% 이하로 입력해주세요.</div>'; return;
        }
        if(appliedShares<minimumShares){
          res.innerHTML=`<div class="cr-sub">내 청약주수 ${appliedShares.toLocaleString('ko-KR')}주는 최소 청약주수 ${minimumShares.toLocaleString('ko-KR')}주보다 적어 균등배정 대상이 될 수 없어요.</div>`; return;
        }
        if(totalAppliedShares<appliedShares){
          res.innerHTML='<div class="cr-sub">총 유효 청약주수는 내 청약주수보다 작을 수 없어요.</div>'; return;
        }
        const requiredDeposit=offerPrice*appliedShares*marginRate;
        const equalExact=Math.min(appliedShares,equalPool/accountCount);
        const equalBase=Math.floor(equalExact);
        const equalChance=(equalExact-equalBase)*100;
        const proportionalRaw=proportionalPool>0?appliedShares/totalAppliedShares*proportionalPool:0;
        const proportionalExpected=Math.min(appliedShares,proportionalRaw);
        const combinedExpected=Math.min(appliedShares,equalExact+proportionalExpected);
        const expectedPayment=combinedExpected*offerPrice;
        const balance=requiredDeposit-expectedPayment-subscriptionFee;
        const proportionalCompetition=proportionalPool>0?totalAppliedShares/proportionalPool:0;
        const equalText=equalChance>0.005
          ? `${equalBase.toLocaleString('ko-KR')}주 기본 + 1주 추첨 약 ${equalChance.toFixed(2)}%`
          : `${equalBase.toLocaleString('ko-KR')}주 기본 몫`;
        const settlementText=balance>=0
          ? `예상 환불액 ${fmtWon(balance)}`
          : `예상 추가 납입 필요액 ${fmtWon(Math.abs(balance))}`;
        res.innerHTML=`<div class="cr-main">필요 증거금 ${fmtWon(requiredDeposit)}</div>
          <div class="cr-sub">청약금액 ${fmtWon(offerPrice*appliedShares)} × 증거금률 ${(marginRate*100).toFixed(1)}%<br><br>
          <strong>균등배정</strong> · 1계좌 기대 ${equalExact.toFixed(4)}주<br>${equalText}<br>
          <strong>비례배정</strong> · 기대 ${proportionalExpected.toFixed(4)}주${proportionalCompetition?` (입력값 기준 약 ${proportionalCompetition.toFixed(2)} 대 1)`:''}<br>
          <strong>합계 기대배정 ${combinedExpected.toFixed(4)}주</strong><br><br>
          기대배정 납입대금 ${fmtWon(expectedPayment)} · 청약수수료 ${fmtWon(subscriptionFee)}<br>${settlementText}<br>
          <span style="color:var(--t3)">기대값은 확정 배정주수가 아니에요. 단수주·우대등급·추첨·추가납입 기준은 해당 인수회사의 최종 공고가 우선합니다.</span></div>`;
      };
    }
    if(item.calcType==='avgprice'){
      btn.onclick=()=>{
        const q1=n0(p('q1').value), pr1=n0(p('p1').value), q2=n0(p('q2').value), pr2=n0(p('p2').value), target=n0(p('target').value);
        const totalQty=q1+q2, totalCost=q1*pr1+q2*pr2;
        const res=p('result'); res.style.display='block';
        if(totalQty<=0){ res.innerHTML='<div class="cr-sub">보유수량과 추가매수 수량을 입력해주세요.</div>'; return; }
        const newAvg=totalCost/totalQty;
        const targetPrice=newAvg*(1+target/100);
        res.innerHTML=`<div class="cr-main">새 평단가 ${fmtWon(newAvg)}</div>
          <div class="cr-sub">총 보유수량 ${totalQty.toLocaleString('ko-KR')}주 · 총 매입금액 ${fmtWon(totalCost)}<br>
          목표 수익률 ${target}% 달성 매도가 ${fmtWon(targetPrice)}</div>`;
      };
    }
    if(item.calcType==='capitalgainstax'){
      btn.onclick=()=>{
        const sell=n0(p('sell').value), buy=n0(p('buy').value);
        const gain=Math.max(0, sell-buy);
        const taxBase=Math.max(0, gain-2500000);
        const tax=taxBase*0.22;
        const res=p('result'); res.style.display='block';
        res.innerHTML=`<div class="cr-main">예상 세액 ${fmtWon(tax)}</div>
          <div class="cr-sub">양도차익 ${fmtWon(gain)} − 기본공제 250만원 = 과세표준 ${fmtWon(taxBase)} × 22%</div>`;
      };
    }
    if(item.calcType==='compound'){
      btn.onclick=()=>{
        const principal=n0(p('principal').value), monthly=n0(p('monthly').value),
              rate=n0(p('rate').value), years=n0(p('years').value);
        const res=p('result'); res.style.display='block';
        if(years<=0){ res.innerHTML='<div class="cr-sub">투자 기간을 입력해주세요.</div>'; return; }
        const monthlyRate=rate/100/12, months=years*12;
        const fvPrincipal=principal*Math.pow(1+monthlyRate, months);
        const fvContrib=Math.abs(monthlyRate)>1e-9 ? monthly*((Math.pow(1+monthlyRate,months)-1)/monthlyRate) : monthly*months;
        const total=fvPrincipal+fvContrib;
        const totalPaid=principal+monthly*months;
        const profit=total-totalPaid;
        res.innerHTML=`<div class="cr-main">${years}년 뒤 ${fmtWon(total)}</div>
          <div class="cr-sub">총 납입원금 ${fmtWon(totalPaid)} · 예상 수익 ${profit>=0?'+':''}${fmtWon(profit)}</div>`;
      };
    }
    if(item.calcType==='loanpayment'){
      btn.onclick=()=>{
        const principal=n0(p('principal').value), rate=n0(p('rate').value), years=n0(p('years').value);
        const res=p('result'); res.style.display='block';
        if(principal<=0||years<=0){ res.innerHTML='<div class="cr-sub">대출원금과 대출기간을 입력해주세요.</div>'; return; }
        const monthlyRate=rate/100/12, months=years*12;
        const monthlyPayment=Math.abs(monthlyRate)>1e-9
          ? principal*monthlyRate*Math.pow(1+monthlyRate,months)/(Math.pow(1+monthlyRate,months)-1)
          : principal/months;
        const totalPayment=monthlyPayment*months;
        const totalInterest=totalPayment-principal;
        res.innerHTML=`<div class="cr-main">매달 ${fmtWon(monthlyPayment)}</div>
          <div class="cr-sub">총 상환액 ${fmtWon(totalPayment)} · 총 이자 ${fmtWon(totalInterest)}</div>`;
      };
    }
    if(item.calcType==='balancepayment'){
      btn.onclick=()=>{
        const price=n0(p('price').value), down=n0(p('down').value), interim=n0(p('interim').value),
              loan=n0(p('loan').value), rate=n0(p('rate').value), years=n0(p('years').value);
        const res=p('result'); res.style.display='block';
        if(price<=0){ res.innerHTML='<div class="cr-sub">매매가를 입력해주세요.</div>'; return; }
        const balance=Math.max(0, price-down-interim);
        const pct=price>0?(balance/price*100):0;
        const equity=Math.max(0, balance-loan);
        let loanHtml='';
        if(loan>0){
          if(years<=0){
            loanHtml=`<br><span style="color:var(--red)">대출기간을 입력하면 월 상환액도 계산해드려요.</span>`;
          } else {
            const monthlyRate=rate/100/12, months=years*12;
            const monthlyPayment=Math.abs(monthlyRate)>1e-9
              ? loan*monthlyRate*Math.pow(1+monthlyRate,months)/(Math.pow(1+monthlyRate,months)-1)
              : loan/months;
            const totalInterest=monthlyPayment*months-loan;
            loanHtml=`<br>대출 ${fmtWon(loan)} → 매달 ${fmtWon(monthlyPayment)}(총 이자 ${fmtWon(totalInterest)})<br>자기자본으로 준비할 금액 ${fmtWon(equity)}`;
          }
        }
        res.innerHTML=`<div class="cr-main">잔금 ${fmtWon(balance)}</div>
          <div class="cr-sub">매매가 대비 ${pct.toFixed(1)}% · 계약금+중도금 ${fmtWon(down+interim)}${loanHtml}</div>`;
      };
    }
    if(item.calcType==='dividendtax'){
      btn.onclick=()=>{
        const div=n0(p('div').value);
        const tax=div*0.154;
        const res=p('result'); res.style.display='block';
        res.innerHTML=`<div class="cr-main">세후 실수령 ${fmtWon(div-tax)}</div>
          <div class="cr-sub">세전 배당금 ${fmtWon(div)} − 원천징수세액 ${fmtWon(tax)}(15.4%)</div>`;
      };
    }
    if(item.calcType==='dsrltv'){
      btn.onclick=()=>{
        const house=n0(p('house').value), loan=n0(p('loan').value), rate=n0(p('rate').value),
              years=n0(p('years').value), income=n0(p('income').value), other=n0(p('other').value);
        const res=p('result'); res.style.display='block';
        if(house<=0||income<=0||years<=0){ res.innerHTML='<div class="cr-sub">주택가격·연소득·대출기간을 입력해주세요.</div>'; return; }
        const ltv=loan/house*100;
        const monthlyRate=rate/100/12, months=years*12;
        const monthlyPayment=Math.abs(monthlyRate)>1e-9
          ? loan*monthlyRate*Math.pow(1+monthlyRate,months)/(Math.pow(1+monthlyRate,months)-1)
          : loan/months;
        const annualPayment=monthlyPayment*12;
        const dsr=(annualPayment+other)/income*100;
        res.innerHTML=`<div class="cr-main">LTV ${ltv.toFixed(1)}% · DSR ${dsr.toFixed(1)}%</div>
          <div class="cr-sub">이 대출 월 예상 상환액 ${fmtWon(monthlyPayment)} · 연 원리금(기타 대출 포함) ${fmtWon(annualPayment+other)}</div>`;
      };
    }
    if(item.calcType==='etfplan') btn.onclick=()=>{const a=n0(p('principal').value),m=n0(p('monthly').value),annual=n0(p('rate').value),r=Math.pow(1+annual/100,1/12)-1,y=n0(p('years').value),dy=n0(p('yield').value)/100,t=n0(p('tax').value)/100,mo=y*12,res=p('result');res.style.display='block';if(y<=0||annual<=-100||dy<0||t<0||t>1){res.innerHTML='<div class="cr-sub">기간과 수익률을 확인하고, 분배율·세율은 0 이상(세율 100% 이하)으로 입력해주세요.</div>';return;}const total=a*Math.pow(1+r,mo)+(Math.abs(r)>1e-9?m*(Math.pow(1+r,mo)-1)/r:m*mo),paid=a+m*mo,netAnnual=total*dy*(1-t),netMonth=netAnnual/12;res.innerHTML=`<div class="cr-main">${y}년 뒤 ${fmtWon(total)}</div><div class="cr-sub">총 납입 ${fmtWon(paid)} · 예상 손익 ${fmtWon(total-paid)}<br>기간 말 평가액 기준 연 세후 분배금 ${fmtWon(netAnnual)} · 월평균 ${fmtWon(netMonth)}<br><span style="color:var(--t3)">분배금은 미래가치에 더하지 않은 기간 말 현금흐름 참고치예요. 연 수익률은 CAGR을 월 수익률로 환산했어요.</span></div>`;};
    if(item.calcType==='taxsavings') btn.onclick=()=>{const pp=n0(p('pension').value),pl=n0(p('pensionLimit').value),c=n0(p('credit').value)/100,g=n0(p('isaGain').value),free=n0(p('isaFree').value),reduced=n0(p('isaReduced').value)/100,normal=n0(p('isaTax').value)/100,res=p('result');res.style.display='block';if(!pl||c<0||c>1||reduced<0||reduced>1||normal<0||normal>1){res.innerHTML='<div class="cr-sub">공제 한도와 0~100% 사이의 세율을 입력해주세요.</div>';return;}const eligible=Math.min(pp,pl),pensionSave=eligible*c,isaTax=Math.max(0,g-free)*reduced,normalTax=g*normal,isaSave=Math.max(0,normalTax-isaTax);res.innerHTML=`<div class="cr-main">연금 세액공제 ${fmtWon(pensionSave)} · ISA 절세 ${fmtWon(isaSave)}</div><div class="cr-sub">연금 공제 대상 ${fmtWon(eligible)}<br>ISA 과세 대상 ${fmtWon(Math.max(0,g-free))} · ISA 세금 추정 ${fmtWon(isaTax)}<br>일반계좌 비교 세금 ${fmtWon(normalTax)}<br><span style="color:var(--t3)">연금은 1년 납입 기준, ISA는 입력한 전체 이익 기준이라 두 금액을 하나의 합계로 더하지 않았어요. 실제 공제는 결정세액 한도의 영향을 받아요.</span></div>`;};
    if(item.calcType==='youthasset') btn.onclick=()=>{const own=n0(p('monthly').value),support=n0(p('support').value),annual=n0(p('rate').value),m=own+support,r=Math.pow(1+annual/100,1/12)-1,n=n0(p('months').value),res=p('result');res.style.display='block';if(n<=0||annual<0){res.innerHTML='<div class="cr-sub">가입 기간과 0 이상의 금리를 입력해주세요.</div>';return;}const total=Math.abs(r)>1e-9?m*(Math.pow(1+r,n)-1)/r:m*n,principal=m*n,benefit=support*n+(total-principal);res.innerHTML=`<div class="cr-main">예상 만기 ${fmtWon(total)}</div><div class="cr-sub">본인 납입 ${fmtWon(own*n)} · 지원금 가정 ${fmtWon(support*n)}<br>예상 이자 ${fmtWon(total-principal)} · 지원금+이자 혜택 ${fmtWon(benefit)}<br><span style="color:var(--t3)">매월 말 본인 납입과 지원금이 함께 적립된다는 단순 가정이에요.</span></div>`;};
    if(item.calcType==='rentvsjeonse') btn.onclick=()=>{const j=n0(p('jeonse').value),l=n0(p('loan').value),lr=n0(p('loanRate').value)/1200,d=n0(p('deposit').value),rent=n0(p('rent').value),o=n0(p('opp').value)/1200,jMgmt=n0(p('jMgmt').value),rMgmt=n0(p('rMgmt').value),jCost=n0(p('jCost').value),rCost=n0(p('rCost').value),n=n0(p('months').value),res=p('result');res.style.display='block';if(n<=0||l>j){res.innerHTML='<div class="cr-sub">계약 기간을 확인하고, 전세 대출금은 전세 보증금 이하로 입력해주세요.</div>';return;}const jc=(l*lr+Math.max(0,j-l)*o+jMgmt)*n+jCost,rc=(rent+d*o+rMgmt)*n+rCost,diff=jc-rc,breakRent=(jc-rCost-(d*o+rMgmt)*n)/n,breakText=breakRent>=0?`두 비용이 같아지는 월세 약 ${fmtWon(breakRent)}`:'현재 가정에서는 0원 이상의 손익분기 월세가 없어요';res.innerHTML=`<div class="cr-main">${diff<=0?'전세':'월세'}가 ${fmtWon(Math.abs(diff))} 낮음</div><div class="cr-sub">${n}개월 전세 비용 ${fmtWon(jc)} · 월세 비용 ${fmtWon(rc)}<br>월 환산 전세 ${fmtWon(jc/n)} · 월세 ${fmtWon(rc/n)}<br>${breakText}</div>`;};
    if(item.calcType==='severance') btn.onclick=()=>{const w=n0(p('wage').value),d=n0(p('days').value),wd=n0(p('workdays').value),hours=n0(p('weeklyHours').value),extra=n0(p('extra').value),cash=n0(p('cash').value),e=n0(p('expense').value),res=p('result');res.style.display='block';if(!w||!d||!wd||!e){res.innerHTML='<div class="cr-sub">모든 필수 항목을 입력해주세요.</div>';return;}const avg=w/d,eligible=wd>=365&&hours>=15,sev=eligible?avg*30*wd/365:0,available=cash+sev+extra,months=available/e,warning=!eligible?'<br><span style="color:var(--red)">근속 1년 또는 주 평균 15시간 기준을 충족하지 않아 법정 퇴직금 추정을 0원으로 표시했어요. 실제 적용은 공식 상담으로 확인하세요.</span>':'';res.innerHTML=`<div class="cr-main">세전 퇴직금 추정 ${fmtWon(sev)}</div><div class="cr-sub">1일 평균임금 ${fmtWon(avg)} · 추가 정산 ${fmtWon(extra)}<br>보유 현금 포함 사용 가능액 ${fmtWon(available)} · 약 ${months.toFixed(1)}개월${warning}</div>`;};
    if(btn.onclick){
      const calculate=btn.onclick;
      btn.onclick=e=>{
        const controls=widget?[...widget.querySelectorAll('input,select,textarea')]:[];
        controls.forEach(control=>{
          control.removeAttribute('aria-invalid');
          const ids=(control.getAttribute('aria-describedby')||'').split(/\s+/).filter(id=>id&&id!==result?.id);
          if(ids.length) control.setAttribute('aria-describedby',ids.join(' '));
          else control.removeAttribute('aria-describedby');
        });
        calculate.call(btn,e);
        if(result){
          const invalid=Boolean(result.querySelector('.cr-sub'))&&!result.querySelector('.cr-main');
          result.setAttribute('role',invalid?'alert':'status');
          const nativeInvalid=controls.filter(control=>typeof control.checkValidity==='function'&&!control.checkValidity());
          const emptyInvalid=controls.filter(control=>control.tagName!=='SELECT'&&String(control.value).trim()==='');
          const invalidControls=nativeInvalid.length?nativeInvalid:emptyInvalid;
          if(invalid) invalidControls.forEach(control=>{
            control.setAttribute('aria-invalid','true');
            const ids=(control.getAttribute('aria-describedby')||'').split(/\s+/).filter(Boolean);
            if(!ids.includes(result.id)) ids.push(result.id);
            control.setAttribute('aria-describedby',ids.join(' '));
          });
          result.focus({preventScroll:true});
        }
      };
    }
  }

  window.GaeoCalc={html:calcWidgetHTML,wire:wireCalcWidget};
})();
