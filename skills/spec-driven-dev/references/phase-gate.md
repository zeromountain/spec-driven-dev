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

## 같은 페이즈 안의 역할 분리는 강제되지 않는다

에이전트가 페이즈당 여러 개로 세분화되면서 한 페이즈 안에 **쓰기 권한이 다른 역할이 여럿**
생겼다. 게이트는 그 차이를 구분하지 못한다 — 위와 같은 이유로 호출자를 모르기 때문이다.

| 경계 | 강제 수단 | 실제로 막히는가 |
|---|---|---|
| 페이즈 간 (spec ↔ implement ↔ review) | 훅 | **그렇다** |
| 읽기 전용 역할 (researcher·auditor·리뷰어 4종) | `tools:` 프론트매터 | **그렇다** — 쓰기 도구가 없다 |
| implement 안에서 engineer ↔ test-engineer | 프롬프트 | **아니다** |
| implement 안에서 planner의 `tasks.md` 전용 쓰기 | 프롬프트 (+ `specs/` 게이트) | 부분적 — `specs/` 밖은 안 막힌다 |

**워크트리를 쓰면 파이프라인 경계는 되살아난다.** 훅의 페이로드에 호출자는 없어도
**경로에는 슬러그가 있다.** `sdd.resolve_write()`가 그 경로를 주인 파이프라인에 귀속시키고,
게이트는 전역 `state.phase`가 아니라 그 파이프라인의 `stage`로 판정한다(deny 메시지에
`[슬러그]` 접두어가 붙는다). 여전히 해결되지 않는 것은 **같은 워크트리 안에서의 역할
분리**다 — engineer와 test-engineer는 같은 디렉터리를 쓴다.

### 어떤 페이즈로 판정하는가 (`resolve_write`)

| 쓰기 경로 | 판정 기준 | 왜 |
|---|---|---|
| `.sdd/worktrees/<슬러그>/...` | 그 파이프라인의 `stage` | 경로가 주인을 말해 준다 |
| `<specsDir>/<슬러그>/...` (본체) | 살아 있으면 그 파이프라인의 `stage` | 명세는 워크트리를 써도 본체에 있다 — 여기도 경로에 슬러그가 있다 |
| 그 밖의 본체 경로 | 전역 `state.phase` | 주인을 알 수 없다 |
| 워크트리 디렉터리 안인데 주인이 없음 | 판정하지 않음(허용) | 남의 영역이거나 정리되다 만 것이다 |

**워크트리를 가진 파이프라인은 전역 `state.phase`를 바꾸지 않는다**(`transition_phase`의
`apply=False`). 페이즈는 프로젝트에 하나뿐이라, 격리된 쪽이 자기 단계로 그걸 밀면 본체를
쓰는 다른 파이프라인의 판정이 남의 단계로 바뀐다 — 워크트리를 켜 놓고도 자기 명세를 못 쓰는
상황이 여기서 나왔다. 판정 자체(예: `implement` 전환이 유효한 명세를 요구하는 것)는 그대로
받는다.

깊은 모드에서 `software-engineer`가 `tests/`를 고치거나 `test-engineer`가 `src/`를 고치는
것은 훅이 통과시킨다. `next`의 `instruction`이 그 금지를 담아 보내고, 두 에이전트의
`filesChanged`·`testFiles`를 사후 대조해 확인해야 한다. 이 한계를 훅으로 메우려면
서브에이전트 신원이 PreToolUse 페이로드에 실려야 한다.

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

## 파이프라인이 도는 동안

페이즈 전환은 `sdd.py next`가 각 단계에 진입할 때 자동으로 한다(`/sdd:phase`와 같은
`transition_phase` 함수다). 파이프라인이 돌고 있으면 페이즈를 손으로 바꾸지 마라 —
상태가 어긋난다. `implement` 전환이 `blocked`면 파이프라인은 게이트를 끄는 대신 그 이유를
담아 `halted`가 된다. 자세한 것은 `pipeline.md`를 본다.

## 탈출구

- `/sdd:phase off` — 게이트가 걸리는 페이즈를 벗어난다.
- `.sdd/state.json`의 `enforce: false` — 게이트 자체를 끈다.
- 모델은 이 두 전환을 **스스로 결정하지 않는다** — deny 메시지는 항상 "사용자에게
  `/sdd:phase off`를 요청하라"고 안내하고, 실제 전환은 사용자가 명령을 내려야 이뤄진다.
