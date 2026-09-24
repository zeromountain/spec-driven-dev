# 역할

SDD 하네스는 하나의 책임을 페이즈 3개 × 역할 6개로 쪼갠다. 각 역할의 상세 프롬프트는
`agents/<이름>.md`에 있다. 여기서는 오케스트레이터가 각 단계에서 지켜야 할 요약과,
역할 사이에 무엇이 오가는지만 둔다.

경량 모드에서는 굵게 표시된 역할만 돈다 — 나머지는 깊은 모드에서 붙는다. 어느 쪽인지는
`sdd.py depth`가 정한다 (`references/depth.md`).

## spec 페이즈

| 역할 | 쓰기 | 받는 것 | 내는 것 |
|---|---|---|---|
| **`spec-architect`** | `specs/` | 기능 설명, 명세 경로, `existingSpecs`/`archivedSpecs` | 채워진 명세, `openQuestions` |

- **조사도 검토도 architect 혼자 감당한다** — 별도의 조사·감사 역할은 없다.
  `existingSpecs`/`archivedSpecs`를 확인하고 필요하면 Read/Grep/Glob으로 기존 코드를
  읽는다. 완성한 뒤에는 스스로 적대적으로 다시 읽어 검증 불가능한 AC·모순·누락된 오류
  케이스가 없는지 확인한다. 거기 없는 사실이 필요하면 `openQuestions`로 돌린다 —
  요구사항을 지어내지 않는다.
- **아카이브는 삭제가 아니다** — 완료된 명세는 `specs/archive/<슬러그>/`로 옮겨지고
  architect에게 `archivedSpecs`로 전달된다. 새 기능과 충돌할 가능성이 가장 높은 것이
  이미 만들어 놓은 기능이다. architect는 아카이브에 쓰지 않는다.
- 동작이 바뀌면 새 버전, 명확화는 제자리 수정.

## implement 페이즈

| 역할 | 쓰기 | 받는 것 | 내는 것 |
|---|---|---|---|
| `impl-planner` | `specs/<slug>/tasks.md` | 명세 경로, `sdd.py tasks` | `tasks[]`(태스크별 `verify` 커맨드 포함), `patternsToFollow`, `testRunner` |
| **`software-engineer`** | `src/`, `tests/` | 명세 경로, (있으면) 계획 JSON | `filesChanged`, `testResult`, `verifyResults`, `specChangeRequests` |

- 구현 전 반드시 명세를 읽고 `validate`로 구조를 확인한다.
- 인수 기준 없는 동작을 구현하지 않는다.
- AC마다 최소 1개 테스트, `AC-N` 태그를 남긴다.
- **구현과 테스트는 항상 engineer 혼자 한다** — 별도의 테스트 작성 역할은 없다. `plan`이
  있으면(깊은 모드) 그 태스크·패턴·순서를 따르되 테스트는 여전히 engineer가 쓴다.
  독립된 검증자가 없으므로 방금 쓴 테스트와 프로젝트의 기존 테스트를 함께 돌려 회귀를
  스스로 확인한다.
- `specs/<slug>/tasks.md` 외에는 `specs/`를 고치지 않는다.

## review 페이즈

| 역할 | 관심사 | 판정에 쓰는 근거 |
|---|---|---|
| **`code-reviewer`** | 가독성·복잡도·중복·에러 처리·프로젝트 관례 | 변경 파일, 기존 코드 |
| `security-reviewer` | 입력 검증·인가·시크릿·인젝션·데이터 노출 | 변경 파일, `securityHits` |
| `perf-reviewer` | N+1·복잡도·재계산·경계 없는 로딩·동시성 | 변경 파일, `perfHits`, 비기능 요구사항 |

- 셋 다 **쓰기 도구가 없다** — 판정과 리포트 본문만 낸다.
- `trace`·`guard` 스크립트 결과(인수 기준 커버리지·게이트 위반)는 리포트에 자동으로
  채워지지만, 이걸 근거로 판정을 내리는 전담 리뷰어는 없다 — **명세 준수·AC 커버리지·
  스펙 밖 구현을 전담 판정하는 역할이 없다.** `code-reviewer`가 리뷰 중 명백히 스펙을
  벗어난 게 보이면 `findings`에 남기지만, 이건 부차적 안전망이지 보장이 아니다.
- 판정은 각자 **approved** 또는 **changes-requested** 둘 중 하나.
  **하나라도 changes-requested면 전체가 changes-requested다** — 평균 내지 않는다.
- 관심사가 겹치면 판정에 넣지 말고 `handoffs`로 넘긴다. 같은 문제를 셋이 각자 감점하면
  심각도가 부풀려진다.
- `severity: high`만 자동 재시도를 유발한다. `medium`/`low`는 리포트에만 남는다.
- `security-reviewer`·`perf-reviewer`는 **깊이와 무관하게** 신호가 잡히면 붙는다 —
  한 줄짜리 인증 수정에도 보안 리뷰는 돈다. 신호가 없으면 `code-reviewer` 혼자
  review 단계를 끝낸다.
- 리뷰어들은 **서로의 판정을 보지 않는다.** 오케스트레이터가 한 메시지에서 동시에 부른다.

## 사람의 역할

AI가 명세·계획·구현·리뷰를 쓰는 동안 사람은 **작성자가 아니라 판단자**다. 파이프라인이
사람에게 돌아오는 자리는 셋이다.

| 자리 | 언제 | 사람이 하는 일 |
|---|---|---|
| 명세 승인 (`approve`, `gate: spec`) | 기본 켜짐. 명세가 검증을 통과할 때마다 | 인수 기준·오류 케이스·범위 밖·가정이 의도와 맞는지 판단. 고칠 점은 `feedback`으로 |
| 계획 승인 (`approve`, `gate: plan`) | `humanGates.plan: true`일 때, 깊은 모드의 계획 직후 | 태스크 분해·손댈 파일·검증 커맨드 판단 |
| 미결 질문 (`ask-user`) | 아키텍트가 `openQuestions`를 낼 때 | 도메인 지식으로 답 |
| 회고 (`reflect`) | 리뷰 승인 직후 | 스크립트가 센 사실(재시도·막힌 내용)을 보고, 다음 기능이 덜 틀리도록 남길 교훈을 고른다 |

그리고 그 전에 **`docs/sdd/`의 PRD·아키텍처·ADR**을 채우는 것 — 에이전트가 모르는
맥락을 외부화하는 일 — 이 사람이 가장 많은 시간을 쓸 자리다.

## 모든 역할이 공통으로 받는 것

- `contextDocs` — 프로젝트 지식 문서(PRD·아키텍처·ADR, `docs/sdd/`). 사람이 머릿속에
  두던 관례·결정을 에이전트가 추측하지 않게 하는 채널이다. 경로만 실리고 본문은 각자
  읽는다. `unfilled: true`인 문서는 빈 양식이니 근거로 쓰지 않는다.
- `parentSpecPath` (spec·implement) — 계층형 명세에서 상위 명세의 경로.

## 무엇이 강제되고 무엇이 강제되지 않는가

`enforce: true`인 프로젝트에서 `hooks/phase_gate.py`가 막는 것은 **페이즈 경계**다 —
spec 페이즈에 `src/`를 못 쓰고, implement 페이즈에 명세를 못 고치고, review 페이즈에
아무것도 못 고친다. 자세한 규칙은 `references/phase-gate.md`.

읽기 전용 역할(리뷰어 3종)은 `tools:` 프론트매터에 쓰기 도구가 아예 없으므로 **도구
수준에서 강제된다** — 이쪽은 확실하다.
