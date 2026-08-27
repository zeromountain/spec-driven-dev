---
description: 명세를 기반으로 구현하고 테스트를 작성한다 (software-engineer 서브에이전트, 한 스텝만)
argument-hint: [슬러그], 예: user-marital-status (비우면 진행 중인 파이프라인)
---

`spec-driven-dev` 스킬을 **implement 모드**로 실행한다. 대상 슬러그: **$ARGUMENTS**

파이프라인 루프를 **한 번만** 돌린다. `sdd.py next`가 지시하는 서브에이전트를 그 컨텍스트로
호출하고, 반환된 JSON을 `sdd.py advance`에 넘긴 뒤 다음 `next`를 보여주고 멈춘다.

`next`가 `halted`를 내면(보통 명세가 유효하지 않아 implement 페이즈 전환이 막힌 경우)
이유를 그대로 보고하고 멈춘다 — 게이트를 우회하지 않는다. 구현자가 반환한 `testResult`는
가공하지 말고 그대로 넘기고, 실제 테스트 실행 결과를 사용자에게도 보고한다.
