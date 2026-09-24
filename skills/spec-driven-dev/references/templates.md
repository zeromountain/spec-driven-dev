# 스캐폴딩 산출물

원본은 이 플러그인의 `templates/`에 있고, **전부 `sdd.py`가 값을 채워 복사한다.**
에이전트가 `templates/` 경로를 직접 읽으려 하면 안 된다 — 대상 프로젝트에는 그 디렉터리가
없다. 항상 스크립트가 만들어 준 파일을 채우는 방식으로 쓴다.

미기입 표시는 전부 `{{...}}`로 통일되어 있다.

| 템플릿 | 만드는 명령 | 산출 위치 |
|---|---|---|
| `spec.md` | `sdd.py new "<설명>"` | `specs/<slug>/spec-v<N>.md` |
| `tasks.md` | `sdd.py tasks <slug>` | `specs/<slug>/tasks.md` |
| `review-report.md` | `sdd.py review-report <slug>` | `.sdd/reviews/<slug>-v<N>-<seq>.md` |
| `AGENTS.sdd.md` | `sdd.py init` | 프로젝트 `AGENTS.md`의 한 섹션 |
| `prd.md` · `architecture.md` · `adr.md` | `sdd.py init` (없을 때만) | `docs/sdd/prd.md` · `docs/sdd/architecture.md` · `docs/sdd/adr/_template.md` |

## 스크립트가 미리 채워 주는 것

- **`tasks.md`** — 명세의 AC ID를 읽어 인수 기준 대응표를 미리 만든다. Engineer가 AC를
  빠뜨릴 수 없다.
- **`review-report.md`** — `trace`와 `guard`를 내부에서 돌려 AC/EC 커버리지 표와 게이트
  위반 목록을 채운 상태로 만든다. Reviewer는 판정과 근거만 채우면 된다.
- **`AGENTS.sdd.md`** — 기존 `AGENTS.md`/`CLAUDE.md`가 있으면 덮지 않고
  `## Spec-Driven Development` 섹션만 추가·교체한다.
- **`review-report.md`의 검증 커맨드 표** — `impl-planner`가 정한 `tasks[].verify`를
  구현자가 실행한 결과(`verifyResults`)로 채운다. 경량 모드처럼 계획이 없으면 그 사실을 적는다.

## 프로젝트 지식 문서 (`docs/sdd/`)

명세보다 위에 있는 지식 — 제품 목표·아키텍처·결정 이유 — 는 기능 명세에 매번 다시 쓰지
않고 `docs/sdd/`에 한 번 적는다. `init`은 양식을 **없을 때만** 만들고 이미 있는 문서를
덮지 않는다.

- `.sdd/config.json`의 `contextDocs`(기본값 `docs/sdd/prd.md`, `docs/sdd/architecture.md`,
  `docs/sdd/adr`)에 있는 파일·디렉터리 안 `*.md`가 **모든 단계의 `context.contextDocs`**에
  경로로 실린다. 본문은 싣지 않는다 — 에이전트가 직접 읽는다.
- `{{...}}`가 남은 문서는 `unfilled: true`로 표시된다. 에이전트는 빈 양식을 근거로 쓰지 않는다.
- 디렉터리 안에서 `_`로 시작하는 파일(ADR 양식)은 목록에서 빠진다.
- `docs/**`는 `alwaysWritable`이라 어느 페이즈에서든 사람이 고칠 수 있다.

## 프로젝트에 생기는 구조

```
<project>/
├── AGENTS.md          # 없으면 생성, 있으면 섹션만 append/교체
├── docs/sdd/          # 프로젝트 지식 (contextDocs) — 없을 때만 양식 생성
│   ├── prd.md
│   ├── architecture.md
│   └── adr/
│       └── _template.md
├── specs/
│   ├── README.md
│   ├── <slug>/            # 진행 중
│   │   ├── spec-v<N>.md
│   │   └── tasks.md
│   └── archive/            # 리뷰 승인으로 완료된 것 (디렉터리째 이동)
│       └── <slug>/
│           ├── spec-v<N>.md
│           └── tasks.md
└── .sdd/
    ├── state.json      # 세션 로컬 (gitignore) — pipelines 레지스트리가 여기 산다
    ├── config.json     # 팀 공유 (커밋)
    ├── .gitignore      # state.json, worktrees/
    ├── reviews/
    │   └── <slug>-v<N>-<seq>.md
    └── worktrees/      # worktrees:true 일 때만 (gitignore)
        └── <slug>/     # 기능별 체크아웃, 브랜치 sdd/<slug>
```
