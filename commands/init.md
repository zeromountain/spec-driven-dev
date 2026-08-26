---
description: 현재 프로젝트에 SDD 하네스를 스캐폴딩한다 (specs/·AGENTS.md·.sdd/ 생성)
argument-hint: (인자 없음, 필요하면 --enforce 를 대화로 안내한다)
---

`spec-driven-dev` 스킬을 **init 모드**로 실행한다.

`sdd.py init --path .`를 실행하고 결과(`created`/`skipped`/`agentsMd`)를 보고한다.
마지막에 AskUserQuestion으로 하드 페이즈 게이트(PreToolUse 훅)를 지금 켤지 물어본다 —
켜기로 하면 `sdd.py init --path . --enforce`로 재실행한다. 이미 `AGENTS.md`/`CLAUDE.md`가
있었다면 어떤 파일에 어떻게 반영됐는지(`created`/`appended`/`replaced`) 명확히 알린다.
