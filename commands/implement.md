---
description: 명세를 기반으로 구현하고 테스트를 작성한다 (software-engineer 서브에이전트)
argument-hint: [슬러그], 예: user-marital-status (비우면 activeSpec 사용)
---

`spec-driven-dev` 스킬을 **implement 모드**로 실행한다. 대상 슬러그: **$ARGUMENTS**
(비어 있으면 `.sdd/state.json`의 `activeSpec`을 쓴다).

phase를 `implement`로 전환한다(명세가 유효하지 않으면 `blocked`로 막히므로 그 이유를
그대로 보고하고 멈춘다). `software-engineer` 서브에이전트를 호출해 구현·테스트를
진행시키고, 실행된 테스트 결과를 실제로 확인해 보고한다.
