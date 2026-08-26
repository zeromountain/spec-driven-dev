---
name: spec-driven-dev
description: 명세를 소스 오브 트루스로 삼는 Spec-Driven Development(SDD) 하네스를 설정하고 운영한다. "SDD 시작해줘", "명세부터 만들자", "spec-driven으로 개발하자", "AGENTS.md에 SDD 규약 걸어줘" 같은 요청, 또는 이미 SDD가 설정된 프로젝트에서 "명세 써줘", "이 기능 구현해줘"(명세 기반으로), "리뷰해줘"(명세 대조), "지금 페이즈가 뭐야" 같은 요청에 쓴다. 단순 코드 작성/버그 수정처럼 명세 없이 바로 구현하면 되는 요청에는 쓰지 않는다 — 그건 일반 개발 워크플로의 영역이다.
---

# Spec-Driven Development (spec-driven-dev)

이 스킬의 목적은 "코드를 고치기 전에 명세부터 고친다"는 규율을 **프롬프트가 아니라
하네스로 집행하는 것**이다. Spec Architect·Software Engineer·Review Agent 세 역할이
각자의 쓰기 범위 안에서만 움직이고, `enforce: true`인 프로젝트에서는 PreToolUse 훅이
실제로 그 경계를 막는다.

## 절대 규칙

1. **명세가 소스 오브 트루스다.** 구현 동작을 바꿔야 하면 먼저 명세를 바꾼다(또는 새
   버전을 만든다) — 코드를 몰래 명세와 다르게 고치지 않는다.
2. **숫자·판정은 스크립트가 낸다.** 명세 유효성(`validate`), 버전 번호(`new`), 페이즈
   전환 가능 여부(`phase`), 추적성(`trace`), 위반(`guard`)을 대화 중 암산하지 않는다.
   `${scriptPath} <subcommand>`의 JSON 출력을 그대로 읽는다.
3. **세 역할의 경계를 존중한다.** Spec Architect는 `specs/`만, Software Engineer는
   `src/`·`tests/`·`specs/<slug>/tasks.md`만, Review Agent는 쓰기 자체를 하지 않는다.
4. **기능은 Review Agent 승인 후에만 완료다.** `verdict: "changes-requested"`인 채로
   "완료됐다"고 보고하지 않는다.
5. **하드 게이트를 대신 끄지 않는다.** 페이즈 게이트가 deny하면, 그 파일을 다른 경로로
   우회해 쓰지 않는다. `/sdd:phase`로 정식 전환하거나 사용자에게 `/sdd:phase off`를
   요청한다.

## 모드

| 모드 | 트리거 | 실행 |
|---|---|---|
| init | `/sdd:init` | `sdd.py init` → 스캐폴딩, AGENTS.md 병합, 하드 게이트 여부 확인 |
| spec | `/sdd:spec <설명>` | phase→`spec`, `spec-architect` 호출, `validate` 통과까지 반복 |
| implement | `/sdd:implement [슬러그]` | phase→`implement`(validate 조건), `software-engineer` 호출 |
| review | `/sdd:review [슬러그]` | phase→`review`, `spec-reviewer` 호출, 리포트 저장 |
| run | `/sdd:run <설명>` | spec→implement→review 순차 실행, 갭 있으면 최대 2회 재시도 |
| status | `/sdd:status` | `sdd.py status` JSON을 표로 렌더 |
| phase | `/sdd:phase <spec\|implement\|review\|off>` | 수동 전환 |

## 워크플로

### 준비: 스크립트 경로 확인 (세션당 한 번)

```bash
find ~/spec-driven-dev ~/.claude/plugins/cache -maxdepth 5 -type d -path '*sdd*/scripts' 2>/dev/null | head -1
```

결과를 `$S`로 취급한다(셸 변수는 Bash 호출 간 유지되지 않으므로, 이후 모든 명령에서
경로를 텍스트로 그대로 치환해 쓴다). `$S/sdd.py`가 CLI 진입점이다.

### 0단계: 컨텍스트 확인

`$S/sdd.py status --path <project-root>`로 현재 phase·명세 목록·게이트 위반을 먼저 본다.
`.sdd/state.json`이 없으면 아직 `/sdd:init`이 실행되지 않은 것이다 — init부터 안내한다.

### 1단계: 명세 (spec 모드)

1. `$S/sdd.py phase spec --path <root>`로 전환한다.
2. `spec-architect` 서브에이전트를 "기능 설명 + 관련 기존 코드 컨텍스트"로 호출한다.
3. 반환된 `specPath`를 `$S/sdd.py validate <specPath>`로 검증한다. `valid: false`면
   에러 목록을 서브에이전트에게 다시 넘겨 고치게 한다(최대 2회 재시도, 그래도 안 되면
   `openQuestions`를 사용자에게 그대로 전달).
4. `openQuestions`가 있으면 사용자에게 묻는다 — 지어내지 않는다.

### 2단계: 구현 (implement 모드)

1. `$S/sdd.py phase implement --spec <slug> --path <root>`로 전환한다. `blocked: true`면
   이유를 그대로 보고하고 멈춘다(보통 명세가 아직 유효하지 않다는 뜻).
2. `software-engineer` 서브에이전트를 "명세 경로 + 프로젝트 언어/테스트 러너 정보"로
   호출한다.
3. 반환된 `testResult`가 실패를 포함하면 재시도시킨다(가설을 바꿔서 — 같은 시도 반복 금지).
4. `specChangeRequests`가 있으면 1단계로 돌아가 명세를 갱신한다.

### 3단계: 리뷰 (review 모드)

1. `$S/sdd.py phase review --spec <slug> --path <root>`로 전환한다.
2. `$S/sdd.py trace <specPath> --path <root>`와 `$S/sdd.py guard --path <root>`를 먼저
   실행해 그 결과를 `spec-reviewer`에게 근거로 준다.
3. 반환된 리포트를 `templates/review-report.md` 구조로 `.sdd/reviews/<slug>-v<N>-<seq>.md`에
   저장한다(seq는 해당 슬러그·버전의 기존 리포트 개수+1).
4. `verdict: "changes-requested"`면 2단계로 되돌아간다. `run` 모드에서는 최대 2회까지만
   자동 반복하고, 그래도 남으면 사용자에게 갭을 보고하고 멈춘다.

### 4단계: run (전체 파이프라인)

**서브에이전트는 서브에이전트를 낳을 수 없다** — 그래서 이 오케스트레이션은 서브에이전트가
아니라 이 스킬(메인 세션)이 1→2→3단계를 순서대로 직접 호출하는 방식으로만 성립한다.

### 5단계: 기록

작업이 끝나면 `$S/sdd.py status --path <root>`로 최종 상태를 한 번 더 확인하고 사용자에게
요약한다(phase, 명세 목록, 리뷰 판정, 남은 게이트 위반).

## 참조 파일

- `references/roles.md` — 세 역할의 책임·금지 사항 요약
- `references/spec-format.md` — 8섹션 정의, AC-N 규약, 버저닝 규칙
- `references/phase-gate.md` — 훅 동작, 페이즈별 deny 표, 탈출구, Bash 미커버 이유
- `references/templates.md` — 스캐폴딩 산출물 전문과 최종 디렉터리 구조

## 하지 않을 것

- `enforce: true`인 프로젝트에서 게이트가 deny한 경로를 셸 명령으로 우회해 쓰지 않는다.
- 커버리지 90%를 이 스킬이 직접 측정해 강제하지 않는다 — 언어별 커버리지 도구는 프로젝트
  마다 다르다. `config.json`의 `minCoverage`는 Review Agent에게 넘기는 기준값일 뿐이고,
  측정 불가하면 리포트에 "측정 안 됨"으로 남긴다.
- 대상 프로젝트의 기존 `AGENTS.md`/`CLAUDE.md`를 통째로 덮어쓰지 않는다.
- auto-dev 같은 다른 개발 하네스와 기능을 합치지 않는다. 구현 루프를 다른 하네스에 맡기고
  싶다면 `/sdd:implement` 대신 그쪽을 쓰고, 이 스킬은 명세·리뷰 단계만 담당하게 한다.

## 면책

이 스킬은 강제되는 프로세스를 제공할 뿐, 명세의 품질이나 구현의 정확성을 보증하지 않는다.
`validate`는 구조를, `trace`는 태깅 규약이 지켜졌을 때의 커버리지만 확인한다 — 실제 코드
리뷰와 테스트 실행 결과를 대체하지 않는다.
