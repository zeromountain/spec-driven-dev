#!/usr/bin/env python3
"""sdd — Spec-Driven Development 하네스의 결정론적 CLI.

모든 서브커맨드는 stdout에 JSON만 출력한다. 에이전트는 이 출력을 읽기만 하고
재계산하지 않는다 (숫자·경로 판정은 전부 이 스크립트가 한다).

stdlib만 사용한다 (외부 의존성 없음).
"""
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = REPO_ROOT / "templates"

REQUIRED_SECTIONS = [
    "목적",
    "배경",
    "비즈니스 규칙",
    "기능 요구사항",
    "비기능 요구사항",
    "인수 기준",
    "오류 케이스",
    "범위 밖",
]

DEFAULT_CONFIG = {
    "version": 1,
    "specsDir": "specs",
    "srcDirs": ["src"],
    "testDirs": ["tests"],
    "reviewsDir": ".sdd/reviews",
    "minCoverage": 0.9,
    "acPattern": r"AC-\d+",
    "alwaysWritable": ["AGENTS.md", "CLAUDE.md", ".sdd/**", "docs/**"],
}

DEFAULT_STATE = {
    "version": 1,
    "phase": "off",
    "enforce": False,
    "activeSpec": None,
    "pipelines": {},
    "activePipeline": None,
    "depth": "light",
    "updatedAt": None,
}

# 페이즈별 서브에이전트 구성. 경량 경로는 역할당 1명, 깊은 경로는 조사·작성·검토를
# 분리한다. security/perf 리뷰어는 깊이와 무관하게 신호(키워드)가 잡힐 때만 붙는다.
AGENT_ROSTER = {
    "light": {
        "spec": ["spec-architect"],
        "implement": ["software-engineer"],
        "review": ["spec-reviewer"],
    },
    "deep": {
        "spec": ["spec-researcher", "spec-architect", "spec-auditor"],
        "implement": ["impl-planner", "software-engineer", "test-engineer"],
        "review": ["spec-reviewer", "code-reviewer"],
    },
}

# 리포트에 항상 네 줄이 다 나와야 "실행되지 않음"과 "문제 없음"이 구분된다.
REVIEWER_CONCERNS = {
    "spec-reviewer": "명세 준수·AC 커버리지·스펙 밖 구현",
    "code-reviewer": "가독성·복잡도·중복·에러 처리",
    "security-reviewer": "입력 검증·인가·시크릿·인젝션",
    "perf-reviewer": "N+1·복잡도·재계산·경계 없는 로딩",
}

# "복잡해 보인다"를 모델이 판단하면 매번 달라진다 — 임계값을 여기 고정한다.
DEPTH_THRESHOLDS = {"acCount": 8, "ecCount": 5, "warningCount": 3}

SECURITY_HINT_RE = re.compile(
    r"(인증|인가|권한|로그인|회원가입|비밀번호|패스워드|토큰|세션|쿠키|암호화|복호화|"
    r"해싱|개인정보|주민등록|결제|카드번호|시크릿|비밀키|파일\s*업로드|SQL|XSS|CSRF|"
    r"auth|oauth|jwt|secret|password|token|credential)",
    re.IGNORECASE,
)
PERF_HINT_RE = re.compile(
    r"(성능|지연|레이턴시|응답\s*시간|처리량|대용량|대량|배치|동시성|동시\s*접속|병렬|"
    r"캐시|캐싱|인덱스|페이지네이션|무한\s*스크롤|스트리밍|N\+1|초당|메모리\s*사용|"
    r"throughput|latency|timeout|타임아웃|"
    # "응답은 3초 이내" 처럼 수치로 표현된 지연 요구도 성능 신호다.
    r"\d+\s*(?:초|ms|밀리초|분)\s*(?:이내|이하|안에))",
    re.IGNORECASE,
)

# 인수 기준(AC)은 체크박스 항목, 오류 케이스(EC)는 일반 불릿 항목이다.
AC_LINE_RE = re.compile(r"^-\s*\[[ xX]\]\s*(.*)$")
EC_LINE_RE = re.compile(r"^-\s+(?!\[[ xX]\])(.*)$")


def _id_re(prefix: str) -> re.Pattern:
    return re.compile(rf"^\*\*{prefix}-(\d+)\*\*\s*[:\-]?\s*(.*)$")


# "~한다."처럼 서술형이면 무엇이든 통과하던 과거 패턴은 검사로서 의미가 없었다.
# 조건/의무를 실제로 표현하는 어미만 남긴다.
CONDITION_HINT_RE = re.compile(
    r"(해야\s*한다|되어야|이어야\s*한다|하면|경우에는|불가하다|안\s*된다|없어야|있어야)"
)
# 아키텍트 프롬프트가 금지하는 모호 표현. 검사기가 같은 규칙을 뒷받침한다.
VAGUE_RE = re.compile(
    r"(빠르게|적절히|적당히|안전하게|잘\s|효율적으로|사용자\s*친화적|등등|필요시|알아서)"
)
PLACEHOLDER_RE = re.compile(r"\{\{[^{}\n]{1,120}\}\}")
FENCE_RE = re.compile(r"^(\s*)(```|~~~)")
SPEC_FILENAME_RE = re.compile(r"^spec-v(\d+)\.md$")

SPECS_README = """# specs/

이 디렉터리는 Spec-Driven Development의 소스 오브 트루스다. 각 기능은
`specs/<slug>/spec-v<N>.md`로 버전 관리되며, `sdd` 플러그인의 `spec-architect`
서브에이전트만 이 디렉터리에 쓴다.

- 명세는 8개 섹션을 모두 포함하고, 인수 기준은 `AC-1`부터, 오류 케이스는 `EC-1`부터
  연속된 ID를 갖는다.
- 동작이 바뀌면 새 버전(`spec-v<N+1>.md`)을 만든다. 오탈자·명확화는 제자리에서 고친다.

전체 규칙(섹션 정의·ID 형식·검증 에러 목록·버저닝)은 `sdd` 플러그인의
`skills/spec-driven-dev/references/spec-format.md`가 정본이다.
"""


# ---------------------------------------------------------------------------
# 공용 유틸
# ---------------------------------------------------------------------------

def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_config(root: Path) -> dict:
    cfg = dict(DEFAULT_CONFIG)
    stored = read_json(root / ".sdd" / "config.json")
    if stored:
        cfg.update(stored)
    return cfg


def load_state(root: Path) -> dict:
    state = read_json(root / ".sdd" / "state.json")
    return state if state else dict(DEFAULT_STATE)


def fill_template(name: str, values: dict) -> str:
    """templates/<name>의 `{{key}}`만 치환한다. 채우지 않은 키는 그대로 남아
    validate가 미기입으로 잡아낸다."""
    text = (TEMPLATES_DIR / name).read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def resolve_slug(root: Path, explicit):
    """명시 슬러그 → state.activeSpec 순으로 대상 명세를 정한다."""
    if explicit:
        return explicit
    return load_state(root).get("activeSpec")


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFC", text).strip().lower()
    text = re.sub(r"[\s_]+", "-", text)
    # ASCII 영문·숫자, 한글 음절/자모, 하이픈만 남긴다
    text = re.sub(r"[^a-z0-9\-가-힣ㄱ-ㆎ]", "", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or "feature"


def to_project_relative(file_path: str, project_root: Path):
    """file_path를 project_root 기준 POSIX 상대경로로 정규화한다.
    심링크·`..`는 실제 경로로 해석한 뒤 판정한다. project_root 밖이면 None."""
    p = Path(file_path)
    if not p.is_absolute():
        p = project_root / p
    try:
        resolved = p.resolve()
    except OSError:
        resolved = p
    try:
        root_resolved = project_root.resolve()
    except OSError:
        root_resolved = project_root
    try:
        rel = resolved.relative_to(root_resolved)
    except ValueError:
        return None
    return rel.as_posix()


# ---------------------------------------------------------------------------
# 명세 파싱 / 검증
# ---------------------------------------------------------------------------

def strip_code_fences(text: str) -> str:
    """펜스 코드 블록의 내용을 빈 줄로 치환한다 (줄 수는 보존).

    명세가 마크다운 형식 자체를 예시로 담을 수 있으므로, 펜스 안의 `## `나
    `{{...}}`를 실제 섹션·플레이스홀더로 오인하면 안 된다."""
    out = []
    fence = None  # 열려 있는 펜스 마커
    for line in text.splitlines():
        m = FENCE_RE.match(line)
        if fence is None:
            if m:
                fence = m.group(2)
                out.append("")
                continue
            out.append(line)
        else:
            out.append("")
            if m and m.group(2) == fence:
                fence = None
    return "\n".join(out)


def parse_frontmatter(text: str):
    """(fields, error). `---` 블록이 없으면 (None, 사유)."""
    if not text.startswith("---\n"):
        return None, "명세는 '---' YAML 프론트매터로 시작해야 한다"
    end = text.find("\n---", 4)
    if end == -1:
        return None, "프론트매터가 닫히지 않았다 (닫는 '---' 없음)"
    fields = {}
    for line in text[4:end].splitlines():
        if not line.strip() or line.strip().startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields, None


def find_duplicate_sections(text: str):
    header_re = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
    seen, dups = set(), []
    for m in header_re.finditer(strip_code_fences(text)):
        name = m.group(1).strip()
        if name in seen and name not in dups:
            dups.append(name)
        seen.add(name)
    return dups


def parse_sections(text: str) -> dict:
    text = strip_code_fences(text)
    header_re = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
    matches = list(header_re.finditer(text))
    sections = {}
    for i, m in enumerate(matches):
        name = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[name] = text[start:end].strip()
    return sections


def extract_id_items(section_text: str, prefix: str):
    """(id:int|None, sentence:str, malformed:bool) 리스트. malformed면 ID 파싱 실패."""
    line_re = AC_LINE_RE if prefix == "AC" else EC_LINE_RE
    id_re = _id_re(prefix)
    items = []
    for line in section_text.splitlines():
        m = line_re.match(line.strip())
        if not m:
            continue
        content = m.group(1).strip()
        id_m = id_re.match(content)
        if not id_m:
            items.append((None, content, True))
            continue
        items.append((int(id_m.group(1)), id_m.group(2).strip(), False))
    return items


def extract_ac_items(ac_section_text: str):
    """하위호환 별칭 — 인수 기준 전용."""
    return extract_id_items(ac_section_text, "AC")


def _validate_id_section(section_text: str, prefix: str, section_name: str,
                         errors: list, warnings: list, check_quality: bool):
    """AC/EC 공통 검증. 수집된 ID 문자열 리스트를 반환한다."""
    items = extract_id_items(section_text, prefix)
    if not items:
        errors.append({"section": section_name,
                       "message": f"{prefix} 항목이 하나도 없다"})
        return []

    ids, nums = [], []
    for num, sentence, malformed in items:
        if malformed:
            errors.append({
                "section": section_name,
                "message": f"{prefix} ID가 없는 항목: '{sentence[:40]}'",
            })
            continue
        nums.append(num)
        ids.append(f"{prefix}-{num}")
        if not sentence:
            errors.append({"section": section_name,
                           "message": f"{prefix}-{num}에 내용이 없다"})
        elif check_quality:
            if not CONDITION_HINT_RE.search(sentence):
                warnings.append({
                    "section": section_name,
                    "message": f"{prefix}-{num} 문장에 검증 가능한 조건 표현이 없다: "
                               f"'{sentence[:40]}'",
                })
            if VAGUE_RE.search(sentence):
                warnings.append({
                    "section": section_name,
                    "message": f"{prefix}-{num} 문장이 모호하다 — 숫자·조건으로 "
                               f"구체화하라: '{sentence[:40]}'",
                })

    if nums:
        if len(set(nums)) != len(nums):
            errors.append({"section": section_name,
                           "message": f"{prefix} 번호가 중복된다"})
        if sorted(set(nums)) != list(range(1, max(nums) + 1)):
            errors.append({"section": section_name,
                           "message": f"{prefix} 번호가 1부터 연속되지 않는다"})
    return ids


def _validate_frontmatter(text: str, path, errors: list):
    fields, err = parse_frontmatter(text)
    if err:
        errors.append({"section": "frontmatter", "message": err})
        return
    for key in ("feature", "version", "status"):
        if key not in fields:
            errors.append({"section": "frontmatter",
                           "message": f"프론트매터에 '{key}'가 없다"})
    if path is None:
        return

    p = Path(path)
    m = SPEC_FILENAME_RE.match(p.name)
    if m and "version" in fields:
        if fields["version"] != m.group(1):
            errors.append({
                "section": "frontmatter",
                "message": f"프론트매터 version={fields['version']} 이 파일명 "
                           f"{p.name}(v{m.group(1)})과 다르다",
            })
    if "feature" in fields and p.parent.name:
        expected = unicodedata.normalize("NFC", p.parent.name)
        actual = unicodedata.normalize("NFC", fields["feature"])
        if actual != expected:
            errors.append({
                "section": "frontmatter",
                "message": f"프론트매터 feature='{fields['feature']}' 가 디렉터리 "
                           f"'{p.parent.name}' 과 다르다",
            })


def validate_spec(text: str, path=None) -> dict:
    """명세 구조를 검증한다.

    path가 주어지면 프론트매터의 version·feature를 파일명·디렉터리와 교차 검증한다."""
    errors: list = []
    warnings: list = []

    _validate_frontmatter(text, path, errors)

    body = strip_code_fences(text)
    sections = parse_sections(text)

    for name in REQUIRED_SECTIONS:
        if name not in sections:
            errors.append({"section": name, "message": f"필수 섹션 '## {name}'이 없다"})

    for dup in find_duplicate_sections(text):
        errors.append({"section": dup,
                       "message": f"'## {dup}' 섹션이 두 번 이상 나온다 — 뒤의 것이 "
                                  "앞의 것을 덮어써 조용히 누락된다"})

    # 미기입 템플릿을 구현 단계로 넘기지 않기 위한 핵심 검사.
    placeholders = sorted({m.group(0) for m in PLACEHOLDER_RE.finditer(body)})
    if placeholders:
        where = [n for n, t in sections.items() if PLACEHOLDER_RE.search(t)]
        errors.append({
            "section": ", ".join(where) if where else "문서 전체",
            "message": f"채워지지 않은 템플릿 플레이스홀더가 {len(placeholders)}개 남아 "
                       f"있다: {', '.join(placeholders[:5])}"
                       + (" …" if len(placeholders) > 5 else ""),
        })

    ac_ids = _validate_id_section(
        sections.get("인수 기준", ""), "AC", "인수 기준",
        errors, warnings, check_quality=True,
    ) if "인수 기준" in sections else []

    ec_ids = _validate_id_section(
        sections.get("오류 케이스", ""), "EC", "오류 케이스",
        errors, warnings, check_quality=False,
    ) if "오류 케이스" in sections else []

    if "범위 밖" in sections and not sections["범위 밖"].strip():
        warnings.append({"section": "범위 밖", "message": "범위 밖 섹션이 비어 있다"})

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "acIds": ac_ids,
        "ecIds": ec_ids,
    }


def extract_ac_ids(text: str):
    sections = parse_sections(text)
    if "인수 기준" not in sections:
        return []
    return [f"AC-{num}" for num, _s, bad
            in extract_id_items(sections["인수 기준"], "AC") if not bad]


# ---------------------------------------------------------------------------
# 추적성 (trace)
# ---------------------------------------------------------------------------

TEXT_EXCLUDE_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".woff", ".woff2",
    ".ico", ".lock", ".pyc",
}


def find_ac_tags_in_tests(test_dirs, ac_pattern: str, project_root: Path):
    pattern = re.compile(ac_pattern)
    hits: dict[str, list[str]] = {}
    for td in test_dirs:
        base = project_root / td
        if not base.exists():
            continue
        for f in sorted(base.rglob("*")):
            if not f.is_file() or f.suffix.lower() in TEXT_EXCLUDE_SUFFIXES:
                continue
            try:
                lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            for i, line in enumerate(lines, start=1):
                for m in pattern.finditer(line):
                    hits.setdefault(m.group(0), []).append(
                        f"{f.relative_to(project_root).as_posix()}:{i}"
                    )
    return hits


def trace_spec(spec_text: str, test_dirs, ac_pattern: str, project_root: Path) -> dict:
    ac_ids = extract_ac_ids(spec_text)
    hits = find_ac_tags_in_tests(test_dirs, ac_pattern, project_root)
    matrix = []
    for ac in ac_ids:
        tests = hits.get(ac, [])
        matrix.append({"ac": ac, "tests": tests, "covered": bool(tests)})
    covered = sum(1 for m in matrix if m["covered"])
    result = {
        "matrix": matrix,
        "uncovered": [m["ac"] for m in matrix if not m["covered"]],
        "coverage": (covered / len(matrix)) if matrix else 0.0,
    }
    total_hits = sum(len(v) for v in hits.values())
    if total_hits == 0 and ac_ids:
        result["convention"] = "absent"
        result["note"] = (
            "태깅된 테스트가 하나도 없다 — AC 태깅 규약이 아직 도입되지 않았을 수 있다. "
            "실패가 아니라 경고로만 취급한다."
        )
    return result


# ---------------------------------------------------------------------------
# 깊이 판정 (어떤 서브에이전트를 부를지)
# ---------------------------------------------------------------------------

def depth_haystack(spec_text=None, feature_text=None) -> str:
    """신호 키워드를 찾을 본문. `범위 밖` 섹션과 미기입 플레이스홀더는 제외한다.

    - "인증 기능은 다루지 않는다"는 보안 신호가 아니라 그 반대다 — 명시적으로 범위에서
      뺀 단어까지 스캔하면 제외 선언이 리뷰어를 부르는 역설이 생긴다.
    - 템플릿의 `{{성능/보안/호환성 등...}}` 같은 안내문은 명세의 내용이 아니라 빈칸이다.
      이걸 세면 갓 생성된 빈 명세가 자기 보일러플레이트 때문에 deep 이 된다."""
    parts = []
    if spec_text:
        sections = parse_sections(spec_text)
        source = list(sections.items()) if sections else [("", spec_text)]
        parts.extend(body for name, body in source if name != "범위 밖")
    if feature_text:
        parts.append(feature_text)
    return PLACEHOLDER_RE.sub(" ", "\n".join(parts))


def decide_depth(spec_text=None, feature_text=None, force=None) -> dict:
    """light/deep 과 페이즈별 서브에이전트 구성을 결정한다 (순수 함수).

    명세가 이미 있으면 명세 본문이 근거가 되고, 아직 없으면(spec 단계 진입 시점)
    기능 설명 문자열만으로 판정한다. 모델이 "이건 복잡해 보인다"로 정하지 않도록
    임계값·키워드는 전부 이 모듈에 있다."""
    haystack = depth_haystack(spec_text, feature_text)

    ac_count = ec_count = warning_count = 0
    if spec_text:
        v = validate_spec(spec_text)
        ac_count = len(v["acIds"])
        ec_count = len(v["ecIds"])
        warning_count = len(v["warnings"])

    security_hits = sorted({m.group(0) for m in SECURITY_HINT_RE.finditer(haystack)})
    perf_hits = sorted({m.group(0) for m in PERF_HINT_RE.finditer(haystack)})

    deep_reasons = []
    if ac_count >= DEPTH_THRESHOLDS["acCount"]:
        deep_reasons.append(
            f"인수 기준이 {ac_count}개로 임계값 {DEPTH_THRESHOLDS['acCount']}개 이상이다")
    if ec_count >= DEPTH_THRESHOLDS["ecCount"]:
        deep_reasons.append(
            f"오류 케이스가 {ec_count}개로 임계값 {DEPTH_THRESHOLDS['ecCount']}개 이상이다")
    if warning_count >= DEPTH_THRESHOLDS["warningCount"]:
        deep_reasons.append(
            f"명세 검증 경고가 {warning_count}개로 임계값 "
            f"{DEPTH_THRESHOLDS['warningCount']}개 이상이다")
    if security_hits:
        deep_reasons.append(f"보안 신호가 잡혔다: {', '.join(security_hits[:5])}")
    if perf_hits:
        deep_reasons.append(f"성능 신호가 잡혔다: {', '.join(perf_hits[:5])}")

    depth = "deep" if deep_reasons else "light"
    forced_to = force if force in ("light", "deep") else None
    if forced_to:
        depth = forced_to

    roster = {phase: list(names) for phase, names in AGENT_ROSTER[depth].items()}
    # 신호 기반 리뷰어는 깊이와 무관하다 — 한 줄짜리 인증 수정에도 보안 리뷰는 붙는다.
    if security_hits:
        roster["review"].append("security-reviewer")
    if perf_hits:
        roster["review"].append("perf-reviewer")

    return {
        "depth": depth,
        "forcedTo": forced_to,
        "signals": {
            "acCount": ac_count,
            "ecCount": ec_count,
            "warningCount": warning_count,
            "securityHits": security_hits,
            "perfHits": perf_hits,
        },
        "thresholds": dict(DEPTH_THRESHOLDS),
        "deepReasons": deep_reasons,
        "agents": roster,
    }


def depth_for_slug(root: Path, slug, feature=None, force=None) -> dict:
    """대상 명세가 있으면 그 본문으로, 없으면 기능 설명으로 깊이를 정한다."""
    config = load_config(root)
    specs_dir = root / config["specsDir"]
    spec_text = None
    version = find_latest_version(specs_dir, slug) if slug else 0
    if version:
        spec_text = (specs_dir / slug / f"spec-v{version}.md").read_text(encoding="utf-8")
    result = decide_depth(spec_text, feature, force)
    result["slug"] = slug
    result["version"] = version or None
    result["basedOn"] = "spec" if spec_text else ("feature" if feature else "none")
    return result


# ---------------------------------------------------------------------------
# 페이즈 게이트 (hooks/phase_gate.py 가 그대로 재사용하는 순수 함수)
# ---------------------------------------------------------------------------

def matches_pattern(rel_path: str, pattern: str) -> bool:
    if pattern.endswith("/**"):
        base = pattern[:-3].strip("/")
        return rel_path == base or rel_path.startswith(base + "/")
    if "*" in pattern:
        return fnmatch.fnmatch(rel_path, pattern)
    return rel_path == pattern.strip("/")


def _under(rel_path: str, base: str) -> bool:
    base = base.strip("/")
    return rel_path == base or rel_path.startswith(base + "/")


def evaluate_gate(phase: str, rel_path: str, config: dict):
    """rel_path(프로젝트 루트 기준 POSIX 상대경로)의 쓰기가 phase에서 허용되는지 판정한다.
    허용이면 None, 차단이면 사람이 읽을 사유 문자열을 반환한다."""
    if not phase or phase == "off":
        return None

    specs_dir = config.get("specsDir", "specs")
    src_dirs = config.get("srcDirs", ["src"])
    test_dirs = config.get("testDirs", ["tests"])
    reviews_dir = config.get("reviewsDir", ".sdd/reviews")
    always = config.get("alwaysWritable", DEFAULT_CONFIG["alwaysWritable"])

    for pat in always:
        if matches_pattern(rel_path, pat):
            return None

    if phase == "spec":
        if _under(rel_path, specs_dir):
            return None
        if rel_path.endswith(".md"):
            return None
        return (
            f"SDD 페이즈 게이트: 현재 phase=spec 이므로 '{rel_path}' 쓰기는 차단된다. "
            f"Spec Architect는 {specs_dir}/ 안에서만 쓸 수 있다. 명세를 먼저 확정하고 "
            "/sdd:implement 로 페이즈를 넘긴 뒤 다시 시도하라. 게이트를 끄려면 사용자에게 "
            "/sdd:phase off 를 요청하라."
        )

    if phase == "implement":
        if _under(rel_path, specs_dir):
            if rel_path.endswith("/tasks.md") or rel_path == "tasks.md":
                return None
            return (
                f"SDD 페이즈 게이트: 현재 phase=implement 이므로 '{rel_path}' ({specs_dir}/ 안) "
                "쓰기는 차단된다. Software Engineer는 명세를 수정하지 않는다 — 동작을 바꿔야 "
                "한다면 스펙 변경을 요청하라. tasks.md 갱신은 허용된다."
            )
        return None

    if phase == "review":
        if _under(rel_path, reviews_dir):
            return None
        if _under(rel_path, specs_dir) or any(_under(rel_path, d) for d in src_dirs) or any(
            _under(rel_path, d) for d in test_dirs
        ):
            return (
                f"SDD 페이즈 게이트: 현재 phase=review 이므로 '{rel_path}' 쓰기는 차단된다. "
                f"Review Agent는 명세·코드·테스트를 수정하지 않고 {reviews_dir}/ 에 리포트만 "
                "남긴다. 수정이 필요하면 /sdd:implement 로 되돌아가라."
            )
        return None

    return None


def guard_violations(changed_files, phase: str, config: dict):
    violations = []
    for f in changed_files:
        reason = evaluate_gate(phase, f, config)
        if reason:
            violations.append({"file": f, "reason": reason})
    return violations


def git_changed_files(root: Path, base: str = "HEAD"):
    files: set[str] = set()
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "diff", "--name-only", base],
            capture_output=True, text=True, check=False,
        ).stdout
        files.update(line.strip() for line in out.splitlines() if line.strip())
    except FileNotFoundError:
        pass
    try:
        out2 = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            capture_output=True, text=True, check=False,
        ).stdout
        for line in out2.splitlines():
            if len(line) > 3:
                files.add(line[3:].strip().strip('"'))
    except FileNotFoundError:
        pass
    return sorted(files)


# ---------------------------------------------------------------------------
# 명세 버저닝
# ---------------------------------------------------------------------------

VERSION_RE = re.compile(r"^spec-v(\d+)\.md$")


def find_latest_version(specs_dir: Path, slug: str) -> int:
    d = specs_dir / slug
    if not d.exists():
        return 0
    versions = [int(m.group(1)) for f in d.glob("spec-v*.md") if (m := VERSION_RE.match(f.name))]
    return max(versions) if versions else 0


# ---------------------------------------------------------------------------
# AGENTS.md 병합
# ---------------------------------------------------------------------------

AGENTS_MARKER = "## Spec-Driven Development"


def render_agents_section() -> str:
    return (TEMPLATES_DIR / "AGENTS.sdd.md").read_text(encoding="utf-8").rstrip() + "\n"


def replace_marked_section(text: str, marker: str, new_section: str) -> str:
    idx = text.index(marker)
    after = text[idx + len(marker):]
    next_header = re.search(r"\n##\s+", after)
    end = idx + len(marker) + (next_header.start() if next_header else len(after))
    tail = text[end:].lstrip("\n")
    head = text[:idx].rstrip("\n")
    body = new_section.rstrip("\n")
    pieces = [p for p in (head, body, tail) if p]
    return "\n\n".join(pieces) + "\n"


def merge_agents_md(root: Path) -> str:
    section = render_agents_section()
    for name in ("AGENTS.md", "CLAUDE.md"):
        p = root / name
        if p.exists():
            text = p.read_text(encoding="utf-8")
            if AGENTS_MARKER in text:
                p.write_text(replace_marked_section(text, AGENTS_MARKER, section), encoding="utf-8")
                return f"{name}:replaced"
            p.write_text(text.rstrip("\n") + "\n\n" + section, encoding="utf-8")
            return f"{name}:appended"
    (root / "AGENTS.md").write_text("# AGENTS.md\n\n" + section, encoding="utf-8")
    return "AGENTS.md:created"


# ---------------------------------------------------------------------------
# 서브커맨드
# ---------------------------------------------------------------------------

def cmd_init(args) -> dict:
    root = Path(args.path).resolve()
    created, skipped = [], []

    def track(p: Path, existed: bool):
        rel = str(p.relative_to(root))
        (skipped if existed else created).append(rel)

    specs_dir = root / (args.specs or DEFAULT_CONFIG["specsDir"])
    sdd_dir = root / ".sdd"
    reviews_dir = sdd_dir / (DEFAULT_CONFIG["reviewsDir"].split("/", 1)[1] if "/" in DEFAULT_CONFIG["reviewsDir"] else "reviews")

    for d in (specs_dir, sdd_dir, reviews_dir):
        existed = d.exists()
        d.mkdir(parents=True, exist_ok=True)
        track(d, existed)

    specs_readme = specs_dir / "README.md"
    existed = specs_readme.exists()
    if not existed:
        specs_readme.write_text(SPECS_README, encoding="utf-8")
    track(specs_readme, existed)

    state_path = sdd_dir / "state.json"
    if not state_path.exists():
        write_json(state_path, {
            "version": 1, "phase": "off", "enforce": bool(args.enforce),
            "activeSpec": None, "updatedAt": now_iso(),
        })
        created.append(str(state_path.relative_to(root)))
    else:
        if args.enforce:
            st = load_state(root)
            st["enforce"] = True
            st["updatedAt"] = now_iso()
            write_json(state_path, st)
        skipped.append(str(state_path.relative_to(root)))

    config_path = sdd_dir / "config.json"
    if not config_path.exists():
        cfg = dict(DEFAULT_CONFIG)
        if args.specs:
            cfg["specsDir"] = args.specs
        if args.src:
            cfg["srcDirs"] = [s.strip() for s in args.src.split(",") if s.strip()]
        if args.tests:
            cfg["testDirs"] = [s.strip() for s in args.tests.split(",") if s.strip()]
        write_json(config_path, cfg)
        created.append(str(config_path.relative_to(root)))
    else:
        skipped.append(str(config_path.relative_to(root)))

    gitignore_path = sdd_dir / ".gitignore"
    if not gitignore_path.exists():
        gitignore_path.write_text("state.json\n", encoding="utf-8")
        created.append(str(gitignore_path.relative_to(root)))
    else:
        skipped.append(str(gitignore_path.relative_to(root)))

    agents_result = merge_agents_md(root)

    return {"created": created, "skipped": skipped, "agentsMd": agents_result}


def create_spec_file(root: Path, feature: str, slug=None) -> dict:
    """다음 버전의 빈 명세 파일을 만든다. `new` 커맨드와 파이프라인이 공유한다."""
    config = load_config(root)
    specs_dir = root / config["specsDir"]
    slug = slugify(slug) if slug else slugify(feature)
    version = find_latest_version(specs_dir, slug) + 1
    feature_dir = specs_dir / slug
    feature_dir.mkdir(parents=True, exist_ok=True)
    spec_path = feature_dir / f"spec-v{version}.md"

    # 문서 전체 substring 치환은 본문을 오염시킬 수 있으므로 채울 키만 명시적으로 넘긴다.
    content = fill_template("spec.md", {
        "slug": slug,
        "version": str(version),
        "createdAt": now_iso(),
        "제목": feature,
    })
    spec_path.write_text(content, encoding="utf-8")

    return {
        "path": str(spec_path.relative_to(root)),
        "version": version,
        "slug": slug,
        "note": "플레이스홀더를 모두 채우기 전에는 validate가 실패한다 (의도된 동작).",
    }


def cmd_new(args) -> dict:
    root = Path(args.path).resolve()
    return create_spec_file(root, args.feature, getattr(args, "slug", None))


TASKS_VERSION_RE = re.compile(r"spec-v(\d+)\s*기준")


def ensure_tasks(root: Path, slug) -> dict:
    """최신 명세의 AC를 읽어 tasks.md를 생성한다 (AC 대응표가 미리 채워진 상태로).

    이미 있으면 그대로 두되, 그 tasks.md가 **이전 버전 명세** 기준이면 다시 만든다 —
    명세가 새 버전으로 올라간 뒤 낡은 AC 대응표를 구현자에게 넘기지 않기 위해서다.
    """
    config = load_config(root)
    specs_dir = root / config["specsDir"]
    if not slug:
        return {"created": False, "reason": "대상 명세가 지정되지 않았다"}

    version = find_latest_version(specs_dir, slug)
    if version == 0:
        return {"created": False, "reason": f"spec '{slug}' 를 찾을 수 없다"}

    spec_path = specs_dir / slug / f"spec-v{version}.md"
    ac_ids = extract_ac_ids(spec_path.read_text(encoding="utf-8"))
    tasks_path = specs_dir / slug / "tasks.md"
    rel = str(tasks_path.relative_to(root))

    if tasks_path.exists():
        m = TASKS_VERSION_RE.search(tasks_path.read_text(encoding="utf-8"))
        if m and int(m.group(1)) == version:
            return {"created": False, "reason": "이미 존재한다",
                    "path": rel, "acIds": ac_ids, "version": version}
        stale = int(m.group(1)) if m else None
        rows = _task_rows(ac_ids)
        tasks_path.write_text(
            fill_template("tasks.md", {"slug": slug, "version": str(version), "acRows": rows}),
            encoding="utf-8",
        )
        return {"created": True, "refreshed": True, "staleVersion": stale,
                "path": rel, "acIds": ac_ids, "version": version}

    tasks_path.write_text(
        fill_template("tasks.md",
                      {"slug": slug, "version": str(version), "acRows": _task_rows(ac_ids)}),
        encoding="utf-8",
    )
    return {"created": True, "path": rel, "acIds": ac_ids, "version": version}


def _task_rows(ac_ids) -> str:
    return "\n".join(f"- [ ] {ac} → {{{{구현할 파일/모듈}}}}" for ac in ac_ids) \
        or "- [ ] {{인수 기준이 없다 — 명세를 먼저 확인하라}}"


def cmd_tasks(args) -> dict:
    root = Path(args.path).resolve()
    return ensure_tasks(root, resolve_slug(root, getattr(args, "slug", None)))


def build_review_report(root: Path, slug, force=None) -> dict:
    """trace·depth 결과를 반영한 리뷰 리포트 골격을 .sdd/reviews/ 에 만든다."""
    config = load_config(root)
    specs_dir = root / config["specsDir"]
    if not slug:
        return {"created": False, "reason": "대상 명세가 지정되지 않았다"}

    version = find_latest_version(specs_dir, slug)
    if version == 0:
        return {"created": False, "reason": f"spec '{slug}' 를 찾을 수 없다"}

    spec_path = specs_dir / slug / f"spec-v{version}.md"
    text = spec_path.read_text(encoding="utf-8")
    v = validate_spec(text, path=spec_path)
    tr = trace_spec(text, config["testDirs"], config["acPattern"], root)
    covered = {m["ac"]: m for m in tr["matrix"]}

    ac_rows = "\n".join(
        f"| {ac} | {{{{✅/❌}}}} | {'✅' if covered.get(ac, {}).get('covered') else '❌'} | "
        f"{', '.join(covered.get(ac, {}).get('tests', [])) or '—'} |"
        for ac in v["acIds"]
    ) or "| — | — | — | 인수 기준 없음 |"
    ac_table = "| AC | 구현됨 | 테스트됨 | 근거 |\n|---|---|---|---|\n" + ac_rows

    ec_rows = "\n".join(f"| {ec} | {{{{✅/❌}}}} | {{{{비고}}}} |" for ec in v["ecIds"]) \
        or "| — | — | 오류 케이스 없음 |"
    ec_table = "| EC | 처리됨 | 비고 |\n|---|---|---|\n" + ec_rows

    state = load_state(root)
    violations = guard_violations(git_changed_files(root), state.get("phase", "off"), config)
    guard_rows = "\n".join(f"- `{x['file']}` — {x['reason'][:80]}" for x in violations) \
        or "- 없음"

    # 어떤 리뷰어가 붙는지는 depth 가 정한다 — 리포트가 그 목록을 미리 담고 있어야
    # "실행되지 않은 리뷰어"와 "문제를 못 찾은 리뷰어"가 구분된다.
    depth = decide_depth(text, force=force)
    reviewers = depth["agents"]["review"]
    reviewer_rows = "| 리뷰어 | 관심사 | 판정 |\n|---|---|---|\n" + "\n".join(
        f"| `{name}` | {REVIEWER_CONCERNS.get(name, '—')} | "
        # 표 셀 안에서는 파이프를 쓸 수 없다 — 셀이 쪼개진다.
        + ("{{approved 또는 changes-requested}}" if name in reviewers else "실행되지 않음")
        + " |"
        for name in REVIEWER_CONCERNS
    )

    def section_for(name: str, hint: str) -> str:
        if name in reviewers:
            return "{{" + name + ": " + hint + "}}"
        return (f"이번 리뷰에서 `{name}`는 실행되지 않았다 "
                f"(깊이: {depth['depth']}, 해당 신호 없음). "
                "이 절의 공백은 '문제 없음'을 뜻하지 않는다.")

    reviews_dir = root / config["reviewsDir"]
    reviews_dir.mkdir(parents=True, exist_ok=True)
    seq = len(list(reviews_dir.glob(f"{slug}-v{version}-*.md"))) + 1
    out = reviews_dir / f"{slug}-v{version}-{seq}.md"
    out.write_text(fill_template("review-report.md", {
        "slug": slug,
        "version": str(version),
        "seq": str(seq),
        "specPath": str(spec_path.relative_to(root)),
        "depth": depth["depth"],
        "reviewerRows": reviewer_rows,
        "acRows": ac_table,
        "ecRows": ec_table,
        "guardRows": guard_rows,
        "codeReviewSection": section_for("code-reviewer", "가독성·복잡도·중복·에러 처리"),
        "securityReviewSection": section_for("security-reviewer", "입력 검증·인가·시크릿"),
        "perfReviewSection": section_for("perf-reviewer", "N+1·복잡도·경계 없는 로딩"),
    }), encoding="utf-8")

    return {"created": True, "path": str(out.relative_to(root)), "seq": seq,
            "version": version, "coverage": tr["coverage"],
            "uncovered": tr["uncovered"], "guardViolations": len(violations),
            "specPath": str(spec_path.relative_to(root)),
            "minCoverage": config.get("minCoverage"),
            "depth": depth["depth"], "reviewers": reviewers,
            "signals": depth["signals"]}


def cmd_review_report(args) -> dict:
    root = Path(args.path).resolve()
    return build_review_report(root, resolve_slug(root, getattr(args, "slug", None)),
                               force=getattr(args, "force", None))


def cmd_depth(args) -> dict:
    """이번 작업에 어떤 서브에이전트를 부를지 결정하고 state 에 기록한다."""
    root = Path(args.path).resolve()
    result = depth_for_slug(root, resolve_slug(root, getattr(args, "slug", None)),
                            getattr(args, "feature", None), getattr(args, "force", None))
    state_path = root / ".sdd" / "state.json"
    if state_path.exists():
        state = load_state(root)
        state["depth"] = result["depth"]
        state["updatedAt"] = now_iso()
        write_json(state_path, state)
        result["stateUpdated"] = True
    else:
        result["stateUpdated"] = False
    return result


def list_specs(root: Path) -> dict:
    config = load_config(root)
    specs_dir = root / config["specsDir"]
    reviews_dir = root / config["reviewsDir"]
    items = []
    if specs_dir.exists():
        for feature_dir in sorted(p for p in specs_dir.iterdir() if p.is_dir()):
            slug = feature_dir.name
            latest = find_latest_version(specs_dir, slug)
            if latest == 0:
                continue
            spec_path = feature_dir / f"spec-v{latest}.md"
            v = validate_spec(spec_path.read_text(encoding="utf-8"), path=spec_path)
            fm, _ = parse_frontmatter(spec_path.read_text(encoding="utf-8"))
            reviews = sorted(reviews_dir.glob(f"{slug}-v{latest}-*.md")) if reviews_dir.exists() else []
            items.append({
                "slug": slug,
                "version": latest,
                "path": str(spec_path.relative_to(root)),
                "status": (fm or {}).get("status", "unknown"),
                "valid": v["valid"],
                "acCount": len(v["acIds"]),
                "ecCount": len(v["ecIds"]),
                "errorCount": len(v["errors"]),
                "warningCount": len(v["warnings"]),
                "reviewCount": len(reviews),
            })
    return {"specs": items}


def cmd_list(args) -> dict:
    return list_specs(Path(args.path).resolve())


def cmd_status(args) -> dict:
    root = Path(args.path).resolve()
    state = load_state(root)
    config = load_config(root)
    listing = cmd_list(args)
    violations = []
    phase = state.get("phase", "off")
    if state.get("enforce") and phase not in (None, "off"):
        violations = guard_violations(git_changed_files(root), phase, config)
    return {
        "phase": phase,
        "enforce": bool(state.get("enforce")),
        "activeSpec": state.get("activeSpec"),
        "depth": state.get("depth", DEFAULT_STATE["depth"]),
        "specs": listing["specs"],
        "guardViolations": violations,
        "pipeline": pipeline_summary(load_pipelines(state).get(
            resolve_pipeline_slug(state, allow_active=True) or "")),
        "board": board(root),
    }


def transition_phase(root: Path, target: str, slug=None) -> dict:
    """페이즈를 전환한다. `/sdd:phase`와 파이프라인이 공유하는 단일 구현."""
    state = load_state(root)
    from_phase = state.get("phase", "off")
    blocked = False
    reasons = []

    # implement 전환은 항상 유효한 명세를 요구한다. --spec 이 없으면 activeSpec 으로
    # 폴백하고, 그마저 없으면 차단한다 — 검증을 통째로 건너뛰는 경로를 남기지 않는다.
    target_slug = slug if slug else state.get("activeSpec")
    if target == "implement":
        if not target_slug:
            blocked = True
            reasons.append(
                "대상 명세가 지정되지 않았다 — --spec 을 주거나 먼저 /sdd:spec 으로 "
                "명세를 만들어 activeSpec 을 설정하라"
            )
        else:
            config = load_config(root)
            specs_dir = root / config["specsDir"]
            latest = find_latest_version(specs_dir, target_slug)
            if latest == 0:
                blocked = True
                reasons.append(f"spec '{target_slug}' 를 찾을 수 없다")
            else:
                spec_path = specs_dir / target_slug / f"spec-v{latest}.md"
                v = validate_spec(spec_path.read_text(encoding="utf-8"), path=spec_path)
                if not v["valid"]:
                    blocked = True
                    reasons.append("spec 검증 실패: "
                                   + "; ".join(e["message"] for e in v["errors"]))

    if not blocked:
        state["phase"] = target
        state.setdefault("enforce", False)
        if target_slug:
            state["activeSpec"] = target_slug
        state["updatedAt"] = now_iso()
        write_json(root / ".sdd" / "state.json", state)

    return {"from": from_phase, "to": target, "blocked": blocked,
            "reasons": reasons, "activeSpec": target_slug}


def cmd_phase(args) -> dict:
    return transition_phase(Path(args.path).resolve(), args.target, args.spec)


def cmd_validate(args) -> dict:
    spec_path = Path(args.spec_path)
    return validate_spec(spec_path.read_text(encoding="utf-8"), path=spec_path)


def cmd_trace(args) -> dict:
    root = Path(args.path).resolve()
    config = load_config(root)
    spec_path = Path(args.spec_path)
    text = spec_path.read_text(encoding="utf-8")
    result = trace_spec(text, config["testDirs"], config["acPattern"], root)
    result["spec"] = str(spec_path)
    return result


def cmd_guard(args) -> dict:
    root = Path(args.path).resolve()
    config = load_config(root)
    state = load_state(root)
    phase = state.get("phase", "off")
    changed = git_changed_files(root, args.base)
    violations = guard_violations(changed, phase, config)
    return {"phase": phase, "base": args.base, "violations": violations}


# ---------------------------------------------------------------------------
# 파이프라인 상태머신 — run → next → advance
#
# 파이프라인의 "지금 어디까지 왔는가"는 대화 컨텍스트가 아니라 .sdd/state.json 의
# `pipeline` 레코드에만 산다. 오케스트레이터(스킬)는 두 가지만 한다: `next` 가 시키는
# 행동 하나를 하고, 그 결과를 `advance` 에 넘긴다. 페이즈 전환·명세 파일 생성·tasks.md·
# 리뷰 리포트 골격 같은 결정론적 작업은 전부 이 안에서 일어나므로 LLM이 단계 사이에
# 판단하거나 사용자가 명령을 다시 칠 일이 없다.
# ---------------------------------------------------------------------------

PIPELINE_STAGES = ("spec", "implement", "review")
DEFAULT_MAX_ATTEMPTS = 2
MAX_PIPELINE_STEPS = 24
MAX_HISTORY = 40
# 각 서브에이전트의 출력 JSON을 **그대로** advance에 넘기면 된다. 아래는 그중 전이를
# 실제로 결정하는 키만 추린 것이고, 나머지 키는 무시된다. 단계가 아니라 **에이전트**로
# 키를 잡는다 — 같은 단계 안에서도 전이를 결정하는 키가 역할마다 다르기 때문이다.
RESULT_SCHEMA = {
    "spec-researcher": {
        "contextPack": "객체 — 다음 단계 spec-architect 프롬프트에 그대로 실린다",
        "unknowns": "[string] — 코드를 읽어도 답이 안 나온 것 (질문 후보이지 질문 자체는 아니다)",
    },
    "spec-architect": {
        "openQuestions": "[string] — 있으면 파이프라인이 멈추고 사용자에게 묻는다 (없으면 빈 배열)",
    },
    "spec-auditor": {
        "verdict": "accepted | revision-requested — 필수",
        "acFindings": "[object] — revision-requested 일 때 아키텍트에게 그대로 되돌아간다",
        "missingErrorCases": "[object] — 같이 되돌아간다",
    },
    "impl-planner": {
        "tasks": "[object] — 구현자·테스트작성자 양쪽 프롬프트에 실린다",
        "testRunner": "객체 — {command, evidence}",
        "specChangeRequests": "[string] — 있으면 spec 단계로 되돌아가 새 버전을 만든다",
    },
    "software-engineer": {
        "filesChanged": "[string] — 리뷰어에게 전달된다",
        "testResult": {"passed": "int", "failed": "int", "raw": "string — 실패 시 핵심 출력"},
        "specChangeRequests": "[string] — 있으면 spec 단계로 되돌아가 새 버전을 만든다",
    },
    "test-engineer": {
        "testResult": {"passed": "int", "failed": "int", "raw": "string — 실패 시 핵심 출력"},
        "implementationDefects": "[object] — 있으면 구현자에게 되돌아간다 (테스트를 고치지 않는다)",
    },
    "_reviewer": {
        "verdict": "approved | changes-requested — 필수. 없으면 파이프라인이 멈춘다",
        "gaps": "[string] — changes-requested 일 때 구현자에게 그대로 전달된다",
        "findings": "[object] — severity high 만 자동 재시도를 유발한다",
    },
}


def result_schema_for(agent: str) -> dict:
    return RESULT_SCHEMA.get(agent) or RESULT_SCHEMA["_reviewer"]


def stage_roster(pipe: dict, stage: str):
    """이 단계에서 부를 에이전트 목록. 없으면 경량 기본값으로 떨어진다."""
    roster = (pipe.get("roster") or {}).get(stage)
    return list(roster) if roster else list(AGENT_ROSTER["light"][stage])


def current_agent(pipe: dict):
    roster = stage_roster(pipe, pipe.get("stage"))
    idx = pipe.get("agentIndex", 0)
    return roster[idx] if 0 <= idx < len(roster) else roster[-1]


def refresh_roster(root: Path, pipe: dict, force=None) -> dict:
    """단계에 진입할 때마다 깊이를 다시 판정한다 — spec 단계에서 light 였어도
    명세가 커졌으면 implement 에서 deep 이 될 수 있다."""
    d = depth_for_slug(root, pipe.get("slug"), pipe.get("feature"),
                       force or pipe.get("forcedDepth"))
    pipe["roster"] = d["agents"]
    pipe["depth"] = d["depth"]
    pipe["depthReasons"] = d["deepReasons"]
    pipe["depthSignals"] = d["signals"]
    return d


def _new_pipeline(feature: str, slug: str, max_attempts: int) -> dict:
    return {
        "feature": feature,
        "slug": slug,
        "stage": "spec",
        "status": "running",
        "agentIndex": 0,
        "roster": None,          # 단계 진입 시 refresh_roster 가 채운다
        "depth": None,
        "forcedDepth": None,
        "attempts": {"spec": 0, "specAudit": 0, "specRevision": 0,
                     "implement": 0, "review": 0},
        "maxAttempts": max_attempts,
        "steps": 0,
        "specPath": None,
        "specVersion": None,
        "tasksPath": None,
        "reviewPath": None,
        "carry": {
            "validateErrors": [],
            "openQuestions": [],
            "userAnswers": {},
            "specChangeRequests": [],
            "testResult": None,
            "testFailures": None,
            "reviewGaps": [],
            "implementNotes": None,
            "contextPack": None,
            "auditFindings": None,
            "plan": None,
            "filesChanged": [],
            "implementationDefects": [],
            "reviewVerdicts": [],
        },
        "history": [],
        "haltReason": None,
        "startedAt": now_iso(),
        "updatedAt": now_iso(),
    }


# ---------------------------------------------------------------------------
# 파이프라인 레지스트리 (기능마다 하나씩, 동시에 여러 개)
# ---------------------------------------------------------------------------
#
# 병렬성의 한계는 **페이즈 게이트가 프로젝트 전역 자원**이라는 데서 온다. 훅의 stdin에
# 호출자 정보가 없으므로 게이트는 "지금 이 프로젝트가 어떤 페이즈인가" 하나만 알 수 있다.
# 그래서 enforce:true 에서는 같은 페이즈에 있는 파이프라인끼리만 동시에 움직인다.
# enforce:false 에서는 게이트가 무동작이므로 페이즈가 서로 달라도 함께 돈다.

LIVE_STATUSES = ("running", "awaiting-user")


def load_pipelines(state: dict) -> dict:
    """{slug: pipeline}. 단일 `pipeline` 필드만 있던 구버전 상태를 그 자리에서 옮긴다."""
    pipes = state.get("pipelines")
    if not isinstance(pipes, dict):
        pipes = {}
    legacy = state.get("pipeline")
    if isinstance(legacy, dict) and legacy.get("slug") and legacy["slug"] not in pipes:
        pipes[legacy["slug"]] = legacy
    return pipes


def _store_pipelines(state: dict, pipes: dict) -> None:
    state["pipelines"] = pipes
    # 구버전 필드는 "지금 초점이 가 있는 것" 하나로만 유지한다 — 예전 리더가 읽어도
    # 최소한 하나는 보인다. 정본은 pipelines 다.
    focus = state.get("activePipeline")
    state["pipeline"] = pipes.get(focus) if focus in pipes else (
        next(iter(pipes.values()), None))


def live_pipelines(pipes: dict) -> dict:
    return {s: p for s, p in pipes.items() if p.get("status") in LIVE_STATUSES}


def resolve_pipeline_slug(state: dict, explicit=None, allow_active=False):
    """대상 파이프라인을 정한다. 명시 → (허용하면) activePipeline → 살아 있는 게 하나뿐.

    **여러 개가 살아 있을 때는 기본적으로 추측하지 않는다(None).** 특히 `advance` 는
    결과를 엉뚱한 파이프라인에 먹이면 그 기능의 상태가 남의 결과로 전이되고, 그건
    조용히 잘못된다. `allow_active` 는 표시용·재개용처럼 틀려도 파괴적이지 않은
    호출에서만 켠다."""
    pipes = load_pipelines(state)
    if explicit:
        return explicit if explicit in pipes else None
    live = live_pipelines(pipes)
    if len(live) == 1:
        return next(iter(live))
    active = state.get("activePipeline")
    if allow_active and active in pipes:
        return active
    if len(live) > 1:
        return None
    return active if active in pipes else next(iter(pipes), None)


def _persist_pipeline(root: Path, pipe: dict, focus: bool = True) -> None:
    """state.json을 새로 읽어 이 파이프라인만 갈아끼운다 — transition_phase가 중간에
    같은 파일을 쓰기 때문에 통째로 덮어쓰면 phase 변경이 유실된다."""
    pipe["updatedAt"] = now_iso()
    state = load_state(root)
    pipes = load_pipelines(state)
    pipes[pipe["slug"]] = pipe
    if focus:
        state["activePipeline"] = pipe["slug"]
    _store_pipelines(state, pipes)
    state["updatedAt"] = now_iso()
    write_json(root / ".sdd" / "state.json", state)


def _record(pipe: dict, event: str, **detail) -> None:
    entry = {"at": now_iso(), "stage": pipe.get("stage"), "event": event}
    entry.update({k: v for k, v in detail.items() if v not in (None, [], {})})
    pipe["history"].append(entry)
    del pipe["history"][:-MAX_HISTORY]


def _halt(pipe: dict, reason: str) -> None:
    pipe["status"] = "halted"
    pipe["haltReason"] = reason
    _record(pipe, "halted", reason=reason)


def _enter_stage(pipe: dict, stage: str, agent_index: int = 0) -> None:
    """단계 진입 시 그 단계에서 한 번만 만들어야 하는 산출물 포인터를 비운다 —
    `next`를 두 번 불러도 리뷰 리포트가 중복 생성되지 않게 하는 멱등성 장치.

    로스터 안의 위치(agentIndex)도 함께 되돌린다. 같은 단계로 되돌아오는 재시도는
    호출부가 agent_index 를 명시해 특정 역할부터 다시 시작시킬 수 있다."""
    pipe["stage"] = stage
    pipe["agentIndex"] = agent_index
    if stage != "review":
        pipe["reviewPath"] = None
        pipe["carry"]["reviewVerdicts"] = []
    _record(pipe, "stage-entered", stage=stage, agentIndex=agent_index)


def _advance_agent(pipe: dict) -> bool:
    """같은 단계 안에서 다음 역할로 넘어간다. 마지막이었으면 False."""
    roster = stage_roster(pipe, pipe["stage"])
    nxt = pipe.get("agentIndex", 0) + 1
    if nxt >= len(roster):
        return False
    pipe["agentIndex"] = nxt
    _record(pipe, "agent-advanced", agent=roster[nxt])
    return True


def set_spec_status(spec_path: Path, status: str) -> bool:
    """명세 프론트매터의 status만 바꾼다 (본문은 건드리지 않는다)."""
    text = spec_path.read_text(encoding="utf-8")
    _, err = parse_frontmatter(text)
    if err:
        return False
    end = text.find("\n---", 4)
    head, tail = text[:end], text[end:]
    if re.search(r"^status:.*$", head, re.MULTILINE):
        head = re.sub(r"^status:.*$", f"status: {status}", head, count=1, flags=re.MULTILINE)
    else:
        head = head.rstrip("\n") + f"\nstatus: {status}"
    spec_path.write_text(head + tail, encoding="utf-8")
    return True


def pipeline_summary(pipe) -> dict:
    if not pipe:
        return None
    return {
        "feature": pipe.get("feature"),
        "slug": pipe.get("slug"),
        "stage": pipe.get("stage"),
        "status": pipe.get("status"),
        "agent": current_agent(pipe) if pipe.get("stage") in PIPELINE_STAGES else None,
        "roster": (pipe.get("roster") or {}).get(pipe.get("stage")),
        "depth": pipe.get("depth"),
        "attempts": pipe.get("attempts"),
        "maxAttempts": pipe.get("maxAttempts"),
        "steps": pipe.get("steps"),
        "specPath": pipe.get("specPath"),
        "reviewPath": pipe.get("reviewPath"),
        "haltReason": pipe.get("haltReason"),
        "startedAt": pipe.get("startedAt"),
        "updatedAt": pipe.get("updatedAt"),
    }


def _tail_history(pipe: dict, n: int = 6):
    return pipe.get("history", [])[-n:]


# ---------------------------------------------------------------------------
# 스케줄러 — 지금 동시에 움직여도 되는 파이프라인은 무엇인가
# ---------------------------------------------------------------------------

def planned_files(pipe: dict) -> set:
    """impl-planner 가 확정한 '건드릴 파일' 집합. 계획이 없으면 빈 집합(=알 수 없음)."""
    plan = (pipe.get("carry") or {}).get("plan") or {}
    files = set()
    for task in plan.get("tasks") or []:
        if isinstance(task, dict):
            files.update(f for f in (task.get("files") or []) if isinstance(f, str))
    files.update(f for f in (pipe.get("carry") or {}).get("filesChanged") or []
                 if isinstance(f, str))
    return files


def implement_conflicts(pipe: dict, others) -> list:
    """구현 단계를 동시에 돌려도 되는지. 같은 파일을 건드리면 나중 쓰기가 앞을 덮는다.

    계획(impl-planner)이 있어야 파일 집합을 알 수 있다. 경량 모드처럼 계획이 없으면
    **모른다 = 겹칠 수 있다**로 보고 직렬화한다 — 추측으로 동시에 돌리지 않는다."""
    mine = planned_files(pipe)
    blockers = []
    for other in others:
        theirs = planned_files(other)
        if not mine or not theirs:
            blockers.append({"slug": other["slug"], "reason": "계획이 없어 파일 범위를 알 수 없다"})
            continue
        overlap = sorted(mine & theirs)
        if overlap:
            blockers.append({"slug": other["slug"],
                             "reason": "같은 파일을 건드린다: " + ", ".join(overlap[:3])})
    return blockers


def schedule(root: Path) -> dict:
    """이번 라운드에 움직일 파이프라인과, 기다려야 하는 파이프라인을 정한다.

    이 판단을 모델에게 맡기면 두 서브에이전트가 같은 파일을 동시에 고쳐 한쪽 작업이
    조용히 사라진다. 그래서 여기서 결정론적으로 정한다."""
    state = load_state(root)
    pipes = load_pipelines(state)
    live = live_pipelines(pipes)
    enforce = bool(state.get("enforce"))
    phase = state.get("phase", "off")

    if not live:
        return {"phase": phase, "enforce": enforce, "runnable": [], "waiting": [],
                "live": 0}

    ready = [p for p in live.values() if p.get("status") == "running"]
    asking = [p for p in live.values() if p.get("status") == "awaiting-user"]

    def by_age(items):
        # 오래 기다린 것부터 — 굶는 파이프라인이 생기지 않게 한다.
        return sorted(items, key=lambda p: (p.get("updatedAt") or "", p["slug"]))

    waiting = []
    if enforce:
        # 게이트가 프로젝트 전역이므로 같은 페이즈끼리만 함께 움직인다.
        candidates = [p for p in ready if p.get("stage") == phase]
        if not candidates:
            # 현재 페이즈에서 움직일 수 있는 게 없다 → 가장 오래 기다린 쪽으로 페이즈를 넘긴다.
            oldest = by_age(ready)
            if oldest:
                phase = oldest[0].get("stage")
                candidates = [p for p in ready if p.get("stage") == phase]
        for p in ready:
            if p not in candidates:
                waiting.append({"slug": p["slug"], "stage": p.get("stage"),
                                "reason": f"페이즈 게이트가 지금 '{phase}' 를 잡고 있다 "
                                          f"(enforce:true 에서는 같은 페이즈끼리만 동시에 돈다)"})
    else:
        candidates = list(ready)

    # 구현 단계는 파일이 겹치면 동시에 돌릴 수 없다 — 페이즈와 무관한 제약이다.
    runnable = []
    for p in by_age(candidates):
        if p.get("stage") == "implement":
            conflicts = implement_conflicts(p, [q for q in runnable if q.get("stage") == "implement"])
            if conflicts:
                waiting.append({"slug": p["slug"], "stage": "implement",
                                "reason": "구현 파일이 겹친다 — " + conflicts[0]["reason"],
                                "blockedBy": [c["slug"] for c in conflicts]})
                continue
        runnable.append(p)

    return {
        "phase": phase,
        "enforce": enforce,
        "live": len(live),
        "runnable": [p["slug"] for p in runnable],
        "waiting": waiting,
        "awaitingUser": [p["slug"] for p in asking],
    }


def board(root: Path) -> dict:
    """모든 파이프라인의 현재 위치를 한 장으로. 사용자에게 보여줄 표의 원본이다."""
    state = load_state(root)
    pipes = load_pipelines(state)
    sched = schedule(root)
    runnable = set(sched["runnable"])
    waiting = {w["slug"]: w for w in sched["waiting"]}
    rows = []
    for slug, pipe in sorted(pipes.items()):
        row = pipeline_summary(pipe)
        row["slug"] = slug
        if pipe.get("status") == "running":
            row["scheduled"] = "runnable" if slug in runnable else "waiting"
            if slug in waiting:
                row["waitReason"] = waiting[slug]["reason"]
        else:
            row["scheduled"] = pipe.get("status")
        rows.append(row)
    return {"phase": sched["phase"], "enforce": sched["enforce"],
            "activePipeline": state.get("activePipeline"),
            "counts": {"total": len(pipes), "live": sched["live"],
                       "runnable": len(sched["runnable"]),
                       "waiting": len(sched["waiting"])},
            "pipelines": rows}


def compute_next_all(root: Path) -> dict:
    """이번 라운드에 **동시에** 호출해도 되는 행동들. 병렬 실행의 진입점이다."""
    if not (root / ".sdd" / "state.json").exists():
        return {"action": "init-required",
                "message": "이 프로젝트에는 아직 SDD가 설정되지 않았다 — 먼저 `sdd.py init` 을 실행하라"}
    sched = schedule(root)
    if not sched["live"]:
        return {"action": "none", "board": board(root),
                "message": "진행 중인 파이프라인이 없다 — `sdd.py run \"<기능 설명>\"` 으로 시작하라"}

    actions = []
    for slug in sched["runnable"]:
        nxt = compute_next(root, slug)
        nxt["slug"] = slug
        actions.append(nxt)
    for slug in sched.get("awaitingUser", []):
        nxt = compute_next(root, slug)
        nxt["slug"] = slug
        actions.append(nxt)

    return {
        "action": "batch",
        "round": actions,
        "waiting": sched["waiting"],
        "board": board(root),
        "concurrency": "위 항목들은 **한 메시지에서 동시에** 호출해도 안전하다 — 스케줄러가 "
                       "페이즈와 구현 파일 겹침을 이미 확인했다. 각 결과는 "
                       "`advance --spec <slug>` 로 따로 넘긴다.",
        "then": "이 라운드를 전부 advance 한 뒤 `next --all` 을 다시 불러라. waiting 에 있던 "
                "파이프라인은 자리가 나면 자동으로 runnable 로 올라온다",
    }


def compute_next(root: Path, slug=None) -> dict:
    if not (root / ".sdd" / "state.json").exists():
        return {"action": "init-required",
                "message": "이 프로젝트에는 아직 SDD가 설정되지 않았다 — 먼저 `sdd.py init` 을 실행하라"}

    state = load_state(root)
    pipes = load_pipelines(state)
    if not pipes:
        return {"action": "none",
                "message": "진행 중인 파이프라인이 없다 — `sdd.py run \"<기능 설명>\"` 으로 시작하라"}

    target = resolve_pipeline_slug(state, slug)
    if target is None:
        live = sorted(live_pipelines(pipes))
        if slug:
            return {"action": "unknown-pipeline", "requested": slug,
                    "pipelines": sorted(pipes),
                    "message": f"'{slug}' 라는 파이프라인이 없다"}
        return {"action": "choose-pipeline", "live": live,
                "board": board(root),
                "message": "살아 있는 파이프라인이 여럿이다 — `--spec <슬러그>` 로 대상을 "
                           "지정하거나 `next --all` 로 이번 라운드에 동시에 돌릴 것을 받아라"}

    pipe = pipes[target]
    sched = schedule(root)
    if (pipe.get("status") == "running" and sched["runnable"]
            and target not in sched["runnable"]):
        blocked = next((w for w in sched["waiting"] if w["slug"] == target), None)
        return {"action": "waiting", "pipeline": pipeline_summary(pipe),
                "reason": (blocked or {}).get("reason"),
                "blockedBy": (blocked or {}).get("blockedBy") or sched["runnable"],
                "board": board(root),
                "message": "이 파이프라인은 지금 움직일 수 없다 — 먼저 진행 가능한 쪽을 "
                           "돌리면 자리가 난다. `next --all` 이 이번 라운드의 목록을 준다"}

    status = pipe.get("status")
    if status == "done":
        return {"action": "done", "pipeline": pipeline_summary(pipe),
                "message": f"'{pipe['feature']}' 파이프라인이 승인으로 완료됐다"}
    if status == "halted":
        return {"action": "halted", "pipeline": pipeline_summary(pipe),
                "reason": pipe.get("haltReason"),
                "history": _tail_history(pipe),
                "message": "파이프라인이 멈춰 있다 — 사용자에게 사유를 보고하라. "
                           "고치고 나서 `sdd.py run --resume` 으로 같은 자리에서 다시 시작할 수 있다"}
    if status == "awaiting-user":
        return {"action": "ask-user", "pipeline": pipeline_summary(pipe),
                "questions": pipe["carry"].get("openQuestions", []),
                "then": "사용자 답을 `sdd.py advance --spec " + pipe["slug"]
                        + " --result '{\"answers\": {...}}'` 로 넘겨라"}

    stage = pipe.get("stage")
    if stage not in PIPELINE_STAGES:
        return {"action": "halted", "reason": f"알 수 없는 단계: {stage}",
                "pipeline": pipeline_summary(pipe)}
    return {"spec": _next_spec, "implement": _next_implement, "review": _next_review}[stage](root, pipe)


def _call_agent(pipe: dict, stage: str, context: dict, instruction: str, phase=None) -> dict:
    agent = current_agent(pipe)
    roster = stage_roster(pipe, stage)
    return {
        "action": "call-agent",
        "agent": agent,
        "stage": stage,
        "roster": roster,
        "rosterPosition": f"{pipe.get('agentIndex', 0) + 1}/{len(roster)}",
        "depth": pipe.get("depth"),
        "attempt": pipe["attempts"].get(stage, 0) + 1,
        "maxAttempts": pipe["maxAttempts"],
        "phase": phase,
        "instruction": instruction,
        "context": context,
        "resultSchema": result_schema_for(agent),
        "then": "서브에이전트가 반환한 JSON을 **그대로** `sdd.py advance --result '<json>'` 로 "
                "넘겨라 (모르는 키는 무시된다). 다음 행동은 advance 응답의 next가 알려준다 — "
                "직접 판단하지 마라",
        "pipeline": pipeline_summary(pipe),
    }


def _call_reviewers(pipe: dict, context: dict, instruction: str, phase=None) -> dict:
    """리뷰어는 하나씩이 아니라 **한 번에** 부른다. 순차로 부르며 앞선 판정을 넘기면
    독립성이 깨지고, 먼저 나온 관심사가 뒤의 것을 덮는다."""
    roster = stage_roster(pipe, "review")
    signals = pipe.get("depthSignals") or {}
    return {
        "action": "call-agents",
        "agents": [
            {
                "agent": name,
                "concern": REVIEWER_CONCERNS.get(name, "—"),
                "context": dict(context, **(
                    {"securityHits": signals.get("securityHits", [])}
                    if name == "security-reviewer" else
                    {"perfHits": signals.get("perfHits", [])}
                    if name == "perf-reviewer" else {}
                )),
            }
            for name in roster
        ],
        "stage": "review",
        "roster": roster,
        "depth": pipe.get("depth"),
        "attempt": pipe["attempts"].get("review", 0) + 1,
        "maxAttempts": pipe["maxAttempts"],
        "phase": phase,
        "instruction": instruction,
        "concurrency": "위 에이전트를 **한 메시지에서 동시에** 호출하라. 순차로 부르며 "
                       "앞선 판정을 다음 리뷰어에게 알려주면 독립성이 깨진다.",
        "resultSchema": RESULT_SCHEMA["_reviewer"],
        "then": "각 리뷰어의 JSON에 `agent` 키를 붙여 배열로 모아 "
                "`sdd.py advance --result '{\"reviews\": [...]}'` 로 넘겨라. "
                "종합 판정은 스크립트가 낸다 — 직접 평균 내지 마라",
        "pipeline": pipeline_summary(pipe),
    }


def _next_spec(root: Path, pipe: dict) -> dict:
    config = load_config(root)
    specs_dir = root / config["specsDir"]
    phase = transition_phase(root, "spec", pipe["slug"])
    refresh_roster(root, pipe)

    if not pipe.get("specPath"):
        created = create_spec_file(root, pipe["feature"], pipe["slug"])
        pipe["specPath"] = created["path"]
        pipe["specVersion"] = created["version"]
        _record(pipe, "spec-created", path=created["path"], version=created["version"])

    carry = pipe["carry"]
    version = pipe.get("specVersion") or find_latest_version(specs_dir, pipe["slug"])
    prev = specs_dir / pipe["slug"] / f"spec-v{version - 1}.md"
    context = {
        "feature": pipe["feature"],
        "slug": pipe["slug"],
        "specPath": pipe["specPath"],
        "specVersion": version,
        "previousSpecPath": str(prev.relative_to(root)) if version > 1 and prev.exists() else None,
        "validateErrors": carry.get("validateErrors") or [],
        "specChangeRequests": carry.get("specChangeRequests") or [],
        "reviewGaps": carry.get("reviewGaps") or [],
        "userAnswers": carry.get("userAnswers") or {},
        "acPattern": config["acPattern"],
        "contextPack": carry.get("contextPack"),
        "auditFindings": carry.get("auditFindings"),
    }
    agent = current_agent(pipe)
    if agent == "spec-researcher":
        context = {"feature": pipe["feature"], "slug": pipe["slug"],
                   "specsDir": config["specsDir"],
                   "existingSpecs": list_specs(root)["specs"]}
        instruction = ("명세를 쓰기 전에 필요한 사실을 모아라. 제안하지 말고 "
                       "'지금 이렇게 되어 있다'만 적는다. 아무 파일도 쓰지 마라.")
    elif agent == "spec-auditor":
        instruction = ("완성된 명세를 적대적으로 읽어라. validate가 통과시킨 구조 뒤의 "
                       "의미 결함 — 검증 불가능한 AC, 모순, 정상 경로에 대응하는 오류 "
                       "케이스 누락 — 을 찾는다. 명세를 고치지 마라.")
    elif context["auditFindings"]:
        instruction = ("spec-auditor가 revision-requested를 냈다. auditFindings가 지목한 "
                       "AC/EC만 그 제안대로 고쳐라 — 지목되지 않은 부분은 건드리지 마라.")
    elif context["validateErrors"]:
        instruction = ("직전 명세가 검증에 실패했다. validateErrors를 전부 해소하도록 "
                       "같은 파일을 고쳐라 (새 버전을 만들지 마라).")
    elif context["specChangeRequests"]:
        instruction = ("구현 단계에서 명세 변경 요청이 올라왔다. specChangeRequests를 반영한 "
                       "새 버전 명세를 specPath에 작성하라. previousSpecPath가 직전 버전이다.")
    else:
        instruction = "specPath 파일의 모든 플레이스홀더를 채워 기능 명세를 완성하라."

    _persist_pipeline(root, pipe)
    return _call_agent(pipe, "spec", context, instruction, phase)


def _next_implement(root: Path, pipe: dict) -> dict:
    config = load_config(root)
    phase = transition_phase(root, "implement", pipe["slug"])
    refresh_roster(root, pipe)
    if phase["blocked"]:
        _halt(pipe, "implement 페이즈 전환이 차단됐다: " + "; ".join(phase["reasons"]))
        _persist_pipeline(root, pipe)
        return compute_next(root)

    tasks = ensure_tasks(root, pipe["slug"])
    if tasks.get("path"):
        pipe["tasksPath"] = tasks["path"]
    if tasks.get("refreshed"):
        _record(pipe, "tasks-refreshed", path=tasks["path"], staleVersion=tasks.get("staleVersion"))

    carry = pipe["carry"]
    context = {
        "slug": pipe["slug"],
        "specPath": pipe["specPath"],
        "specVersion": pipe.get("specVersion"),
        "tasksPath": pipe.get("tasksPath"),
        "acIds": tasks.get("acIds") or [],
        "srcDirs": config["srcDirs"],
        "testDirs": config["testDirs"],
        "acPattern": config["acPattern"],
        "previousTestFailures": carry.get("testFailures"),
        "reviewGaps": carry.get("reviewGaps") or [],
        "lastReviewPath": pipe.get("lastReviewPath"),
        "reviewRound": pipe["attempts"].get("review", 0),
        "plan": carry.get("plan"),
        "filesChanged": carry.get("filesChanged") or [],
        "implementationDefects": carry.get("implementationDefects") or [],
    }
    agent = current_agent(pipe)
    roster = stage_roster(pipe, "implement")
    context["mode"] = "deep" if "test-engineer" in roster else "light"

    if agent == "impl-planner":
        instruction = ("인수 기준을 작업 단위로 쪼개고 영향 파일·따를 패턴·테스트 러너를 "
                       "실제 경로 근거와 함께 확정해 tasksPath의 플레이스홀더를 채워라. "
                       "구현 코드는 한 줄도 쓰지 마라.")
    elif agent == "test-engineer":
        instruction = ("인수 기준마다 최소 1개 테스트를 acPattern 태그와 함께 쓰고 실제로 "
                       "실행하라. **구현 코드를 고치지 마라** — 실패는 "
                       "implementationDefects로 보고한다.")
    elif context["implementationDefects"]:
        instruction = ("test-engineer가 구현 결함을 보고했다. implementationDefects를 보고 "
                       "구현을 고쳐라 — 테스트를 고쳐서 통과시키지 마라.")
    elif context["reviewGaps"]:
        instruction = ("리뷰가 changes-requested를 냈다. reviewGaps 항목을 하나도 남기지 말고 "
                       "고쳐라. lastReviewPath에 리뷰 리포트 전문이 있다.")
    elif context["previousTestFailures"]:
        instruction = ("직전 시도의 테스트가 실패했다. previousTestFailures를 보고 **가설을 바꿔서** "
                       "고쳐라 — 같은 시도를 반복하지 마라.")
    elif context["mode"] == "deep":
        instruction = ("plan을 따라 명세의 인수 기준을 구현하라. **테스트 파일은 쓰지 마라** — "
                       "test-engineer가 쓴다. 기존 테스트 실행까지만 한다.")
    else:
        instruction = ("명세의 인수 기준을 구현하고, AC별 최소 1개 테스트를 "
                       "acPattern 태그와 함께 작성한 뒤 실제로 실행하라.")

    _persist_pipeline(root, pipe)
    return _call_agent(pipe, "implement", context, instruction, phase)


def _next_review(root: Path, pipe: dict) -> dict:
    config = load_config(root)
    phase = transition_phase(root, "review", pipe["slug"])
    refresh_roster(root, pipe)

    if not pipe.get("reviewPath"):
        rep = build_review_report(root, pipe["slug"], force=pipe.get("forcedDepth"))
        if not rep.get("created"):
            _halt(pipe, "리뷰 리포트를 만들지 못했다: " + str(rep.get("reason")))
            _persist_pipeline(root, pipe)
            return compute_next(root)
        pipe["reviewPath"] = rep["path"]
        pipe["lastReviewPath"] = rep["path"]
        pipe["reviewMeta"] = {"coverage": rep["coverage"], "uncovered": rep["uncovered"],
                              "guardViolations": rep["guardViolations"],
                              "minCoverage": rep.get("minCoverage")}
        _record(pipe, "review-report-created", path=rep["path"], coverage=rep["coverage"])

    carry = pipe["carry"]
    meta = pipe.get("reviewMeta") or {}
    context = {
        "slug": pipe["slug"],
        "specPath": pipe["specPath"],
        "specVersion": pipe.get("specVersion"),
        "reviewPath": pipe["reviewPath"],
        "coverage": meta.get("coverage"),
        "uncovered": meta.get("uncovered"),
        "guardViolations": meta.get("guardViolations"),
        "minCoverage": meta.get("minCoverage", config.get("minCoverage")),
        "implementNotes": carry.get("implementNotes"),
        "testResult": carry.get("testResult"),
        "previousGaps": carry.get("reviewGaps") or [],
        "round": pipe["attempts"].get("review", 0) + 1,
    }
    context["filesChanged"] = carry.get("filesChanged") or []
    instruction = ("각자 자기 관심사만으로 reviewPath 리포트의 해당 절을 채우고 판정을 "
                   "내려라. 관심사가 겹치면 판정에 넣지 말고 handoffs로 넘긴다. "
                   "coverage·uncovered·guardViolations는 이미 측정된 값이니 다시 계산하지 마라.")
    if context["previousGaps"]:
        instruction += " previousGaps가 실제로 해소됐는지 먼저 확인하라."

    _persist_pipeline(root, pipe)
    return _call_reviewers(pipe, context, instruction, phase)


# --- advance -------------------------------------------------------------

def _advance_spec(root: Path, pipe: dict, result: dict) -> None:
    carry = pipe["carry"]
    agent = current_agent(pipe)

    if agent == "spec-researcher":
        carry["contextPack"] = result.get("contextPack") or result
        _record(pipe, "context-pack-collected",
                unknowns=len(result.get("unknowns") or []))
        _advance_agent(pipe)
        return

    if agent == "spec-auditor":
        verdict = str(result.get("verdict") or "").strip().lower()
        if verdict == "accepted":
            carry["auditFindings"] = None
            pipe["attempts"]["specAudit"] = 0
            _record(pipe, "spec-audited", verdict="accepted")
            _enter_stage(pipe, "implement")
            return
        if verdict == "revision-requested":
            carry["auditFindings"] = {
                "acFindings": result.get("acFindings") or [],
                "contradictions": result.get("contradictions") or [],
                "missingErrorCases": result.get("missingErrorCases") or [],
                "undefinedBoundaries": result.get("undefinedBoundaries") or [],
            }
            pipe["attempts"]["specAudit"] += 1
            _record(pipe, "spec-revision-requested",
                    attempt=pipe["attempts"]["specAudit"])
            if pipe["attempts"]["specAudit"] > pipe["maxAttempts"]:
                _halt(pipe, f"명세 감사가 {pipe['attempts']['specAudit']}회 연속 "
                            "revision-requested를 냈다 — 요구사항을 사용자와 다시 합의해야 한다")
                return
            # 아키텍트로 되돌린다 (로스터에서 architect 의 위치로).
            roster = stage_roster(pipe, "spec")
            pipe["agentIndex"] = roster.index("spec-architect")
            return
        _halt(pipe, f"명세 감사 판정을 읽을 수 없다 (verdict={result.get('verdict')!r}) — "
                    "accepted 또는 revision-requested 여야 한다")
        return

    _advance_spec_architect(root, pipe, result)


def _advance_spec_architect(root: Path, pipe: dict, result: dict) -> None:
    config = load_config(root)
    carry = pipe["carry"]

    questions = result.get("openQuestions") or []
    if questions:
        carry["openQuestions"] = questions
        pipe["status"] = "awaiting-user"
        _record(pipe, "awaiting-user", count=len(questions))
        return

    spec_path = root / pipe["specPath"]
    if not spec_path.exists():
        _halt(pipe, f"명세 파일이 없다: {pipe['specPath']} — 아키텍트가 파일을 쓰지 않았다")
        return

    v = validate_spec(spec_path.read_text(encoding="utf-8"), path=spec_path)
    if not v["valid"]:
        carry["validateErrors"] = [e["message"] for e in v["errors"]]
        pipe["attempts"]["spec"] += 1
        _record(pipe, "spec-invalid", errors=len(v["errors"]),
                attempt=pipe["attempts"]["spec"])
        if pipe["attempts"]["spec"] > pipe["maxAttempts"]:
            _halt(pipe, f"명세 검증이 {pipe['attempts']['spec']}회 실패했다: "
                        + "; ".join(carry["validateErrors"][:5]))
        return

    carry["validateErrors"] = []
    carry["specChangeRequests"] = []
    carry["reviewGaps"] = []
    pipe["attempts"]["spec"] = 0
    _record(pipe, "spec-valid", acCount=len(v["acIds"]), ecCount=len(v["ecIds"]))
    # 로스터에 감사자가 있으면 구현으로 넘기기 전에 그쪽을 먼저 태운다.
    if _advance_agent(pipe):
        return
    _enter_stage(pipe, "implement")


def _advance_implement(root: Path, pipe: dict, result: dict) -> None:
    carry = pipe["carry"]
    agent = current_agent(pipe)

    if agent == "impl-planner" and not (result.get("specChangeRequests") or []):
        carry["plan"] = {
            "tasks": result.get("tasks") or [],
            "patternsToFollow": result.get("patternsToFollow") or [],
            "testRunner": result.get("testRunner"),
            "order": result.get("order") or [],
        }
        _record(pipe, "plan-ready", tasks=len(carry["plan"]["tasks"]))
        _advance_agent(pipe)
        return

    if agent == "test-engineer":
        _advance_test_engineer(pipe, result)
        return

    changes = result.get("specChangeRequests") or []
    if changes:
        carry["specChangeRequests"] = changes
        carry["testFailures"] = None
        pipe["attempts"]["specRevision"] += 1
        _record(pipe, "spec-change-requested", count=len(changes),
                attempt=pipe["attempts"]["specRevision"])
        if pipe["attempts"]["specRevision"] > pipe["maxAttempts"]:
            _halt(pipe, f"명세 변경 요청이 {pipe['attempts']['specRevision']}회 반복됐다 — "
                        "기능 범위를 사용자와 다시 합의해야 한다: " + "; ".join(changes[:5]))
            return
        pipe["specPath"] = None          # 다음 _next_spec이 새 버전을 만든다
        pipe["specVersion"] = None
        pipe["attempts"]["spec"] = 0
        _enter_stage(pipe, "spec")
        return

    tr = result.get("testResult")
    carry["testResult"] = tr
    carry["implementNotes"] = result.get("notes")
    failed = _failed_count(tr)

    if failed:
        carry["testFailures"] = tr
        pipe["attempts"]["implement"] += 1
        _record(pipe, "tests-failed", failed=failed, attempt=pipe["attempts"]["implement"])
        if pipe["attempts"]["implement"] > pipe["maxAttempts"]:
            _halt(pipe, f"테스트 실패가 {pipe['attempts']['implement']}회 이어졌다 "
                        f"(마지막: {failed}개 실패) — 사용자 판단이 필요하다")
        return

    carry["testFailures"] = None
    carry["reviewGaps"] = []
    carry["implementationDefects"] = []
    carry["filesChanged"] = result.get("filesChanged") or carry.get("filesChanged") or []
    pipe["attempts"]["implement"] = 0
    _record(pipe, "implement-done", testResult=tr or "보고 없음")
    # 로스터에 테스트 작성자가 있으면 리뷰로 넘기기 전에 그쪽을 먼저 태운다.
    if _advance_agent(pipe):
        return
    _enter_stage(pipe, "review")


def _advance_test_engineer(pipe: dict, result: dict) -> None:
    """테스트 작성자는 구현을 고치지 않는다 — 실패는 구현자에게 되돌린다."""
    carry = pipe["carry"]
    tr = result.get("testResult")
    carry["testResult"] = tr
    defects = result.get("implementationDefects") or []
    failed = _failed_count(tr)

    if defects or failed:
        carry["implementationDefects"] = defects
        carry["testFailures"] = tr
        pipe["attempts"]["implement"] += 1
        _record(pipe, "tests-failed", failed=failed, defects=len(defects),
                attempt=pipe["attempts"]["implement"])
        if pipe["attempts"]["implement"] > pipe["maxAttempts"]:
            _halt(pipe, f"테스트 실패가 {pipe['attempts']['implement']}회 이어졌다 "
                        f"(구현 결함 {len(defects)}건) — 사용자 판단이 필요하다")
            return
        # 테스트를 고치는 게 아니라 구현자에게 되돌린다.
        roster = stage_roster(pipe, "implement")
        _enter_stage(pipe, "implement", roster.index("software-engineer"))
        return

    carry["testFailures"] = None
    carry["implementationDefects"] = []
    carry["reviewGaps"] = []
    pipe["attempts"]["implement"] = 0
    _record(pipe, "tests-passed", testResult=tr or "보고 없음")
    _enter_stage(pipe, "review")


def _failed_count(tr):
    """testResult에서 실패 개수를 뽑는다. 보고가 없으면 None (실패로 단정하지 않는다)."""
    if not isinstance(tr, dict):
        return None
    if isinstance(tr.get("failed"), int):
        return tr["failed"] or None
    status = str(tr.get("status", "")).lower()
    if status in ("fail", "failed", "failing", "error"):
        return 1
    return None


def combine_verdicts(reviews) -> dict:
    """리뷰어 판정을 종합한다. **평균 내지 않는다** — 하나라도 changes-requested면
    전체가 changes-requested다. severity high 지적만 자동 재시도를 유발한다."""
    seen, gaps, high, soft, unreadable = [], [], [], [], []
    for r in reviews:
        if not isinstance(r, dict):
            continue
        name = r.get("agent") or "(이름 없음)"
        v = str(r.get("verdict") or "").strip().lower()
        if v not in ("approved", "changes-requested"):
            unreadable.append(name)
            continue
        seen.append({"agent": name, "verdict": v})
        if v == "changes-requested":
            gaps.extend(f"[{name}] {g}" for g in (r.get("gaps") or []))
        for f in r.get("findings") or []:
            if not isinstance(f, dict):
                continue
            line = f"[{name}] {f.get('issue') or f.get('summary') or ''}".strip()
            where = f.get("file")
            if where:
                line += f" ({where}:{f.get('line')})" if f.get("line") else f" ({where})"
            (high if str(f.get("severity", "")).lower() == "high" else soft).append(line)

    gaps.extend(g for g in high if g not in gaps)
    verdict = "changes-requested" if any(
        x["verdict"] == "changes-requested" for x in seen) else "approved"
    return {"verdict": verdict, "perReviewer": seen, "gaps": gaps,
            "highFindings": high, "softFindings": soft, "unreadable": unreadable}


def _advance_review(root: Path, pipe: dict, result: dict) -> None:
    carry = pipe["carry"]

    # 리뷰어가 여럿이면 {"reviews": [...]} 로 온다. 단일 판정도 계속 받아들인다.
    reviews = result.get("reviews")
    if isinstance(reviews, list):
        combined = combine_verdicts(reviews)
        if combined["unreadable"]:
            _halt(pipe, "리뷰 판정을 읽을 수 없는 리뷰어가 있다: "
                        + ", ".join(combined["unreadable"]))
            return
        expected = set(stage_roster(pipe, "review"))
        got = {x["agent"] for x in combined["perReviewer"]}
        if expected - got:
            _halt(pipe, "리뷰 결과가 빠진 리뷰어가 있다: " + ", ".join(sorted(expected - got))
                        + " — 로스터 전원의 판정이 있어야 종합할 수 있다")
            return
        carry["reviewVerdicts"] = combined["perReviewer"]
        _record(pipe, "reviews-combined", verdict=combined["verdict"],
                reviewers=len(combined["perReviewer"]),
                high=len(combined["highFindings"]))
        result = {"verdict": combined["verdict"], "gaps": combined["gaps"]}

    verdict = str(result.get("verdict") or "").strip().lower()

    if verdict == "approved":
        spec_path = root / pipe["specPath"]
        # status를 쓰려면 specs/ 쓰기가 열려 있어야 한다. 게이트를 우회하는 대신
        # 정식으로 spec 페이즈로 되돌린 뒤 고치고 off로 닫는다.
        transition_phase(root, "spec", pipe["slug"])
        ok = set_spec_status(spec_path, "done") if spec_path.exists() else False
        transition_phase(root, "off", pipe["slug"])
        pipe["status"] = "done"
        pipe["stage"] = "done"
        _record(pipe, "approved", specStatusUpdated=ok, reviewPath=pipe.get("reviewPath"))
        return

    if verdict == "changes-requested":
        gaps = result.get("gaps") or []
        carry["reviewGaps"] = gaps
        pipe["attempts"]["review"] += 1
        _record(pipe, "changes-requested", gaps=len(gaps), attempt=pipe["attempts"]["review"])
        if pipe["attempts"]["review"] > pipe["maxAttempts"]:
            _halt(pipe, f"리뷰가 {pipe['attempts']['review']}회 연속 changes-requested를 냈다 — "
                        "남은 갭: " + ("; ".join(gaps[:5]) or "리포트 참조"))
            return
        # 갭은 구현 수준이고 계획은 이미 있다 — 계획자를 다시 태우지 않고 구현자로 간다.
        roster = stage_roster(pipe, "implement")
        _enter_stage(pipe, "implement", roster.index("software-engineer"))
        return

    _halt(pipe, f"리뷰 판정을 읽을 수 없다 (verdict={result.get('verdict')!r}) — "
                "approved 또는 changes-requested 여야 한다")


def cmd_run(args) -> dict:
    root = Path(args.path).resolve()
    if not (root / ".sdd" / "state.json").exists():
        return {"ok": False, "action": "init-required",
                "reason": "이 프로젝트에는 아직 SDD가 설정되지 않았다 — 먼저 `sdd.py init` 을 실행하라"}

    state = load_state(root)
    pipes = load_pipelines(state)
    feature = (getattr(args, "feature", None) or "").strip()
    explicit = getattr(args, "spec", None)

    # 새 기능이면 그 슬러그의 파이프라인을 본다. 다른 기능이 돌고 있어도 막지 않는다 —
    # 여러 기능을 동시에 진행하는 것이 이 레지스트리의 목적이다.
    slug = slugify(args.slug) if getattr(args, "slug", None) else (
        slugify(feature) if feature else None)
    target = explicit or slug or resolve_pipeline_slug(state, allow_active=True)
    pipe = pipes.get(target)
    resumable = pipe and pipe.get("status") in ("running", "awaiting-user", "halted")

    if pipe and pipe.get("status") in LIVE_STATUSES and feature and not args.restart \
            and not args.resume:
        return {"ok": False, "reason": f"'{target}' 파이프라인이 이미 진행 중이다",
                "pipeline": pipeline_summary(pipe),
                "board": board(root),
                "hint": "그대로 이어가려면 `run --resume --spec " + str(target)
                        + "`, 버리고 다시 시작하려면 `--restart`. **다른 기능**을 함께 "
                          "돌리려면 그냥 다른 설명으로 `run \"<다른 기능>\"` 하면 된다"}

    if (args.resume or not feature) and resumable:
        revived = pipe.get("status") == "halted"
        if revived:
            # 멈춘 원인을 사람이 고치고 되살리는 것이므로 단계별 재시도 예산을 되돌린다.
            # 무한 루프는 steps 상한(MAX_PIPELINE_STEPS)이 계속 막는다.
            pipe["status"] = "running"
            pipe["haltReason"] = None
            pipe["attempts"] = {k: 0 for k in pipe["attempts"]}
        _record(pipe, "revived" if revived else "resumed")
        _persist_pipeline(root, pipe)
        return {"ok": True, "resumed": True, "slug": pipe["slug"],
                "pipeline": pipeline_summary(pipe),
                "history": _tail_history(pipe), "board": board(root),
                "next": compute_next(root, pipe["slug"])}

    if not feature:
        live = sorted(live_pipelines(pipes))
        return {"ok": False, "board": board(root),
                "reason": ("재개할 파이프라인이 없다 — 기능 설명을 인자로 줘라" if not live
                           else "재개 대상이 모호하다 — `--spec <슬러그>` 로 지정하라"),
                "live": live}

    if pipe:
        archive = state.setdefault("pipelineHistory", [])
        archive.append(pipeline_summary(pipe))
        del archive[:-5]
        write_json(root / ".sdd" / "state.json", state)

    pipe = _new_pipeline(feature, slug, args.max_attempts)
    pipe["forcedDepth"] = getattr(args, "depth", None)
    d = refresh_roster(root, pipe)
    _record(pipe, "started", feature=feature, slug=slug, depth=d["depth"])
    _persist_pipeline(root, pipe)
    result = {"ok": True, "started": True, "slug": slug,
              "pipeline": pipeline_summary(pipe),
              "depth": {"depth": d["depth"], "forcedTo": d["forcedTo"],
                        "deepReasons": d["deepReasons"], "agents": d["agents"],
                        "agentCount": sum(len(v) for v in d["agents"].values())},
              "next": compute_next(root, slug)}
    brd = board(root)
    if brd["counts"]["live"] > 1:
        result["board"] = brd
        result["note"] = (f"파이프라인 {brd['counts']['live']}개가 함께 살아 있다 — "
                          "`next --all` 로 이번 라운드에 동시에 돌릴 것을 받아라")
    return result


def cmd_next(args) -> dict:
    root = Path(args.path).resolve()
    if getattr(args, "all", False):
        return compute_next_all(root)
    return compute_next(root, getattr(args, "spec", None))


def cmd_board(args) -> dict:
    return board(Path(args.path).resolve())


RESULT_FENCE_RE = re.compile(r"^\s*(?:```|~~~)[a-zA-Z]*\s*\n(.*?)\n\s*(?:```|~~~)\s*$", re.DOTALL)


def _parse_result(raw: str) -> dict:
    if raw == "-":
        raw = sys.stdin.read()
    elif raw.startswith("@"):
        raw = Path(raw[1:]).read_text(encoding="utf-8")
    # 서브에이전트가 결과를 ```json 펜스로 감싸 오는 경우가 흔하다 — 벗겨서 읽는다.
    m = RESULT_FENCE_RE.match(raw)
    if m:
        raw = m.group(1)
    raw = raw.strip()
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("결과는 JSON 객체여야 한다")
    return data


def cmd_advance(args) -> dict:
    root = Path(args.path).resolve()
    state = load_state(root)
    pipes = load_pipelines(state)
    if not pipes:
        return {"ok": False, "reason": "진행 중인 파이프라인이 없다"}

    target = resolve_pipeline_slug(state, getattr(args, "spec", None))
    if target is None:
        return {"ok": False, "board": board(root),
                "reason": ("살아 있는 파이프라인이 여럿이다 — 결과가 어느 것인지 "
                           "`--spec <슬러그>` 로 밝혀라. 잘못 넘기면 다른 기능의 상태가 "
                           "그 결과로 전이된다"),
                "live": sorted(live_pipelines(pipes))}
    pipe = pipes[target]
    if pipe.get("status") in ("done", "halted"):
        return {"ok": False, "reason": f"'{target}' 파이프라인이 이미 {pipe['status']} 상태다",
                "pipeline": pipeline_summary(pipe), "next": compute_next(root, target)}

    try:
        result = _parse_result(args.result)
    except (json.JSONDecodeError, ValueError, OSError) as e:
        return {"ok": False, "reason": f"결과 JSON을 읽지 못했다: {e}",
                "hint": "--result '<json>' 또는 --result @path 또는 --result - (stdin)"}

    stage_before = pipe.get("stage")

    if pipe.get("status") == "awaiting-user":
        pipe["carry"]["userAnswers"] = result.get("answers") or result
        pipe["carry"]["openQuestions"] = []
        pipe["status"] = "running"
        _record(pipe, "user-answered")
    else:
        if args.stage and args.stage != stage_before:
            return {"ok": False,
                    "reason": f"단계가 어긋났다 — 파이프라인은 '{stage_before}' 인데 결과는 "
                              f"'{args.stage}' 로 왔다. `next` 를 먼저 확인하라",
                    "pipeline": pipeline_summary(pipe)}
        pipe["steps"] += 1
        if pipe["steps"] > MAX_PIPELINE_STEPS:
            _halt(pipe, f"단계 전환이 {MAX_PIPELINE_STEPS}회를 넘었다 — 루프가 수렴하지 않는다")
        else:
            {"spec": _advance_spec, "implement": _advance_implement,
             "review": _advance_review}[stage_before](root, pipe, result)

    _persist_pipeline(root, pipe)
    out = {"ok": True, "slug": target, "stageBefore": stage_before,
           "pipeline": pipeline_summary(pipe),
           "recorded": _tail_history(pipe, 3),
           "next": compute_next(root, target)}
    brd = board(root)
    if brd["counts"]["live"] > 1:
        out["board"] = brd
    return out


def cmd_abort(args) -> dict:
    root = Path(args.path).resolve()
    state = load_state(root)
    pipes = load_pipelines(state)
    if not pipes:
        return {"ok": False, "reason": "진행 중인 파이프라인이 없다"}
    reason = args.reason or "사용자가 중단했다"

    if getattr(args, "all", False):
        stopped = []
        for slug, pipe in sorted(live_pipelines(pipes).items()):
            _halt(pipe, reason)
            _persist_pipeline(root, pipe, focus=False)
            stopped.append(slug)
        return {"ok": True, "aborted": stopped, "board": board(root)}

    target = resolve_pipeline_slug(state, getattr(args, "spec", None))
    if target is None:
        return {"ok": False, "board": board(root),
                "reason": "살아 있는 파이프라인이 여럿이다 — `--spec <슬러그>` 또는 `--all`",
                "live": sorted(live_pipelines(pipes))}
    pipe = pipes[target]
    _halt(pipe, reason)
    _persist_pipeline(root, pipe)
    return {"ok": True, "slug": target, "pipeline": pipeline_summary(pipe)}


# ---------------------------------------------------------------------------
# CLI 진입점
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sdd", description="Spec-Driven Development 하네스 CLI")
    sub = p.add_subparsers(dest="command", required=True)

    def add_path(sp):
        sp.add_argument("--path", default=".", help="프로젝트 루트 (기본: 현재 디렉터리)")

    sp = sub.add_parser("init", help="SDD 하네스 스캐폴딩")
    add_path(sp)
    sp.add_argument("--enforce", action="store_true", help="페이즈 게이트 훅을 즉시 켠다")
    sp.add_argument("--specs", default=None, help="specs 디렉터리 이름 (기본: specs)")
    sp.add_argument("--src", default=None, help="쉼표로 구분된 소스 디렉터리 목록")
    sp.add_argument("--tests", default=None, help="쉼표로 구분된 테스트 디렉터리 목록")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("new", help="새 기능 명세 생성")
    add_path(sp)
    sp.add_argument("feature", help="기능 설명 (슬러그로 정규화됨)")
    sp.add_argument("--slug", default=None,
                    help="슬러그를 직접 지정한다 (예: ASCII 슬러그를 쓰고 싶을 때)")
    sp.set_defaults(func=cmd_new)

    sp = sub.add_parser("tasks", help="명세의 AC로 tasks.md 생성")
    add_path(sp)
    sp.add_argument("slug", nargs="?", default=None,
                    help="대상 명세 슬러그 (생략하면 activeSpec)")
    sp.set_defaults(func=cmd_tasks)

    sp = sub.add_parser("review-report", help="리뷰 리포트 골격 생성 (trace·depth 결과 반영)")
    add_path(sp)
    sp.add_argument("slug", nargs="?", default=None,
                    help="대상 명세 슬러그 (생략하면 activeSpec)")
    sp.add_argument("--force", default=None, choices=["light", "deep"],
                    help="리뷰어 구성의 깊이를 덮어쓴다")
    sp.set_defaults(func=cmd_review_report)

    sp = sub.add_parser("depth", help="이번 작업에 부를 서브에이전트 구성 결정 (light/deep)")
    add_path(sp)
    sp.add_argument("slug", nargs="?", default=None,
                    help="대상 명세 슬러그 (생략하면 activeSpec)")
    sp.add_argument("--feature", default=None,
                    help="아직 명세가 없을 때 판정 근거로 쓸 기능 설명")
    sp.add_argument("--force", default=None, choices=["light", "deep"],
                    help="자동 판정을 덮어쓴다 (--deep/--light 플래그의 실체)")
    sp.set_defaults(func=cmd_depth)

    sp = sub.add_parser("list", help="모든 명세 나열")
    add_path(sp)
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("status", help="현재 페이즈·명세·게이트 위반 요약")
    add_path(sp)
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("phase", help="페이즈 전환")
    add_path(sp)
    sp.add_argument("target", choices=["spec", "implement", "review", "off"])
    sp.add_argument("--spec", default=None, help="대상 명세 슬러그")
    sp.set_defaults(func=cmd_phase)

    sp = sub.add_parser("validate", help="명세 구조 검증")
    add_path(sp)
    sp.add_argument("spec_path", help="검증할 spec-vN.md 경로")
    sp.set_defaults(func=cmd_validate)

    sp = sub.add_parser("trace", help="인수기준 ↔ 테스트 추적성 행렬")
    add_path(sp)
    sp.add_argument("spec_path", help="대상 spec-vN.md 경로")
    sp.set_defaults(func=cmd_trace)

    sp = sub.add_parser("guard", help="페이즈 위반 사후 탐지 (git diff 기준)")
    add_path(sp)
    sp.add_argument("--base", default="HEAD", help="비교 기준 (기본: HEAD)")
    sp.set_defaults(func=cmd_guard)

    sp = sub.add_parser("run", help="파이프라인 시작 또는 재개 (spec→implement→review)")
    add_path(sp)
    sp.add_argument("feature", nargs="?", default=None,
                    help="기능 설명 (생략하면 진행 중이던 파이프라인을 재개한다)")
    sp.add_argument("--slug", default=None, help="슬러그를 직접 지정한다")
    sp.add_argument("--resume", action="store_true", help="설명을 줘도 재개를 우선한다")
    sp.add_argument("--restart", action="store_true", help="진행 중인 파이프라인을 버리고 새로 시작한다")
    sp.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS,
                    dest="max_attempts", help=f"단계별 재시도 상한 (기본: {DEFAULT_MAX_ATTEMPTS})")
    sp.add_argument("--depth", default=None, choices=["light", "deep"],
                    help="자동 깊이 판정을 덮어쓴다 (파이프라인 내내 유지된다)")
    sp.add_argument("--spec", default=None,
                    help="재개할 파이프라인 슬러그 (여러 개가 살아 있을 때)")
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("next", help="다음 행동을 지시한다 (--all 이면 동시 실행 가능한 전부)")
    add_path(sp)
    sp.add_argument("--spec", default=None, help="대상 파이프라인 슬러그")
    sp.add_argument("--all", action="store_true",
                    help="이번 라운드에 동시에 호출해도 되는 행동을 전부 낸다")
    sp.set_defaults(func=cmd_next)

    sp = sub.add_parser("board", help="모든 파이프라인의 위치·실행 가능 여부를 한 장으로")
    add_path(sp)
    sp.set_defaults(func=cmd_board)

    sp = sub.add_parser("advance", help="서브에이전트 결과를 넘겨 다음 단계로 전이한다")
    add_path(sp)
    sp.add_argument("--result", required=True,
                    help="결과 JSON 문자열, @파일경로, 또는 - (stdin)")
    sp.add_argument("--stage", default=None, choices=list(PIPELINE_STAGES),
                    help="결과를 낸 단계 (주면 어긋남을 검사한다)")
    sp.add_argument("--spec", default=None,
                    help="결과를 낸 파이프라인 슬러그 (여러 개가 살아 있으면 필수)")
    sp.set_defaults(func=cmd_advance)

    sp = sub.add_parser("abort", help="진행 중인 파이프라인을 중단한다")
    add_path(sp)
    sp.add_argument("--reason", default=None, help="중단 사유")
    sp.add_argument("--spec", default=None, help="중단할 파이프라인 슬러그")
    sp.add_argument("--all", action="store_true", help="살아 있는 파이프라인을 전부 중단한다")
    sp.set_defaults(func=cmd_abort)

    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = args.func(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
