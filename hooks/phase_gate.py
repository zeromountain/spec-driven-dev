#!/usr/bin/env python3
"""SDD 페이즈 게이트 — PreToolUse 훅.

플러그인 설치 즉시 모든 세션에 등록되므로, 대상 프로젝트가 opt-in 하지 않았으면
반드시 무동작(allow)이어야 한다. opt-in 여부는 `<project>/.sdd/state.json`의
`enforce` 필드로만 판단한다.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import sdd  # noqa: E402

WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return 0  # 입력을 못 읽으면 판단하지 않고 허용

    tool_name = payload.get("tool_name", "")
    if tool_name not in WRITE_TOOLS:
        return 0

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or "."
    project_root = Path(project_dir).resolve()

    state = sdd.read_json(project_root / ".sdd" / "state.json")
    if not state or not state.get("enforce"):
        return 0  # opt-in 안 됨 — 무동작

    tool_input = payload.get("tool_input", {}) or {}
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not file_path:
        return 0

    config = sdd.load_config(project_root)
    # 워크트리 안의 경로면 그 워크트리를 가진 파이프라인의 단계로 판정한다 — 경로가
    # 호출자를 알려주는 유일한 단서다.
    phase, rel, owner = sdd.resolve_write(file_path, project_root, state, config)
    if rel is None:
        return 0  # 프로젝트 밖이거나 주인을 알 수 없는 경로 — 이 게이트의 관심사가 아니다
    if not phase or phase == "off":
        return 0

    reason = sdd.evaluate_gate(phase, rel, config)
    if reason is None:
        return 0
    if owner:
        reason = f"[{owner}] {reason}"

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        },
        "systemMessage": reason,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
