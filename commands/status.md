---
description: 현재 SDD 페이즈·명세 목록·게이트 위반을 표로 보여준다
argument-hint: (인자 없음)
---

`spec-driven-dev` 스킬을 **status 모드**로 실행한다.

`sdd.py status --path .`의 JSON을 표로 렌더한다: 현재 phase·enforce 여부·activeSpec,
명세별 슬러그/버전/유효성/AC 개수/리뷰 횟수, 남은 guard 위반. `.sdd/state.json`이 없으면
아직 `/sdd:init`이 안 된 것이니 그 사실만 알리고 안내한다.
