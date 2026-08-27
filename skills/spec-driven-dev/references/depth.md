# 깊이 판정 (`sdd.py depth`)

에이전트가 10개가 되면 "이번엔 몇 명을 부를까"가 매번 달라진다. 모델이 "복잡해 보인다"로
정하면 같은 작업이 세션마다 다르게 돈다 — 그래서 판정을 `scripts/sdd.py`의 순수 함수
`decide_depth()`로 옮겼다. 임계값과 키워드는 전부 그 모듈에 있다.

```bash
sdd.py depth [<슬러그>] --feature "<기능 설명>" [--force deep|light] --path <root>
```

- 명세가 아직 없는 시점(spec 페이즈 진입)에는 `--feature` 문자열만으로 판정한다.
- 명세가 생긴 뒤에는 슬러그를 주면 최신 `spec-v<N>.md` 본문으로 판정한다.
- **페이즈마다 다시 실행한다.** spec에서 light였어도 명세가 커졌으면 implement에서 deep이
  될 수 있다. 판정 결과는 `.sdd/state.json`의 `depth`에 기록된다(`sdd.py status`에 나온다).

## 임계값

`DEPTH_THRESHOLDS` — 하나라도 넘으면 `deep`.

| 신호 | 임계값 | 이유 |
|---|---|---|
| `acCount` | 8 이상 | AC가 많으면 한 에이전트의 컨텍스트 안에서 전부 추적되지 않는다 |
| `ecCount` | 5 이상 | 오류 경로가 많다 = 상태 공간이 넓다 |
| `warningCount` | 3 이상 | `validate` 경고가 쌓였다 = 명세 문장이 흐리다 |

## 신호 키워드

`SECURITY_HINT_RE` / `PERF_HINT_RE`가 명세 본문(없으면 기능 설명)에서 찾는다.
하나라도 걸리면 `deep`이 되고, **그와 별개로** 해당 리뷰어가 붙는다.

- 보안: 인증·인가·권한·로그인·비밀번호·토큰·세션·쿠키·암호화·개인정보·결제·시크릿·
  파일 업로드·SQL·XSS·CSRF, 그리고 `auth`/`oauth`/`jwt`/`secret`/`token`/`credential`
- 성능: 성능·지연·응답 시간·처리량·대용량·배치·동시성·병렬·캐시·인덱스·페이지네이션·
  스트리밍·N+1·초당·메모리 사용, 그리고 `throughput`/`latency`/`timeout`.
  **수치로 표현된 지연 요구**도 잡는다 — "응답은 3초 이내", "500ms 안에"처럼
  `<숫자><초|ms|밀리초|분> <이내|이하|안에>` 형태. 비기능 요구사항이 성능 리뷰를 부르는
  가장 흔한 경로다. ("3초짜리 애니메이션"처럼 뒤에 조건 어미가 없으면 걸리지 않는다.)

**리뷰어 부착은 깊이와 독립이다.** `--force light`로 경량을 강제해도 보안 신호가 잡혀
있으면 `security-reviewer`는 붙는다 — 한 줄짜리 인증 수정이야말로 보안 리뷰가 필요한
경우이기 때문이다.

## 결과

```json
{
  "depth": "deep",
  "forcedTo": null,
  "signals": {"acCount": 9, "ecCount": 3, "warningCount": 0,
              "securityHits": ["토큰"], "perfHits": []},
  "thresholds": {"acCount": 8, "ecCount": 5, "warningCount": 3},
  "deepReasons": ["인수 기준이 9개로 임계값 8개 이상이다", "보안 신호가 잡혔다: 토큰"],
  "agents": {
    "spec": ["spec-researcher", "spec-architect", "spec-auditor"],
    "implement": ["impl-planner", "software-engineer", "test-engineer"],
    "review": ["spec-reviewer", "code-reviewer", "security-reviewer"]
  },
  "slug": "...", "version": 2, "basedOn": "spec", "stateUpdated": true
}
```

`agents.<phase>`가 **이번 페이즈에 부를 에이전트 목록이자 호출 순서**다. 오케스트레이터는
이 목록을 늘리거나 줄이지 않는다. 사용자가 더/덜 원하면 `--deep`/`--light`로 넘긴다
(그 값이 `--force`가 되고 `forcedTo`에 기록된다).

`deepReasons`는 사용자에게 그대로 알린다 — 근거 없이 에이전트 수가 바뀐 것처럼 보이면
비용을 예측할 수 없다.

## 비용

깊은 모드 + 두 신호가 다 잡히면 `/sdd:run` 한 번이 spec 3 + implement 3 + review 4 =
**10개 서브에이전트**를 부르고, 리뷰가 `changes-requested`면 implement·review를 최대
2회 더 돈다. 경량 모드는 3개다. 시작 전에 `depth`와 `deepReasons`를 알리는 것은 선택이
아니라 규칙이다.
