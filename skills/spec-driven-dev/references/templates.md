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

## 스크립트가 미리 채워 주는 것

- **`tasks.md`** — 명세의 AC ID를 읽어 인수 기준 대응표를 미리 만든다. Engineer가 AC를
  빠뜨릴 수 없다.
- **`review-report.md`** — `trace`와 `guard`를 내부에서 돌려 AC/EC 커버리지 표와 게이트
  위반 목록을 채운 상태로 만든다. Reviewer는 판정과 근거만 채우면 된다.
- **`AGENTS.sdd.md`** — 기존 `AGENTS.md`/`CLAUDE.md`가 있으면 덮지 않고
  `## Spec-Driven Development` 섹션만 추가·교체한다.

## 프로젝트에 생기는 구조

```
<project>/
├── AGENTS.md          # 없으면 생성, 있으면 섹션만 append/교체
├── specs/
│   ├── README.md
│   └── <slug>/
│       ├── spec-v<N>.md
│       └── tasks.md
└── .sdd/
    ├── state.json      # 세션 로컬 (gitignore)
    ├── config.json     # 팀 공유 (커밋)
    ├── .gitignore
    └── reviews/
        └── <slug>-v<N>-<seq>.md
```
