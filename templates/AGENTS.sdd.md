## Spec-Driven Development

이 프로젝트는 `sdd` 플러그인으로 Spec-Driven Development(SDD)를 적용한다. 명세가 소스 오브
트루스이며, 구현 코드를 직접 고치는 대신 명세를 고치고 코드를 다시 생성한다.

### 역할

세 역할이 있고 각자 쓰기 범위가 제한된다. 하드 게이트(`enforce: true`)가 켜져 있으면
아래 경계는 훅이 강제한다 — 위반은 프롬프트가 아니라 도구 호출 단계에서 막힌다.

1. **Spec Architect** — `specs/`에만 쓴다. 비즈니스 규칙·인수 기준을 정의한다.
   `src/`, `tests/`를 건드리지 않는다.
2. **Software Engineer** — `specs/`를 먼저 읽고서만 구현한다. 인수 기준 없는 동작을
   구현하지 않는다. `specs/`를 고치지 않는다(단, `specs/<slug>/tasks.md`는 예외).
3. **Review Agent** — 코드와 명세를 대조해 인수 기준마다 구현·테스트 여부를 확인하고
   리포트를 낸다. 승인 전에는 기능이 완료된 것으로 치지 않는다.

### 명세 구조

각 기능 명세(`specs/<slug>/spec-v<N>.md`)는 8개 섹션을 모두 포함한다: 목적, 배경,
비즈니스 규칙, 기능 요구사항, 비기능 요구사항, 인수 기준(`AC-1`부터), 오류 케이스
(`EC-1`부터), 범위 밖.

새 명세는 `sdd.py new`가 템플릿에서 만들어 주며, 안에는 `{{...}}` 플레이스홀더가 들어
있다. **하나라도 남아 있으면 검증에 실패하고 구현 단계로 넘어갈 수 없다.**

전체 규칙(프론트매터·ID 형식·검증 에러 목록·버저닝)은 `sdd` 플러그인의
`skills/spec-driven-dev/references/spec-format.md`가 정본이다.

### 명령

`/sdd:spec` · `/sdd:implement` · `/sdd:review` · `/sdd:run` · `/sdd:status` · `/sdd:phase`.
자세한 사용법은 `sdd` 플러그인의 `spec-driven-dev` 스킬을 참고한다.
