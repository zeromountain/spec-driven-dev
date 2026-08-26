# 스캐폴딩 산출물

`/sdd:init`이 대상 프로젝트에 심는 파일들. 원본은 이 플러그인의 `templates/`에 있고,
`sdd.py`가 값을 채워 복사한다.

## `templates/AGENTS.sdd.md`

대상 프로젝트의 `AGENTS.md`(없으면 `CLAUDE.md`, 둘 다 없으면 새 `AGENTS.md`)에 병합되는
"## Spec-Driven Development" 섹션. 세 역할 요약과 명세 8섹션 규칙, 사용 가능한 커맨드를
담는다. 이미 같은 섹션이 있으면 **그 블록만 교체**한다(전체 파일을 건드리지 않는다).

## `templates/spec.md`

`sdd.py new`가 복사해 값을 채우는 명세 템플릿. 8개 섹션 구조는
`references/spec-format.md`에서 상세히 다룬다.

## `templates/tasks.md`

`specs/<slug>/tasks.md` 초기 구조. 인수 기준 대응표 + 작업 항목 + 실행 로그.

## `templates/review-report.md`

Review Agent가 채우는 리포트 골격. 명세 준수 / 인수 기준 커버리지 / 스펙 밖 구현 /
발견된 갭 / 개선 제안 / 결론 순서. `.sdd/reviews/<slug>-v<N>-<seq>.md`로 저장된다.

## 프로젝트에 생기는 구조

```
<project>/
├── AGENTS.md          # 없으면 생성, 있으면 섹션만 append/교체
├── specs/
│   ├── README.md      # 명세 작성 규약 요약
│   └── <slug>/
│       ├── spec-v<N>.md
│       └── tasks.md
└── .sdd/
    ├── state.json      # 세션 로컬 (gitignore)
    ├── config.json      # 팀 공유 (커밋)
    ├── .gitignore
    └── reviews/
        └── <slug>-v<N>-<seq>.md
```
