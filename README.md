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
/sdd:run 사용자 엔티티에 결혼여부 필드 추가    # 명세→구현→리뷰를 끝까지 자동으로
/sdd:run                                   # 중단된 파이프라인을 그 자리에서 재개
/sdd:spec / implement / review              # 파이프라인을 한 스텝만 (수동)
/sdd:status                                # 페이즈·파이프라인 위치·명세·게이트 위반
/sdd:phase off                             # 페이즈 게이트 해제
```

`/sdd:init` 실행 시 하드 페이즈 게이트(파일 쓰기를 실제로 차단하는 훅)를 켤지 물어본다.
꺼둔 채로도 세 역할 분리와 명세 규약은 그대로 적용된다 — 다만 강제는 프롬프트 수준이다.

### 파이프라인

`/sdd:run`은 대화가 아니라 `sdd.py`의 상태머신을 따라 돈다. `next`가 다음 행동 하나를
지시하고, 서브에이전트 결과를 `advance`가 받아 전이를 결정한다 — 페이즈 전환, 명세 파일
생성, `tasks.md`, 리뷰 리포트 골격, 재시도 카운트, 승인 시 `status: done` 기록까지 전부
스크립트 몫이라 오케스트레이터가 단계 사이에서 판단하지 않는다.

```
spec ──validate 통과──▶ implement ──테스트 통과──▶ review ──approved──▶ done
 ▲                          │                        │
 └──specChangeRequests──────┘      changes-requested └──▶ implement (gaps 인계)
```

진행 위치는 `.sdd/state.json`의 `pipeline` 레코드 하나에만 있으므로 세션이 끊기거나
컨텍스트가 날아가도 `/sdd:run`을 인자 없이 다시 부르면 같은 자리에서 이어진다. 멈추는
경우는 미결 질문(`ask-user`)과 재시도 상한 초과(`halted`) 둘뿐이고, 단계별 상한은 기본
2회, 전체 전이 상한은 24회다. 전이표·인계 항목·중단 사유는
[`references/pipeline.md`](skills/spec-driven-dev/references/pipeline.md)에 있다.

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
