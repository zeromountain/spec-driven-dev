"""sdd.py 핵심 로직 단위 테스트. 외부 의존성·네트워크 없음."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import sdd  # noqa: E402


VALID_SPEC = """# 기능: 테스트 기능

## 목적

테스트용 명세.

## 배경

배경 설명.

## 비즈니스 규칙

- 규칙 1

## 기능 요구사항

- 요구사항 1

## 비기능 요구사항

- 해당 없음

## 인수 기준

- [ ] **AC-1**: 조건 A가 충족되면 시스템은 X를 반환해야 한다.
- [ ] **AC-2**: 조건 B에서 오류가 발생하면 안 된다.

## 오류 케이스

- 잘못된 입력이 들어오면 에러를 낸다.

## 범위 밖

- 인증 기능은 다루지 않는다.
"""

DEFAULT_CONFIG = dict(sdd.DEFAULT_CONFIG)


class ValidateSpecTests(unittest.TestCase):
    def test_valid_spec_passes(self):
        result = sdd.validate_spec(VALID_SPEC)
        self.assertTrue(result["valid"])
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["acIds"], ["AC-1", "AC-2"])

    def test_missing_section_is_error(self):
        broken = VALID_SPEC.replace("## 범위 밖\n\n- 인증 기능은 다루지 않는다.\n", "")
        result = sdd.validate_spec(broken)
        self.assertFalse(result["valid"])
        self.assertTrue(any(e["section"] == "범위 밖" for e in result["errors"]))

    def test_ac_without_id_is_error(self):
        broken = VALID_SPEC.replace(
            "- [ ] **AC-2**: 조건 B에서 오류가 발생하면 안 된다.\n",
            "- [ ] 조건 B에서 오류가 발생하면 안 된다.\n",
        )
        result = sdd.validate_spec(broken)
        self.assertFalse(result["valid"])
        self.assertTrue(any("AC ID가 없는" in e["message"] for e in result["errors"]))

    def test_duplicate_ac_number_is_error(self):
        broken = VALID_SPEC.replace(
            "- [ ] **AC-2**: 조건 B에서 오류가 발생하면 안 된다.\n",
            "- [ ] **AC-1**: 중복된 번호다.\n",
        )
        result = sdd.validate_spec(broken)
        self.assertFalse(result["valid"])
        self.assertTrue(any("중복된다" in e["message"] for e in result["errors"]))

    def test_non_contiguous_ac_number_is_error(self):
        broken = VALID_SPEC.replace(
            "- [ ] **AC-2**: 조건 B에서 오류가 발생하면 안 된다.\n",
            "- [ ] **AC-3**: 번호를 건너뛴다.\n",
        )
        result = sdd.validate_spec(broken)
        self.assertFalse(result["valid"])
        self.assertTrue(any("연속되지" in e["message"] for e in result["errors"]))

    def test_empty_out_of_scope_is_warning_not_error(self):
        broken = VALID_SPEC.replace("- 인증 기능은 다루지 않는다.\n", "")
        result = sdd.validate_spec(broken)
        self.assertTrue(result["valid"])  # 여전히 valid — 경고일 뿐
        self.assertTrue(any(w["section"] == "범위 밖" for w in result["warnings"]))


class SlugifyTests(unittest.TestCase):
    def test_spaces_and_uppercase(self):
        self.assertEqual(sdd.slugify("  User Auth Flow  "), "user-auth-flow")

    def test_korean_text_normalizes_spaces(self):
        self.assertEqual(sdd.slugify("사용자 인증 흐름"), "사용자-인증-흐름")

    def test_strips_disallowed_chars(self):
        self.assertEqual(sdd.slugify("feature: v2.0!!"), "feature-v20")

    def test_empty_falls_back(self):
        self.assertEqual(sdd.slugify("   "), "feature")


class VersioningTests(unittest.TestCase):
    def test_new_spec_starts_at_v1(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".sdd").mkdir()
            sdd.write_json(root / ".sdd" / "config.json", DEFAULT_CONFIG)
            args = _ns(path=str(root), feature="사용자 인증")
            result = sdd.cmd_new(args)
            self.assertEqual(result["version"], 1)
            self.assertTrue((root / result["path"]).exists())

    def test_next_version_picks_max_plus_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".sdd").mkdir()
            sdd.write_json(root / ".sdd" / "config.json", DEFAULT_CONFIG)
            feature_dir = root / "specs" / "login"
            feature_dir.mkdir(parents=True)
            (feature_dir / "spec-v1.md").write_text("x", encoding="utf-8")
            (feature_dir / "spec-v3.md").write_text("x", encoding="utf-8")
            result = sdd.cmd_new(_ns(path=str(root), feature="login"))
            self.assertEqual(result["version"], 4)


class PhaseTransitionTests(unittest.TestCase):
    def test_blocked_when_spec_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".sdd").mkdir()
            sdd.write_json(root / ".sdd" / "config.json", DEFAULT_CONFIG)
            feature_dir = root / "specs" / "broken"
            feature_dir.mkdir(parents=True)
            (feature_dir / "spec-v1.md").write_text("# 불완전한 명세", encoding="utf-8")

            result = sdd.cmd_phase(_ns(path=str(root), target="implement", spec="broken"))
            self.assertTrue(result["blocked"])
            self.assertTrue(result["reasons"])

    def test_allowed_when_spec_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".sdd").mkdir()
            sdd.write_json(root / ".sdd" / "config.json", DEFAULT_CONFIG)
            feature_dir = root / "specs" / "ok"
            feature_dir.mkdir(parents=True)
            (feature_dir / "spec-v1.md").write_text(VALID_SPEC, encoding="utf-8")

            result = sdd.cmd_phase(_ns(path=str(root), target="implement", spec="ok"))
            self.assertFalse(result["blocked"])
            state = sdd.load_state(root)
            self.assertEqual(state["phase"], "implement")
            self.assertEqual(state["activeSpec"], "ok")


class TraceTests(unittest.TestCase):
    def test_tagged_tests_are_matched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tests_dir = root / "tests"
            tests_dir.mkdir()
            # 파이썬 식별자는 하이픈을 못 쓰므로 태그는 주석/문자열로 남긴다 (AC-1 그대로).
            (tests_dir / "test_x.py").write_text(
                "def test_returns_x():\n    # AC-1\n    pass\n", encoding="utf-8"
            )
            result = sdd.trace_spec(VALID_SPEC, ["tests"], r"AC-\d+", root)
            covered = {m["ac"]: m["covered"] for m in result["matrix"]}
            self.assertTrue(covered["AC-1"])
            self.assertFalse(covered["AC-2"])
            self.assertEqual(result["uncovered"], ["AC-2"])

    def test_no_tags_is_warning_not_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tests").mkdir()
            (root / "tests" / "test_x.py").write_text("def test_ok(): pass\n", encoding="utf-8")
            result = sdd.trace_spec(VALID_SPEC, ["tests"], r"AC-\d+", root)
            self.assertEqual(result.get("convention"), "absent")
            self.assertEqual(result["uncovered"], ["AC-1", "AC-2"])


class GuardTests(unittest.TestCase):
    def test_spec_phase_blocks_src_change(self):
        violations = sdd.guard_violations(["src/x.py"], "spec", DEFAULT_CONFIG)
        self.assertEqual(len(violations), 1)

    def test_off_phase_has_no_violations(self):
        violations = sdd.guard_violations(["src/x.py", "specs/a/spec-v1.md"], "off", DEFAULT_CONFIG)
        self.assertEqual(violations, [])


class EvaluateGateTests(unittest.TestCase):
    def test_off_phase_allows_everything(self):
        self.assertIsNone(sdd.evaluate_gate("off", "src/a.ts", DEFAULT_CONFIG))

    def test_spec_phase_denies_src(self):
        self.assertIsNotNone(sdd.evaluate_gate("spec", "src/a.ts", DEFAULT_CONFIG))

    def test_spec_phase_allows_specs_dir(self):
        self.assertIsNone(sdd.evaluate_gate("spec", "specs/x/notes.txt", DEFAULT_CONFIG))

    def test_implement_phase_allows_tasks_md(self):
        self.assertIsNone(sdd.evaluate_gate("implement", "specs/x/tasks.md", DEFAULT_CONFIG))

    def test_implement_phase_denies_spec_file(self):
        self.assertIsNotNone(sdd.evaluate_gate("implement", "specs/x/spec-v1.md", DEFAULT_CONFIG))

    def test_implement_phase_allows_src(self):
        self.assertIsNone(sdd.evaluate_gate("implement", "src/a.ts", DEFAULT_CONFIG))

    def test_review_phase_denies_src_and_specs(self):
        self.assertIsNotNone(sdd.evaluate_gate("review", "src/a.ts", DEFAULT_CONFIG))
        self.assertIsNotNone(sdd.evaluate_gate("review", "specs/x/spec-v1.md", DEFAULT_CONFIG))

    def test_review_phase_allows_reviews_dir(self):
        self.assertIsNone(sdd.evaluate_gate("review", ".sdd/reviews/x-v1-1.md", DEFAULT_CONFIG))

    def test_always_writable_wins_in_any_phase(self):
        for phase in ("spec", "implement", "review"):
            self.assertIsNone(sdd.evaluate_gate(phase, "AGENTS.md", DEFAULT_CONFIG))


class ToProjectRelativeTests(unittest.TestCase):
    def test_path_outside_root_is_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            root.mkdir()
            self.assertIsNone(sdd.to_project_relative("/etc/hosts", root))

    def test_dot_dot_traversal_resolves_outside(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            root.mkdir()
            outside = str(root / ".." / "escape.txt")
            self.assertIsNone(sdd.to_project_relative(outside, root))

    def test_normal_relative_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            root.mkdir()
            self.assertEqual(sdd.to_project_relative("src/a.ts", root), "src/a.ts")


def _ns(**kwargs):
    class NS:
        pass
    ns = NS()
    for k, v in kwargs.items():
        setattr(ns, k, v)
    return ns


if __name__ == "__main__":
    unittest.main()
