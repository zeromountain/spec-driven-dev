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
- [하드 페이즈 게이트 켜기](#하드-페이즈-게이트-켜기)
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
   7개 커맨드가 보여야 한다.

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
python3 -m unittest discover -s scripts/tests -t .   # sdd.py 단위 테스트 (30개)
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
$sdd:spec-driven-dev init 해줘
```

`init`은 다음을 만든다: `specs/`, `.sdd/state.json`(세션 로컬, gitignore됨),
`.sdd/config.json`(팀 공유, 커밋됨), `.sdd/reviews/`, 그리고 프로젝트의 `AGENTS.md`(없으면
생성, 있으면 "## Spec-Driven Development" 섹션만 추가/교체). 이미 있는 내용은 절대
덮어쓰지 않는다.

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

## 호스트별 차이

플러그인 매니페스트가 두 개인 이유: Claude Code는 `.claude-plugin/plugin.json`을, Codex는
`.codex-plugin/plugin.json`을 읽는다. 저장소 구조는 하나지만 각 호스트가 지원하는
컴포넌트 종류가 다르다.

| 컴포넌트 | Claude Code | Codex CLI |
|---|---|---|
| `skills/spec-driven-dev/SKILL.md` | ✅ | ✅ |
| `commands/*.md` (`/sdd:*`) | ✅ | ❌ (스킬을 직접 호출) |
| `agents/*.md` (서브에이전트 10개) | ✅ | ❌ (Codex 플러그인은 서브에이전트 정의를 지원하지 않는다) |
| `hooks/hooks.json` (페이즈 게이트) | ✅ (opt-in) | ❌ (Codex 플러그인 매니페스트에 훅 필드가 없다) |
| `scripts/sdd.py` (CLI) | ✅ | ✅ (스킬이 Bash로 호출) |

Codex에서는 `spec-driven-dev` 스킬 하나가 10개 역할을 **하나의 세션 안에서 순서대로 직접 수행**한다 — 별도 서브에이전트로 위임하지
않는다. 역할 경계(예: "Spec Architect는 src/를 쓰지 않는다")는 스킬 프롬프트로만
지켜지고, Claude Code처럼 훅이 실제로 차단하지는 않는다. `sdd.py guard`는 두 호스트
모두에서 동작하므로, Codex에서는 이걸로 사후에 위반 여부를 확인한다.

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

**하드 게이트를 켰는데 정상적인 쓰기까지 막힌다.**
`.sdd/state.json`의 `phase`를 확인한다(`sdd.py status`). 페이즈와 쓰려는 경로가
맞지 않으면 의도된 차단이다 — `/sdd:phase off`로 게이트를 잠깐 끄거나, `/sdd:phase`로
올바른 페이즈로 전환한다. 훅 자체가 오작동한다고 의심되면 [`AGENTS.md`](../AGENTS.md)에 있는 훅 단독 실행 예시로
직접 stdin을 넣어 재현해본다.

**사설(private) 저장소로 옮기고 싶다.**
`gh repo edit zeromountain/spec-driven-dev --visibility private`으로 바꿀 수 있지만,
그러면 설치하려는 모든 사용자가 그 저장소에 대한 Git 읽기 권한을 가져야 한다(SSH 키 또는
`gh auth`로 인증된 계정). 개인 전용으로만 쓸 경우에만 권장한다.
