---
name: spec-driven-dev
description: 명세를 소스 오브 트루스로 삼는 Spec-Driven Development(SDD) 하네스를 설정하고 운영한다. "SDD 시작해줘", "명세부터 만들자", "spec-driven으로 개발하자", "AGENTS.md에 SDD 규약 걸어줘" 같은 요청, 또는 이미 SDD가 설정된 프로젝트에서 "명세 써줘", "이 기능 구현해줘"(명세 기반으로), "리뷰해줘"(명세 대조), "지금 페이즈가 뭐야" 같은 요청에 쓴다. SDD 프로젝트에서 중단된 작업을 이어가려는 요청("이어서 해줘", "아까 하던 거 계속", "어디까지 했지")에도 쓴다 — 진행 위치가 .sdd/state.json에 남아 있어 컨텍스트 없이도 재개된다. 단순 코드 작성/버그 수정처럼 명세 없이 바로 구현하면 되는 요청에는 쓰지 않는다 — 그건 일반 개발 워크플로의 영역이다.
---

# Spec-Driven Development (spec-driven-dev)

이 스킬의 목적은 "코드를 고치기 전에 명세부터 고친다"는 규율을 **프롬프트가 아니라
하네스로 집행하는 것**이다. 세 페이즈(spec / implement / review)마다 역할이 나뉜
서브에이전트가 자기 쓰기 범위 안에서만 움직이고, `enforce: true`인 프로젝트에서는
PreToolUse 훅이 페이즈 경계를 실제로 막는다. 진행 위치와 **누구를 부를지**는 대화가
아니라 `sdd.py`의 상태에 있다.

## 절대 규칙

1. **명세가 소스 오브 트루스다.** 구현 동작을 바꿔야 하면 먼저 명세를 바꾼다(또는 새
   버전을 만든다) — 코드를 몰래 명세와 다르게 고치지 않는다.
2. **숫자·판정은 스크립트가 낸다.** 명세 유효성(`validate`), 버전 번호(`new`), 페이즈
   전환 가능 여부(`phase`), **어떤 서브에이전트를 부를지(`depth`)**, 추적성(`trace`),
   위반(`guard`)을 대화 중 암산하지 않는다. `${scriptPath} <subcommand>`의 JSON 출력을
   그대로 읽는다.
3. **무엇을 동시에 해도 되는지도 스크립트가 정한다.** 두 기능을 병렬로 돌릴 때
   "이 정도면 같이 해도 되겠지"라고 판단하지 않는다 — `next --all`의 `round[]`에 함께 온
   것만 동시에 부르고, `waiting[]`은 기다린다. 이 판단을 모델이 하면 두 서브에이전트가
   같은 파일을 동시에 고쳐 한쪽 작업이 조용히 사라진다.
4. **다음 행동도 스크립트가 정한다.** 파이프라인이 돌고 있는 동안 "이제 구현으로 넘어갈
   차례"라고 네가 판단하지 않는다 — `next`가 시키는 행동 하나만 하고 `advance`로 결과를
   넘긴다. 진행 위치는 대화가 아니라 `.sdd/state.json`의 `pipeline`에 있으므로, 어디까지
   했는지 사용자에게 되묻지 않는다.
5. **역할 경계를 존중한다.** Spec Architect는 `specs/`만, Software Engineer는 `src/`만,
   Test Engineer는 `tests/`만, Impl Planner는 `tasks.md`만, 리서처·감사자·리뷰어는 쓰기
   자체를 하지 않는다. **같은 페이즈 안의 경계는 훅이 막지 못한다** — 특히 깊은 모드에서
   `software-engineer`가 테스트를 쓰거나 `test-engineer`가 구현을 고치는 것은 통과된다.
   `next`의 `instruction`에 그 금지가 담겨 있으니 **줄여서 전달하지 마라.**
6. **기능은 리뷰 승인 후에만 완료다.** 리뷰어가 여럿일 때 **하나라도
   `changes-requested`면 전체가 `changes-requested`다** — 평균 내지 않는다. 종합은
   `advance`가 하므로 네가 판정을 합치지 않는다.
7. **하드 게이트를 대신 끄지 않는다.** 페이즈 게이트가 deny하면, 그 파일을 다른 경로로
   우회해 쓰지 않는다. 파이프라인 안에서는 `next`가 정식 전환을 이미 하며, 전환이 막히면
   `halted`로 그 이유를 그대로 보고한다. 게이트를 끄는 것은 사용자의 `/sdd:phase off`뿐이다.

## 서브에이전트 10종

| 페이즈 | 에이전트 | 하는 일 | 쓰기 |
|---|---|---|---|
| spec | `spec-researcher` | 기존 코드·명세·용어 조사 → 컨텍스트 팩 | 없음 |
| spec | **`spec-architect`** | 8섹션 명세 작성 | `specs/` |
| spec | `spec-auditor` | 명세를 적대적으로 검토 (검증 가능성·모순·누락 EC) | 없음 |
| implement | `impl-planner` | AC → 태스크 분해, 영향 파일·패턴·순서 확정 | `tasks.md` |
| implement | **`software-engineer`** | 구현 | `src/` |
| implement | `test-engineer` | AC별 테스트 작성·실행 | `tests/` |
| review | **`spec-reviewer`** | 명세 준수·AC 커버리지·스펙 밖 구현 | 없음 |
| review | `code-reviewer` | 가독성·복잡도·중복·에러 처리 | 없음 |
| review | `security-reviewer` | 입력 검증·인가·시크릿·인젝션 | 없음 |
| review | `perf-reviewer` | N+1·복잡도·재계산·경계 없는 로딩 | 없음 |

굵은 3개는 항상 돌고, 나머지는 `sdd.py depth`가 정할 때만 붙는다. **누구를 부를지 네가
정하지 않는다** — `next` 응답의 `agent`(또는 `agents`)가 그대로 답이다. `roster`와
`rosterPosition`으로 지금 단계의 몇 번째인지도 함께 온다.

깊이 판정 근거는 인수 기준 개수(8개 이상)·오류 케이스 개수(5개 이상)·검증 경고 수(3개
이상)와 명세 본문의 보안·성능 키워드다. `run` 응답의 `depth.deepReasons`를 사용자에게
한 줄로 알린다 — 깊은 모드는 한 번의 `/sdd:run`이 최대 10개 서브에이전트를 부르므로,
근거 없이 에이전트 수가 바뀌면 비용을 예측할 수 없다. 사용자가 직접 정하려면
`/sdd:run <설명> --deep` 또는 `--light`다(파이프라인 내내 유지된다).

`security-reviewer`·`perf-reviewer`는 **깊이와 무관하게** 신호가 잡히면 붙는다 —
`--light`를 강제해도 명세에 인증·토큰이 등장하면 보안 리뷰는 돈다.

## 모드

| 모드 | 트리거 | 실행 |
|---|---|---|
| init | `/sdd:init` | `sdd.py init` → 스캐폴딩, AGENTS.md 병합, 하드 게이트 여부 확인 |
| run | `/sdd:run <설명> [--deep\|--light]` | 파이프라인 시작 → **next/advance 루프**를 끝까지 돌린다 |
| resume | `/sdd:run` (인자 없이) | 중단된 파이프라인을 그 자리에서 재개 |
| run-all | `/sdd:run --all` | 살아 있는 파이프라인 **전부**를 배치 루프로 끝까지 돌린다 |
| board | `/sdd:board` | 살아 있는 파이프라인 전부의 위치·실행 가능 여부 |
| worktree | `/sdd:worktree <list\|status\|add\|remove>` | 기능별 워크트리 조회·생성·정리 |
| spec / implement / review | `/sdd:spec` 등 | 루프를 **한 번만** 돌린다 (수동 스텝) |
| audit | `/sdd:audit [슬러그]` | `spec-auditor`만 단독 호출 (파이프라인 밖에서 명세만 재검토) |
| status | `/sdd:status` | `sdd.py status` JSON을 표로 렌더 (파이프라인 위치·깊이 포함) |
| phase | `/sdd:phase <spec\|implement\|review\|off>` | 수동 전환 (파이프라인이 알아서 하므로 평소엔 불필요) |

## 워크플로

### 준비: 스크립트 경로 확인 (세션당 한 번)

```bash
ls -d ~/spec-driven-dev/scripts 2>/dev/null \
  || find ~/.claude/plugins/cache ~/.codex/plugins/cache -maxdepth 5 -type d \
       -path '*sdd*/scripts' 2>/dev/null | sort -V | tail -1
```

개발용 체크아웃(`~/spec-driven-dev`)이 있으면 그쪽을 쓰고, 없으면 설치된 캐시에서 찾는다.
캐시에는 orphaned 구버전이 함께 남아 있으므로 **버전 정렬 후 마지막**을 쓴다 — `head -1`은
0.2.0 같은 구버전을 집을 수 있다.

결과를 `$S`로 취급한다(셸 변수는 Bash 호출 간 유지되지 않으므로, 이후 모든 명령에서
경로를 텍스트로 그대로 치환해 쓴다). `$S/sdd.py`가 CLI 진입점이다.

### 0단계: 컨텍스트 확인

`$S/sdd.py status --path <project-root>`로 현재 phase·명세 목록·게이트 위반·파이프라인
위치를 먼저 본다. `.sdd/state.json`이 없으면 아직 `/sdd:init`이 실행되지 않은 것이다 —
init부터 안내한다.

### 1단계: 파이프라인 루프 (run 모드 — 기본 경로)

파이프라인의 진행 위치는 **대화 컨텍스트가 아니라 `.sdd/state.json`의 `pipeline` 레코드**에
있다. 그러니 이 루프에서 네가 판단할 것은 없다. `next`가 시키는 행동 하나를 하고, 그 결과를
`advance`에 넘기고, 그 응답의 `next`로 다음 라운드를 연다.

```bash
# 시작 (인자를 비우면 중단된 파이프라인을 그 자리에서 재개한다)
$S/sdd.py run "<기능 설명>" --path <root>
```

응답의 `next.action`에 따라 아래를 **`done`·`halted`·`ask-user`가 나올 때까지 반복한다**:

| `action` | 할 일 |
|---|---|
| `call-agent` | `agent`가 지정한 서브에이전트를 `instruction` + `context`를 **그대로** 전달해 호출한다. 반환된 JSON을 그대로 `$S/sdd.py advance --path <root> --stage <stage> --result '<json>'`에 넘긴다. 그 응답의 `next`가 다음 라운드다. |
| `call-agents` | 리뷰 단계. `agents[]`의 리뷰어를 **한 메시지에서 동시에** 호출한다 — 순차로 부르며 앞선 판정을 다음 리뷰어에게 알려주면 독립성이 깨진다. 각 결과에 `agent` 키를 붙여 `advance --result '{"reviews": [...]}'`로 한 번에 넘긴다. 종합 판정은 `advance`가 낸다. |
| `ask-user` | `questions`를 사용자에게 그대로 묻는다. 답을 `advance --result '{"answers": {...}}'`로 넘기면 루프가 이어진다. |
| `done` | 완료. 5단계(기록)로 간다. |
| `halted` | `reason`과 `history`를 그대로 사용자에게 보고하고 멈춘다. 지어내서 우회하지 않는다. |
| `init-required` / `none` | 각각 `/sdd:init`, `/sdd:run <설명>`을 안내한다. |

**루프 중 하지 말 것:**

- `next`가 시키지 않은 일을 미리 하지 마라. 페이즈 전환, 명세 파일 생성, `tasks.md`,
  리뷰 리포트 골격, 승인 시 `status: done` 갱신은 **전부 `next`/`advance`가 이미 했다**.
  `phase`·`new`·`tasks`·`review-report`를 손으로 부르면 상태가 어긋난다.
- `advance`를 건너뛰고 다음 서브에이전트를 부르지 마라 — 그 순간 파이프라인이 제자리에 남는다.
- 단계 사이에서 사용자에게 "계속할까요?"를 묻지 마라. 멈추는 건 `ask-user`와 `halted`뿐이다.
- 재시도 횟수를 세지 마라. `attempts`/`maxAttempts`는 `advance`가 센다.
- `waiting`에 있는 파이프라인을 억지로 돌리지 마라. 스케줄러가 페이즈 충돌이나 파일 겹침을
  이미 확인했다 — 우회하면 한쪽 작업이 사라지거나 게이트에 막힌다.
- 살아 있는 파이프라인이 여럿일 때 `--spec` 없이 `advance` 하지 마라.
- 워크트리가 있는 파이프라인의 코드를 본체에서 고치지 마라. `context.workdir` 안에서만 쓴다.
- 승인됐다고 브랜치를 병합하거나 워크트리를 지우지 마라 — 사용자에게 경로와 브랜치를 알린다.
- 로스터를 늘리거나 줄이지 마라. 사용자가 더/덜 원하면 `--deep`/`--light`로 넘긴다.
- 리뷰어 판정을 네가 합치지 마라. 전원의 결과를 모아 한 번에 `advance`에 넘긴다 —
  일부만 넘기면 파이프라인이 `halted`로 그 사실을 알린다.
- 서브에이전트 출력을 요약해서 넘기지 마라. `advance`에는 받은 JSON을 **그대로** 넣는다.

### 1.5단계: 여러 기능을 동시에

`run`은 **다른 기능이면 막지 않는다.** 기능마다 파이프라인이 하나씩 생기고
`.sdd/state.json`의 `pipelines`에 슬러그로 저장된다. 같은 기능을 다시 `run`할 때만
`--restart`/`--resume`이 필요하다.

```bash
$S/sdd.py run "프로필 이미지 업로드" --path <root>
$S/sdd.py run "결제 취소 정책" --path <root>     # 막히지 않는다
$S/sdd.py run --all --path <root>                # 전부를 대상으로 배치 루프를 연다
```

`run --all`은 살아 있는 것 전부를 대상으로 잡고 첫 라운드까지 돌려준다. `--resume`을 함께
주면 `halted`인 파이프라인도 되살린다. 인자 없는 `/sdd:run`은 **하나만**(마지막에 손댄 것)
재개하므로, 여러 개를 함께 돌리려면 `--all`을 붙인다.

이후 라운드는 `$S/sdd.py next --all`로 연다. `action: "batch"`를 내면 **`round[]`의 행동들을 한 메시지에서 동시에
호출한다.** 스케줄러가 이미 안전을 확인한 목록이므로 네가 다시 판단하지 않는다. 각 결과는
`advance --spec <슬러그>`로 **따로** 넘긴다.

```bash
$S/sdd.py advance --spec 프로필-이미지-업로드 --result '<json>' --path <root>
$S/sdd.py advance --spec 결제-취소-정책 --result '<json>' --path <root>
$S/sdd.py next --all --path <root>               # 다음 라운드
```

**`--spec`을 빼먹지 마라.** 살아 있는 파이프라인이 둘 이상이면 `advance`는 대상을 추측하지
않고 거부한다 — 결과를 엉뚱한 파이프라인에 먹이면 그 기능의 상태가 남의 결과로 조용히
전이된다. 하나뿐일 때는 예전처럼 생략해도 된다.

### 워크트리 (`worktrees: true`)

워크트리를 켜면 기능마다 `.sdd/worktrees/<슬러그>/`에 독립된 체크아웃과 `sdd/<슬러그>`
브랜치가 생기고, **위 두 제약이 모두 사라진다.**

- 디렉터리가 아예 다르므로 구현 파일이 겹칠 수가 없다.
- 워크트리 경로에 슬러그가 들어 있으므로 훅이 "이 쓰기가 어느 파이프라인의 것인가"를 알 수
  있다. 그래서 `enforce: true`여도 **파이프라인마다 자기 단계로 게이팅**되고, 전역 페이즈에
  매이지 않는다. 페이즈 게이트를 켠 채로 진짜 병렬 실행이 되는 유일한 경로다.

`next`의 `context.workdir`가 그 파이프라인의 작업 디렉터리다. **서브에이전트에게 이 경로를
그대로 넘기고, 코드·테스트는 반드시 그 안에서만 읽고 쓰게 한다.** 본체에 쓰면 격리가
무너지고 게이트 판정도 전역 페이즈로 떨어진다.

**명세(`specs/`)와 제어면(`.sdd/`)은 본체에만 있다.** 슬러그별로 갈라져 있어 애초에
충돌하지 않고, 상태가 여러 곳에 흩어지면 재개가 깨진다. `context.specPath`는 본체 기준
경로이므로 그대로 쓰면 된다.

승인 후에는 **워크트리 경로와 브랜치 이름을 사용자에게 알리고 멈춘다.** 이 하네스는
브랜치를 병합하지 않는다 — 어디에 어떻게 합칠지는 사용자의 판단이다. 정리는
`/sdd:worktree remove <슬러그>`이고, 커밋되지 않은 변경이 있으면 거부된다.

git 저장소가 아니면 워크트리를 만들지 못한다. 그때 파이프라인은 본체에서 돌되
`worktreeWarning`으로 그 사실을 알린다 — 숨기지 말고 전달한다.

`waiting[]`에 올라온 파이프라인은 **그 이유를 사용자에게 전하되 우회하지 마라.** 자리가
나면 다음 `next --all`에서 자동으로 `round[]`로 올라온다. 이유는 두 가지뿐이다:

| 이유 | 왜 |
|---|---|
| 페이즈 게이트가 다른 페이즈를 잡고 있다 | 게이트는 프로젝트 전역이라 `enforce: true`에서는 같은 페이즈끼리만 동시에 돈다 |
| 구현 파일이 겹친다 | 두 서브에이전트가 같은 파일을 동시에 고치면 한쪽 작업이 조용히 사라진다 |

둘 다 **워크트리를 쓰면 없어진다** (아래).

`/sdd:board`(또는 `$S/sdd.py board`)로 전체 현황을 표로 보여줄 수 있다.

### 2단계: 수동 스텝 (`/sdd:spec`, `/sdd:implement`, `/sdd:review`)

진행 중인 파이프라인이 있으면 이 명령들은 **루프를 한 번만 돌린다** — `next` 한 번,
서브에이전트 한 번, `advance` 한 번. 그리고 다음 `next`를 사용자에게 보여주고 멈춘다.
`next.stage`가 사용자가 부른 단계와 다르면 그 사실을 알리고 파이프라인의 단계를 따른다
(임의로 건너뛰지 않는다).

진행 중인 파이프라인이 없으면 `$S/sdd.py run "<설명>"`으로 새로 시작한 뒤 한 스텝만 돌린다.

### 3단계: 중단과 재개

- 세션이 끊겼거나 `/clear` 후에도 `$S/sdd.py next --path <root>` 한 번이면 진행 위치·다음
  행동·직전 이력이 전부 돌아온다. 어디까지 했는지 사용자에게 되묻지 마라.
- `halted` 상태에서 원인을 고쳤으면 `$S/sdd.py run --resume --path <root>`로 같은 자리에서
  다시 시작한다.
- 사용자가 그만두길 원하면 `$S/sdd.py abort --reason "<사유>" --path <root>`.
- 다른 기능으로 갈아타려면 `$S/sdd.py run "<새 설명>" --restart --path <root>` (직전
  파이프라인은 `pipelineHistory`에 요약만 남는다).

### 4단계: 왜 이 구조인가

**서브에이전트는 서브에이전트를 낳을 수 없다** — 그래서 오케스트레이션은 서브에이전트가
아니라 이 스킬(메인 세션)이 직접 돌린다. 다만 *무엇을 다음에 할지*는 이 스킬이 아니라
`sdd.py`의 상태머신이 정한다. 그래야 컨텍스트가 날아가도, 사용자가 중간에 끼어들어도,
호스트가 Claude Code든 Codex든 같은 자리에서 같은 다음 행동이 나온다.

### 5단계: 기록

작업이 끝나면 `$S/sdd.py status --path <root>`로 최종 상태를 한 번 더 확인하고 사용자에게
요약한다(phase, 명세 목록, 리뷰 판정, 남은 게이트 위반, 파이프라인 라운드 수).

## 참조 파일

- `references/pipeline.md` — 상태머신 전이표, `next`/`advance` 계약, 중단 사유별 대처
- `references/roles.md` — 10개 역할의 책임·금지 사항·인계 관계
- `references/depth.md` — light/deep 판정 규칙, 임계값, 신호 키워드
- `references/spec-format.md` — 8섹션 정의, AC-N 규약, 버저닝 규칙
- `references/phase-gate.md` — 훅 동작, 페이즈별 deny 표, 탈출구, Bash 미커버 이유
- `references/templates.md` — 스캐폴딩 산출물 전문과 최종 디렉터리 구조

## 하지 않을 것

- `enforce: true`인 프로젝트에서 게이트가 deny한 경로를 셸 명령으로 우회해 쓰지 않는다.
- 커버리지 90%를 이 스킬이 직접 측정해 강제하지 않는다 — 언어별 커버리지 도구는 프로젝트
  마다 다르다. `config.json`의 `minCoverage`는 Review Agent에게 넘기는 기준값일 뿐이고,
  측정 불가하면 리포트에 "측정 안 됨"으로 남긴다.
- 대상 프로젝트의 기존 `AGENTS.md`/`CLAUDE.md`를 통째로 덮어쓰지 않는다.
- auto-dev 같은 다른 개발 하네스와 기능을 합치지 않는다. 구현 루프를 다른 하네스에 맡기고
  싶다면 `/sdd:implement` 대신 그쪽을 쓰고, 이 스킬은 명세·리뷰 단계만 담당하게 한다.

## 면책

이 스킬은 강제되는 프로세스를 제공할 뿐, 명세의 품질이나 구현의 정확성을 보증하지 않는다.
`validate`는 구조를, `trace`는 태깅 규약이 지켜졌을 때의 커버리지만 확인한다 — 실제 코드
리뷰와 테스트 실행 결과를 대체하지 않는다. 리뷰어를 늘리는 것은 놓칠 확률을 줄일 뿐,
`approved`가 결함 없음을 뜻하지는 않는다.
