# 페이즈 게이트

## opt-in 메커니즘

`hooks/hooks.json`은 `sdd` 플러그인이 설치되는 즉시 **모든 세션**에 등록된다. 그래서
`hooks/phase_gate.py`는 대상 프로젝트가 opt-in 했을 때만 동작해야 한다. 판단 순서:

1. `$CLAUDE_PROJECT_DIR` (없으면 훅 stdin의 `cwd`)로 프로젝트 루트를 정한다.
2. `<root>/.sdd/state.json`이 없으면 → **무동작(allow)**.
3. `state.json.enforce`가 `true`가 아니면 → **무동작(allow)**.
4. `state.json.phase`가 `off`거나 없으면 → **무동작(allow)**.
5. 그 외에는 `evaluate_gate(phase, rel_path, config)`로 판정한다.

`/sdd:init`이 만드는 기본 `state.json`은 `enforce: false`다. 하드 게이트를 켜려면
`/sdd:init --enforce`를 쓰거나 `/sdd:phase`가 아니라 **`sdd.py init --enforce`를 다시
실행**해야 한다(페이즈 게이트 자체를 켜고 끄는 것은 `phase off`와 다른 결정이다 — `enforce`는
"게이트가 존재하는가", `phase`는 "지금 어떤 게이트가 걸리는가").

## 페이즈별 규칙

| phase | 차단 | 예외 |
|---|---|---|
| `spec` | `specsDir`·`.sdd`·`docs`·`*.md` 밖 전부 | `alwaysWritable`(`AGENTS.md`, `CLAUDE.md`, `.sdd/**`, `docs/**`), 임의의 `*.md` |
| `implement` | `specsDir` 안 전부 | `specs/<slug>/tasks.md` |
| `review` | `specsDir`·`srcDirs`·`testDirs` | `reviewsDir`(`.sdd/reviews`) |
| `off` | (무동작) | — |

`evaluate_gate`는 `scripts/sdd.py`에 순수 함수로 구현되어 있고, 훅(`hooks/phase_gate.py`)과
사후 탐지(`sdd.py guard`)가 이 함수를 그대로 재사용한다 — 규칙이 두 곳에서 따로 구현되지
않는다.

## 왜 "누가 호출했는가"가 아니라 "지금 어떤 페이즈인가"인가

PreToolUse 훅의 stdin 페이로드에는 `session_id`, `cwd`, `tool_name`, `tool_input`은 있어도
**호출한 서브에이전트가 무엇인지는 없다**. 서브에이전트별 화이트리스트는 `agents/*.md`의
`tools:` 프론트매터로만 가능하고, 그마저도 도구 단위 제한이라 "Write는 되지만 특정 디렉터리는
안 됨"은 표현하지 못한다. 그래서 게이트는 세션 전체에 걸리는 **페이즈 상태 머신**이다 —
`/sdd:spec`, `/sdd:implement`, `/sdd:review`가 명시적으로 페이즈를 전환하고, 그 순간부터
다음 전환까지 세션의 모든 쓰기가 그 페이즈 규칙을 받는다.

## 경로 정규화

`sdd.to_project_relative()`가 `Path.resolve()`로 심링크와 `..`를 실제 경로로 해석한 뒤
프로젝트 루트 기준 상대경로를 만든다. 프로젝트 루트 밖으로 나가면 `None`을 반환하고, 훅은
그 경우 판단하지 않고 허용한다(이 게이트의 책임 범위가 아니다).

## Bash를 막지 않는 이유

`hooks.json`의 matcher는 `Write|Edit|MultiEdit|NotebookEdit`만 잡는다. `cat > src/x.ts`
같은 셸 리다이렉션으로 우회하는 것을 막으려면 `Bash` 도구까지 검사해야 하는데, 그러려면
`npm test`, `mkdir`, `git`처럼 파일을 안 건드리는 명령까지 파싱해서 걸러야 하고 오탐이
쌓인다. 대신 `sdd.py guard`가 `git diff`/`git status`로 변경 파일을 모아 사후에 같은
`evaluate_gate`로 검사한다 — 실시간 차단은 아니지만, 리뷰 단계에서 위반이 있었는지는
반드시 드러난다.

## 탈출구

- `/sdd:phase off` — 게이트가 걸리는 페이즈를 벗어난다.
- `.sdd/state.json`의 `enforce: false` — 게이트 자체를 끈다.
- 모델은 이 두 전환을 **스스로 결정하지 않는다** — deny 메시지는 항상 "사용자에게
  `/sdd:phase off`를 요청하라"고 안내하고, 실제 전환은 사용자가 명령을 내려야 이뤄진다.
