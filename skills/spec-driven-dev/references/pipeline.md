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

`combine_verdicts`가 종합한다:

- **하나라도 `changes-requested`면 전체가 `changes-requested`다.** 평균 내지 않는다.
- `gaps`에는 `[리뷰어이름]` 접두어가 붙어 구현자가 출처를 안다.
- `severity: "high"` 지적만 `gaps`에 합류해 재시도를 유발한다. `medium`/`low`는
  `softFindings`로 리포트에만 남는다.
- 로스터 전원의 판정이 오지 않으면 종합하지 않고 `halted`가 된다 — 일부만 보고 승인하는
  경로를 남기지 않는다.
- 판정 문자열이 `approved`/`changes-requested`가 아니면 그 리뷰어를 이름으로 지목하며
  `halted`가 된다.

