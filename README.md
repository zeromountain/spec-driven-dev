# spec-driven-dev

명세를 소스 오브 트루스로 삼는 Spec-Driven Development(SDD) 하네스를 어느 프로젝트에나
설치해주는 플러그인. Claude Code와 Codex CLI 양쪽에서 설치할 수 있다.

## 왜

AI로 코드를 빨리 만들 수는 있지만, 그럴수록 "일단 되게 만들고 나중에 정리하자"가 쌓여
암묵적 결정과 부서지기 쉬운 구조가 남는다. SDD는 그 반대를 강제한다 — **코드가 아니라
명세를 고치고, 코드는 명세로부터 다시 만든다.** 이 플러그인은 그 규율을 프롬프트로만
걸어두지 않는다. 명세는 Spec Architect만, 구현은 Software Engineer만, 승인은 Review
Agent만 하도록 역할을 나누고, 프로젝트가 원하면 PreToolUse 훅으로 그 경계를 실제로
집행한다.

## 설치

**Claude Code:**
```
/plugin marketplace add zeromountain/spec-driven-dev
/plugin install sdd@spec-driven-dev
```

**Codex CLI:**
```bash
codex plugin marketplace add zeromountain/spec-driven-dev
codex plugin add sdd@spec-driven-dev
```

두 호스트 모두 설치 후 세션을 재시작해야 반영된다. 단계별 화면·문제 해결까지 포함한
전체 가이드는 [`docs/SETUP.md`](docs/SETUP.md)를 본다.

로컬 테스트(퍼블리시 전에 디스크에서 바로 로드):
```bash
cc --plugin-dir ~/spec-driven-dev                 # Claude Code
codex --plugin-dir ~/spec-driven-dev              # Codex CLI
```

## 사용법

**Claude Code** — 슬래시 커맨드 7개:
```
/sdd:init                                  # specs/·AGENTS.md·.sdd/ 스캐폴딩
/sdd:spec 사용자 엔티티에 결혼여부 필드 추가    # 명세 작성 (Spec Architect)
/sdd:implement                             # 구현 + 테스트 (Software Engineer)
/sdd:review                                # 명세 대조 리뷰 (Review Agent)
/sdd:run 사용자 엔티티에 결혼여부 필드 추가    # 위 세 단계를 순서대로
/sdd:status                                # 현재 페이즈·명세 목록·게이트 위반
/sdd:phase off                             # 페이즈 게이트 해제
```

`/sdd:init` 실행 시 하드 페이즈 게이트(파일 쓰기를 실제로 차단하는 훅)를 켤지 물어본다.
꺼둔 채로도 세 역할 분리와 명세 규약은 그대로 적용된다 — 다만 강제는 프롬프트 수준이다.

**Codex CLI** — 슬래시 커맨드 대신 스킬을 직접 부른다:
```
$sdd:spec-driven-dev init 해줘
$sdd:spec-driven-dev 사용자 엔티티에 결혼여부 필드 추가 — 명세부터 시작
```
Codex는 플러그인 커맨드·서브에이전트·훅을 지원하지 않는다(스킬만 설치된다) — `sdd`의
세 역할 분리와 페이즈 관리는 Codex에서 전부 `spec-driven-dev` 스킬 하나가 순서대로
직접 수행하고, 하드 페이즈 게이트(파일 쓰기 차단)는 Claude Code에서만 동작한다. 자세한
차이는 [`docs/SETUP.md`의 "호스트별 차이"](docs/SETUP.md#호스트별-차이)를 본다.

## 페이즈 게이트 (Claude Code 전용)

`enforce: true`인 프로젝트에서는 지금 페이즈에 따라 쓰기가 실제로 막힌다. 이 훅은 Claude
Code에서만 동작한다 — Codex 플러그인은 훅을 지원하지 않으므로, Codex에서는 `sdd.py guard`로
사후 점검하거나 스킬의 프롬프트 규율에 의존한다.

| phase | 막히는 것 | 예외 |
|---|---|---|
| `spec` | `specs/`·`.sdd/`·`docs/`·`*.md` 밖 전부 | 항상 허용 목록, 임의의 `.md` |
| `implement` | `specs/` 안 전부 | `specs/<slug>/tasks.md` |
| `review` | `specs/`·`src/`·`tests/` | `.sdd/reviews/` |

플러그인 자체는 설치되면 모든 세션에 훅이 등록되지만, 프로젝트에 `.sdd/state.json`이
없거나 `enforce`가 꺼져 있으면 완전히 무동작이다 — 다른 프로젝트에는 영향이 없다.

## 데이터

모든 상태·설정은 대상 프로젝트의 `.sdd/`와 `specs/` 아래에 쌓인다. 자세한 스키마는
`skills/spec-driven-dev/references/spec-format.md`, `phase-gate.md`를 본다.

## 개발

```bash
python3 -m unittest discover -s scripts/tests -t .   # 스크립트 단위 테스트
python3 scripts/validate.py                            # 이 레포 자체 컴포넌트 검증
claude plugin validate --strict .                       # Claude Code 매니페스트 검증
```

저장소 유지보수 방법은 [`AGENTS.md`](AGENTS.md)에 정리되어 있다.

## 관련 프로젝트

구현 루프 자체를 더 무겁게 자동화하고 싶다면 (레포지토리 탐색·계획 워크스페이스·
검증 루프를 갖춘) [`auto-dev`](https://github.com/zeromountain/auto-dev)를 `/sdd:implement`
대신 쓸 수 있다. 이 플러그인은 그 기능을 흡수하지 않는다 — 명세·리뷰 규율에 집중한다.
