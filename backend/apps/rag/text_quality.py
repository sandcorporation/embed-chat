"""깨진 추출(Garbled Extraction) 감지 — 문자 클래스 비율 휴리스틱.

PDF 텍스트 레이어의 폰트 인코딩(ToUnicode/CID 매핑) 부재로 글리프가 의미 없는
문자열(mojibake)로 추출된 경우를 감지한다. 외부 의존이 없는 순수 함수로,
PDFIngester의 OCR 폴백 결정과 Text Unit 청크 드롭 양쪽에서 공유한다.
"""
import re

# 의미 있는 letter: 한글 음절 + 라틴 알파벳
_LETTER_RE = re.compile(r"[A-Za-z가-힣]")
_NON_SPACE_RE = re.compile(r"\S")

# 비공백 문자 중 letter 비율이 이 값 미만이면 깨짐으로 본다.
# 측정치(문서 전체): 깨짐 ~0.18, 정상 ~0.82.
_MIN_LETTER_RATIO = 0.5


def is_garbled(text: str) -> bool:
    """추출 텍스트가 mojibake로 깨졌는지 판정한다."""
    non_space = _NON_SPACE_RE.findall(text)
    if not non_space:
        return False
    letters = _LETTER_RE.findall(text)
    return len(letters) / len(non_space) < _MIN_LETTER_RATIO
