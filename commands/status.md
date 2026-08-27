---
description: 현재 SDD 페이즈·파이프라인 위치·명세 목록·게이트 위반을 표로 보여준다
argument-hint: (인자 없음)
---

`spec-driven-dev` 스킬을 **status 모드**로 실행한다.

`sdd.py status --path .`의 JSON을 표로 렌더한다: 현재 phase·enforce 여부·activeSpec,
명세별 슬러그/버전/유효성/AC 개수/리뷰 횟수, 남은 guard 위반. `pipeline`이 있으면 진행
중인 기능·단계·상태·재시도 횟수를 함께 보여주고, `status`가 `running`이나 `awaiting-user`
면 `sdd.py next`로 다음 행동까지 확인해 알린다(`/sdd:run`으로 이어갈 수 있다고 안내).

`.sdd/state.json`이 없으면 아직 `/sdd:init`이 안 된 것이니 그 사실만 알리고 안내한다.
