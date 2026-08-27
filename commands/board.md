---
description: 살아 있는 파이프라인 전부의 위치와 실행 가능 여부를 표로 보여준다
argument-hint: (인자 없음)
---

`spec-driven-dev` 스킬을 **board 모드**로 실행한다.

`sdd.py board --path .`의 JSON을 표로 렌더한다: 슬러그·기능·단계·상태·깊이·지금 부를
에이전트, 그리고 `scheduled`(runnable / waiting / done / halted). `waiting`이면
`waitReason`을 그대로 보여준다 — 페이즈 게이트가 다른 페이즈를 잡고 있거나 구현 파일이
겹치는 두 경우뿐이다.

`counts.runnable`이 2 이상이면 `/sdd:run`으로 이번 라운드를 동시에 돌릴 수 있다고 안내한다.
