---
description: 완성된 명세를 적대적으로 재검토한다 (spec-auditor 서브에이전트)
argument-hint: [슬러그], 예: user-marital-status (비우면 activeSpec 사용)
---

`spec-driven-dev` 스킬을 **audit 모드**로 실행한다. 대상 슬러그: **$ARGUMENTS**
(비어 있으면 `.sdd/state.json`의 `activeSpec`을 쓴다).

`sdd.py validate <spec-path>`를 먼저 실행해 그 JSON을 근거로 주고 `spec-auditor`
서브에이전트를 호출한다. `validate`는 구조만 보므로, 이 명령은 그 통과분에서
검증 불가능한 AC·모순·누락된 오류 케이스를 찾는 단계다. `verdict`가
`revision-requested`면 지적을 그대로 보고하고, 고칠지 사용자에게 묻는다 —
명세 수정은 `/sdd:spec`(spec-architect)의 일이다.
