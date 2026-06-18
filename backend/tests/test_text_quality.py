"""깨진 추출(Garbled Extraction) 감지 휴리스틱 단위 테스트.

is_garbled는 외부 의존이 없는 순수 함수다. DB·인프라 없이 검증한다.
"""
from apps.rag.text_quality import is_garbled


# fcb1010 문서에서 실제로 추출된 깨진(mojibake) 텍스트 — 폰트 ToUnicode 매핑 부재로
# 글리프가 의미 없는 ASCII/기호로 찍힌 케이스 (visitor checkpoint rag_chunks에서 채집).
GARBLED_FCB1010 = (
    "-%&././ 2*$* . ./G/ 2*$* . 1 PRG CHG 1 2 PRG CHG 2 3 PRG CHG 3 4 PRG CHG 4 "
    "5 PRG CHG 5 6 CNT 1 7 CNT 2 8 EXP A 9 EXP B 10/0 NOTE -% *+ , ,(/. 4 2*$* "
    "?'$ 8G'') 2*$* 2*$*%(4?'$ % 2*$* . ./G/ 'F)'::*@'$4?47 8G'') "
    "$@0G':%4' $)1& %@-*+?'$ %@-*+8)4*@"
)


def test_is_garbled_detects_fcb1010_mojibake():
    """폰트 인코딩이 깨져 mojibake로 추출된 텍스트를 깨짐으로 판정한다."""
    assert is_garbled(GARBLED_FCB1010) is True


def test_is_garbled_accepts_normal_korean():
    """정상 한글 본문은 깨짐이 아니다."""
    text = (
        "이 설명서는 모니터 기능, 모니터 설정 및 모니터 사용에 관한 기술 사양 및 정보를 제공합니다. "
        "설치 지침과 문제 해결 방법을 단계별로 안내하며, 안전 정보도 함께 포함합니다."
    )
    assert is_garbled(text) is False


def test_is_garbled_accepts_normal_english():
    """정상 영어 본문은 깨짐이 아니다."""
    text = (
        "SWITCH 1 determines if the UP key toggles the SWITCH 1 relay "
        "while DIRECT SELECT is enabled. Press and hold the footswitch to enter edit mode."
    )
    assert is_garbled(text) is False


def test_is_garbled_accepts_symbol_heavy_code():
    """기호가 많은 정상 코드 스니펫은 깨짐이 아니다 (오탐 방지)."""
    text = "def calc(x, y): return (x * 2) + (y - 1) / 3  # compute weighted score"
    assert is_garbled(text) is False


def test_is_garbled_accepts_numeric_spec_table():
    """숫자·기호 위주의 정상 사양 표는 깨짐이 아니다 (오탐 방지)."""
    text = (
        "Resolution 1920x1080 | Refresh 60Hz | Aspect 16:9 | Brightness 250 cd/m2 | "
        "Ports HDMI 2.0, DisplayPort 1.4, USB-C | Weight 4.5 kg | Power 90W"
    )
    assert is_garbled(text) is False


def test_is_garbled_empty_text_is_not_garbled():
    """빈/공백 텍스트는 깨짐이 아니다 — OCR 트리거는 단어 수 조건이 담당한다."""
    assert is_garbled("") is False
    assert is_garbled("   \n\t ") is False
