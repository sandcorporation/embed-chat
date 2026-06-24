"""토큰 사용량 기록 (deep module).

record_usage가 TokenUsage 일 버킷 행을 원자적 upsert로 증분한다(ON CONFLICT, GraphStore 패턴).
동시 호출에도 손실 없이 누적된다. 호출 상세는 Langfuse가, 이 집계는 인앱 뷰가 쓴다.
"""
from django.db import connection


def record_usage(tenant_id, call_type: str, model: str,
                 input_tokens: int = 0, output_tokens: int = 0) -> None:
    input_tokens = int(input_tokens or 0)
    output_tokens = int(output_tokens or 0)
    total = input_tokens + output_tokens
    with connection.cursor() as cur:
        cur.execute(
            """
            INSERT INTO token_usage
                (tenant_id, call_type, model, date,
                 input_tokens, output_tokens, total_tokens, request_count)
            VALUES (%s, %s, %s, CURRENT_DATE, %s, %s, %s, 1)
            ON CONFLICT (tenant_id, call_type, model, date) DO UPDATE SET
                input_tokens  = token_usage.input_tokens  + EXCLUDED.input_tokens,
                output_tokens = token_usage.output_tokens + EXCLUDED.output_tokens,
                total_tokens  = token_usage.total_tokens  + EXCLUDED.total_tokens,
                request_count = token_usage.request_count + 1
            """,
            [str(tenant_id), call_type, model, input_tokens, output_tokens, total],
        )
