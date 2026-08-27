# 파이프라인 상태머신

`spec → implement → review` 진행을 오케스트레이터의 판단이 아니라 `sdd.py`의 상태에
맡기기 위한 장치다. 흐름이 끊기는 자리 — 세션 종료, `/clear`, 사용자 개입, 호스트 교체 —
에서 위치를 잃지 않는 것이 목적이다.

## 진행 위치는 어디에 있나

`<project>/.sdd/state.json`의 `pipeline` 키 하나에만 있다.

```jsonc
{
  "phase": "implement",              // 페이즈 게이트용 (기존 필드)
  "activeSpec": "user-marital-status",
  "pipeline": {
    "feature": "사용자 엔티티에 결혼여부 필드 추가",
    "slug": "user-marital-status",
    "stage": "implement",            // spec | implement | review | done
    "status": "running",             // running | awaiting-user | halted | done
    "attempts": {"spec": 0, "specRevision": 0, "implement": 1, "review": 1},
    "maxAttempts": 2,
    "steps": 5,                      // 전체 전이 횟수 (MAX_PIPELINE_STEPS=24에서 중단)
    "specPath": "specs/user-marital-status/spec-v1.md",
    "tasksPath": "specs/user-marital-status/tasks.md",
    "reviewPath": ".sdd/reviews/user-marital-status-v1-1.md",
    "carry": { /* 단계 간 인계 컨텍스트 — 아래 참조 */ },
    "history": [ {"at": "...", "stage": "review", "event": "changes-requested", "gaps": 2} ]
  }
}
```

`.sdd/.gitignore`가 `state.json`을 제외하므로 이 레코드는 커밋되지 않는다 — 로컬 진행
상태이지 공유 산출물이 아니다.

## 세 개의 서브커맨드

| 커맨드 | 하는 일 |
|---|---|
| `run "<설명>"` | 파이프라인 시작. 인자 없이 부르면 재개, `--resume`은 halted도 되살린다, `--restart`는 버리고 새로 시작 |
| `next` | **다음 행동 하나**를 지시한다. 부수효과(페이즈 전환·파일 생성)는 여기서 일어난다 |
| `advance --result '<json>'` | 서브에이전트 결과를 받아 전이를 결정하고, 새 `next`를 함께 돌려준다 |
| `abort --reason "<사유>"` | 진행 중인 파이프라인을 halted로 닫는다 |

`advance`의 응답에 이미 `next`가 들어 있으므로, 정상 루프에서 `next`를 따로 부를 일은
재개할 때뿐이다.

## `next.action`

| action | 의미 | 오케스트레이터가 할 일 |
|---|---|---|
| `call-agent` | 서브에이전트 한 번 호출 | `agent`·`instruction`·`context`를 그대로 전달, 결과를 `advance`에 |
| `ask-user` | 명세 단계에서 미결 질문 발생 | `questions`를 묻고 `{"answers": {...}}`로 `advance` |
| `done` | 리뷰 승인으로 완료 | 결과 요약 보고 |
| `halted` | 재시도 상한·수렴 실패·판정 불가 | `reason`을 그대로 보고하고 멈춤 |
| `none` | 파이프라인 없음 | `run "<설명>"` 안내 |
| `init-required` | `.sdd/state.json` 없음 | `/sdd:init` 안내 |

## 전이표

전이를 결정하는 것은 서브에이전트 결과의 몇 개 키뿐이다. 나머지 키는 무시된다.

| 현재 단계 | 결과 | 다음 |
|---|---|---|
| spec | `openQuestions` 있음 | `status: awaiting-user` — 사용자 답을 받으면 같은 단계 재개 |
| spec | `validate` 실패 | `attempts.spec++`, 같은 파일을 고치도록 spec 재호출. 상한 초과 시 halted |
| spec | `validate` 통과 | → implement |
| implement | `specChangeRequests` 있음 | `attempts.specRevision++`, **새 버전 명세**(v+1)를 만들며 → spec |
| implement | `testResult.failed > 0` | `attempts.implement++`, 실패 내용을 넘겨 재호출. 상한 초과 시 halted |
| implement | 테스트 통과 (또는 보고 없음) | → review |
| review | `verdict: approved` | 명세 `status: done` 기록, `phase: off`, `status: done` |
| review | `verdict: changes-requested` | `attempts.review++`, `gaps`를 넘겨 → implement. 상한 초과 시 halted |
| review | verdict 판독 불가 | halted |

`maxAttempts`는 기본 2이고 `run --max-attempts N`으로 바꾼다. 그 위에 전체 전이 횟수
상한(`MAX_PIPELINE_STEPS = 24`)이 따로 있어, 어떤 조합으로도 무한 루프가 되지 않는다.

`halted` 상태를 `run --resume`으로 되살리면 **단계별 재시도 예산이 0으로 리셋된다** —
멈춘 원인을 사람이 고치고 다시 시작하는 것이기 때문이다. 되살리기를 반복해도 `steps`
상한은 계속 누적되므로 결국 "수렴하지 않는다"로 멈춘다.

## 단계 간 인계 (`carry`)

서브에이전트끼리는 서로의 컨텍스트를 볼 수 없다. 그 간극을 메우는 것이 `carry`이며,
`next`가 각 단계의 `context`에 실어 보낸다.

| 인계 항목 | 만든 곳 | 받는 곳 |
|---|---|---|
| `validateErrors` | spec 검증 실패 | 다음 spec 호출 — 무엇이 틀렸는지 |
| `specChangeRequests` | 구현자 | spec 호출 — 새 버전에 반영할 항목 |
| `userAnswers` | 사용자 | spec 호출 — 미결 질문의 답 |
| `testFailures` | 구현 결과 | 다음 implement 호출 — "가설을 바꿔서" 재시도하도록 |
| `reviewGaps` | 리뷰어 | implement 호출 — 리뷰 지적이 구현으로 직접 넘어가는 경로 |
| `implementNotes` / `testResult` | 구현자 | review 호출 — 무엇을 어떻게 했는지 |
| `lastReviewPath` | 리뷰 리포트 골격 | implement 호출 — 리포트 전문을 읽을 수 있게 |

## 페이즈 게이트와의 관계

페이즈 전환은 `next` 안에서 자동으로 일어난다(`transition_phase`는 `/sdd:phase`와 같은
함수다). 손으로 `phase`를 부를 일은 파이프라인 밖에서 작업할 때뿐이다.

- `implement` 전환이 `blocked`면 파이프라인은 그 이유를 담아 **halted**가 된다. 게이트를
  끄고 지나가지 않는다.
- 리뷰 승인 시 명세 프론트매터의 `status: done`을 써야 하는데 review 페이즈에서는 `specs/`
  쓰기가 막힌다. `advance`는 이를 우회하지 않고 `phase: spec` → 기록 → `phase: off` 순으로
  **정식 전환**을 거친다. 그래서 `guard`에도 위반으로 남지 않는다.

## 멱등성

`next`는 부수효과를 갖지만 같은 단계에서 여러 번 불러도 안전하다. 명세 파일은 `specPath`가
비어 있을 때만, 리뷰 리포트는 `reviewPath`가 비어 있을 때만 만들어지고, 두 포인터는 단계를
떠날 때 비워진다. `tasks.md`는 이미 있으면 그대로 두되 **명세 버전이 올라갔으면 다시**
만든다(낡은 AC 대응표를 구현자에게 넘기지 않기 위해서다).

`advance`는 멱등이 아니다 — 한 번의 서브에이전트 호출에 정확히 한 번 부른다. `--stage`를
같이 주면 파이프라인의 현재 단계와 어긋난 결과를 거부하므로, 실수로 두 번 넘기는 사고를
막을 수 있다.

## 단계 안의 역할 순회

한 단계는 이제 에이전트 하나가 아니라 **로스터**다. `sdd.py depth`가 정한 목록을
`pipeline.roster[stage]`에 담고, `agentIndex`가 그 안의 위치를 가리킨다. `next`는
`roster`·`rosterPosition`(예: `2/3`)을 함께 돌려주므로 지금 몇 번째인지 알 수 있다.

| 단계 | 깊은 모드 순서 | 되돌아가는 지점 |
|---|---|---|
| spec | researcher → architect → auditor | auditor가 `revision-requested` → **architect** (`specAudit` 카운트) |
| implement | planner → engineer → tester | tester가 결함 보고 → **engineer** (`implement` 카운트) |
| review | 리뷰어 전원 **동시** | 하나라도 `changes-requested` → implement 단계 |

- 로스터는 **단계에 진입할 때마다 다시 계산된다**(`refresh_roster`). spec에서 light였어도
  명세가 커졌으면 implement에서 deep이 될 수 있다. `run --depth`로 강제한 값은
  `forcedDepth`에 남아 파이프라인 내내 유지된다.
- `_advance_agent`가 같은 단계의 다음 역할로 넘기고, 마지막이었으면 `_enter_stage`가
  다음 단계로 넘긴다. 그래서 경량 모드(역할 1개)의 전이는 예전과 완전히 같다.

## 리뷰 단계는 `call-agents`다

리뷰만 `action: "call-agent"`가 아니라 `"call-agents"`를 낸다. 리뷰어를 순차로 부르며 앞선
판정을 넘기면 독립성이 깨지고, 먼저 나온 관심사가 뒤의 것을 덮기 때문이다. 리뷰어가 하나뿐인
경량 모드에서도 형태는 같다 — 오케스트레이터가 분기할 일이 없게 한다.

```
advance --result '{"reviews": [{"agent": "spec-reviewer", "verdict": "approved"},
                               {"agent": "code-reviewer", "verdict": "changes-requested",
                                "gaps": ["빈 catch"]}]}'
```

**결과는 누적된다.** 한 번에 다 넘겨도 되고 하나씩 넘겨도 된다 — 다만 각 결과에 `agent`
키가 있어야 한다. 로스터가 여럿인데 이름 없는 판정을 넘기면 거부한다(한 리뷰어가 나머지를
대신 승인하는 경로를 막는다). 판정을 읽을 수 없는 리뷰어가 있으면 **그 리뷰어만** 다시
부르고, 이미 낸 사람은 `alreadyReported`에 담겨 재실행되지 않는다. 같은 요청이 무한
반복되지 않도록 재시도 상한이 계속 센다.

`combine_verdicts`가 종합한다:

- **하나라도 `changes-requested`면 전체가 `changes-requested`다.** 평균 내지 않는다.
- `gaps`에는 `[리뷰어이름]` 접두어가 붙어 구현자가 출처를 안다.
- `severity: "high"` 지적만 `gaps`에 합류해 재시도를 유발한다. `medium`/`low`는
  `softFindings`로 리포트에만 남는다.
- 로스터 전원의 판정이 오기 전에는 종합하지 않는다 — 일부만 보고 승인하는 경로가 없다.
- `gaps`의 `[리뷰어이름]` 접두어는 리뷰어가 둘 이상일 때만 붙는다(한 명이면 노이즈다).

## 여러 파이프라인 (병렬)

파이프라인은 기능마다 하나씩 `.sdd/state.json`의 `pipelines[<슬러그>]`에 산다.
`activePipeline`은 "마지막으로 손댄 것"일 뿐 정본이 아니다. 0.5.0 이전의 단일 `pipeline`
필드는 `load_pipelines()`가 읽는 순간 레지스트리로 옮겨진다(구버전 리더를 위해 초점이 가
있는 하나는 그 필드에 계속 비춰 준다).

```bash
sdd.py run "기능 A"          # 막히지 않는다
sdd.py run "기능 B"          # 둘 다 살아 있다
sdd.py run --all             # 살아 있는 것 전부를 대상으로 배치 루프를 연다
sdd.py board                 # 누가 지금 움직일 수 있는가
sdd.py next --all            # 이번 라운드에 동시에 호출해도 되는 행동들
sdd.py advance --spec 기능-a --result '<json>'
sdd.py advance --spec 기능-b --result '<json>'
```

### `--spec`을 언제 반드시 줘야 하는가

살아 있는 파이프라인이 **하나면 생략해도 된다** — 예전 호출과 완전히 같다. 둘 이상이면:

| 명령 | 생략하면 |
|---|---|
| `advance` | **거부한다.** 결과를 엉뚱한 파이프라인에 먹이면 그 기능의 상태가 남의 결과로 전이되고, 그건 조용히 잘못된다 |
| `next` | `action: "choose-pipeline"` + 보드를 돌려준다 |
| `abort` | 거부한다 (`--all`이 전부 중단) |
| `run`(재개) | `activePipeline` **하나만** 재개한다 — 전부를 돌리려면 `--all` |

### 스케줄러가 정하는 것

`schedule()`이 이번 라운드의 `runnable`과 `waiting`을 나눈다. **이 판단을 모델이 하면 두
서브에이전트가 같은 파일을 동시에 고쳐 한쪽 작업이 조용히 사라진다.**

1. **페이즈 게이트는 프로젝트 전역이다.** 훅의 stdin에 호출자 정보가 없으므로 게이트는
   "지금 이 프로젝트가 어떤 페이즈인가" 하나만 안다. 그래서 `enforce: true`에서는 **같은
   페이즈에 있는 파이프라인끼리만** 동시에 움직인다. 현재 페이즈에서 아무도 못 움직이면
   가장 오래 기다린 파이프라인의 단계로 페이즈가 넘어간다 — 굶지 않는다.
   `enforce: false`면 게이트가 무동작이므로 페이즈가 달라도 함께 돈다.
2. **구현 단계는 파일이 겹치면 직렬화한다.** `impl-planner`가 확정한 `tasks[].files`와
   지금까지의 `filesChanged`로 집합을 만들어 교집합을 본다. **계획이 없으면(경량 모드)
   "모른다 = 겹칠 수 있다"로 보고 직렬화한다** — 추측으로 동시에 돌리지 않는다.
   깊은 모드에서 파일 범위가 서로 다르면 두 기능의 구현이 진짜로 동시에 돈다.
3. spec 단계는 각자 `specs/<슬러그>/`만 쓰고, review 단계는 아무것도 쓰지 않으므로
   둘 다 겹침 검사가 필요 없다.

`waiting[]` 항목은 `slug`·`stage`·`reason`(·`blockedBy`)을 담는다. 우회하지 말고 그대로
보고한다 — 다음 `next --all`에서 자리가 나면 자동으로 `round[]`로 올라온다.

## 워크트리 — 병렬성의 두 병목을 없앤다

`config.json`의 `"worktrees": true`(또는 `run --worktree`)면 기능마다
`.sdd/worktrees/<슬러그>/`에 독립된 체크아웃과 `sdd/<슬러그>` 브랜치가 생긴다.
`sdd.py init --worktrees`로 켜고, 그 디렉터리는 `.sdd/.gitignore`에 자동으로 들어간다.

| 제약 | 워크트리 없이 | 워크트리로 |
|---|---|---|
| 구현 파일 겹침 | 계획으로 교집합을 보고 직렬화 | **디렉터리가 달라 겹칠 수 없다** |
| `enforce: true`의 페이즈 결합 | 같은 페이즈끼리만 동시 실행 | **파이프라인마다 자기 단계로 게이팅** |

두 번째가 핵심이다. PreToolUse 페이로드에는 호출자가 없지만 **워크트리 경로에는 슬러그가
있다.** `resolve_write()`가 쓰기 경로를 그 워크트리의 주인에게 귀속시키고, 훅은 전역
`state.phase`가 아니라 **그 파이프라인의 `stage`** 로 판정한다. deny 메시지에는
`[슬러그]` 접두어가 붙는다. 이것이 페이즈 게이트를 켠 채로 진짜 병렬 실행이 되는 유일한
경로다.

### 무엇이 어디에 사는가

| | 위치 | 왜 |
|---|---|---|
| `specs/<슬러그>/` | **본체** | 슬러그별로 갈라져 있어 충돌하지 않는다 |
| `.sdd/` (상태·리뷰) | **본체** | 상태가 흩어지면 재개가 깨진다 |
| `src/`, `tests/` | **워크트리** | 여기가 격리되어야 하는 유일한 부분이다 |

`next`의 `context.workdir`가 그 파이프라인의 작업 디렉터리다. `trace`·`guard`는
`--workdir`로 그쪽을 스캔하고, `review-report`는 파이프라인의 workdir을 자동으로 쓴다.

### 정리와 병합

`sdd.py worktree list | status | add | remove`. **병합은 하지 않는다** — 승인된 브랜치를
어디에 어떻게 합칠지는 사용자의 판단이다. `remove`는 커밋되지 않은 변경이 있으면 거부하고
변경 목록을 보여준다(`--force`로 버릴 수 있지만 그건 사용자가 정한다).

git 저장소가 아니면 워크트리를 만들지 못한다. 그때 `run`은 파이프라인을 막지 않고 본체에서
돌리되 `worktreeWarning`에 사유를 담는다 — 조용히 본체에서 도는 일이 없게 한다.

## 끝난 단계를 다시 열기 (`run --from`)

```bash
sdd.py run --spec <슬러그> --from review [--depth deep]
```

`done`·`halted` 인 파이프라인의 특정 단계를 되연다. `--restart` 와 다르다 — `--restart`
는 파이프라인을 새로 만들어 **명세 버전을 올린다.** `--from` 은 `specPath`·`specVersion`
과 carry 를 유지하고 그 단계만 되돌린다.

되열 때 `refresh_roster` 가 다시 돌아 **지금 버전의 로스터가 적용된다.** 반환값의
`rosterBefore` / `roster` 로 무엇이 달라졌는지 알 수 있다 — 리뷰어가 1명에서 4명으로
늘어난 업그레이드 뒤에 리뷰만 다시 돌리는 것이 주 용도다.

단계별로 되돌리는 것:

| `--from` | 초기화되는 것 |
|---|---|
| `review` | `reviewPath`(리포트를 새로 만든다), 리뷰 재시도 카운트, 누적된 리뷰어 결과 |
| `implement` | 구현 재시도 카운트, 직전 테스트 실패, 구현 결함 |
| `spec` | 명세 재시도·감사 카운트 |

