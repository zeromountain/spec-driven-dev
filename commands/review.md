---
description: 구현이 명세를 따르는지 검증하고 리뷰 리포트를 남긴다 (spec-reviewer 서브에이전트)
argument-hint: [슬러그], 예: user-marital-status (비우면 activeSpec 사용)
---

`spec-driven-dev` 스킬을 **review 모드**로 실행한다. 대상 슬러그: **$ARGUMENTS**
(비어 있으면 `.sdd/state.json`의 `activeSpec`을 쓴다).

phase를 `review`로 전환한다. `sdd.py trace`와 `sdd.py guard`를 먼저 실행해 그 결과를
`spec-reviewer` 서브에이전트에게 근거로 준 뒤 호출한다. 반환된 리포트를
`.sdd/reviews/<슬러그>-v<N>-<seq>.md`에 저장하고 판정(approved/changes-requested)을
명확히 보고한다.
