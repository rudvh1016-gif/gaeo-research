"""기업행사 관련 공시 제목 판정 — 옛 저장소 comparison_evidence.py 의 relevant() 만 옮겼다.

옛 comparison_evidence 는 가격 비교(시세 원장)·KIND 시장조치 분류와 묶여 있어 그대로 가져오지 않는다.
이 모듈은 공시 제목 문자열만 본다(네트워크 0 · 시세 0). SCOPE_VERSION 은 이미 저장된 증거와
호환되도록 옛 값을 그대로 쓴다 — 바꾸면 기존 comparisonFindings 가 다른 범위로 읽힌다.
"""
import corporate_action_classify as corporate

SCOPE_VERSION = 'price-comparison-v1'
EXTRA_TERMS = ('주식병합', '주식분할', '액면병합', '권리락', '배당락', '기준가격', '거래중단', '재상장', '변경상장', '정리매매',
               '현금배당', '현금·현물배당', '현금및현물배당')


def relevant(title):
    """Additional observation scope; never changes the collector's scoring inputs."""
    return bool(corporate.classify(title)['effects'] or any(t in title for t in EXTRA_TERMS))
