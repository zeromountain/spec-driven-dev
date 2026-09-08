# herdr 워크플로우

**herdr는 `sdd.py`의 파이프라인 레지스트리(`run`/`next`/`advance`/`board`/`abort`)를 쓰지
않는다.** 진행 위치·재시도 횟수·단계 간 인계(`carry`)는 herdr 자신의 오케스트레이션
프리미티브(태스크 그래프, 상태 저장)가 관리한다. Claude Code·Codex 두 호스트가 공유하는
`.sdd/state.json`의 `pipeline(s)` 레코드는 herdr 경로에서 쓰지 않는다.

## 이게 SDD 원칙 위반이 아닌 이유

`SKILL.md`의 절대 규칙 2번 "숫자·판정은 스크립트가 낸다"는 **두 가지를 함께** 요구한다 —
① 명세 유효성·로스터·추적성·위반 같은 *판정*이 스크립트에서 나올 것, ② *지금 어느
단계인지*가 대화가 아니라 어딘가에 결정론적으로 저장될 것. herdr 워크플로우는 ①을 그대로
`sdd.py`에 맡기고, ②만 herdr 자신의 상태 관리로 옮긴다. 그래서 아래 두 절의 경계가
이 문서 전체에서 가장 중요하다 — 어느 쪽으로도 "고치지" 마라.

## 유지: `sdd.py`의 stateless 판정

herdr 코디네이터가 각 게이트에서 **직접** 호출한다. 전부 파이프라인 레지스트리 없이도
동작하는 순수 판정/스캐폴딩 명령이다.

| 명령 | 언제 | 비고 |
|---|---|---|
| `validate <spec-path>` | spec 완료 게이트 | `spec-architect`가 낸 명세가 구조적으로 유효한지 |
| `depth [slug] [--feature ...] [--force light\|deep]` | spec 완료 후 로스터 결정 | 아래 "슬러그를 항상 명시한다" 참고 |
| `new <feature> [--slug ...]` | spec 시작 | 슬러그 정규화, 버전 파일 생성. 아카이브에 같은 슬러그가 있으면 먼저 복원한다(`references/pipeline.md`의 "완료 명세 아카이빙") |
| `tasks <slug>` | implement 시작 | AC 대응표가 채워진 `tasks.md` 생성. `slug`를 생략하면 `activeSpec`을 보는데, herdr는 그 필드를 유지하지 않으므로 **항상 명시한다** |
| `trace <spec-path> [--workdir]` | implement→review 게이트 | AC↔테스트 커버리지. 워크트리/herdr 자체 격리 디렉터리를 쓰면 `--workdir`로 그쪽을 가리킨다 |
| `review-report <slug> [--force light\|deep]` | review 시작 | 리뷰 리포트 골격 생성 |
| `guard [--base] [--workdir]` | review 게이트, 그리고 각 단계 종료 시 | herdr에도 PreToolUse 훅이 없다(Codex와 같은 처지) — 경계 위반은 여기서만 사후에 잡힌다 |
| `phase <target> --spec <slug>` | 매 단계 전환 시 | 전환 유효성 판정 **+ 전역 `state.phase` 갱신**. 아래 "전역 상태 위험" 필독 |
| `status` / `list` | 재개·보고 시 | 조회용. herdr가 "지금 어디인지"의 근거로 쓰지 않는다 — 근거는 herdr 자신의 태스크 상태다 |

## 넘기지 않음: 파이프라인 레지스트리와 그 안의 로직

`run`/`next`/`advance`/`board`/`abort`, 그리고 `.sdd/state.json`의 `pipeline(s)` 필드는
호출·기록하지 않는다. 이 레지스트리 안쪽에만 있고 CLI로 노출되지 않은 로직은 herdr
코디네이터가 **직접 구현**해야 한다 — 대표적으로 아래 두 가지.

### 1. 리뷰 종합 (`combine_verdicts`)

CLI 명령이 없다. herdr의 join 게이트가 아래 4규칙을 그대로 지켜야 한다
(`references/pipeline.md` "리뷰 단계는 `call-agents`다" 참고):

1. **하나라도 `changes-requested`면 전체가 `changes-requested`다.** 평균 내지 않는다.
2. **로스터 전원의 판정이 오기 전에는 종합하지 않는다.** 일부만 보고 승인하는 경로가 없다.
3. `severity: "high"` 지적만 재시도를 유발한다. `medium`/`low`는 리포트에만 남긴다.
4. `[리뷰어이름]` 접두어는 리뷰어가 둘 이상일 때만 붙인다(한 명이면 노이즈다).

### 2. 승인 시 3단 쓰기

CLI 명령이 없다. review 로스터 전원이 `approved`면, herdr 코디네이터가 **이 순서로 직접**
써야 한다(`references/pipeline.md` "페이즈 게이트와의 관계" 참고):

1. 명세와 `tasks.md`의 남은 `- [ ]`를 전부 채운다.
2. 명세 프론트매터에 `status: done`을 쓴다.
3. `specs/<슬러그>/`를 **디렉터리째** `specs/archive/<슬러그>/`로 옮긴다.

순서가 중요한 이유: 1·2는 같은 파일을 각자 읽고 쓰므로 순차여야 하고, `enforce: true`인
프로젝트라면 review 페이즈에서는 `specs/` 쓰기가 막혀 있으므로 세 쓰기 모두 `phase: spec`
으로 잠깐 돌렸다가 끝나면 `phase: off`로 넘기는 창 안에서 해야 한다(`sdd.py phase spec
--spec <슬러그>` → 세 쓰기 → `sdd.py phase off`). 이 창을 건너뛰면 `guard`에 위반으로
남는다.

같은 슬러그를 나중에 다시 열 때는(재작업) `specs/archive/`에서 직접 파일을 옮기지 마라 —
`sdd.py new <같은 기능>`을 불러 `create_spec_file`이 먼저 복원하게 한다. 아카이브에 있는
동안 살아 있는 파이프라인이 그 슬러그를 갖는 순간은 없어야 한다는 불변식이 여기에도 그대로
적용된다.

> 이 두 가지를 매번 손으로 맞추는 게 번거로우면, `sdd.py`에 파이프라인 레지스트리 없이
> "리뷰 결과 배열을 받아 종합하고, approved면 3단 쓰기까지 하는" stateless 서브커맨드
> (예: `combine`/`approve`)를 추가하는 방법이 있다. 이 문서는 현재 스코프(기존
> `scripts/sdd.py` 변경 없음)에서는 그 커맨드를 만들지 않는다 — 필요하면 별도로 요청한다.

## 3페이즈·10역할을 herdr에 매핑하기

herdr의 실제 API 이름은 이 저장소가 알지 못한다. 그래서 아래는 특정 함수 이름이 아니라
**herdr 코디네이터가 반드시 제공해야 하는 능력**과, 그 능력이 실어야 하는 SDD 개념을
짝지은 것이다.

| herdr 코디네이터가 제공해야 하는 능력 | 실어야 하는 SDD 개념 |
|---|---|
| 격리된 컨텍스트로 역할을 하나씩(또는 로스터 크기만큼 fan-out) 실행 | `agents/<역할>.md`의 프롬프트 — 역할별 책임·쓰기 범위는 `references/roles.md` 그대로 |
| 병렬 fan-out (review 단계) | 리뷰어 전원 **동시** 호출, 서로의 판정을 못 보게 격리 |
| fan-out 전원 도착을 기다리는 join | `combine_verdicts`의 4규칙(위) |
| 사용자에게 묻고 응답을 받아 재개하는 블로킹 지점 | spec 단계의 `openQuestions` |
| 실패·중단을 사용자에게 보고하고 멈추는 경로 | `halted` — 지어내서 우회하지 않는다 |
| 한 단계의 결과를 다음 단계 입력에 실어 보내는 전달 | `carry`(`validateErrors`/`specChangeRequests`/`testFailures`/`reviewGaps`/`implementNotes`·`testResult`/`lastReviewPath`) — `references/pipeline.md` "단계 간 인계" 표 그대로 |
| 단계 재시도 상한과 전체 스텝 상한 | 파이프라인 레지스트리의 `maxAttempts`(기본 2)·`MAX_PIPELINE_STEPS`(24) 값을 herdr 쪽 설정으로 옮겨 그대로 적용 — 상한 자체를 없애지 않는다 |

전이 조건(무슨 결과가 오면 어디로 가는지)은 `references/pipeline.md`의 "전이표"를 herdr
그래프의 엣지 조건으로 그대로 옮긴다 — 여기서 다시 베끼지 않는다.

## 동시성과 전역 상태 위험

`phase`와 (state.json이 있을 때) `depth`는 **프로젝트 전역에 딱 하나씩** 쓴다. 파이프라인
레지스트리 안에서는 워크트리를 가진 파이프라인이 `apply=False`로 이 전역 쓰기를 피해가지만,
그 경로는 CLI로 노출돼 있지 않다 — herdr에서는 쓸 수 없다. 그래서:

- **herdr로 여러 기능을 동시에 진행할 때, `phase`를 쓰는 기능들은 같은 페이즈에 있을 때만
  동시에 진행한다.** 다른 페이즈의 기능이 동시에 전역 phase를 밀면, 뒤에 쓴 쪽이 앞선
  기능의 phase 판정을 덮어써 `guard`가 엉뚱한 페이즈로 위반을 검사하게 된다.
- 이 제약을 피하려면 `enforce: false`(또는 `.sdd/state.json`의 `phase`를 아예 쓰지 않고
  herdr 자체 격리 디렉터리 + `guard --workdir`만으로 사후 검사)로 운영한다. herdr가 자체
  워크트리/디렉터리 격리를 제공한다면 이 쪽이 낫다.
- `depth` 호출이 `.sdd/state.json`에 남기는 `state["depth"]`는 **정보용 캐시일 뿐**,
  기능별 로스터의 정본이 아니다. herdr는 각 기능의 로스터 판정을 자기 태스크 상태에
  직접 들고 있어야 한다 — 파이프라인 레지스트리의 `forcedDepth`(파이프라인 내내 유지되는
  깊이 강제값)에 대응하는 것이 없으므로, 사용자가 `--deep`/`--light`를 골랐으면 herdr가
  그 기능의 이후 모든 `depth` 호출에 **매번** 같은 `--force`를 넘겨야 한다.
- **한 슬러그는 한 오케스트레이터만 소유한다.** 같은 기능을 herdr 워크플로우와 파이프라인
  레지스트리(`sdd.py run`)로 동시에 진행하지 않는다 — "지금 어디인지"의 근거가 둘이
  생기고, 서로 모르는 채로 같은 명세·파일을 건드리게 된다.

## 운영상 디테일

- `tasks`/`review-report`/`depth`는 `slug`를 생략하면 `activeSpec`으로 폴백한다. herdr는
  이 필드를 유지·갱신하지 않으므로 **모든 호출에 슬러그를 명시한다.**
- `validate`/`trace`는 명세 경로(`spec-v<N>.md`)를 직접 받는다 — herdr가 자기 상태에서
  최신 버전 경로를 알고 있어야 한다(`sdd.py list`로 확인 가능).
- 워크트리 격리가 필요하면 `sdd.py init --worktrees`로 켜고 `.sdd/worktrees/<슬러그>/`를
  쓸 수 있다. 다만 "파이프라인마다 자기 단계로 게이팅"되는 이점(`references/pipeline.md`
  "워크트리" 절)은 훅이 판정할 때만 성립하며, herdr 자체 오케스트레이션에서는 순수
  디렉터리 격리로만 쓰인다.

## Orca와의 차이

이 문서는 herdr 전용이다. **Orca에서는 이 문서가 필요 없다** — Orca는 이 세션이 실제로
그 위에서 동작하는 것으로 보이며, Orca가 호스팅하는 세션은 Claude Code 서브에이전트를
그대로 쓸 수 있는 것으로 확인된다. 그렇다면 기존에 설계된 워크플로우(파이프라인
레지스트리 + `next`/`advance` 루프, Claude Code 열)가 변경 없이 그대로 적용된다 —
"호스트별 차이" 표에 새 사실을 추측해서 채우지 않는다.
