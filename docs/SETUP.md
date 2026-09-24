# 설정 가이드

`sdd` 플러그인을 Claude Code와 Codex CLI에 설치하고, 실제 프로젝트에 SDD 하네스를
켜기까지의 전체 절차. 빠른 설치만 필요하면 [`README.md`](../README.md)의 "설치" 절만
봐도 된다 — 이 문서는 사전 조건, 검증 방법, 두 호스트의 차이, 문제 해결까지 다룬다.

## 목차

- [사전 조건](#사전-조건)
- [Claude Code에 설치](#claude-code에-설치)
- [Codex CLI에 설치](#codex-cli에-설치)
- [퍼블리시 전 로컬 테스트](#퍼블리시-전-로컬-테스트)
- [프로젝트에 SDD 켜기](#프로젝트에-sdd-켜기)
- [기능 하나를 끝까지: 사용 흐름](#기능-하나를-끝까지-사용-흐름)
- [설정 (`.sdd/config.json`)](#설정-sddconfigjson)
- [하드 페이즈 게이트 켜기](#하드-페이즈-게이트-켜기)
- [워크트리 켜기](#워크트리-켜기-두-호스트-모두)
- [호스트별 차이](#호스트별-차이)
- [업데이트](#업데이트)
- [제거](#제거)
- [문제 해결](#문제-해결)

## 사전 조건

- **Claude Code**로 쓰려면: Claude Code CLI가 설치되어 있어야 한다(`claude --version`).
- **Codex CLI**로 쓰려면: Codex CLI가 설치되어 있어야 한다(`codex --version`).
- `sdd`의 모든 로직은 **Python 3 표준 라이브러리만** 쓴다. `python3`이 PATH에 있으면
  충분하고, pip 설치나 가상환경은 필요 없다.
- 마켓플레이스 소스는 GitHub 저장소(`zeromountain/spec-driven-dev`)다. 두 호스트 모두
  `marketplace add`가 내부적으로 `git clone`을 수행하므로, 사설 저장소로 옮길 경우 그
  호스트가 해당 저장소를 볼 수 있는 Git 자격증명이 있어야 한다(공개 저장소라면 필요 없음).

## Claude Code에 설치

1. 마켓플레이스를 등록한다.
   ```
   /plugin marketplace add zeromountain/spec-driven-dev
   ```
2. 플러그인을 설치한다.
   ```
   /plugin install sdd@spec-driven-dev
   ```
3. Claude Code 세션을 재시작한다. 플러그인의 커맨드·에이전트·훅은 세션 시작 시점에
   고정되므로, 재시작 전까지는 `/sdd:*` 커맨드가 보이지 않는다.
4. 확인:
   ```
   /plugin list
   ```
   목록에 `sdd@spec-driven-dev`가 나오면 설치된 것이다. `/help`에서도 `/sdd:init` 등
   9개 커맨드가 보여야 한다.

CLI에서 미리 검증하고 싶다면(선택):
```bash
claude plugin marketplace add zeromountain/spec-driven-dev
claude plugin install sdd@spec-driven-dev
claude plugin list
```

## Codex CLI에 설치

1. 마켓플레이스를 등록한다.
   ```bash
   codex plugin marketplace add zeromountain/spec-driven-dev
   ```
2. 플러그인을 설치한다.
   ```bash
   codex plugin add sdd@spec-driven-dev
   ```
3. Codex 세션을 재시작한다.
4. 확인:
   ```bash
   codex plugin list --json
   ```
   `sdd@spec-driven-dev` 항목이 `enabled: true`로 나오면 설치된 것이다.

Codex는 플러그인의 `skills/` 디렉터리만 읽는다 — `commands/`, `agents/`, `hooks/`는
저장소에 그대로 있지만 Codex 쪽에서는 쓰이지 않는다(자세한 이유는 아래
[호스트별 차이](#호스트별-차이) 참고).

## 퍼블리시 전 로컬 테스트

저장소를 수정한 뒤 마켓플레이스에 반영하기 전에, 디스크에서 바로 플러그인을 로드해
확인할 수 있다.

```bash
cc --plugin-dir ~/spec-driven-dev          # Claude Code (cc는 --permission-mode auto 별칭)
codex --plugin-dir ~/spec-driven-dev       # Codex CLI
```

둘 다 마켓플레이스 등록 없이 그 세션에서만 플러그인을 활성화한다. 배포용 검증은
저장소 자체의 테스트로 한다:

```bash
cd ~/spec-driven-dev
python3 -m unittest discover -s scripts/tests -t .   # sdd.py 단위 테스트
python3 scripts/validate.py                            # 컴포넌트 자체 검증
claude plugin validate --strict .                       # Claude Code 매니페스트 검증
python3 -m json.tool .codex-plugin/plugin.json          # Codex 매니페스트 JSON 검증
```

## 프로젝트에 SDD 켜기

설치가 끝나면 실제로 SDD를 적용할 프로젝트로 이동해 초기화한다.

**Claude Code:**
```
cd ~/my-project
claude
/sdd:init
```

**Codex CLI:**
```
cd ~/my-project
codex
$sdd:spec-driven-dev SDD 설정해줘
```

Codex에는 슬래시 커맨드가 없으므로 **의도를 말로 전한다.** 스킬이 그 의도를 모드로 옮긴다:

| 하고 싶은 것 | Codex에서 | (Claude Code) |
|---|---|---|
| 스캐폴딩 | `$sdd:spec-driven-dev SDD 설정해줘` | `/sdd:init` |
| 기능 하나를 끝까지 | `$sdd:spec-driven-dev <기능> — 명세부터 끝까지` | `/sdd:run <기능>` |
| 기능을 하나 더 (병렬) | `$sdd:spec-driven-dev <다른 기능>도 시작해줘` | `/sdd:run <기능>` |
| 걸린 것 전부 진행 | `$sdd:spec-driven-dev 걸린 거 전부 같이 진행해줘` | `/sdd:run --all` |
| 현황 보기 | `$sdd:spec-driven-dev 지금 뭐뭐 돌고 있어` | `/sdd:board` |
| 이어서 하기 | `$sdd:spec-driven-dev 아까 하던 거 이어서` | `/sdd:run` |
| 워크트리 정리 | `$sdd:spec-driven-dev 워크트리 정리해줘` | `/sdd:worktree remove` |
| 확인 없이 끝까지 | `$sdd:spec-driven-dev <기능> 확인 없이 끝까지 돌려` | `/sdd:run <기능> --no-gate` |
| 교훈 목록 보기 | `$sdd:spec-driven-dev 쌓인 교훈 보여줘` | (말로) "교훈 목록 보여줘" |

명세 승인·피드백·회고 교훈 고르기는 커맨드가 아니라 **파이프라인이 멈춰서 물어볼 때 말로
답한다** — 아래 [사용 흐름](#기능-하나를-끝까지-사용-흐름)을 본다.

깊이를 직접 정하려면 "깊게" / "가볍게"를 덧붙인다(`--deep`/`--light`에 대응). 진행 위치는
`.sdd/state.json`에 남으므로 세션이 끊겨도 "아까 하던 거 이어서"로 같은 자리에서 이어진다.

`init`은 다음을 만든다: `specs/`, `.sdd/state.json`(세션 로컬, gitignore됨),
`.sdd/config.json`(팀 공유, 커밋됨), `.sdd/reviews/`, 프로젝트 지식 양식 `docs/sdd/prd.md`·
`docs/sdd/architecture.md`·`docs/sdd/adr/_template.md`(없을 때만 — 채워 두면 모든 에이전트가
명세보다 먼저 읽는다), 그리고 프로젝트의 `AGENTS.md`(없으면
생성, 있으면 "## Spec-Driven Development" 섹션만 추가/교체). 이미 있는 내용은 절대
덮어쓰지 않는다.

## 기능 하나를 끝까지: 사용 흐름

AI가 명세·계획·구현·리뷰를 쓰는 동안 **사람은 작성자가 아니라 판단자**다. 파이프라인은
사람이 판단할 자리에서만 멈추고, 나머지는 스스로 진행한다. 아래는 `/sdd:run` 한 번이
지나가는 길과, 그중 사람이 개입하는 자리다.

### 0. 먼저 프로젝트 지식을 적는다 (한 번만, 가장 효과가 크다)

`init`이 만든 `docs/sdd/`의 양식을 채운다. 모든 에이전트가 명세보다 먼저 읽는 문서다.

| 파일 | 적을 것 |
|---|---|
| `docs/sdd/prd.md` | 제품 목표·사용자·핵심 기능·**MVP에서 하지 않는 것**·제약 |
| `docs/sdd/architecture.md` | 디렉터리 구조·따를 패턴(에러 처리·검증 위치·네이밍)·데이터 흐름 |
| `docs/sdd/adr/NNNN-<제목>.md` | 결정과 **그 이유** (`_template.md`를 복사해 쓴다) |

비워 둬도 동작하지만, 채우지 않은 문서는 `unfilled`로 표시돼 에이전트가 근거로 쓰지 않는다.
머릿속에만 있는 관례는 에이전트가 매번 추측하게 된다.

### 1. 시작

```
/sdd:run 비밀번호 5회 실패 시 계정 잠금
```

시작 응답의 깊이(`light`/`deep`)와 붙는 에이전트 수를 한 줄로 먼저 알려 준다.

### 2. 명세 → **사람이 승인** (기본 켜짐)

`spec-architect`가 명세를 쓰고 검증을 통과하면 파이프라인이 멈추고 요약을 보여준다:
인수 기준(AC)·오류 케이스(EC)·범위 밖·아키텍트가 세운 가정·검증 경고. 요약은 모델이
쓴 게 아니라 스크립트가 명세 파일에서 그대로 뽑은 것이다. 명세 파일 경로도 함께 나오니
열어서 본다.

- **승인** → "승인" / "좋아, 진행해"라고 답하면 구현으로 간다.
- **고칠 점** → "AC-2에 잠금 해제 시간을 30분으로 명시해" 처럼 말하면 같은 명세 파일에
  반영돼 **다시 승인 요청으로 돌아온다.** 몇 번을 되돌려도 재시도 횟수로 세지 않는다.
- 명세를 쓰는 도중 아키텍트가 모르는 게 있으면 승인 전에 **질문**(`ask-user`)으로 먼저 멈춘다.

좋은 명세의 기준 — 체크리스트로 쓰면 된다:

| 섹션 | 확인할 것 |
|---|---|
| 입력과 출력 | 무엇이 들어오고 무엇이 나오는가 (관측 가능한 동작) |
| 인수 기준 | 숫자·조건으로 검증 가능한가 ("빠르게" ✗ → "1초 이내" ✓) |
| 비기능 요구사항 | 응답 시간·보안·호환성 같은 제약 |
| 범위 밖 | 이번에 **하지 않을 것** — 비어 있으면 AI가 범위를 넓힌다 |
| 오류 케이스 | 정상 경로마다 대응하는 예외 |
| 인터페이스 | 함수·API 시그니처 수준의 경계 (구현은 적지 않는다) |

`입력과 출력`·`인터페이스`는 권장 섹션이라 없어도 통과하지만 경고가 뜬다. 인수 기준이 15개를
넘으면 한 세션에 담기 어렵다는 경고가 뜬다 — 상위 명세 아래 컴포넌트 명세로 쪼개고
하위 명세의 프론트매터에 `parent: <상위 슬러그>`를 적는다.

### 3. 계획 → (선택) 사람이 승인

깊은 모드(AC가 많거나 경고가 쌓였을 때)에서는 `impl-planner`가 태스크를 나누고 태스크마다
**검증 커맨드**(`verify` — exit code 0이면 그 AC가 충족됐다고 확인되는 커맨드)를 정한다.
`.sdd/config.json`에서 `humanGates.plan`을 켜면 여기서도 태스크·손댈 파일·검증 커맨드를
보여주고 승인을 기다린다(기본은 꺼짐). 답하는 방법은 명세 승인과 같다.

### 4. 구현 (자동)

`software-engineer`가 구현하고 AC마다 테스트를 쓰고 실행한다. 계획에 검증 커맨드가 있으면
전부 실행해 보고한다 — 실패하거나 **실행 보고가 빠지면** 파이프라인이 구현을 다시 돌린다.
구현하다 명세를 바꿔야 하면 새 버전 명세(`spec-v2.md`)로 되돌아가고, 그 버전도 다시 승인을
받는다.

### 5. 리뷰 (자동)

`code-reviewer`(항상)와 신호가 있을 때 `security-reviewer`·`perf-reviewer`가 동시에 판정한다.
하나라도 `changes-requested`면 지적 사항을 들고 구현으로 돌아간다. 리포트는
`.sdd/reviews/<slug>-v<N>-<seq>.md` — AC 커버리지·검증 커맨드 결과·게이트 위반 표가 들어 있다.

### 6. 승인 → **회고** (사람이 교훈을 고른다)

리뷰가 승인되면 명세 체크박스가 채워지고 디렉터리째 `specs/archive/<slug>/`로 옮겨진다.
그다음 회고 단계가 나온다. 스크립트가 센 사실 — 명세 검증 실패, 사람 피드백, 명세 변경 요청,
테스트·검증 실패, 리뷰 반려가 각각 몇 번이었고 무엇 때문이었는지, 에이전트별 호출 수 — 가
`specs/archive/<slug>/retro-v<N>.md`에 남고, 에이전트가 "다음 기능에서 같은 실수를 덜 하려면
남길 규칙" 후보를 0~3개 제안한다.

- **고른다** → "1번이랑 3번 남겨" — 고른 것만 `docs/sdd/learnings.md`에 `LRN-N`으로 쌓인다.
- **건너뛴다** → "이번엔 없어" — 한 번에 통과했다면 후보가 0개인 게 정상이다.

쌓인 교훈은 **다음 기능부터 모든 에이전트의 컨텍스트에 실린다.** 이것이 같은 실수를 두 번
하지 않게 하는 학습 루프다. 교훈은 "더 꼼꼼히" 같은 다짐이 아니라 "에러 응답에는 사용자용
메시지를 넣는다" 같은 구체적 행동 규칙이어야 효과가 있다. 여러 기능에 걸쳐 반복되는
교훈은 `AGENTS.md`의 SDD 섹션으로 옮기는 편이 낫다.

교훈은 직접 관리할 수도 있다:

```bash
python3 <플러그인 경로>/scripts/sdd.py learn --list --path .              # 목록
python3 <플러그인 경로>/scripts/sdd.py learn --add "<규칙>" --path .     # 직접 추가
python3 <플러그인 경로>/scripts/sdd.py learn --remove LRN-3 --path .     # 잘못된 교훈 삭제
```

`docs/sdd/learnings.md`를 직접 고쳐도 된다 — `- **LRN-N**: ...` 형식만 유지하면 된다.

### 멈추는 자리 요약

| 멈춤 | 언제 | 답하는 법 |
|---|---|---|
| 명세 승인 | 명세가 검증을 통과할 때마다 (기본 켜짐) | 승인 / 고칠 점을 말로 |
| 계획 승인 | `humanGates.plan: true`이고 깊은 모드일 때 | 승인 / 고칠 점을 말로 |
| 질문 | 아키텍트가 모르는 게 있을 때 | 답 |
| 회고 | 리뷰 승인 직후 | 남길 교훈 고르기 / 건너뛰기 |
| 중단(`halted`) | 같은 단계가 재시도 상한(기본 2회)을 넘었을 때 | 원인을 고치고 `/sdd:run`으로 재개 |

그 밖에는 단계 사이에서 "계속할까요?"라고 묻지 않는다. 확인 없이 끝까지 돌리고 싶으면
`/sdd:run <기능> --no-gate` — 그 run에서만 승인 지점을 건너뛴다(에이전트가 알아서 승인하는
일은 없다). 세션이 끊겨도 진행 위치는 `.sdd/state.json`에 있으니 `/sdd:run`(Codex는 "아까
하던 거 이어서")으로 같은 자리에서 이어진다.

## 설정 (`.sdd/config.json`)

팀이 공유하는 설정이다(커밋한다). 키가 없으면 기본값을 쓴다.

| 키 | 기본값 | 뜻 |
|---|---|---|
| `humanGates` | `{"spec": true, "plan": false}` | 사람 승인 지점. 일부 키만 적어도 나머지는 기본값을 따른다 |
| `contextDocs` | `["docs/sdd/prd.md", "docs/sdd/architecture.md", "docs/sdd/adr"]` | 모든 에이전트가 먼저 읽는 프로젝트 지식 (디렉터리면 안의 `*.md`, `_`로 시작하는 파일 제외) |
| `learningsPath` | `"docs/sdd/learnings.md"` | 회고 교훈이 쌓이는 파일 |
| `specsDir` | `"specs"` | 명세 디렉터리 |
| `srcDirs` / `testDirs` | `["src"]` / `["tests"]` | 구현·테스트 경로 (게이트와 AC 추적에 쓰인다) |
| `acPattern` | `"AC-\\d+"` | 테스트에 붙이는 AC 태그 형식 |
| `minCoverage` | `0.9` | 리뷰 리포트에 표시하는 AC 커버리지 기준 (판정에 쓰이지 않는다) |
| `worktrees` | `false` | 기능마다 git 워크트리에서 작업 ([워크트리 켜기](#워크트리-켜기-두-호스트-모두)) |

하드 게이트 여부(`enforce`)와 파이프라인 진행 상태는 세션 로컬인 `.sdd/state.json`에 있다.

## 하드 페이즈 게이트 켜기

**Claude Code에서만 가능하다.** `/sdd:init` 마지막에 하드 게이트(파일 쓰기를 실제로
차단하는 PreToolUse 훅)를 켤지 물어본다. 나중에 켜려면:

```bash
python3 <플러그인 경로>/scripts/sdd.py init --path . --enforce
```

플러그인 경로는 아래로 찾는다:
```bash
find ~/.claude/plugins/cache ~/spec-driven-dev -maxdepth 5 -type d -path '*sdd*/scripts' 2>/dev/null | head -1
```

`.sdd/state.json`의 `enforce`가 `true`가 되면, 그 순간부터 현재 페이즈(`spec`/
`implement`/`review`)에 맞지 않는 파일 쓰기가 실제로 막힌다. 다른 프로젝트에는 영향이
없다 — 훅은 `.sdd/state.json`이 없거나 `enforce`가 꺼져 있으면 완전히 무동작이다. 규칙과
탈출구는 [`README.md`의 "페이즈 게이트"](../README.md#페이즈-게이트-claude-code-전용)와
`skills/spec-driven-dev/references/phase-gate.md`에 있다.

## 워크트리 켜기 (두 호스트 모두)

기능마다 독립된 git 워크트리에서 작업하게 하면 병렬 실행에서 파일이 겹치지 않는다.
`/sdd:init`(Claude Code)이나 "SDD 설정해줘"(Codex)가 물어보고, 나중에 켜려면:

```bash
python3 <플러그인 경로>/scripts/sdd.py init --path . --worktrees
```

`.sdd/config.json`의 `"worktrees": true`가 되고, 기능마다
`.sdd/worktrees/<슬러그>/`에 체크아웃과 `sdd/<슬러그>` 브랜치가 생긴다(그 디렉터리는
`.sdd/.gitignore`에 자동으로 들어간다). git 저장소가 아니면 본체에서 돌되 그 사실을
`worktreeWarning`으로 알린다.

Claude Code에서는 여기에 더해 **훅이 워크트리 경로로 파이프라인을 식별해 각자의 단계로
판정**하므로, 하드 게이트를 켠 채로도 페이즈가 다른 기능들이 동시에 돈다. Codex에서는
훅이 없으므로 파일 격리만 얻는다.

브랜치는 자동으로 병합되지 않는다 — 승인되면 경로와 브랜치 이름만 알려준다.

## 호스트별 차이

플러그인 매니페스트가 두 개인 이유: Claude Code는 `.claude-plugin/plugin.json`을, Codex는
`.codex-plugin/plugin.json`을 읽는다. 저장소 구조는 하나지만 각 호스트가 지원하는
컴포넌트 종류가 다르다.

| 컴포넌트 | Claude Code | Codex CLI |
|---|---|---|
| `skills/spec-driven-dev/SKILL.md` | ✅ | ✅ |
| `commands/*.md` (`/sdd:*`) | ✅ | ❌ (스킬을 직접 호출) |
| `agents/*.md` (서브에이전트 6개) | ✅ | ❌ (Codex 플러그인은 서브에이전트 정의를 지원하지 않는다) |
| `hooks/hooks.json` (페이즈 게이트) | ✅ (opt-in) | ❌ (Codex 플러그인 매니페스트에 훅 필드가 없다) |
| `scripts/sdd.py` (파이프라인·깊이·스케줄러·워크트리) | ✅ | ✅ (스킬이 Bash로 호출) |

**`sdd.py`에 있는 것은 두 호스트에서 똑같이 동작한다** — 파이프라인 상태머신, `depth`의
역할 구성 판정, 파이프라인 레지스트리와 병렬 스케줄러, 워크트리,
`validate`/`trace`/`guard`. 차이는 두 가지뿐이다.

**1. 역할을 누가 수행하는가.** Codex에서는 `spec-driven-dev` 스킬 하나가 6개 역할을
**한 세션 안에서 순서대로 직접 수행**한다. `next`가 지정한 `agent`의 프롬프트를 스킬이
직접 맡는데, `agents/*.md`는 Codex에 설치되지 않으므로 역할의 책임·금지 사항은
`references/roles.md`가 근거다. `sdd.py depth`가 "이번엔 어느 역할까지 도는가"를 똑같이
정해 주지만, 각 역할이 **독립된 컨텍스트에서 도는 이점은 Claude Code에서만** 얻는다 —
리뷰어 3종의 독립 판정은 Codex에서 순차적 자기 점검에 가깝다.

**2. 게이트가 실제로 막는가.** 역할 경계(예: "Spec Architect는 src/를 쓰지 않는다")는
Codex에서 스킬 프롬프트로만 지켜진다. 그래서 리뷰 단계의 `sdd.py guard`가 Codex에서는
선택이 아니라 필수다 — 위반이 있었는지 드러나는 유일한 지점이다.

여기서 따라오는 실무 조언 하나: **Codex 전용 프로젝트라면 `enforce`를 켜지 마라.** 훅이
없어 아무것도 막히지 않는데, `schedule()`은 `enforce: true`를 보고 같은 페이즈끼리만
동시에 돌린다 — 막지도 못하면서 병렬성만 줄어든다.

**워크트리는 Codex에서도 동작한다**(git만 있으면 된다). 파일 격리는 그대로 얻지만,
"훅이 워크트리 경로로 파이프라인을 식별해 각자의 단계로 판정한다"는 이점은 훅이 없으니
해당 없다.

## 업데이트

두 호스트 모두 **버전 비교**로 업데이트 여부를 판단한다 — 내용만 바뀌고
`.claude-plugin/plugin.json` / `.codex-plugin/plugin.json`의 `version`이 그대로면
"이미 최신"이라고 보고하고 아무것도 갱신하지 않는다.

```
# Claude Code
/plugin marketplace update spec-driven-dev
/plugin update sdd@spec-driven-dev

# Codex CLI
codex plugin marketplace upgrade spec-driven-dev
codex plugin add sdd@spec-driven-dev   # 최신 버전으로 재설치
```

각 호스트 모두 적용에는 세션 재시작이 필요하다.

**0.14 이하에서 올릴 때 달라지는 점:**

- **0.15.0** — 새 명세에 `입력과 출력`·`인터페이스` 섹션이 생긴다. 기존 명세는 경고만 뜨고
  그대로 통과하며 깊이 판정도 바뀌지 않는다. `docs/sdd/` 양식은 `/sdd:init`을 다시 부르면
  (없을 때만) 생긴다.
- **0.16.0** — 명세가 완성되면 한 번 멈추고 승인을 기다린다. 예전처럼 끝까지 자동으로 돌리려면
  `.sdd/config.json`에 `"humanGates": {"spec": false}`.
- **0.17.0** — 리뷰 승인 뒤 `done` 대신 회고(`reflect`)가 먼저 나온다. 명세 정리·아카이브는
  승인 시점에 이미 끝나 있으므로, 승인 직후 `action == "done"`을 기다리던 외부 스크립트는
  `reflect`도 완료로 받거나 `sdd.py learn --skip`을 먼저 부르면 된다.

## 제거

```
# Claude Code
/plugin uninstall sdd@spec-driven-dev
/plugin marketplace remove spec-driven-dev

# Codex CLI
codex plugin remove sdd@spec-driven-dev
codex plugin marketplace remove spec-driven-dev
```

프로젝트에 이미 만들어진 `.sdd/`, `specs/`, `AGENTS.md`의 SDD 섹션은 플러그인 제거와
무관하게 그대로 남는다 — 지우려면 직접 삭제한다.

## 문제 해결

**`/plugin marketplace add`가 "marketplace not found"를 낸다.**
저장소가 아직 공개(public)로 푸시되지 않았거나 이름이 틀렸다. `gh repo view
zeromountain/spec-driven-dev`로 저장소가 실제로 존재하는지, `.claude-plugin/marketplace.json`의
`name`이 `spec-driven-dev`인지 확인한다.

**설치했는데 `/sdd:init`이 안 보인다.**
플러그인은 세션 시작 시점에 로드된다. 세션을 완전히 재시작한다. 그래도 안 보이면
`/plugin list`로 `sdd@spec-driven-dev`가 실제로 설치·활성화됐는지 확인한다.

**Codex에서 `$sdd:spec-driven-dev`가 안 먹는다.**
`codex plugin list --json`으로 설치 여부를 먼저 확인한다. Codex는 슬래시 커맨드가
아니라 스킬 트리거이므로, 정확한 문법 대신 "SDD로 시작해줘" 같은 자연어로 스킬의
`description`이 자동으로 매칭되게 해도 된다.

**Codex에서 `/sdd:run` 같은 커맨드가 없다.**
Codex 플러그인 매니페스트에는 커맨드 필드 자체가 없다 — 정상이다. 위 "설치 후 첫 실행"의
대응표대로 의도를 말로 전한다.

**Codex인데 여러 기능이 동시에 안 돌아간다.**
`sdd.py board`의 `waiting` 사유를 본다. "페이즈 게이트가 …를 잡고 있다"면 이 프로젝트의
`.sdd/state.json`에 `enforce: true`가 남아 있는 것이다 — Codex에는 훅이 없어 막지도
못하면서 스케줄러만 같은 페이즈로 묶는다. `sdd.py phase off`로는 풀리지 않는다(스케줄러가
기다리는 쪽 단계로 페이즈를 다시 고른다). `.sdd/state.json`의 `enforce`를 `false`로
바꿔야 한다 — 이 파일은 세션 로컬이고 gitignore되므로 손으로 고쳐도 안전하다. 대신 리뷰
단계에서 `sdd.py guard`로 위반을 반드시 확인한다.

**파이프라인이 명세를 쓰고 나서 더 진행하지 않는다.**
명세 승인을 기다리는 중이다(`/sdd:status`나 `/sdd:board`에서 `pendingApproval: spec`). 승인하거나
고칠 점을 말하면 이어진다. 에이전트가 대신 승인하지 않는 것은 의도된 동작이다 — 매번 멈추는
게 싫으면 [설정](#설정-sddconfigjson)의 `humanGates`를 끈다.

**리뷰가 승인됐는데 `done`이 아니라 회고가 남았다고 나온다.**
회고(`reflect`) 대기다. 남길 교훈을 고르거나 "이번엔 없어"라고 답하면 닫힌다. 명세 정리와
아카이브는 이미 끝났고, 회고 대기는 다른 기능의 진행을 막지 않는다.

**잘못된 교훈이 쌓여 에이전트가 이상하게 행동한다.**
`sdd.py learn --list`로 확인하고 `learn --remove LRN-N`으로 지우거나 `docs/sdd/learnings.md`를
직접 고친다. 다음 `next`부터 바로 반영된다.

**하드 게이트를 켰는데 정상적인 쓰기까지 막힌다.**
`.sdd/state.json`의 `phase`를 확인한다(`sdd.py status`). 페이즈와 쓰려는 경로가
맞지 않으면 의도된 차단이다 — `/sdd:phase off`로 게이트를 잠깐 끄거나, `/sdd:phase`로
올바른 페이즈로 전환한다. 훅 자체가 오작동한다고 의심되면 [`AGENTS.md`](../AGENTS.md)에 있는 훅 단독 실행 예시로
직접 stdin을 넣어 재현해본다.

**사설(private) 저장소로 옮기고 싶다.**
`gh repo edit zeromountain/spec-driven-dev --visibility private`으로 바꿀 수 있지만,
그러면 설치하려는 모든 사용자가 그 저장소에 대한 Git 읽기 권한을 가져야 한다(SSH 키 또는
`gh auth`로 인증된 계정). 개인 전용으로만 쓸 경우에만 권장한다.
