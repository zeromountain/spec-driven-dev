"""sdd.py 핵심 로직 단위 테스트. 외부 의존성·네트워크 없음."""
import shutil
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


def _init_project(tmp: str) -> Path:
    root = Path(tmp)
    sdd.cmd_init(_ns(path=str(root), enforce=False, specs=None, src=None, tests=None,
                     worktrees=False))
    return root


def _run(root: Path, feature=None, **kw):
    return sdd.cmd_run(_ns(path=str(root), feature=feature, slug=kw.get("slug"),
                           resume=kw.get("resume", False), restart=kw.get("restart", False),
                           max_attempts=kw.get("max_attempts", sdd.DEFAULT_MAX_ATTEMPTS),
                           depth=kw.get("depth"), spec=kw.get("spec"),
                           all=kw.get("all", False), worktree=kw.get("worktree"),
                           from_stage=kw.get("from_stage")))


def _next(root: Path, spec=None, all=False):
    return sdd.cmd_next(_ns(path=str(root), spec=spec, all=all))


def _advance(root: Path, result: dict, stage=None, spec=None):
    import json as _json
    return sdd.cmd_advance(_ns(path=str(root), result=_json.dumps(result), stage=stage,
                               spec=spec))


def _write_valid_spec(root: Path, rel_path: str, version: int = 1):
    """파이프라인이 만든 빈 명세 자리에 유효한 명세를 써넣는다 (아키텍트 역할 대역).

    프론트매터의 feature 는 파일이 놓인 디렉터리 이름과 같아야 validate 를 통과한다."""
    text = VALID_SPEC.replace("feature: 테스트-기능",
                              f"feature: {Path(rel_path).parent.name}")
    if version != 1:
        text = text.replace("version: 1", f"version: {version}")
    (root / rel_path).write_text(text, encoding="utf-8")


class PipelineTests(unittest.TestCase):
    """run → next → advance 상태머신. 흐름의 연속성이 상태 파일에만 의존하는지 본다."""

    def test_run_starts_and_next_calls_architect(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            started = _run(root, "테스트 기능")
            self.assertTrue(started["ok"])
            nxt = started["next"]
            self.assertEqual(nxt["action"], "call-agent")
            self.assertEqual(nxt["agent"], "spec-architect")
            self.assertEqual(nxt["stage"], "spec")
            spec_rel = nxt["context"]["specPath"]
            self.assertTrue((root / spec_rel).exists())
            self.assertEqual(sdd.load_state(root)["phase"], "spec")

    def test_next_is_idempotent(self):
        """next를 두 번 불러도 명세 파일이 두 개 생기지 않는다."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            _run(root, "테스트 기능")
            first = _next(root)["context"]["specPath"]
            second = _next(root)["context"]["specPath"]
            self.assertEqual(first, second)
            self.assertEqual(len(list((root / "specs" / "테스트-기능").glob("spec-v*.md"))), 1)

    def test_happy_path_to_approved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            spec_rel = _run(root, "테스트 기능")["next"]["context"]["specPath"]
            _write_valid_spec(root, spec_rel)

            after_spec = _advance(root, {"notes": "명세 완성"})
            self.assertEqual(after_spec["next"]["stage"], "implement")
            self.assertEqual(after_spec["next"]["agent"], "software-engineer")
            self.assertEqual(sdd.load_state(root)["phase"], "implement")
            self.assertTrue((root / "specs" / "테스트-기능" / "tasks.md").exists())

            after_impl = _advance(root, {"testResult": {"passed": 2, "failed": 0}})
            self.assertEqual(after_impl["next"]["stage"], "review")
            self.assertEqual(after_impl["next"]["action"], "call-agents")
            self.assertEqual(after_impl["next"]["roster"], ["spec-reviewer"])

            after_review = _advance(root, {"verdict": "approved"})
            self.assertEqual(after_review["next"]["action"], "done")
            self.assertEqual(after_review["pipeline"]["status"], "done")
            fm, _ = sdd.parse_frontmatter((root / spec_rel).read_text(encoding="utf-8"))
            self.assertEqual(fm["status"], "done")
            self.assertEqual(sdd.load_state(root)["phase"], "off")

    def test_invalid_spec_retries_then_halts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            _run(root, "테스트 기능", max_attempts=2)
            first = _advance(root, {})            # 플레이스홀더 그대로 → 검증 실패
            self.assertEqual(first["next"]["stage"], "spec")
            self.assertTrue(first["next"]["context"]["validateErrors"])
            _advance(root, {})
            third = _advance(root, {})
            self.assertEqual(third["next"]["action"], "halted")
            self.assertIn("명세 검증", third["pipeline"]["haltReason"])

    def test_review_gaps_reach_the_engineer(self):
        """리뷰 지적이 구현 단계 컨텍스트로 그대로 넘어간다."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            spec_rel = _run(root, "테스트 기능")["next"]["context"]["specPath"]
            _write_valid_spec(root, spec_rel)
            _advance(root, {})
            _advance(root, {"testResult": {"passed": 1, "failed": 0}, "notes": "구현함"})
            back = _advance(root, {"verdict": "changes-requested",
                                   "gaps": ["AC-2 테스트가 없다"]})
            self.assertEqual(back["next"]["stage"], "implement")
            self.assertEqual(back["next"]["context"]["reviewGaps"], ["AC-2 테스트가 없다"])
            self.assertIsNotNone(back["next"]["context"]["lastReviewPath"])

    def test_review_loop_halts_after_max_attempts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            spec_rel = _run(root, "테스트 기능", max_attempts=1)["next"]["context"]["specPath"]
            _write_valid_spec(root, spec_rel)
            _advance(root, {})
            for _ in range(2):
                _advance(root, {"testResult": {"passed": 1, "failed": 0}})
                last = _advance(root, {"verdict": "changes-requested", "gaps": ["여전히 갭"]})
            self.assertEqual(last["next"]["action"], "halted")
            self.assertIn("changes-requested", last["pipeline"]["haltReason"])

    def test_failing_tests_carry_forward_then_halt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            spec_rel = _run(root, "테스트 기능", max_attempts=1)["next"]["context"]["specPath"]
            _write_valid_spec(root, spec_rel)
            _advance(root, {})
            retry = _advance(root, {"testResult": {"failed": 3, "output": "boom"}})
            self.assertEqual(retry["next"]["stage"], "implement")
            self.assertEqual(retry["next"]["context"]["previousTestFailures"]["failed"], 3)
            halted = _advance(root, {"testResult": {"failed": 1}})
            self.assertEqual(halted["next"]["action"], "halted")

    def test_spec_change_request_creates_new_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            spec_rel = _run(root, "테스트 기능")["next"]["context"]["specPath"]
            _write_valid_spec(root, spec_rel)
            _advance(root, {})
            back = _advance(root, {"specChangeRequests": ["AC-3이 빠졌다"]})
            self.assertEqual(back["next"]["stage"], "spec")
            ctx = back["next"]["context"]
            self.assertTrue(ctx["specPath"].endswith("spec-v2.md"))
            self.assertEqual(ctx["previousSpecPath"], spec_rel)
            self.assertEqual(ctx["specChangeRequests"], ["AC-3이 빠졌다"])

    def test_tasks_refresh_on_new_spec_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            spec_rel = _run(root, "테스트 기능")["next"]["context"]["specPath"]
            _write_valid_spec(root, spec_rel)
            _advance(root, {})
            tasks = root / "specs" / "테스트-기능" / "tasks.md"
            self.assertIn("spec-v1 기준", tasks.read_text(encoding="utf-8"))
            _advance(root, {"specChangeRequests": ["범위 변경"]})
            _write_valid_spec(root, _next(root)["context"]["specPath"], version=2)
            _advance(root, {})
            self.assertIn("spec-v2 기준", tasks.read_text(encoding="utf-8"))

    def test_open_questions_pause_and_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            spec_rel = _run(root, "테스트 기능")["next"]["context"]["specPath"]
            paused = _advance(root, {"openQuestions": ["결혼여부는 필수인가?"]})
            self.assertEqual(paused["next"]["action"], "ask-user")
            self.assertEqual(paused["next"]["questions"], ["결혼여부는 필수인가?"])
            _write_valid_spec(root, spec_rel)
            answered = _advance(root, {"answers": {"결혼여부는 필수인가?": "선택 입력"}})
            self.assertEqual(answered["next"]["stage"], "spec")
            self.assertEqual(
                answered["next"]["context"]["userAnswers"], {"결혼여부는 필수인가?": "선택 입력"})

    def test_resume_reads_position_from_state_only(self):
        """대화 컨텍스트가 사라져도 state.json만으로 같은 자리에서 재개된다."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            spec_rel = _run(root, "테스트 기능")["next"]["context"]["specPath"]
            _write_valid_spec(root, spec_rel)
            _advance(root, {})
            resumed = _run(root)                      # 인자 없는 재개
            self.assertTrue(resumed["resumed"])
            self.assertEqual(resumed["next"]["stage"], "implement")
            self.assertEqual(resumed["next"]["context"]["specPath"], spec_rel)

    def test_resume_revives_a_halted_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            _run(root, "테스트 기능")
            sdd.cmd_abort(_ns(path=str(root), reason="잠깐 멈춤"))
            self.assertEqual(_next(root)["action"], "halted")
            revived = _run(root, resume=True)
            self.assertEqual(revived["next"]["action"], "call-agent")
            self.assertEqual(revived["pipeline"]["status"], "running")

    def test_revive_resets_the_retry_budget(self):
        """상한에 걸려 멈춘 파이프라인을 되살리면 재시도 예산이 돌아온다."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            _run(root, "테스트 기능", max_attempts=1)
            _advance(root, {})
            halted = _advance(root, {})
            self.assertEqual(halted["next"]["action"], "halted")
            revived = _run(root, resume=True)
            self.assertEqual(revived["pipeline"]["attempts"]["spec"], 0)
            self.assertEqual(revived["next"]["attempt"], 1)

    def test_revive_still_bounded_by_step_cap(self):
        """되살리기를 반복해도 전체 전이 상한은 계속 막는다."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            _run(root, "테스트 기능", max_attempts=1)
            last = None
            for _ in range(sdd.MAX_PIPELINE_STEPS + 4):
                last = _advance(root, {})
                if "수렴하지 않는다" in (last["pipeline"]["haltReason"] or ""):
                    break
                if last["next"]["action"] == "halted":
                    _run(root, resume=True)
            self.assertIn("수렴하지 않는다", last["pipeline"]["haltReason"])

    def test_different_slug_starts_alongside(self):
        """다른 기능은 막히지 않고 함께 시작된다 — 이게 병렬 실행의 진입점이다."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            _run(root, "테스트 기능")
            second = _run(root, "다른 기능")
            self.assertTrue(second["ok"])
            self.assertEqual(second["slug"], "다른-기능")
            self.assertEqual(sdd.board(root)["counts"]["live"], 2)

    def test_same_slug_needs_restart_or_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            _run(root, "테스트 기능")
            clash = _run(root, "테스트 기능")
            self.assertFalse(clash["ok"])
            self.assertIn("이미 진행 중", clash["reason"])
            fresh = _run(root, "테스트 기능", restart=True)
            self.assertTrue(fresh["started"])
            self.assertEqual(len(sdd.load_state(root)["pipelineHistory"]), 1)

    def test_reopen_review_applies_the_new_roster(self):
        """플러그인 업그레이드로 리뷰어가 늘었을 때 명세·구현을 그대로 두고 리뷰만 다시 연다."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            spec_rel = _run(root, "테스트 기능")["next"]["context"]["specPath"]
            _write_valid_spec(root, spec_rel)
            _advance(root, {})
            _advance(root, {"testResult": {"passed": 1, "failed": 0}})
            _advance(root, {"verdict": "approved"})
            self.assertEqual(_next(root)["action"], "done")
            first_report = sdd.load_pipelines(sdd.load_state(root))["테스트-기능"]["reviewPath"]

            out = _run(root, from_stage="review", spec="테스트-기능", depth="deep")
            self.assertTrue(out["ok"])
            self.assertEqual(out["from"], {"stage": "done", "status": "done"})
            self.assertEqual(out["rosterBefore"], ["spec-reviewer"])
            self.assertEqual(out["roster"], ["spec-reviewer", "code-reviewer"])
            self.assertEqual(out["next"]["action"], "call-agents")
            # 리포트는 새로 만든다 — 낡은 리포트에는 새 리뷰어 절이 없다
            reopened = sdd.load_pipelines(sdd.load_state(root))["테스트-기능"]
            self.assertNotEqual(reopened["reviewPath"], first_report)
            # 명세는 건드리지 않았다
            self.assertTrue((root / spec_rel).exists())

    def test_reopen_needs_an_existing_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            out = _run(root, from_stage="review", spec="없는-기능")
            self.assertFalse(out["ok"])
            self.assertIn("파이프라인이 없다", out["reason"])

    def test_reopen_implement_keeps_the_spec_version(self):
        """--restart 와 달리 명세 버전을 올리지 않는다."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            spec_rel = _run(root, "테스트 기능")["next"]["context"]["specPath"]
            _write_valid_spec(root, spec_rel)
            _advance(root, {})
            _advance(root, {"testResult": {"passed": 1, "failed": 0}})
            out = _run(root, from_stage="implement", spec="테스트-기능")
            self.assertEqual(out["next"]["stage"], "implement")
            self.assertEqual(out["next"]["context"]["specPath"], spec_rel)
            self.assertEqual(
                len(list((root / "specs" / "테스트-기능").glob("spec-v*.md"))), 1)

    def test_review_report_is_rebuilt_when_deleted(self):
        """리포트를 지우고 재개하면 새로 만든다 — 없는 파일을 채우라고 시키지 않는다."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            spec_rel = _run(root, "테스트 기능")["next"]["context"]["specPath"]
            _write_valid_spec(root, spec_rel)
            _advance(root, {})
            _advance(root, {"testResult": {"passed": 1, "failed": 0}})
            first = _next(root)["agents"][0]["context"]["reviewPath"]
            self.assertTrue((root / first).exists())

            (root / first).unlink()
            again = _next(root)["agents"][0]["context"]["reviewPath"]
            self.assertTrue((root / again).exists())
            body = (root / again).read_text(encoding="utf-8")
            self.assertIn("AC-1", body)

    def test_advance_rejects_stage_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            _run(root, "테스트 기능")
            bad = _advance(root, {"verdict": "approved"}, stage="review")
            self.assertFalse(bad["ok"])
            self.assertIn("단계가 어긋났다", bad["reason"])

    def test_unreadable_verdict_halts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            spec_rel = _run(root, "테스트 기능")["next"]["context"]["specPath"]
            _write_valid_spec(root, spec_rel)
            _advance(root, {})
            _advance(root, {"testResult": {"passed": 1, "failed": 0}})
            # 판정을 읽을 수 없으면 그 리뷰어만 다시 부른다 (라운드 전체를 버리지 않는다)
            again = _advance(root, {"notes": "좋아 보인다"})
            self.assertEqual(again["next"]["action"], "call-agents")
            self.assertEqual(again["next"]["roster"], ["spec-reviewer"])
            # 같은 요청을 무한 반복하지는 않는다 — 상한에 걸리면 멈춘다
            _advance(root, {"notes": "여전히 판정 없음"})
            halted = _advance(root, {"notes": "여전히 판정 없음"})
            self.assertEqual(halted["next"]["action"], "halted")
            self.assertIn("리뷰 판정", halted["pipeline"]["haltReason"])

    def test_step_cap_halts_runaway_loop(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            spec_rel = _run(root, "테스트 기능", max_attempts=99)["next"]["context"]["specPath"]
            _write_valid_spec(root, spec_rel)
            _advance(root, {})
            last = None
            for _ in range(sdd.MAX_PIPELINE_STEPS + 2):
                last = _advance(root, {"testResult": {"passed": 1, "failed": 0}})
                if last["next"]["action"] == "halted":
                    break
                last = _advance(root, {"verdict": "changes-requested", "gaps": ["갭"]})
                if last["next"]["action"] == "halted":
                    break
            self.assertEqual(last["next"]["action"], "halted")
            self.assertIn("수렴하지 않는다", last["pipeline"]["haltReason"])

    def test_next_without_pipeline_and_without_init(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(_next(root)["action"], "init-required")
            _init_project(root)
            self.assertEqual(_next(root)["action"], "none")

    def test_status_exposes_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            _run(root, "테스트 기능")
            st = sdd.cmd_status(_ns(path=str(root)))
            self.assertEqual(st["pipeline"]["stage"], "spec")
            self.assertEqual(st["pipeline"]["feature"], "테스트 기능")

    def test_advance_accepts_fenced_json(self):
        """서브에이전트가 ```json 펜스를 붙여도 결과를 읽는다."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            _run(root, "테스트 기능")
            res = sdd.cmd_advance(_ns(path=str(root), stage=None,
                                      result='```json\n{"openQuestions": ["q"]}\n```'))
            self.assertTrue(res["ok"])
            self.assertEqual(res["next"]["action"], "ask-user")



class DepthTests(unittest.TestCase):
    """어떤 서브에이전트를 부를지는 모델이 아니라 decide_depth 가 정한다."""

    def test_plain_feature_is_light(self):
        r = sdd.decide_depth(feature_text="버튼 색상을 파란색으로 바꾼다")
        self.assertEqual(r["depth"], "light")
        self.assertEqual(r["agents"]["spec"], ["spec-architect"])
        self.assertEqual(r["agents"]["implement"], ["software-engineer"])
        self.assertEqual(r["agents"]["review"], ["spec-reviewer"])

    def test_security_keyword_forces_deep_and_attaches_reviewer(self):
        r = sdd.decide_depth(feature_text="로그인 토큰 만료 처리")
        self.assertEqual(r["depth"], "deep")
        self.assertIn("security-reviewer", r["agents"]["review"])
        self.assertNotIn("perf-reviewer", r["agents"]["review"])

    def test_numeric_latency_is_a_perf_signal(self):
        r = sdd.decide_depth(feature_text="업로드 응답은 3초 이내여야 한다")
        self.assertIn("perf-reviewer", r["agents"]["review"])
        r2 = sdd.decide_depth(feature_text="3초짜리 애니메이션 추가")
        self.assertEqual(r2["signals"]["perfHits"], [])

    def test_signal_reviewer_survives_force_light(self):
        """경량을 강제해도 보안 신호가 있으면 보안 리뷰어는 붙는다."""
        r = sdd.decide_depth(feature_text="비밀번호 재설정", force="light")
        self.assertEqual(r["depth"], "light")
        self.assertEqual(r["agents"]["implement"], ["software-engineer"])
        self.assertIn("security-reviewer", r["agents"]["review"])

    def test_out_of_scope_keywords_are_not_signals(self):
        """VALID_SPEC 의 범위 밖은 '인증 기능은 다루지 않는다' — 신호가 아니다."""
        r = sdd.decide_depth(spec_text=VALID_SPEC)
        self.assertEqual(r["signals"]["securityHits"], [])
        self.assertEqual(r["depth"], "light")

    def test_template_boilerplate_is_not_a_signal(self):
        """빈 명세가 자기 안내문({{성능/보안...}}) 때문에 deep 이 되면 안 된다."""
        blank = sdd.fill_template("spec.md", {"slug": "x", "version": "1",
                                              "createdAt": "now", "제목": "테스트"})
        r = sdd.decide_depth(spec_text=blank)
        self.assertEqual(r["signals"]["securityHits"], [])
        self.assertEqual(r["signals"]["perfHits"], [])
        self.assertEqual(r["depth"], "light")

    def test_many_acs_cross_threshold(self):
        acs = "\n".join(f"- [ ] **AC-{i}**: 조건 {i}이 충족되면 값을 반환해야 한다."
                        for i in range(1, 9))
        spec = VALID_SPEC.replace(
            "- [ ] **AC-1**: 조건 A가 충족되면 시스템은 X를 반환해야 한다.\n"
            "- [ ] **AC-2**: 조건 B에서 오류가 발생하면 안 된다.", acs)
        r = sdd.decide_depth(spec_text=spec)
        self.assertEqual(r["signals"]["acCount"], 8)
        self.assertEqual(r["depth"], "deep")

    def test_roster_is_not_shared_between_calls(self):
        """agents 를 얕게 복사하면 신호 리뷰어가 전역 상수에 누적된다."""
        sdd.decide_depth(feature_text="로그인 토큰")
        r = sdd.decide_depth(feature_text="버튼 색상 변경")
        self.assertEqual(r["agents"]["review"], ["spec-reviewer"])
        self.assertEqual(sdd.AGENT_ROSTER["deep"]["review"],
                         ["spec-reviewer", "code-reviewer"])


class CombineVerdictsTests(unittest.TestCase):
    """리뷰어 판정은 평균이 아니라 최악값으로 합쳐진다."""

    def test_one_changes_requested_decides_all(self):
        c = sdd.combine_verdicts([
            {"agent": "spec-reviewer", "verdict": "approved"},
            {"agent": "code-reviewer", "verdict": "approved"},
            {"agent": "security-reviewer", "verdict": "changes-requested",
             "gaps": ["소유권 검사가 없다"]},
        ])
        self.assertEqual(c["verdict"], "changes-requested")
        self.assertTrue(any("security-reviewer" in g for g in c["gaps"]))

    def test_all_approved_is_approved(self):
        c = sdd.combine_verdicts([{"agent": "spec-reviewer", "verdict": "approved"}])
        self.assertEqual(c["verdict"], "approved")

    def test_only_high_findings_become_gaps(self):
        c = sdd.combine_verdicts([{
            "agent": "code-reviewer", "verdict": "approved",
            "findings": [{"severity": "high", "issue": "빈 catch", "file": "src/a.ts", "line": 9},
                         {"severity": "low", "issue": "네이밍"}],
        }])
        self.assertEqual(len(c["highFindings"]), 1)
        self.assertIn("src/a.ts:9", c["highFindings"][0])
        self.assertEqual(len(c["softFindings"]), 1)

    def test_unreadable_verdict_is_reported(self):
        c = sdd.combine_verdicts([{"agent": "code-reviewer", "verdict": "괜찮음"}])
        self.assertEqual(c["unreadable"], ["code-reviewer"])


class RosterPipelineTests(unittest.TestCase):
    """깊은 모드에서 파이프라인이 단계 안의 역할을 순서대로 걸어간다."""

    def test_deep_walks_spec_roster_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            started = _run(root, "테스트 기능", depth="deep")
            self.assertEqual(started["depth"]["depth"], "deep")
            self.assertEqual(_next(root)["agent"], "spec-researcher")

            after = _advance(root, {"contextPack": {"relatedFiles": []}})
            self.assertEqual(after["next"]["agent"], "spec-architect")
            self.assertEqual(after["next"]["context"]["contextPack"], {"relatedFiles": []})

            _write_valid_spec(root, _next(root)["context"]["specPath"])
            after = _advance(root, {"openQuestions": []})
            self.assertEqual(after["next"]["agent"], "spec-auditor")

            after = _advance(root, {"verdict": "accepted"})
            self.assertEqual(after["next"]["stage"], "implement")
            self.assertEqual(after["next"]["agent"], "impl-planner")

    def test_auditor_revision_returns_to_architect(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            _run(root, "테스트 기능", depth="deep")
            _advance(root, {"contextPack": {}})
            _write_valid_spec(root, _next(root)["context"]["specPath"])
            _advance(root, {"openQuestions": []})            # → auditor

            after = _advance(root, {"verdict": "revision-requested",
                                    "acFindings": [{"ac": "AC-1", "testable": False}]})
            self.assertEqual(after["next"]["agent"], "spec-architect")
            self.assertTrue(after["next"]["context"]["auditFindings"]["acFindings"])

    def test_auditor_loop_halts_at_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            _run(root, "테스트 기능", depth="deep", max_attempts=2)
            _advance(root, {"contextPack": {}})
            _write_valid_spec(root, _next(root)["context"]["specPath"])
            for _ in range(3):
                _advance(root, {"openQuestions": []})                 # architect
                out = _advance(root, {"verdict": "revision-requested"})  # auditor
            self.assertEqual(out["next"]["action"], "halted")
            self.assertIn("명세 감사", out["pipeline"]["haltReason"])

    def test_deep_implement_splits_engineer_and_tester(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            _run(root, "테스트 기능", depth="deep")
            _advance(root, {"contextPack": {}})
            _write_valid_spec(root, _next(root)["context"]["specPath"])
            _advance(root, {"openQuestions": []})
            _advance(root, {"verdict": "accepted"})                    # → impl-planner

            after = _advance(root, {"tasks": [{"id": "T-1"}],
                                    "testRunner": {"command": "pytest"}})
            self.assertEqual(after["next"]["agent"], "software-engineer")
            self.assertEqual(after["next"]["context"]["mode"], "deep")
            self.assertIn("테스트 파일은 쓰지 마라", after["next"]["instruction"])
            self.assertEqual(after["next"]["context"]["plan"]["tasks"], [{"id": "T-1"}])

            after = _advance(root, {"filesChanged": ["src/a.py"]})
            self.assertEqual(after["next"]["agent"], "test-engineer")

            after = _advance(root, {"testResult": {"passed": 2, "failed": 0}})
            self.assertEqual(after["next"]["stage"], "review")

    def test_test_engineer_failure_returns_to_engineer_not_itself(self):
        """테스트 작성자가 실패를 내면 테스트를 고치는 게 아니라 구현자에게 돌아간다."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            _run(root, "테스트 기능", depth="deep")
            _advance(root, {"contextPack": {}})
            _write_valid_spec(root, _next(root)["context"]["specPath"])
            _advance(root, {"openQuestions": []})
            _advance(root, {"verdict": "accepted"})
            _advance(root, {"tasks": []})
            _advance(root, {"filesChanged": ["src/a.py"]})              # → test-engineer

            after = _advance(root, {"testResult": {"passed": 1, "failed": 1},
                                    "implementationDefects": [{"ac": "AC-2"}]})
            self.assertEqual(after["next"]["agent"], "software-engineer")
            self.assertTrue(after["next"]["context"]["implementationDefects"])
            self.assertIn("테스트를 고쳐서 통과시키지 마라", after["next"]["instruction"])

    def test_reviewers_are_called_together_and_combined(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            _run(root, "테스트 기능", depth="deep")
            _advance(root, {"contextPack": {}})
            _write_valid_spec(root, _next(root)["context"]["specPath"])
            _advance(root, {"openQuestions": []})
            _advance(root, {"verdict": "accepted"})
            _advance(root, {"tasks": []})
            _advance(root, {"filesChanged": ["src/a.py"]})
            after = _advance(root, {"testResult": {"passed": 2, "failed": 0}})

            nxt = after["next"]
            self.assertEqual(nxt["action"], "call-agents")
            self.assertEqual(nxt["roster"], ["spec-reviewer", "code-reviewer"])
            self.assertIn("동시에", nxt["concurrency"])

            after = _advance(root, {"reviews": [
                {"agent": "spec-reviewer", "verdict": "approved"},
                {"agent": "code-reviewer", "verdict": "changes-requested",
                 "gaps": ["빈 catch"]},
            ]})
            self.assertEqual(after["next"]["stage"], "implement")
            # 갭은 구현 수준이다 — 계획자를 다시 태우지 않는다
            self.assertEqual(after["next"]["agent"], "software-engineer")
            self.assertTrue(any("code-reviewer" in g
                                for g in after["next"]["context"]["reviewGaps"]))

    def test_partial_reviews_accumulate_and_ask_only_the_missing(self):
        """일부만 와도 버리지 않는다 — 남은 리뷰어만 다시 부르고, 종합은 전원이 모여야 한다."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            _run(root, "테스트 기능", depth="deep")
            _advance(root, {"contextPack": {}})
            _write_valid_spec(root, _next(root)["context"]["specPath"])
            _advance(root, {"openQuestions": []})
            _advance(root, {"verdict": "accepted"})
            _advance(root, {"tasks": []})
            _advance(root, {"filesChanged": []})
            _advance(root, {"testResult": {"passed": 1, "failed": 0}})

            out = _advance(root, {"reviews": [
                {"agent": "spec-reviewer", "verdict": "approved"}]})
            # 종합하지 않고 남은 리뷰어만 다시 부른다
            self.assertEqual(out["next"]["action"], "call-agents")
            self.assertEqual(out["next"]["roster"], ["code-reviewer"])
            self.assertEqual(out["next"]["alreadyReported"], ["spec-reviewer"])
            self.assertEqual(out["pipeline"]["stage"], "review")

            # 나머지가 오면 그때 종합된다 — 먼저 온 판정도 살아 있다
            done = _advance(root, {"reviews": [
                {"agent": "code-reviewer", "verdict": "changes-requested",
                 "gaps": ["빈 catch"]}]})
            self.assertEqual(done["next"]["stage"], "implement")
            self.assertTrue(any("code-reviewer" in g
                                for g in done["next"]["context"]["reviewGaps"]))

    def test_unnamed_verdict_cannot_stand_in_for_the_roster(self):
        """리뷰어가 여럿인데 이름 없는 판정 하나로 단계를 끝내면 한 명이 나머지를 승인한다."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            _run(root, "테스트 기능", depth="deep")
            _advance(root, {"contextPack": {}})
            _write_valid_spec(root, _next(root)["context"]["specPath"])
            _advance(root, {"openQuestions": []})
            _advance(root, {"verdict": "accepted"})
            _advance(root, {"tasks": []})
            _advance(root, {"filesChanged": []})
            _advance(root, {"testResult": {"passed": 1, "failed": 0}})

            out = _advance(root, {"verdict": "approved"})
            self.assertEqual(out["next"]["action"], "halted")
            self.assertIn("누구의 판정인지", out["pipeline"]["haltReason"])
            self.assertNotEqual(out["pipeline"]["status"], "done")

    def test_light_path_is_unchanged(self):
        """경량 모드는 예전과 같은 3단계 그대로다."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            self.assertEqual(_run(root, "테스트 기능")["depth"]["depth"], "light")
            self.assertEqual(_next(root)["agent"], "spec-architect")

    def test_forced_depth_survives_stage_transitions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            _run(root, "테스트 기능", depth="deep")
            _advance(root, {"contextPack": {}})
            _write_valid_spec(root, _next(root)["context"]["specPath"])
            _advance(root, {"openQuestions": []})
            after = _advance(root, {"verdict": "accepted"})
            # VALID_SPEC 자체는 light 로 판정되지만 --depth deep 이 유지돼야 한다
            self.assertEqual(after["pipeline"]["depth"], "deep")
            self.assertEqual(after["next"]["agent"], "impl-planner")


class ParallelPipelineTests(unittest.TestCase):
    """여러 기능을 동시에. 병렬성의 한계는 페이즈 게이트와 파일 겹침에서 온다."""

    def _two(self, tmp, enforce=False):
        root = Path(tmp)
        sdd.cmd_init(_ns(path=str(root), enforce=enforce, specs=None, src=None, tests=None))
        _run(root, "기능 하나")
        _run(root, "기능 둘")
        return root

    def test_next_all_returns_both_when_gate_is_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._two(tmp)
            batch = sdd.cmd_next(_ns(path=str(root), spec=None, all=True))
            self.assertEqual(batch["action"], "batch")
            self.assertEqual(len(batch["round"]), 2)
            self.assertEqual({a["slug"] for a in batch["round"]}, {"기능-하나", "기능-둘"})
            self.assertEqual(batch["waiting"], [])
            self.assertIn("동시에", batch["concurrency"])

    def test_ambiguous_next_asks_which_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._two(tmp)
            out = sdd.cmd_next(_ns(path=str(root), spec=None, all=False))
            self.assertEqual(out["action"], "choose-pipeline")
            self.assertEqual(sorted(out["live"]), ["기능-둘", "기능-하나"])

    def test_next_with_spec_targets_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._two(tmp)
            out = sdd.cmd_next(_ns(path=str(root), spec="기능-둘", all=False))
            self.assertEqual(out["action"], "call-agent")
            self.assertEqual(out["pipeline"]["slug"], "기능-둘")

    def test_advance_requires_spec_when_ambiguous(self):
        """잘못 넘기면 다른 기능의 상태가 그 결과로 전이된다 — 추측하지 않는다."""
        with tempfile.TemporaryDirectory() as tmp:
            root = self._two(tmp)
            out = _advance(root, {"openQuestions": []})
            self.assertFalse(out["ok"])
            self.assertIn("--spec", out["reason"])

    def test_advance_routes_to_named_pipeline_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._two(tmp)
            spec_rel = sdd.cmd_next(_ns(path=str(root), spec="기능-하나",
                                        all=False))["context"]["specPath"]
            _write_valid_spec(root, spec_rel)
            out = _advance(root, {"openQuestions": []}, spec="기능-하나")
            self.assertEqual(out["slug"], "기능-하나")
            self.assertEqual(out["next"]["stage"], "implement")
            pipes = sdd.load_pipelines(sdd.load_state(root))
            self.assertEqual(pipes["기능-둘"]["stage"], "spec")   # 옆 파이프라인은 그대로

    def test_enforce_serializes_across_phases(self):
        """게이트가 켜져 있으면 페이즈가 다른 파이프라인은 기다린다."""
        with tempfile.TemporaryDirectory() as tmp:
            root = self._two(tmp, enforce=True)
            spec_rel = sdd.cmd_next(_ns(path=str(root), spec="기능-하나",
                                        all=False))["context"]["specPath"]
            _write_valid_spec(root, spec_rel)
            _advance(root, {"openQuestions": []}, spec="기능-하나")   # → implement

            batch = sdd.cmd_next(_ns(path=str(root), spec=None, all=True))
            slugs = [a["slug"] for a in batch["round"]]
            waiting = [w["slug"] for w in batch["waiting"]]
            self.assertEqual(len(slugs), 1)
            self.assertEqual(len(waiting), 1)
            self.assertNotEqual(slugs[0], waiting[0])
            self.assertIn("페이즈 게이트", batch["waiting"][0]["reason"])

    def test_enforce_runs_same_phase_together(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._two(tmp, enforce=True)
            batch = sdd.cmd_next(_ns(path=str(root), spec=None, all=True))
            self.assertEqual(len(batch["round"]), 2)      # 둘 다 spec 단계다
            self.assertEqual(batch["waiting"], [])

    def test_phase_moves_on_when_nobody_can_act(self):
        """현재 페이즈에서 아무도 못 움직이면 게이트가 기다리는 쪽으로 넘어간다."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sdd.cmd_init(_ns(path=str(root), enforce=True, specs=None, src=None,
                             tests=None, worktrees=False))
            _run(root, "기능 하나")
            spec_rel = _next(root)["context"]["specPath"]
            _write_valid_spec(root, spec_rel)
            _advance(root, {"openQuestions": []})        # 유일한 파이프라인 → implement
            sdd.transition_phase(root, "spec")           # 페이즈만 spec 으로 되돌려 놓는다
            batch = sdd.cmd_next(_ns(path=str(root), spec=None, all=True))
            self.assertEqual(batch["waiting"], [])
            self.assertEqual(batch["round"][0]["stage"], "implement")

    def test_overlapping_implement_files_serialize(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sdd.cmd_init(_ns(path=str(root), enforce=False, specs=None, src=None,
                             tests=None, worktrees=False))
            for name in ("기능 하나", "기능 둘"):
                _run(root, name)
            state = sdd.load_state(root)
            pipes = sdd.load_pipelines(state)
            for slug in pipes:
                pipes[slug]["stage"] = "implement"
                pipes[slug]["carry"]["plan"] = {"tasks": [{"files": ["src/shared.py"]}]}
            sdd._store_pipelines(state, pipes)
            sdd.write_json(root / ".sdd" / "state.json", state)

            sched = sdd.schedule(root)
            self.assertEqual(len(sched["runnable"]), 1)
            self.assertEqual(len(sched["waiting"]), 1)
            self.assertIn("같은 파일", sched["waiting"][0]["reason"])

    def test_disjoint_implement_files_run_together(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sdd.cmd_init(_ns(path=str(root), enforce=False, specs=None, src=None,
                             tests=None, worktrees=False))
            for name in ("기능 하나", "기능 둘"):
                _run(root, name)
            state = sdd.load_state(root)
            pipes = sdd.load_pipelines(state)
            for slug, f in zip(sorted(pipes), ("src/a.py", "src/b.py")):
                pipes[slug]["stage"] = "implement"
                pipes[slug]["carry"]["plan"] = {"tasks": [{"files": [f]}]}
            sdd._store_pipelines(state, pipes)
            sdd.write_json(root / ".sdd" / "state.json", state)

            sched = sdd.schedule(root)
            self.assertEqual(len(sched["runnable"]), 2)

    def test_unplanned_implement_serializes(self):
        """계획이 없으면 파일 범위를 모른다 — 추측으로 동시에 돌리지 않는다."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sdd.cmd_init(_ns(path=str(root), enforce=False, specs=None, src=None,
                             tests=None, worktrees=False))
            for name in ("기능 하나", "기능 둘"):
                _run(root, name)
            state = sdd.load_state(root)
            pipes = sdd.load_pipelines(state)
            for slug in pipes:
                pipes[slug]["stage"] = "implement"
            sdd._store_pipelines(state, pipes)
            sdd.write_json(root / ".sdd" / "state.json", state)

            sched = sdd.schedule(root)
            self.assertEqual(len(sched["runnable"]), 1)
            self.assertIn("계획이 없어", sched["waiting"][0]["reason"])

    def test_legacy_single_pipeline_state_migrates(self):
        """0.5.0 이전 state.json 은 pipeline 하나만 갖고 있다."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            _run(root, "옛날 기능")
            state = sdd.load_state(root)
            legacy = state["pipelines"]["옛날-기능"]
            sdd.write_json(root / ".sdd" / "state.json", {
                "version": 1, "phase": "spec", "enforce": False,
                "activeSpec": "옛날-기능", "pipeline": legacy, "updatedAt": None,
            })
            self.assertEqual(sorted(sdd.load_pipelines(sdd.load_state(root))), ["옛날-기능"])
            self.assertEqual(_next(root)["pipeline"]["slug"], "옛날-기능")

    def test_abort_all_stops_every_live_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._two(tmp)
            out = sdd.cmd_abort(_ns(path=str(root), reason="정리", spec=None, all=True))
            self.assertEqual(sorted(out["aborted"]), ["기능-둘", "기능-하나"])
            self.assertEqual(sdd.board(root)["counts"]["live"], 0)

    def test_run_all_opens_the_batch_loop(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._two(tmp)
            out = _run(root, all=True)
            self.assertTrue(out["ok"])
            self.assertTrue(out["all"])
            self.assertEqual(out["live"], 2)
            self.assertEqual(out["next"]["action"], "batch")
            self.assertEqual({a["slug"] for a in out["next"]["round"]},
                             {"기능-하나", "기능-둘"})

    def test_run_all_does_not_resume_halted_without_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._two(tmp)
            sdd.cmd_abort(_ns(path=str(root), reason="테스트", spec="기능-둘", all=False))
            out = _run(root, all=True)
            self.assertEqual(out["live"], 1)
            self.assertEqual(out["revived"], [])
            self.assertEqual([a["slug"] for a in out["next"]["round"]], ["기능-하나"])

    def test_run_all_resume_revives_halted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._two(tmp)
            sdd.cmd_abort(_ns(path=str(root), reason="테스트", spec=None, all=True))
            out = _run(root, all=True, resume=True)
            self.assertEqual(sorted(out["revived"]), ["기능-둘", "기능-하나"])
            self.assertEqual(out["live"], 2)

    def test_run_all_with_nothing_live_explains(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._two(tmp)
            sdd.cmd_abort(_ns(path=str(root), reason="테스트", spec=None, all=True))
            out = _run(root, all=True)
            self.assertFalse(out["ok"])
            self.assertIn("--resume", out["reason"])

    def test_run_feature_with_all_starts_then_batches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._two(tmp)
            out = _run(root, "기능 셋", all=True)
            self.assertEqual(out["slug"], "기능-셋")
            self.assertEqual(out["next"]["action"], "batch")
            self.assertEqual(len(out["next"]["round"]), 3)

    def test_board_lists_every_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._two(tmp)
            b = sdd.board(root)
            self.assertEqual(b["counts"], {"total": 2, "live": 2, "runnable": 2, "waiting": 0})
            self.assertTrue(all(r["scheduled"] == "runnable" for r in b["pipelines"]))


def _git_project(tmp: str, enforce=False, worktrees=True) -> Path:
    """커밋이 하나 있는 실제 git 저장소 위에 SDD 를 깐다."""
    import subprocess
    root = Path(tmp)
    (root / "src").mkdir(exist_ok=True)
    (root / "tests").mkdir(exist_ok=True)
    (root / "README.md").write_text("# demo\n", encoding="utf-8")
    # git 은 빈 디렉터리를 추적하지 않는다 — 파일이 있어야 워크트리에도 생긴다
    (root / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
    for args in (["init", "-q"], ["config", "user.email", "t@t"],
                 ["config", "user.name", "t"], ["add", "-A"], ["commit", "-qm", "init"]):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    sdd.cmd_init(_ns(path=str(root), enforce=enforce, specs=None, src=None,
                     tests=None, worktrees=worktrees))
    return root


@unittest.skipUnless(shutil.which("git"), "git 이 없다")
class WorktreeTests(unittest.TestCase):
    """기능마다 독립된 작업 디렉터리. 병렬 실행의 두 병목을 한 번에 없앤다."""

    def test_run_creates_a_worktree_per_feature(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _git_project(tmp)
            a = _run(root, "기능 하나")
            b = _run(root, "기능 둘")
            self.assertEqual(a["worktree"]["rel"], ".sdd/worktrees/기능-하나")
            self.assertEqual(b["worktree"]["branch"], "sdd/기능-둘")
            self.assertTrue((root / a["worktree"]["rel"] / "README.md").exists())
            self.assertTrue((root / b["worktree"]["rel"] / "README.md").exists())

    def test_worktrees_dir_is_gitignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _git_project(tmp)
            _run(root, "기능 하나")
            self.assertIn("worktrees/",
                          (root / ".sdd" / ".gitignore").read_text(encoding="utf-8"))

    def test_worktree_lifts_phase_coupling(self):
        """enforce:true 여도 워크트리를 쓰면 페이즈가 달라도 함께 돈다."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _git_project(tmp, enforce=True)
            _run(root, "기능 하나")
            _run(root, "기능 둘")
            _write_valid_spec(root, _next(root, spec="기능-하나")["context"]["specPath"])
            _advance(root, {"openQuestions": []}, spec="기능-하나")
            sched = sdd.schedule(root)
            self.assertEqual(len(sched["runnable"]), 2)
            self.assertEqual(sched["waiting"], [])

    def test_worktree_lifts_file_overlap_serialization(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _git_project(tmp)
            for name in ("기능 하나", "기능 둘"):
                _run(root, name)
            state = sdd.load_state(root)
            pipes = sdd.load_pipelines(state)
            for slug in pipes:
                pipes[slug]["stage"] = "implement"
                pipes[slug]["carry"]["plan"] = {"tasks": [{"files": ["src/shared.py"]}]}
            sdd._store_pipelines(state, pipes)
            sdd.write_json(root / ".sdd" / "state.json", state)
            self.assertEqual(len(sdd.schedule(root)["runnable"]), 2)

    def test_implement_context_points_at_the_worktree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _git_project(tmp)
            _run(root, "기능 하나")
            _write_valid_spec(root, _next(root)["context"]["specPath"])
            _advance(root, {"openQuestions": []})
            ctx = _next(root)["context"]
            self.assertTrue(ctx["workdir"].endswith(".sdd/worktrees/기능-하나"))
            self.assertEqual(ctx["worktree"]["branch"], "sdd/기능-하나")
            # 명세는 본체에 남는다 — 상태가 흩어지면 재개가 깨진다
            self.assertTrue((root / ctx["specPath"]).exists())

    def test_trace_scans_the_worktree_tests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _git_project(tmp)
            _run(root, "기능 하나")
            _write_valid_spec(root, _next(root)["context"]["specPath"])
            wt = root / ".sdd" / "worktrees" / "기능-하나" / "tests"
            wt.mkdir(parents=True, exist_ok=True)
            (wt / "test_a.py").write_text("# AC-1\ndef test_a(): pass\n", encoding="utf-8")
            # 워크트리를 스캔하면 AC-1 이 잡힌다 (AC-2 는 태깅하지 않았다)
            rep = sdd.build_review_report(root, "기능-하나", workdir=wt.parent)
            self.assertEqual(rep["uncovered"], ["AC-2"])
            self.assertEqual(rep["coverage"], 0.5)
            # 본체를 스캔하면 아무것도 못 찾는다 — 실제로 워크트리를 본 것이다
            main = sdd.build_review_report(root, "기능-하나", workdir=root)
            self.assertEqual(main["coverage"], 0.0)

    def test_hook_resolves_worktree_writes_per_pipeline(self):
        """전역 phase 가 아니라 그 워크트리를 가진 파이프라인의 단계로 판정한다."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _git_project(tmp, enforce=True)
            _run(root, "기능 하나")
            _run(root, "기능 둘")
            _write_valid_spec(root, _next(root, spec="기능-하나")["context"]["specPath"])
            _advance(root, {"openQuestions": []}, spec="기능-하나")

            state, config = sdd.load_state(root), sdd.load_config(root)
            # 격리된 파이프라인은 전역 페이즈를 밀지 않는다 — 판정은 경로가 한다
            self.assertEqual(state["phase"], "off")

            phase, rel, owner = sdd.resolve_write(
                str(root / ".sdd/worktrees/기능-둘/src/a.py"), root, state, config)
            self.assertEqual((phase, rel, owner), ("spec", "src/a.py", "기능-둘"))
            self.assertIsNotNone(sdd.evaluate_gate(phase, rel, config))

            phase, rel, owner = sdd.resolve_write(
                str(root / ".sdd/worktrees/기능-하나/src/a.py"), root, state, config)
            self.assertEqual(owner, "기능-하나")
            self.assertIsNone(sdd.evaluate_gate(phase, rel, config))

    def test_worktree_remove_refuses_to_drop_uncommitted_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _git_project(tmp)
            _run(root, "기능 하나")
            (root / ".sdd/worktrees/기능-하나/src/new.py").write_text("x\n", encoding="utf-8")
            out = sdd.cmd_worktree(_ns(path=str(root), action="remove",
                                       spec="기능-하나", force=False))
            self.assertFalse(out["ok"])
            self.assertIn("커밋되지 않은 변경", out["reason"])
            self.assertTrue((root / ".sdd/worktrees/기능-하나").exists())

    def test_worktree_list_reports_dirty_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _git_project(tmp)
            _run(root, "기능 하나")
            (root / ".sdd/worktrees/기능-하나/src/new.py").write_text("x\n", encoding="utf-8")
            out = sdd.cmd_worktree(_ns(path=str(root), action="list", spec=None, force=False))
            self.assertTrue(out["enabled"])
            self.assertTrue(out["worktrees"][0]["dirty"])

    def test_no_worktree_flag_overrides_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _git_project(tmp)
            out = _run(root, "기능 하나", worktree=False)
            self.assertIsNone(out["worktree"])
            self.assertFalse((root / ".sdd/worktrees/기능-하나").exists())

    def test_porcelain_first_line_path_is_not_truncated(self):
        """_git 이 stdout 을 통째로 strip 하면 첫 줄의 선행 공백이 사라져
        ' M src/a.py' 가 'M src/a.py' 가 되고 [3:] 파싱이 'rc/a.py' 를 낸다."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _git_project(tmp)
            _run(root, "기능 하나")
            wt = root / ".sdd/worktrees/기능-하나"
            # 추적 중인 파일을 고친다 → porcelain 의 첫 줄이 ' M ...' 으로 시작한다
            (wt / "src" / "app.py").write_text("x = 2\n", encoding="utf-8")
            st = sdd.worktree_status(root, "기능-하나")
            self.assertIn("src/app.py", st["changedFiles"])
            self.assertNotIn("rc/app.py", st["changedFiles"])

    def test_status_sees_violations_inside_worktrees(self):
        """워크트리를 빼먹으면 위반이 있어도 '없음' 으로 보고하게 된다."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _git_project(tmp, enforce=True)
            _run(root, "기능 하나")
            # 파이프라인은 spec 단계인데 워크트리의 src/ 를 고쳤다 → 위반이다
            (root / ".sdd/worktrees/기능-하나/src/app.py").write_text(
                "x = 2\n", encoding="utf-8")
            out = sdd.cmd_status(_ns(path=str(root)))
            self.assertTrue(out["guardViolations"])
            v = out["guardViolations"][0]
            self.assertEqual(v["pipeline"], "기능-하나")
            self.assertEqual(v["file"], "src/app.py")

    def test_non_git_project_falls_back_to_main_tree(self):
        """git 이 아니어도 파이프라인은 돌아야 한다 — 다만 그 사실을 숨기지 않는다."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sdd.cmd_init(_ns(path=str(root), enforce=False, specs=None, src=None,
                             tests=None, worktrees=True))
            out = _run(root, "기능 하나")
            self.assertTrue(out["ok"])
            self.assertIsNone(out["worktree"])
            self.assertIn("git 저장소가 아니다", out["worktreeWarning"])

    def test_hand_edited_worktree_field_does_not_crash(self):
        """상태를 손으로 고쳐 worktree 가 경로 문자열로 들어와도 하네스는 살아 있어야 한다.

        실제로 있었던 일이다 — 형식이 어긋났다고 board·next 가 통째로 죽으면 그 파이프라인은
        재개할 방법이 없어진다."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _git_project(tmp)
            _run(root, "기능 하나")
            state = sdd.load_state(root)
            state["pipelines"]["기능-하나"]["worktree"] = ".sdd/worktrees/기능-하나"
            sdd.write_json(root / ".sdd" / "state.json", state)

            pipe = sdd.load_pipelines(sdd.load_state(root))["기능-하나"]
            self.assertTrue(sdd.is_isolated(root, pipe))
            row = [r for r in sdd.cmd_board(_ns(path=str(root)))["pipelines"]
                   if r["slug"] == "기능-하나"][0]
            self.assertEqual(row["worktree"], ".sdd/worktrees/기능-하나")
            self.assertTrue(_next(root)["context"]["workdir"]
                            .endswith(".sdd/worktrees/기능-하나"))

    def test_isolated_pipeline_leaves_the_global_phase_alone(self):
        """워크트리 파이프라인이 단계를 넘어도 전역 페이즈는 그대로다.

        페이즈는 프로젝트에 하나뿐이라, 격리된 쪽이 그걸 밀면 본체를 쓰는 다른
        파이프라인의 게이트 판정이 남의 단계로 바뀐다."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _git_project(tmp, enforce=True)
            _run(root, "기능 하나")
            _write_valid_spec(root, _next(root, spec="기능-하나")["context"]["specPath"])
            _advance(root, {"openQuestions": []}, spec="기능-하나")

            pipes = sdd.load_pipelines(sdd.load_state(root))
            self.assertEqual(pipes["기능-하나"]["stage"], "implement")
            self.assertEqual(sdd.load_state(root)["phase"], "off")

            # 본체를 쓰는 파이프라인은 예전 그대로 전역 페이즈를 잡는다
            _run(root, "기능 둘", worktree=False)
            _next(root, spec="기능-둘")
            self.assertEqual(sdd.load_state(root)["phase"], "spec")

    def test_main_tree_spec_writes_are_judged_by_their_owner(self):
        """명세는 워크트리를 써도 본체에 있다 — 그래도 경로가 주인을 말해 준다."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _git_project(tmp, enforce=True)
            _run(root, "기능 하나")                 # 워크트리, spec 단계
            _run(root, "기능 둘", worktree=False)   # 본체, implement 로 간다
            _write_valid_spec(root, _next(root, spec="기능-둘")["context"]["specPath"])
            _advance(root, {"openQuestions": []}, spec="기능-둘")

            state, config = sdd.load_state(root), sdd.load_config(root)
            self.assertEqual(state["phase"], "implement")

            # 기능-하나 는 아직 spec 단계다. 남이 잡은 implement 로 판정하면 자기
            # 명세를 못 쓰게 된다.
            phase, rel, owner = sdd.resolve_write(
                str(root / "specs/기능-하나/spec-v1.md"), root, state, config)
            self.assertEqual((phase, owner), ("spec", "기능-하나"))
            self.assertIsNone(sdd.evaluate_gate(phase, rel, config))

            # 주인이 없는 본체 경로는 예전처럼 전역 페이즈로 판정된다
            phase, rel, owner = sdd.resolve_write(
                str(root / "specs/README.md"), root, state, config)
            self.assertEqual((phase, rel, owner), ("implement", "specs/README.md", None))


class StateConcurrencyTests(unittest.TestCase):
    """`.sdd/state.json` 은 워크트리를 써도 공유 자원이다 — 여기서 잃으면 끝이다."""

    def test_write_json_is_atomic_for_concurrent_readers(self):
        """쓰는 도중 읽어도 잘린 JSON 이 보이면 안 된다 (load_state 가 빈 상태로 떨어진다)."""
        import threading
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            path = root / ".sdd" / "state.json"
            big = {"version": 1, "phase": "off",
                   "pipelines": {f"p{i}": {"slug": f"p{i}", "history": ["x" * 300]}
                                 for i in range(60)}}
            stop, torn = threading.Event(), []

            def reader():
                while not stop.is_set():
                    if sdd.read_json(path) is None:
                        torn.append(1)

            t = threading.Thread(target=reader, daemon=True)
            t.start()
            try:
                for _ in range(80):
                    sdd.write_json(path, big)
            finally:
                stop.set()
                t.join(timeout=5)
            self.assertEqual(torn, [])
            self.assertEqual(list((root / ".sdd").glob("*.tmp")), [])

    def test_concurrent_pipeline_writes_do_not_lose_each_other(self):
        """동시에 들어온 파이프라인 갱신이 서로를 덮어쓰면 안 된다."""
        import threading
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            pipes = [sdd._new_pipeline(f"기능 {i}", f"f{i}", 2) for i in range(8)]
            threads = [threading.Thread(target=sdd._persist_pipeline, args=(root, pipe))
                       for pipe in pipes]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)
            stored = sdd.load_pipelines(sdd.load_state(root))
            self.assertEqual(sorted(stored), sorted(pipe["slug"] for pipe in pipes))

    def test_state_lock_is_exclusive(self):
        """락은 실제로 배타적이어야 한다 — 아니면 위 두 테스트가 우연히 통과한 것이다."""
        import threading
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(tmp)
            with sdd.state_lock(root) as held:
                self.assertTrue(held)
                second = []
                t = threading.Thread(
                    target=lambda: second.append(
                        sdd.state_lock(root, timeout=0.2).__enter__()))
                t.start()
                t.join(timeout=5)
                self.assertEqual(second, [False])


if __name__ == "__main__":
    unittest.main()
