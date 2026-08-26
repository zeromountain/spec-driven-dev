---
description: 기능 명세를 작성하거나 갱신한다 (spec-architect 서브에이전트)
argument-hint: <기능 설명>, 예: 사용자 엔티티에 결혼여부 필드 추가
---

`spec-driven-dev` 스킬을 **spec 모드**로 실행한다. 대상: **$ARGUMENTS**

phase를 `spec`으로 전환한 뒤 `spec-architect` 서브에이전트를 호출한다. 반환된 명세를
`sdd.py validate`로 검증하고, 실패하면 최대 2회까지 고쳐서 재검증한다. `openQuestions`가
있으면 사용자에게 그대로 묻는다.
