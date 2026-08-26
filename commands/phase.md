---
description: SDD 페이즈 게이트를 수동으로 전환하거나 해제한다
argument-hint: <spec|implement|review|off>
---

`spec-driven-dev` 스킬을 **phase 모드**로 실행한다. 전환 대상: **$ARGUMENTS**

`sdd.py phase <target> --path .`를 실행하고 결과(`from`/`to`/`blocked`/`reasons`)를
그대로 보고한다. `implement`로 전환하면서 대상 명세가 유효하지 않으면 `blocked: true`가
반환되니 이유를 사용자에게 알린다.
