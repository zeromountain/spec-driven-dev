---
description: 기능 명세를 작성하거나 갱신한다 (spec-architect 서브에이전트, 한 스텝만)
argument-hint: <기능 설명>, 예: 사용자 엔티티에 결혼여부 필드 추가
---

`spec-driven-dev` 스킬을 **spec 모드**로 실행한다. 대상: **$ARGUMENTS**

파이프라인 루프를 **한 번만** 돌린다. 진행 중인 파이프라인이 없으면
`sdd.py run "$ARGUMENTS"`로 시작하고, 있으면 `sdd.py next`부터 이어간다.

`next`가 `call-agent`를 지시하면 그 컨텍스트로 `spec-architect`를 호출하고, 반환된 JSON을
`sdd.py advance`에 넘긴 뒤 **다음 `next`를 사용자에게 보여주고 멈춘다**(이어서 구현까지
가려면 `/sdd:run`). `next.stage`가 `spec`이 아니면 그 사실을 알리고 파이프라인의 단계를
따른다. `ask-user`가 나오면 질문을 그대로 사용자에게 전달한다.
