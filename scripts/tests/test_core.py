"""sdd.py 핵심 로직 단위 테스트. 외부 의존성·네트워크 없음."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import sdd  # noqa: E402


VALID_SPEC = """---
feature: 테스트-기능
version: 1
status: draft
createdAt: 2026-08-27T00:00:00Z
---

# 기능: 테스트 기능

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

- **EC-1**: 잘못된 입력이 들어오면 400을 반환해야 한다.

## 범위 밖

- 인증 기능은 다루지 않는다.
"""

# 프론트매터 교차검증이 걸리지 않도록 하는 경로 (feature/version 과 일치)
VALID_SPEC_PATH = "specs/테스트-기능/spec-v1.md"

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

    # --- 미기입 템플릿 차단 (이 플러그인의 핵심 전제) -----------------------

    def test_unfilled_template_from_new_is_invalid(self):
        """cmd_new 가 만든 파일은 반드시 validate 에 실패해야 한다.

        이 테스트가 템플릿과 검사기의 drift 를 막는다 — 예전에는 손도 대지 않은
        템플릿이 valid:true 로 통과해 implement 게이트가 열려 있었다."""
        generated = sdd.fill_template("spec.md", {
            "slug": "user-login", "version": "1",
            "createdAt": "2026-08-27T00:00:00Z", "제목": "사용자 로그인",
        })
        result = sdd.validate_spec(generated, path=Path("specs/user-login/spec-v1.md"))
        self.assertFalse(result["valid"])
        self.assertTrue(any("플레이스홀더" in e["message"] for e in result["errors"]))

    def test_filled_template_is_valid(self):
        result = sdd.validate_spec(VALID_SPEC, path=Path(VALID_SPEC_PATH))
        self.assertTrue(result["valid"], result["errors"])

    def test_placeholder_inside_code_fence_is_not_flagged(self):
        doc = VALID_SPEC.replace(
            "테스트용 명세.",
            "테스트용 명세.\n\n```\n- [ ] **AC-1**: {{조건}}\n```",
        )
        result = sdd.validate_spec(doc)
        self.assertFalse(any("플레이스홀더" in e["message"] for e in result["errors"]))

    # --- 구조 파싱 ---------------------------------------------------------

    def test_section_inside_code_fence_is_ignored(self):
        doc = "## 목적\n설명\n\n```md\n## 인수 기준\n- [ ] **AC-9**: 가짜\n```\n\n## 배경\n진짜\n"
        self.assertEqual(list(sdd.parse_sections(doc).keys()), ["목적", "배경"])

    def test_duplicate_section_is_error(self):
        doc = VALID_SPEC + "\n## 인수 기준\n\n- [ ] **AC-1**: 덮어쓴다.\n"
        result = sdd.validate_spec(doc)
        self.assertFalse(result["valid"])
        self.assertTrue(any("두 번 이상" in e["message"] for e in result["errors"]))

    # --- 프론트매터 -------------------------------------------------------

    def test_missing_frontmatter_is_error(self):
        result = sdd.validate_spec(VALID_SPEC.split("---\n", 2)[2])
        self.assertFalse(result["valid"])
        self.assertTrue(any(e["section"] == "frontmatter" for e in result["errors"]))

    def test_version_mismatch_with_filename_is_error(self):
        result = sdd.validate_spec(VALID_SPEC, path=Path("specs/테스트-기능/spec-v3.md"))
        self.assertFalse(result["valid"])
        self.assertTrue(any("파일명" in e["message"] for e in result["errors"]))

    def test_slug_mismatch_with_directory_is_error(self):
        result = sdd.validate_spec(VALID_SPEC, path=Path("specs/다른-기능/spec-v1.md"))
        self.assertFalse(result["valid"])
        self.assertTrue(any("디렉터리" in e["message"] for e in result["errors"]))

    # --- 오류 케이스 ID ---------------------------------------------------

    def test_ec_without_id_is_error(self):
        broken = VALID_SPEC.replace(
            "- **EC-1**: 잘못된 입력이 들어오면 400을 반환해야 한다.",
            "- 잘못된 입력이 들어오면 400을 반환해야 한다.",
        )
        result = sdd.validate_spec(broken)
        self.assertFalse(result["valid"])
        self.assertTrue(any("EC ID가 없는" in e["message"] for e in result["errors"]))

    def test_ec_non_contiguous_is_error(self):
        broken = VALID_SPEC.replace("**EC-1**", "**EC-2**")
        result = sdd.validate_spec(broken)
        self.assertFalse(result["valid"])
        self.assertTrue(any("EC 번호가 1부터" in e["message"] for e in result["errors"]))

    # --- 모호성 경고 ------------------------------------------------------

    def test_vague_ac_produces_warning_not_error(self):
        doc = VALID_SPEC.replace(
            "조건 A가 충족되면 시스템은 X를 반환해야 한다.",
            "빠르게 처리해야 한다.",
        )
        result = sdd.validate_spec(doc, path=Path(VALID_SPEC_PATH))
        self.assertTrue(result["valid"])  # 경고일 뿐 — 에러로 올리지 않는다
        self.assertTrue(any("모호하다" in w["message"] for w in result["warnings"]))

    def test_ac_without_condition_expression_warns(self):
        doc = VALID_SPEC.replace(
            "조건 A가 충족되면 시스템은 X를 반환해야 한다.", "뭔가 저장.",
        )
        result = sdd.validate_spec(doc, path=Path(VALID_SPEC_PATH))
        self.assertTrue(any("조건 표현이 없다" in w["message"] for w in result["warnings"]))


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
            root = _project_with_spec(tmp, "테스트-기능")
            result = sdd.cmd_phase(_ns(path=str(root), target="implement",
                                       spec="테스트-기능"))
            self.assertFalse(result["blocked"], result["reasons"])
            state = sdd.load_state(root)
            self.assertEqual(state["phase"], "implement")
            self.assertEqual(state["activeSpec"], "테스트-기능")

    def test_blocked_when_no_spec_and_no_active_spec(self):
        """--spec 없이 implement 로 넘어가면 예전에는 검증이 통째로 생략됐다."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".sdd").mkdir()
            sdd.write_json(root / ".sdd" / "config.json", DEFAULT_CONFIG)
            result = sdd.cmd_phase(_ns(path=str(root), target="implement", spec=None))
            self.assertTrue(result["blocked"])
            self.assertTrue(any("지정되지 않았다" in r for r in result["reasons"]))

    def test_falls_back_to_active_spec_when_spec_omitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project_with_spec(tmp, "테스트-기능")
            sdd.write_json(root / ".sdd" / "state.json", {
                "version": 1, "phase": "spec", "enforce": False,
                "activeSpec": "테스트-기능", "updatedAt": None,
            })
            result = sdd.cmd_phase(_ns(path=str(root), target="implement", spec=None))
            self.assertFalse(result["blocked"], result["reasons"])
            self.assertEqual(result["activeSpec"], "테스트-기능")

    def test_active_spec_fallback_still_validates(self):
        """폴백 경로도 검증을 우회하지 않는다."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".sdd").mkdir()
            sdd.write_json(root / ".sdd" / "config.json", DEFAULT_CONFIG)
            d = root / "specs" / "broken"
            d.mkdir(parents=True)
            (d / "spec-v1.md").write_text("# 불완전", encoding="utf-8")
            sdd.write_json(root / ".sdd" / "state.json", {
                "version": 1, "phase": "spec", "enforce": False,
                "activeSpec": "broken", "updatedAt": None,
            })
            result = sdd.cmd_phase(_ns(path=str(root), target="implement", spec=None))
            self.assertTrue(result["blocked"])


class TasksAndReportTests(unittest.TestCase):
    def test_tasks_prefills_ac_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project_with_spec(tmp, "테스트-기능")
            result = sdd.cmd_tasks(_ns(path=str(root), slug="테스트-기능"))
            self.assertTrue(result["created"])
            self.assertEqual(result["acIds"], ["AC-1", "AC-2"])
            body = (root / "specs" / "테스트-기능" / "tasks.md").read_text(encoding="utf-8")
            self.assertIn("AC-1", body)
            self.assertIn("AC-2", body)
            # 템플릿 메타 설명이 산출물로 새지 않는다
            self.assertNotIn("서브에이전트가 생성·갱신한다", body)

    def test_tasks_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project_with_spec(tmp, "테스트-기능")
            sdd.cmd_tasks(_ns(path=str(root), slug="테스트-기능"))
            again = sdd.cmd_tasks(_ns(path=str(root), slug="테스트-기능"))
            self.assertFalse(again["created"])

    def test_review_report_numbers_sequentially(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project_with_spec(tmp, "테스트-기능")
            first = sdd.cmd_review_report(_ns(path=str(root), slug="테스트-기능"))
            second = sdd.cmd_review_report(_ns(path=str(root), slug="테스트-기능"))
            self.assertEqual(first["seq"], 1)
            self.assertEqual(second["seq"], 2)
            body = (root / first["path"]).read_text(encoding="utf-8")
            self.assertIn("AC-1", body)
            self.assertIn("EC-1", body)


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


def _project_with_spec(tmp: str, slug: str) -> Path:
    """VALID_SPEC 이 담긴 유효한 SDD 프로젝트를 만든다 (프론트매터·경로 일치)."""
    root = Path(tmp)
    (root / ".sdd").mkdir(exist_ok=True)
    sdd.write_json(root / ".sdd" / "config.json", DEFAULT_CONFIG)
    d = root / "specs" / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "spec-v1.md").write_text(VALID_SPEC, encoding="utf-8")
    return root


def _ns(**kwargs):
    class NS:
        pass
    ns = NS()
    for k, v in kwargs.items():
        setattr(ns, k, v)
    return ns


if __name__ == "__main__":
    unittest.main()
