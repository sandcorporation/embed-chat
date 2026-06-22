"""상담 가능 시간(영업시간) 판정 — deep module (issue 135).

테넌트 타임존 + 요일별 시간창 + 휴일 캘린더로 "지금이 상담 시간인가"를 결정한다.
미설정(타임존·스케줄 비어 있음)이면 항상 open(24/7, opt-in 하위호환). 순수 함수라
고정 now_utc를 주입해 결정적으로 테스트한다. 그래프 선택(issue 136)이 이 신호를 쓴다.
"""
import datetime as dt
from zoneinfo import ZoneInfo

# 월요일=0 … 일요일=6 인덱스를 스케줄 키로 매핑.
_WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _parse_hhmm(value: str) -> dt.time:
    h, m = value.split(":")
    return dt.time(int(h), int(m))


def is_open(config, now_utc: dt.datetime) -> bool:
    """now_utc(타임존 인지 datetime) 기준으로 상담 가능 시간이면 True.

    미설정 → True. 휴일 → False. 요일 off → False. 시간창 [start, end) 밖 → False.
    """
    timezone = getattr(config, "hitl_timezone", "") or ""
    schedule = getattr(config, "hitl_schedule", None) or {}
    if not timezone or not schedule:
        return True  # opt-in: 미설정이면 24/7

    local = now_utc.astimezone(ZoneInfo(timezone))

    holidays = getattr(config, "hitl_holidays", None) or []
    if local.date().isoformat() in holidays:
        return False  # 휴일은 요일을 덮어쓴다

    day = schedule.get(_WEEKDAY_KEYS[local.weekday()])
    if not day or not day.get("enabled"):
        return False

    start = _parse_hhmm(day["start"])
    end = _parse_hhmm(day["end"])
    return start <= local.time() < end  # start 포함, end 제외
