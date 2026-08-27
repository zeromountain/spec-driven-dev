# 역할

SDD 하네스는 하나의 책임을 페이즈 3개 × 역할 10개로 쪼갠다. 각 역할의 상세 프롬프트는
`agents/<이름>.md`에 있다. 여기서는 오케스트레이터가 각 단계에서 지켜야 할 요약과,
역할 사이에 무엇이 오가는지만 둔다.

경량 모드에서는 굵게 표시된 역할만 돈다 — 나머지는 깊은 모드에서 붙는다. 어느 쪽인지는
`sdd.py depth`가 정한다 (`references/depth.md`).

## spec 페이즈

| 역할 | 쓰기 | 받는 것 | 내는 것 |
|---|---|---|---|
| `spec-researcher` | 없음 | 기능 설명, `sdd.py list` | `contextPack` |
| **`spec-architect`** | `specs/` | 기능 설명, 명세 경로, `contextPack`, `auditFindings` | 채워진 명세, `openQuestions` |
| `spec-auditor` | 없음 | 명세 경로, `validate` JSON | `verdict`, `acFindings`, `missingErrorCases` |

- **researcher는 제안하지 않는다** — "지금 이렇게 되어 있다"만 적는다. 설계는 아키텍트의 몫.
- **architect는 조사하지 않는다**(깊은 모드에서) — 컨텍스트 팩에 없는 사실이 필요하면
  `openQuestions`로 돌린다. 요구사항을 지어내지 않는다.
- **auditor는 고치지 않는다** — 결함과 제안 문장만 낸다. 수정은 아키텍트에게 되돌아간다.
- 동작이 바뀌면 새 버전, 명확화는 제자리 수정.
- auditor → architect 왕복은 **최대 2회**. 그래도 남으면 사용자에게 넘긴다.

## implement 페이즈

| 역할 | 쓰기 | 받는 것 | 내는 것 |
|---|---|---|---|
| `impl-planner` | `specs/<slug>/tasks.md` | 명세 경로, `sdd.py tasks` | `tasks[]`, `patternsToFollow`, `testRunner` |
| **`software-engineer`** | `src/` | 모드, 명세 경로, 계획 JSON | `filesChanged`, `specChangeRequests` |
| `test-engineer` | `tests/` | 명세 경로, 계획 JSON, 변경 파일 목록 | `testResult`, `implementationDefects` |

- 구현 전 반드시 명세를 읽고 `validate`로 구조를 확인한다.
- 인수 기준 없는 동작을 구현하지 않는다.
- AC마다 최소 1개 테스트, `AC-N` 태그를 남긴다.
- **깊은 모드에서 engineer는 테스트를 쓰지 않는다.** 구현자가 테스트까지 쓰면 테스트가
  구현의 실제 동작을 베껴, 명세와 어긋난 부분까지 통과시킨다. 경량 모드에서는 engineer가
  둘 다 한다(에이전트 하나를 아끼는 대신 이 위험을 감수하는 선택이다).
- **test-engineer는 구현을 고치지 않는다.** 실패는 `implementationDefects`로 보고하고,
  오케스트레이터가 engineer에게 되돌린다.
- `specs/<slug>/tasks.md` 외에는 `specs/`를 고치지 않는다.

## review 페이즈

| 역할 | 관심사 | 판정에 쓰는 근거 |
|---|---|---|
| **`spec-reviewer`** | 명세 준수·AC 커버리지·스펙 밖 구현·게이트 위반 | `trace`, `guard`, 코드 |
| `code-reviewer` | 가독성·복잡도·중복·에러 처리·프로젝트 관례 | 변경 파일, 기존 코드 |
| `security-reviewer` | 입력 검증·인가·시크릿·인젝션·데이터 노출 | 변경 파일, `securityHits` |
| `perf-reviewer` | N+1·복잡도·재계산·경계 없는 로딩·동시성 | 변경 파일, `perfHits`, 비기능 요구사항 |

- 넷 다 **쓰기 도구가 없다** — 판정과 리포트 본문만 낸다.
- `trace`·`guard` 스크립트 결과를 근거로 삼는다(직접 재계산하지 않는다).
- 판정은 각자 **approved** 또는 **changes-requested** 둘 중 하나.
  **하나라도 changes-requested면 전체가 changes-requested다** — 평균 내지 않는다.
- 관심사가 겹치면 판정에 넣지 말고 `handoffs`로 넘긴다. 같은 문제를 넷이 각자 감점하면
  심각도가 부풀려진다.
- `severity: high`만 자동 재시도를 유발한다. `medium`/`low`는 리포트에만 남는다.
- `security-reviewer`·`perf-reviewer`는 **깊이와 무관하게** 신호가 잡히면 붙는다 —
  한 줄짜리 인증 수정에도 보안 리뷰는 돈다.
- 리뷰어들은 **서로의 판정을 보지 않는다.** 오케스트레이터가 한 메시지에서 동시에 부른다.

## 무엇이 강제되고 무엇이 강제되지 않는가

`enforce: true`인 프로젝트에서 `hooks/phase_gate.py`가 막는 것은 **페이즈 경계**다 —
spec 페이즈에 `src/`를 못 쓰고, implement 페이즈에 명세를 못 고치고, review 페이즈에
아무것도 못 고친다. 자세한 규칙은 `references/phase-gate.md`.

**같은 페이즈 안의 역할 분리는 훅이 강제하지 못한다.** 훅의 stdin에는 어느 서브에이전트가
호출했는지가 없기 때문이다. 그래서:

- `software-engineer`가 깊은 모드에서 `tests/`를 건드리는 것 → **막히지 않는다.**
  오케스트레이터가 프롬프트로 금지하고, `test-engineer`의 출력과 `filesChanged`를
  대조해 사후에 확인한다.
- `test-engineer`가 `src/`를 고치는 것 → **막히지 않는다.** 같은 방식으로 확인한다.
- 읽기 전용 역할(`spec-researcher`, `spec-auditor`, 리뷰어 4종)은 `tools:` 프론트매터에
  쓰기 도구가 아예 없으므로 **도구 수준에서 강제된다** — 이쪽은 확실하다.
