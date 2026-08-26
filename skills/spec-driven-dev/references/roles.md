# 세 역할

SDD 하네스는 하나의 책임을 세 역할로 쪼갠다. 각 역할의 상세 프롬프트는
`agents/spec-architect.md`, `agents/software-engineer.md`, `agents/spec-reviewer.md`에
있다. 여기서는 오케스트레이터가 각 단계에서 지켜야 할 요약만 둔다.

## Spec Architect

- `specs/`에만 쓴다. `src/`, `tests/`는 읽기만 한다.
- 요구사항을 지어내지 않는다 — 불명확하면 `openQuestions[]`로 반환하고, 오케스트레이터가
  사용자에게 되묻는다.
- 동작이 바뀌면 새 버전, 명확화는 제자리 수정.

## Software Engineer

- 구현 전 반드시 명세를 읽고 `validate`로 구조를 확인한다.
- 인수 기준 없는 동작을 구현하지 않는다.
- AC마다 최소 1개 테스트, `AC-N` 태그를 남긴다.
- `specs/<slug>/tasks.md` 외에는 `specs/`를 고치지 않는다.

## Review Agent

- 쓰기 도구가 없다 — 판정과 리포트만 낸다.
- `trace`·`guard` 스크립트 결과를 근거로 삼는다(직접 재계산하지 않는다).
- 판정은 **approved** 또는 **changes-requested** 둘 중 하나.
- 기능은 Review Agent 승인 후에만 완료로 친다.

## 왜 강제되는가

세 역할의 경계는 프롬프트만으로는 지켜지지 않는다. `enforce: true`인 프로젝트에서는
`hooks/phase_gate.py`가 페이즈별로 Write/Edit/MultiEdit/NotebookEdit을 실제로 차단한다.
자세한 규칙은 `references/phase-gate.md`를 본다.
