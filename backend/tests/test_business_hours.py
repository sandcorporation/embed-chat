"""상담 가능 시간(영업시간) 판정 (issue 135).

순수 함수 is_open을 고정 now_utc로 결정적 검증. 타임존·요일·시간창·휴일·미설정(24/7).
"""
import datetime as dt
import pytest

UTC = dt.timezone.utc


def _config(**kw):
    """is_open이 읽는 속성만 가진 가벼운 config 대역(타임존·스케줄·휴일)."""
    from types import SimpleNamespace
    return SimpleNamespace(
        hitl_timezone=kw.get("tz", ""),
        hitl_schedule=kw.get("schedule", {}),
        hitl_holidays=kw.get("holidays", []),
    )


# 2026-06-22는 월요일(KST). 09:00~18:00 KST 창을 기준으로 검증.
WEEKDAY_9_18 = {"mon": {"enabled": True, "start": "09:00", "end": "18:00"}}


def test_unconfigured_is_always_open():
    """타임존·스케줄 미설정이면 24/7 open(opt-in 하위호환)."""
    from apps.tenants.business_hours import is_open
    assert is_open(_config(), dt.datetime(2026, 6, 22, 3, 0, tzinfo=UTC)) is True


def test_open_within_window_in_tenant_timezone():
    """KST 13:00(=04:00 UTC) 월요일은 09:00~18:00 창 안 → open."""
    from apps.tenants.business_hours import is_open
    cfg = _config(tz="Asia/Seoul", schedule=WEEKDAY_9_18)
    assert is_open(cfg, dt.datetime(2026, 6, 22, 4, 0, tzinfo=UTC)) is True


def test_start_inclusive_end_exclusive():
    """창 경계: start(09:00 KST=00:00 UTC) 포함, end(18:00 KST=09:00 UTC) 제외."""
    from apps.tenants.business_hours import is_open
    cfg = _config(tz="Asia/Seoul", schedule=WEEKDAY_9_18)
    assert is_open(cfg, dt.datetime(2026, 6, 22, 0, 0, tzinfo=UTC)) is True    # 09:00 KST
    assert is_open(cfg, dt.datetime(2026, 6, 22, 9, 0, tzinfo=UTC)) is False   # 18:00 KST
    assert is_open(cfg, dt.datetime(2026, 6, 21, 23, 0, tzinfo=UTC)) is False  # 08:00 KST(전)


def test_weekday_off_is_closed():
    """월요일만 켠 스케줄에서 화요일(2026-06-23)은 closed."""
    from apps.tenants.business_hours import is_open
    cfg = _config(tz="Asia/Seoul", schedule=WEEKDAY_9_18)
    assert is_open(cfg, dt.datetime(2026, 6, 23, 4, 0, tzinfo=UTC)) is False  # 화 13:00 KST


def test_holiday_overrides_open_window():
    """창 안이어도 그 날짜가 휴일이면 강제 휴무."""
    from apps.tenants.business_hours import is_open
    cfg = _config(tz="Asia/Seoul", schedule=WEEKDAY_9_18, holidays=["2026-06-22"])
    assert is_open(cfg, dt.datetime(2026, 6, 22, 4, 0, tzinfo=UTC)) is False


@pytest.mark.django_db
def test_fields_persist_on_tenant_config(tenant_with_key):
    """새 스케줄 필드가 TenantConfig에 저장·복원된다(마이그레이션 검증)."""
    from apps.tenants.models import TenantConfig
    from apps.tenants.business_hours import is_open
    tenant, _ = tenant_with_key
    config = TenantConfig.objects.get(tenant=tenant)
    config.hitl_timezone = "Asia/Seoul"
    config.hitl_schedule = WEEKDAY_9_18
    config.hitl_holidays = ["2026-06-22"]
    config.save()

    reloaded = TenantConfig.objects.get(tenant=tenant)
    assert reloaded.hitl_timezone == "Asia/Seoul"
    assert reloaded.hitl_schedule["mon"]["start"] == "09:00"
    assert is_open(reloaded, dt.datetime(2026, 6, 22, 4, 0, tzinfo=UTC)) is False  # 휴일
