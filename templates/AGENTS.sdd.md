## Spec-Driven Development

이 프로젝트는 `sdd` 플러그인으로 Spec-Driven Development(SDD)를 적용한다. 명세가 소스 오브
트루스이며, 구현 코드를 직접 고치는 대신 명세를 고치고 코드를 다시 생성한다.

### 역할

세 페이즈(spec → implement → review)마다 역할이 나뉘고 각자 쓰기 범위가 제한된다.
하드 게이트(`enforce: true`)가 켜져 있으면 **페이즈 경계**는 훅이 강제한다.

**spec** — Spec Researcher(조사, 쓰기 없음) → Spec Architect(`specs/`에만 쓴다) →
Spec Auditor(검증 불가능한 AC·모순·누락된 오류 케이스 적발, 쓰기 없음)

**implement** — Implementation Planner(AC 분해·영향 파일 확정, `tasks.md`만) →
Software Engineer(구현, `src/`) → Test Engineer(AC별 테스트, `tests/`).
**Test Engineer는 구현 코드를 고치지 않는다** — 실패는 결함 보고이지 수정 대상이 아니다.

**review** (넷 다 쓰기 없음) — Spec Reviewer(명세 준수) · Code Reviewer(가독성·복잡도) ·
Security Reviewer(입력 검증·인가·시크릿) · Performance Reviewer(N+1·복잡도·경계 없는 로딩).
**하나라도 `changes-requested`를 내면 기능은 완료가 아니다.** 판정을 평균 내지 않는다.

### 깊이

작은 변경까지 10개 역할을 다 돌리지 않는다. `sdd.py depth`가 인수 기준 개수·검증 경고·
본문 키워드를 근거로 `light`(역할 3개)와 `deep`(역할 8개 이상)을 정한다. 보안·성능
리뷰어는 깊이와 무관하게 해당 신호가 잡히면 붙는다 — 한 줄짜리 인증 수정에도 보안 리뷰는
돈다. `/sdd:run <설명> --deep`, `--light`로 직접 지정할 수 있다.

### 명세 구조

각 기능 명세(`specs/<slug>/spec-v<N>.md`)는 8개 섹션을 모두 포함한다: 목적, 배경,
비즈니스 규칙, 기능 요구사항, 비기능 요구사항, 인수 기준(`AC-1`부터), 오류 케이스
(`EC-1`부터), 범위 밖.

새 명세는 `sdd.py new`가 템플릿에서 만들어 주며, 안에는 `{{...}}` 플레이스홀더가 들어
있다. **하나라도 남아 있으면 검증에 실패하고 구현 단계로 넘어갈 수 없다.**

전체 규칙(프론트매터·ID 형식·검증 에러 목록·버저닝)은 `sdd` 플러그인의
`skills/spec-driven-dev/references/spec-format.md`가 정본이다.

### 진행 방식

`/sdd:run <기능 설명>`이 기본 경로다. 명세→구현→리뷰가 한 번의 요청으로 끝까지 돌아가며,
단계 전환·재시도·페이즈 게이트 조작은 `sdd.py`의 상태머신이 처리한다. 진행 위치는
`.sdd/state.json`의 `pipeline` 레코드에 있으므로, 세션이 끊겨도 `/sdd:run`을 인자 없이
다시 부르면 같은 자리에서 이어진다.

멈추는 경우는 두 가지뿐이다: 명세 단계에서 사용자에게 물어야 할 미결 질문이 생겼을 때,
그리고 재시도 상한에 걸렸을 때(기본 단계별 2회).

### 명령

`/sdd:run` · `/sdd:audit` · `/sdd:spec` · `/sdd:implement` · `/sdd:review` · `/sdd:status` · `/sdd:phase`.
`/sdd:spec`·`/sdd:implement`·`/sdd:review`는 파이프라인을 한 스텝만 진행시키는 수동 경로다.
자세한 사용법은 `sdd` 플러그인의 `spec-driven-dev` 스킬을 참고한다.
