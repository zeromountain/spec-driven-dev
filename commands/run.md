---
description: 명세 작성부터 구현·리뷰까지 전체 파이프라인을 순서대로 실행한다
argument-hint: <기능 설명>, 예: 사용자 엔티티에 결혼여부 필드 추가
---

`spec-driven-dev` 스킬을 **run 모드**로 실행한다. 대상: **$ARGUMENTS**

spec → implement → review를 이 세션이 직접 순서대로 호출한다(서브에이전트는 서브에이전트를
낳을 수 없으므로 오케스트레이션은 여기서 한다). review 판정이 `changes-requested`면
implement로 되돌아가되 최대 2회까지만 자동 반복한다. 그래도 남으면 자동 반복을 멈추고
남은 갭을 사용자에게 보고한다.
