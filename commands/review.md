---
description: 명세 준수·코드 품질·보안·성능 리뷰를 돌리고 리포트를 남긴다 (한 스텝만)
argument-hint: [슬러그] [--deep|--light], 예: user-marital-status (비우면 진행 중인 파이프라인)
---

`spec-driven-dev` 스킬을 **review 모드**로 실행한다. 대상 슬러그: **$ARGUMENTS**

파이프라인 루프를 **한 번만** 돌린다. `sdd.py next`가 review 단계를 지시하면 리뷰 리포트
골격은 이미 `.sdd/reviews/`에 만들어져 있고 커버리지·미커버 AC·게이트 위반이 채워져 있다 —
그 값을 근거로 주고 `next.agents[]`의 리뷰어를 **한 메시지에서 동시에** 호출한다
(다시 계산하지 말고, 서로의 판정을 알려주지 마라 — 독립성이 깨진다).

각 리뷰어의 본문으로 리포트의 남은 `{{...}}`를 채워 저장한 뒤, 결과에 `agent` 키를 붙여
`sdd.py advance --result '{"reviews": [...]}'`로 **한 번에** 넘긴다. 종합 판정은 스크립트가
낸다 — 하나라도 `changes-requested`면 전체가 그렇다. 리뷰어별 판정과 종합 판정, 다음
`next`를 명확히 보고한다. 승인이면 명세의 `status: done` 기록과 페이즈 정리는 스크립트가 이미 했다.
