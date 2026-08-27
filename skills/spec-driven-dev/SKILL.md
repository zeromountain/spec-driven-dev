---
name: spec-driven-dev
description: 명세를 소스 오브 트루스로 삼는 Spec-Driven Development(SDD) 하네스를 설정하고 운영한다. "SDD 시작해줘", "명세부터 만들자", "spec-driven으로 개발하자", "AGENTS.md에 SDD 규약 걸어줘" 같은 요청, 또는 이미 SDD가 설정된 프로젝트에서 "명세 써줘", "이 기능 구현해줘"(명세 기반으로), "리뷰해줘"(명세 대조), "지금 페이즈가 뭐야" 같은 요청에 쓴다. SDD 프로젝트에서 중단된 작업을 이어가려는 요청("이어서 해줘", "아까 하던 거 계속", "어디까지 했지")에도 쓴다 — 진행 위치가 .sdd/state.json에 남아 있어 컨텍스트 없이도 재개된다. 단순 코드 작성/버그 수정처럼 명세 없이 바로 구현하면 되는 요청에는 쓰지 않는다 — 그건 일반 개발 워크플로의 영역이다.
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
3. **다음 행동도 스크립트가 정한다.** 파이프라인이 돌고 있는 동안 "이제 구현으로 넘어갈
   차례"라고 네가 판단하지 않는다 — `next`가 시키는 행동 하나만 하고 `advance`로 결과를
   넘긴다. 진행 위치는 대화가 아니라 `.sdd/state.json`의 `pipeline`에 있으므로, 어디까지
   했는지 사용자에게 되묻지 않는다.
4. **세 역할의 경계를 존중한다.** Spec Architect는 `specs/`만, Software Engineer는
   `src/`·`tests/`·`specs/<slug>/tasks.md`만, Review Agent는 쓰기 자체를 하지 않는다.
5. **기능은 Review Agent 승인 후에만 완료다.** `verdict: "changes-requested"`인 채로
   "완료됐다"고 보고하지 않는다.
6. **하드 게이트를 대신 끄지 않는다.** 페이즈 게이트가 deny하면, 그 파일을 다른 경로로
   우회해 쓰지 않는다. 파이프라인 안에서는 `next`가 정식 전환을 이미 하며, 전환이 막히면
   `halted`로 그 이유를 그대로 보고한다. 게이트를 끄는 것은 사용자의 `/sdd:phase off`뿐이다.

## 모드

| 모드 | 트리거 | 실행 |
|---|---|---|
| init | `/sdd:init` | `sdd.py init` → 스캐폴딩, AGENTS.md 병합, 하드 게이트 여부 확인 |
| run | `/sdd:run <설명>` | 파이프라인 시작 → **next/advance 루프**를 끝까지 돌린다 |
| resume | `/sdd:run` (인자 없이) | 중단된 파이프라인을 그 자리에서 재개 |
| spec / implement / review | `/sdd:spec` 등 | 루프를 **한 번만** 돌린다 (수동 스텝) |
| status | `/sdd:status` | `sdd.py status` JSON을 표로 렌더 (파이프라인 위치 포함) |
| phase | `/sdd:phase <spec\|implement\|review\|off>` | 수동 전환 (파이프라인이 알아서 하므로 평소엔 불필요) |

## 워크플로

### 준비: 스크립트 경로 확인 (세션당 한 번)

```bash
ls -d ~/spec-driven-dev/scripts 2>/dev/null \
  || find ~/.claude/plugins/cache ~/.codex/plugins/cache -maxdepth 5 -type d \
       -path '*sdd*/scripts' 2>/dev/null | sort -V | tail -1
```

개발용 체크아웃(`~/spec-driven-dev`)이 있으면 그쪽을 쓰고, 없으면 설치된 캐시에서 찾는다.
캐시에는 orphaned 구버전이 함께 남아 있으므로 **버전 정렬 후 마지막**을 쓴다 — `head -1`은
0.2.0 같은 구버전을 집을 수 있다.

결과를 `$S`로 취급한다(셸 변수는 Bash 호출 간 유지되지 않으므로, 이후 모든 명령에서
경로를 텍스트로 그대로 치환해 쓴다). `$S/sdd.py`가 CLI 진입점이다.

### 0단계: 컨텍스트 확인

`$S/sdd.py status --path <project-root>`로 현재 phase·명세 목록·게이트 위반·파이프라인
위치를 먼저 본다. `.sdd/state.json`이 없으면 아직 `/sdd:init`이 실행되지 않은 것이다 —
init부터 안내한다.

### 1단계: 파이프라인 루프 (run 모드 — 기본 경로)

파이프라인의 진행 위치는 **대화 컨텍스트가 아니라 `.sdd/state.json`의 `pipeline` 레코드**에
있다. 그러니 이 루프에서 네가 판단할 것은 없다. `next`가 시키는 행동 하나를 하고, 그 결과를
`advance`에 넘기고, 그 응답의 `next`로 다음 라운드를 연다.

```bash
# 시작 (인자를 비우면 중단된 파이프라인을 그 자리에서 재개한다)
$S/sdd.py run "<기능 설명>" --path <root>
```

응답의 `next.action`에 따라 아래를 **`done`·`halted`·`ask-user`가 나올 때까지 반복한다**:

| `action` | 할 일 |
|---|---|
| `call-agent` | `agent`가 지정한 서브에이전트를 `instruction` + `context`를 **그대로** 전달해 호출한다. 반환된 JSON을 그대로 `$S/sdd.py advance --path <root> --stage <stage> --result '<json>'`에 넘긴다. 그 응답의 `next`가 다음 라운드다. |
| `ask-user` | `questions`를 사용자에게 그대로 묻는다. 답을 `advance --result '{"answers": {...}}'`로 넘기면 루프가 이어진다. |
| `done` | 완료. 5단계(기록)로 간다. |
| `halted` | `reason`과 `history`를 그대로 사용자에게 보고하고 멈춘다. 지어내서 우회하지 않는다. |
| `init-required` / `none` | 각각 `/sdd:init`, `/sdd:run <설명>`을 안내한다. |

**루프 중 하지 말 것:**

- `next`가 시키지 않은 일을 미리 하지 마라. 페이즈 전환, 명세 파일 생성, `tasks.md`,
  리뷰 리포트 골격, 승인 시 `status: done` 갱신은 **전부 `next`/`advance`가 이미 했다**.
  `phase`·`new`·`tasks`·`review-report`를 손으로 부르면 상태가 어긋난다.
- `advance`를 건너뛰고 다음 서브에이전트를 부르지 마라 — 그 순간 파이프라인이 제자리에 남는다.
- 단계 사이에서 사용자에게 "계속할까요?"를 묻지 마라. 멈추는 건 `ask-user`와 `halted`뿐이다.
- 재시도 횟수를 세지 마라. `attempts`/`maxAttempts`는 `advance`가 센다.

### 2단계: 수동 스텝 (`/sdd:spec`, `/sdd:implement`, `/sdd:review`)

진행 중인 파이프라인이 있으면 이 명령들은 **루프를 한 번만 돌린다** — `next` 한 번,
서브에이전트 한 번, `advance` 한 번. 그리고 다음 `next`를 사용자에게 보여주고 멈춘다.
`next.stage`가 사용자가 부른 단계와 다르면 그 사실을 알리고 파이프라인의 단계를 따른다
(임의로 건너뛰지 않는다).

진행 중인 파이프라인이 없으면 `$S/sdd.py run "<설명>"`으로 새로 시작한 뒤 한 스텝만 돌린다.

### 3단계: 중단과 재개

- 세션이 끊겼거나 `/clear` 후에도 `$S/sdd.py next --path <root>` 한 번이면 진행 위치·다음
  행동·직전 이력이 전부 돌아온다. 어디까지 했는지 사용자에게 되묻지 마라.
- `halted` 상태에서 원인을 고쳤으면 `$S/sdd.py run --resume --path <root>`로 같은 자리에서
  다시 시작한다.
- 사용자가 그만두길 원하면 `$S/sdd.py abort --reason "<사유>" --path <root>`.
- 다른 기능으로 갈아타려면 `$S/sdd.py run "<새 설명>" --restart --path <root>` (직전
  파이프라인은 `pipelineHistory`에 요약만 남는다).

### 4단계: 왜 이 구조인가

**서브에이전트는 서브에이전트를 낳을 수 없다** — 그래서 오케스트레이션은 서브에이전트가
아니라 이 스킬(메인 세션)이 직접 돌린다. 다만 *무엇을 다음에 할지*는 이 스킬이 아니라
`sdd.py`의 상태머신이 정한다. 그래야 컨텍스트가 날아가도, 사용자가 중간에 끼어들어도,
호스트가 Claude Code든 Codex든 같은 자리에서 같은 다음 행동이 나온다.

### 5단계: 기록

작업이 끝나면 `$S/sdd.py status --path <root>`로 최종 상태를 한 번 더 확인하고 사용자에게
요약한다(phase, 명세 목록, 리뷰 판정, 남은 게이트 위반, 파이프라인 라운드 수).

## 참조 파일

- `references/pipeline.md` — 상태머신 전이표, `next`/`advance` 계약, 중단 사유별 대처
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
