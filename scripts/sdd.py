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
    "updatedAt": None,
}

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


def cmd_new(args) -> dict:
    root = Path(args.path).resolve()
    config = load_config(root)
    specs_dir = root / config["specsDir"]
    slug = slugify(args.slug) if getattr(args, "slug", None) else slugify(args.feature)
    version = find_latest_version(specs_dir, slug) + 1
    feature_dir = specs_dir / slug
    feature_dir.mkdir(parents=True, exist_ok=True)
    spec_path = feature_dir / f"spec-v{version}.md"

    # 문서 전체 substring 치환은 본문을 오염시킬 수 있으므로 채울 키만 명시적으로 넘긴다.
    content = fill_template("spec.md", {
        "slug": slug,
        "version": str(version),
        "createdAt": now_iso(),
        "제목": args.feature,
    })
    spec_path.write_text(content, encoding="utf-8")

    return {
        "path": str(spec_path.relative_to(root)),
        "version": version,
        "slug": slug,
        "note": "플레이스홀더를 모두 채우기 전에는 validate가 실패한다 (의도된 동작).",
    }


def cmd_tasks(args) -> dict:
    """최신 명세의 AC를 읽어 tasks.md를 생성한다 (AC 대응표가 미리 채워진 상태로)."""
    root = Path(args.path).resolve()
    config = load_config(root)
    specs_dir = root / config["specsDir"]
    slug = resolve_slug(root, getattr(args, "slug", None))
    if not slug:
        return {"created": False, "reason": "대상 명세가 지정되지 않았다"}

    version = find_latest_version(specs_dir, slug)
    if version == 0:
        return {"created": False, "reason": f"spec '{slug}' 를 찾을 수 없다"}

    spec_path = specs_dir / slug / f"spec-v{version}.md"
    ac_ids = extract_ac_ids(spec_path.read_text(encoding="utf-8"))
    tasks_path = specs_dir / slug / "tasks.md"
    if tasks_path.exists():
        return {"created": False, "reason": "이미 존재한다",
                "path": str(tasks_path.relative_to(root)), "acIds": ac_ids}

    rows = "\n".join(f"- [ ] {ac} → {{{{구현할 파일/모듈}}}}" for ac in ac_ids) \
        or "- [ ] {{인수 기준이 없다 — 명세를 먼저 확인하라}}"
    tasks_path.write_text(
        fill_template("tasks.md", {"slug": slug, "version": str(version), "acRows": rows}),
        encoding="utf-8",
    )
    return {"created": True, "path": str(tasks_path.relative_to(root)),
            "acIds": ac_ids, "version": version}


def cmd_review_report(args) -> dict:
    """trace 결과를 반영한 리뷰 리포트 골격을 .sdd/reviews/ 에 만든다."""
    root = Path(args.path).resolve()
    config = load_config(root)
    specs_dir = root / config["specsDir"]
    slug = resolve_slug(root, getattr(args, "slug", None))
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

    reviews_dir = root / config["reviewsDir"]
    reviews_dir.mkdir(parents=True, exist_ok=True)
    seq = len(list(reviews_dir.glob(f"{slug}-v{version}-*.md"))) + 1
    out = reviews_dir / f"{slug}-v{version}-{seq}.md"
    out.write_text(fill_template("review-report.md", {
        "slug": slug,
        "version": str(version),
        "seq": str(seq),
        "specPath": str(spec_path.relative_to(root)),
        "acRows": ac_table,
        "ecRows": ec_table,
        "guardRows": guard_rows,
    }), encoding="utf-8")

    return {"created": True, "path": str(out.relative_to(root)), "seq": seq,
            "version": version, "coverage": tr["coverage"],
            "uncovered": tr["uncovered"], "guardViolations": len(violations)}


def cmd_list(args) -> dict:
    root = Path(args.path).resolve()
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
        "specs": listing["specs"],
        "guardViolations": violations,
    }


def cmd_phase(args) -> dict:
    root = Path(args.path).resolve()
    state = load_state(root)
    from_phase = state.get("phase", "off")
    target = args.target
    blocked = False
    reasons = []

    # implement 전환은 항상 유효한 명세를 요구한다. --spec 이 없으면 activeSpec 으로
    # 폴백하고, 그마저 없으면 차단한다 — 검증을 통째로 건너뛰는 경로를 남기지 않는다.
    target_slug = resolve_slug(root, args.spec)
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

    sp = sub.add_parser("review-report", help="리뷰 리포트 골격 생성 (trace 결과 반영)")
    add_path(sp)
    sp.add_argument("slug", nargs="?", default=None,
                    help="대상 명세 슬러그 (생략하면 activeSpec)")
    sp.set_defaults(func=cmd_review_report)

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

    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = args.func(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
