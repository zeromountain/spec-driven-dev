---
description: 구현이 명세를 따르는지 검증하고 리뷰 리포트를 남긴다 (spec-reviewer 서브에이전트, 한 스텝만)
argument-hint: [슬러그], 예: user-marital-status (비우면 진행 중인 파이프라인)
---

`spec-driven-dev` 스킬을 **review 모드**로 실행한다. 대상 슬러그: **$ARGUMENTS**

파이프라인 루프를 **한 번만** 돌린다. `sdd.py next`가 review 단계를 지시하면 리뷰 리포트
골격은 이미 `.sdd/reviews/`에 만들어져 있고 커버리지·미커버 AC·게이트 위반이 채워져 있다 —
그 값을 `spec-reviewer`에게 근거로 주고 호출한다(다시 계산하지 마라).

반환된 판정·갭·제안으로 리포트의 남은 `{{...}}`를 채워 저장한 뒤, 그 JSON을
`sdd.py advance`에 넘긴다. 판정(approved / changes-requested)과 다음 `next`를 명확히
보고한다. 승인이면 명세의 `status: done` 기록과 페이즈 정리는 스크립트가 이미 했다.
