#!/usr/bin/env python3
"""이 레포 자신의 컴포넌트(SKILL.md·commands/*.md·agents/*.md)를 검증한다.

`claude plugin validate`가 잡는 것과 별개로, 이 레포의 자체 관례(프론트매터 필드 집합,
이름 규칙, 500줄 예산)를 확인한다. stdlib only.
"""
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MAX_SKILL_MD_LINES = 500


def parse_frontmatter(text: str):
    if not text.startswith("---\n"):
        return None, "'---' YAML 프론트매터로 시작해야 한다"
    end = text.find("\n---", 4)
    if end == -1:
        return None, "프론트매터가 닫히지 않았다 (닫는 '---' 없음)"
    raw = text[4:end]
    fields = {}
    for line in raw.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields, None


def check_skill(errors: list, warnings: list):
    path = REPO_ROOT / "skills" / "spec-driven-dev" / "SKILL.md"
    if not path.exists():
        errors.append(f"{path}: 파일이 없다")
        return
    text = path.read_text(encoding="utf-8")
    fields, err = parse_frontmatter(text)
    if err:
        errors.append(f"{path}: {err}")
        return
    for req in ("name", "description"):
        if req not in fields:
            errors.append(f"{path}: 필수 프론트매터 '{req}' 없음")
    name = fields.get("name", "")
    if name and name != "spec-driven-dev":
        errors.append(f"{path}: name '{name}' 이 스킬 디렉터리 이름과 다르다")
    if name and not NAME_RE.match(name):
        errors.append(f"{path}: name '{name}' 이 kebab-case 규칙을 어긴다")
    line_count = len(text.splitlines())
    if line_count > MAX_SKILL_MD_LINES:
        warnings.append(f"{path}: {line_count}줄 — {MAX_SKILL_MD_LINES}줄 예산 초과")

    # references/*.md 링크가 실제로 존재하는지
    refs_dir = path.parent / "references"
    for m in re.finditer(r"references/([a-zA-Z0-9_\-]+\.md)", text):
        ref_path = refs_dir / m.group(1)
        if not ref_path.exists():
            errors.append(f"{path}: references/{m.group(1)} 참조가 존재하지 않는다")


def check_commands(errors: list, warnings: list):
    commands_dir = REPO_ROOT / "commands"
    for path in sorted(commands_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        fields, err = parse_frontmatter(text)
        if err:
            errors.append(f"{path}: {err}")
            continue
        for req in ("description", "argument-hint"):
            if req not in fields:
                errors.append(f"{path}: 필수 프론트매터 '{req}' 없음")
        body_lines = len(text.splitlines())
        if body_lines > 25:
            warnings.append(f"{path}: {body_lines}줄 — 커맨드는 얇은 라우터여야 한다")


def check_agents(errors: list, warnings: list):
    agents_dir = REPO_ROOT / "agents"
    for path in sorted(agents_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        fields, err = parse_frontmatter(text)
        if err:
            errors.append(f"{path}: {err}")
            continue
        for req in ("name", "description", "tools"):
            if req not in fields:
                errors.append(f"{path}: 필수 프론트매터 '{req}' 없음")
        name = fields.get("name", "")
        expected = path.stem
        if name and name != expected:
            errors.append(f"{path}: name '{name}' 이 파일명 '{expected}' 과 다르다")
        if "## 출력 스키마" not in text:
            warnings.append(f"{path}: '## 출력 스키마' 섹션이 없다")


def check_manifests(errors: list, warnings: list):
    import json

    parsed = {}
    for rel in (
        ".claude-plugin/marketplace.json",
        ".claude-plugin/plugin.json",
        ".codex-plugin/plugin.json",
    ):
        path = REPO_ROOT / rel
        if not path.exists():
            errors.append(f"{path}: 파일이 없다")
            continue
        try:
            parsed[rel] = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"{path}: JSON 파싱 실패 — {e}")

    claude_pkg = parsed.get(".claude-plugin/plugin.json")
    codex_pkg = parsed.get(".codex-plugin/plugin.json")
    if claude_pkg and codex_pkg:
        cv, xv = claude_pkg.get("version"), codex_pkg.get("version")
        if cv != xv:
            errors.append(
                f".claude-plugin/plugin.json(version={cv})와 .codex-plugin/plugin.json"
                f"(version={xv})의 버전이 다르다 — 두 매니페스트는 함께 올려야 한다"
            )
        if codex_pkg.get("skills") != "./skills/":
            warnings.append(".codex-plugin/plugin.json의 skills 필드가 './skills/'가 아니다")


def main() -> int:
    errors: list = []
    warnings: list = []

    check_manifests(errors, warnings)
    check_skill(errors, warnings)
    check_commands(errors, warnings)
    check_agents(errors, warnings)

    for w in warnings:
        print(f"[WARN] {w}")
    for e in errors:
        print(f"[ERROR] {e}")

    if errors:
        print(f"\n{len(errors)}개 오류.")
        return 1
    print(f"\n검증 통과 ({len(warnings)}개 경고).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
