# ADR-0010: Entity 정체성을 이름이 아니라 맥락으로 — Mention/Entity 분리 + 비파괴 동치(SAME_AS)

## Status
Accepted (ADR-0007의 "name이 Entity 식별키" 전제를 supersede)

## Context
현재 Entity는 `MERGE (e:Entity {tenant_id, name})`로 **이름 정확일치**로만 식별·병합된다(graph_store.upsert_entity). Community는 union-find **연결요소**라 각 Entity는 정확히 하나의 Community에 속한다. 이름을 정체성으로 삼은 결과 양방향으로 새는 것이 특성화 테스트로 확인됐다(test_graph_community.py: synonym/identical/overmerge):

- **과소병합**: 같은 대상의 다른 표기(`FCB1010` vs `FCB-1010`, `메뉴` vs `OSD Menu`)가 별도 노드 → 서로 다른 Community로 파편화.
- **과대병합**: 다른 대상의 같은 이름(동음이의 — 한강 "다리" vs 신체 "다리", 또는 흔한 일반명 `User Manual`)이 한 노드로 뭉개짐. 이건 resolution 이전에 **ingest 시점에 이미** 발생하며 description 임베딩마저 덮어써진다.

세 케이스(`FCB1010/FCB-1010`=같음, `다리/다리`=다름, `Pedal A/Pedal B`=다름)를 나란히 놓으면 **이름은 세 번 다 오답**을 준다. 일치하는 신호는 맥락뿐이다.

## Decision
**Entity의 정체성을 이름이 아니라 맥락(설명·이웃 관계·출처)으로 정의한다.**

- **동치 정의(Entity Equivalence)**: 두 Entity Mention이 같은 실세계 referent를 가리키면 동치다. 이름 유사도는 약한 보조 신호일 뿐이고, **맥락 정합**이 판별한다.
- **Mention/Entity 분리**: 문서에서 추출된 개별 언급을 **Entity Mention**(name + 그 문맥의 설명 + 출처)으로 둔다. 이름이 같아도 맥락이 다르면 별개 Mention이다(name-MERGE 폐기). resolution이 동치인 Mention들을 하나의 **Entity**로 묶는다.
- **비파괴 SAME_AS**: 동치를 노드 물리 병합이 아니라 **SAME_AS 동치 엣지**로 표현한다. 노드·표기·출처를 보존하고, 잘못 묶으면 엣지만 끊어 되돌린다.
- **배치 시점**: SAME_AS 계산을 `rebuild_communities`(ADR-0008의 배치 트리거)에 얹는다. 전역 그래프를 보고 일관되게 resolution하고, 연결요소 계산에 SAME_AS를 연결로 포함시켜 동치 Mention이 같은 Community에 들어가게 한다.
- **신호 = 임베딩(name+description) 유사도**: 이미 entity 임베딩이 `name: description`으로 만들어지므로(graph_ingester) 맥락(설명)이 반영된다. 동음이의("다리")는 설명 임베딩이 달라 분리되고, 표기변이는 합쳐진다.
- **보수적 resolution**: 위험이 비대칭이다 — 과대병합은 referent를 오염시키고("다리"가 뒤섞임) 의미를 손상하지만, 과소병합은 중복 노드가 남을 뿐 검색은 임베딩으로 여전히 둘 다 찾는다. 따라서 **확신할 때만 SAME_AS**를 만들고 애매하면 분리를 유지한다. SAME_AS는 비파괴라 놓친 동치는 추후 보강할 수 있다.

## Considered Options
- **파괴적 canonical 병합(노드 물리 합침)**: 기각. 표기·출처가 손실되고 잘못된 병합을 되돌릴 수 없다. 비파괴 SAME_AS가 같은 효과(Community 통합)를 내면서 안전하다.
- **name-MERGE 유지 + SAME_AS로 과소병합만 해결**: 기각. 동음이의 과대병합("다리")을 못 고친다 — 이름이 식별키인 한 ingest에서 이미 뭉개지기 때문.
- **이름 임베딩 단독 신호**: 기각. `FCB1010/FCB-1010`(같음)과 `Pedal A/Pedal B`(다름)를 둘 다 "매우 유사"로 봐 구분 못 한다. 맥락(설명·이웃)이 referent를 결정한다.
- **LLM 1차 판정**: 보류. 미세 구분(Pedal A/B)엔 가장 정확하나 비결정적이고 LLM 경계를 Fake로 막는 테스트 원칙상 resolution 품질을 회귀로 검증할 수 없다. 보수적 임베딩 신호로 1차 처리하고, LLM 최종 판정은 향후 보강 후보로 남긴다.
- **공격적(낮은 임계) 병합**: 기각. 비대칭 위험상 과병합은 과소병합보다 해롭다.
- **인제스션 시점 resolution**: 기각. 증분 비교가 복잡하고 이미 무거운 인제스션에 부담. 배치가 전역 일관성과 "더 넓은 범위" 관점에 맞다.

## Consequences
- ADR-0007의 "name이 Entity 식별키" 전제가 바뀐다. RELATED 관계·Community 멤버십·search_entities·neighbors 등 **이름을 Entity 참조로 쓰는 모든 경로**가 Mention/Entity 단위로 재정의되어야 한다 — 큰 재설계다.
- Community(연결요소)는 이제 Entity 단위로 의미를 가지며, SAME_AS가 동치 Mention을 잇는다.
- test_graph_community.py의 특성화 테스트(synonym→2, overmerge→1)는 resolution 도입 시 **깨지면서 '고쳐졌다'는 신호**가 된다 — 그대로 수용 기준이다.
- 보수적 정책상 일부 동의어는 초기엔 분리된 채 남을 수 있다(검색은 임베딩으로 무중단). 임계·맥락 신호는 fixture로 튜닝한다.
- LLM 최종 판정은 도입하지 않았으므로 `Pedal A/B`류 미세 구분은 설명/이웃 신호의 품질에 의존한다.
