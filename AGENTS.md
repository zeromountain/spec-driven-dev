# AGENTS.md

This file guides Claude Code (and other AGENTS.md-compatible agents) when working on this
repository.

## What this repo is

A standalone Claude Code plugin (also a self-hosted marketplace, following the same layout as
`zeromountain/auto-dev`). It ships a single plugin, `sdd`, that scaffolds and runs a
Spec-Driven Development harness in any target project: specs as the source of truth, ten
role-bound subagents across three phases, a registry of pipeline state machines in `sdd.py` (one per
feature, running concurrently) that decides the next action and what may run at the same time, and an opt-in PreToolUse hook that enforces each *phase's* write boundaries
by file path.

The ten agents, by phase (bold = also runs in light mode):

| phase | agents |
|---|---|
| spec | `spec-researcher`, **`spec-architect`**, `spec-auditor` |
| implement | `impl-planner`, **`software-engineer`**, `test-engineer` |
| review | **`spec-reviewer`**, `code-reviewer`, `security-reviewer`, `perf-reviewer` |

## Structure

```
spec-driven-dev/
├── .claude-plugin/
│   ├── marketplace.json   # name: spec-driven-dev, plugins[0].source: "./"
│   └── plugin.json         # name: sdd — read by Claude Code
├── .codex-plugin/
│   └── plugin.json         # name: sdd, skills: "./skills/" — read by Codex CLI
├── skills/spec-driven-dev/ # SKILL.md orchestrator + references/ (both hosts)
├── commands/                # thin routers into the skill (/sdd:*) — Claude Code only
├── agents/                  # 10 role-bound subagents (see above) — Claude Code only
├── hooks/                   # phase_gate.py + hooks.json (opt-in per project) — Claude Code only
├── scripts/                 # sdd.py (stdlib-only CLI) + tests/ (both hosts)
├── templates/                # scaffolded artifacts (spec.md, tasks.md, review-report.md, AGENTS.sdd.md)
└── docs/SETUP.md            # install/verify/troubleshoot guide for both hosts
```

Two-level manifest: the root `.claude-plugin/marketplace.json` declares the marketplace
(`name: spec-driven-dev`) with a single plugin entry whose `source` is `"./"` — the repo root
doubles as the plugin directory (same pattern as `auto-dev`), unlike `zeromountain/claude-plugins`
where each plugin lives under `plugins/<name>/`. **The repo ships two plugin manifests for the
same tree**: Claude Code reads `.claude-plugin/plugin.json` and gets commands, agents, and the
hook; Codex CLI reads `.codex-plugin/plugin.json` and gets only the `skills/` directory —
Codex plugins have no manifest field for commands, subagents, or hooks (confirmed against the
bundled Codex marketplaces under `~/.codex/.tmp/bundled-marketplaces/openai-bundled`, whose
`plugin.json` files only ever use `skills`/`mcpServers`, never `commands`/`agents`/`hooks`).
Keep the two manifests' `version` fields in lockstep — `scripts/validate.py` enforces this.

## Design discipline

- **Numbers and path decisions come from `scripts/sdd.py`, never from the LLM.** Every
  subcommand prints JSON to stdout only; subagents and commands read it, they don't
  recompute it.
- **The phase gate is a pure function** (`sdd.evaluate_gate`) shared by the hook
  (`hooks/phase_gate.py`) and the post-hoc detector (`sdd.py guard`) — the rule lives in one
  place.
- **The hook is inert unless a project opts in.** It must no-op the instant
  `<project>/.sdd/state.json` is missing or `enforce` is not `true`. Never assume the plugin's
  hook is safe to leave "mostly harmless" by default — verify the early-return path whenever
  you touch `hooks/phase_gate.py`.
- **A Claude Code subagent cannot spawn another subagent.** `/sdd:run`'s spec → implement →
  review orchestration therefore lives in `SKILL.md` (loaded into the main session), not in an
  agent.
- **The orchestrator decides nothing about sequencing.** Where a run is and what comes next
  live in `.sdd/state.json`'s `pipeline` record, driven by `sdd.py run` / `next` / `advance`
  (see `skills/spec-driven-dev/references/pipeline.md`). `next` also performs the deterministic
  side effects of entering a stage — phase transition, spec file creation, `tasks.md`, review
  report skeleton — so the skill never calls `phase`/`new`/`tasks`/`review-report` by hand
  during a run. `next` is idempotent per stage; `advance` is not (exactly one call per
  subagent result, and `--stage` guards against a mismatched one).
- **Everything that crosses a subagent boundary goes through `pipeline.carry`.** Subagents
  can't see each other's context, so review gaps, test failures, validate errors, and user
  answers are carried in state and re-injected by `next` — never re-summarized by the LLM.
- **Which subagents run is decided by `sdd.py depth`, not by the model.** Thresholds
  (AC/EC counts, validate warnings) and the security/perf signal keywords live in
  `decide_depth()`; the pipeline re-derives the roster on every stage entry
  (`refresh_roster`). Adding an agent means adding it to `AGENT_ROSTER` — never teaching the
  skill to pick agents on vibes. `depth_haystack()` excludes the spec's `범위 밖` section and
  unfilled `{{...}}` placeholders: an exclusion clause and the template's own boilerplate are
  not signals.
- **Concurrency is decided by `schedule()`, not by the model.** Pipelines live in
  `state["pipelines"][slug]`; `activePipeline` is only a focus hint. Two constraints bound
  parallelism and both are structural, not stylistic: the phase gate is *project-wide* (the
  PreToolUse payload has no caller identity), so under `enforce: true` only same-phase
  pipelines advance together; and implement-stage pipelines serialize unless
  `impl-planner` gave disjoint `tasks[].files` — no plan means "unknown, assume overlap".
  `advance` refuses to guess a target when several pipelines are live, because feeding a
  result to the wrong pipeline corrupts it silently. `run --all` is the batch entry point
  (bare `run` resumes only `activePipeline`); `run --all --resume` also revives halted ones. Keep `load_pipelines()`'s migration of
  the pre-0.6.0 single `pipeline` field working whenever you touch the registry.
- **Reviewers are called together, never in sequence.** The review stage emits
  `action: "call-agents"` (even when the roster holds one) and `advance` takes
  `{"reviews": [...]}`. `combine_verdicts()` takes the worst verdict, never an average, and
  halts if any roster member's result is missing — there is no path to approving on a subset.
- **The gate enforces phase boundaries, not intra-phase role separation.** PreToolUse
  payloads carry no subagent identity, so `software-engineer` writing to `tests/` in deep
  mode is not blocked. Read-only roles are enforced by having no write tool in their
  `tools:` frontmatter — that half *is* real. Say so plainly in docs rather than implying
  the hook covers both.
- Scaffolded artifacts (`AGENTS.md` section, spec/tasks/review templates, command and skill
  descriptions) are written in Korean for the target audience; this repo's own `AGENTS.md` is
  English.

## Commands

**Validate manifests are well-formed JSON:**
```bash
python3 -m json.tool .claude-plugin/marketplace.json
python3 -m json.tool .claude-plugin/plugin.json
python3 -m json.tool .codex-plugin/plugin.json
```

**Validate the plugin's manifest, skill, agents, and commands (Claude Code):**
```bash
claude plugin validate --strict .
```

**Validate this repo's own conventions, including the two-manifest version lockstep:**
```bash
python3 scripts/validate.py
```

**Run the script test suite** (stdlib `unittest`, no network, no third-party deps):
```bash
python3 -m unittest discover -s scripts/tests -t .
```

**Test the plugin locally before pushing** (loads it directly from disk):
```bash
cc --plugin-dir /Users/son-yeongsan/spec-driven-dev       # Claude Code
codex --plugin-dir /Users/son-yeongsan/spec-driven-dev    # Codex CLI
```

**Exercise the phase-gate hook directly:**
```bash
echo '{"cwd":"/tmp/x","tool_name":"Write","tool_input":{"file_path":"/tmp/x/src/a.ts"}}' \
  | CLAUDE_PROJECT_DIR=/tmp/x python3 hooks/phase_gate.py
```

## Adding or changing a component

- New subcommand → add to `scripts/sdd.py`, add its test cases to
  `scripts/tests/test_core.py`, and document it in
  `skills/spec-driven-dev/references/spec-format.md`, `phase-gate.md`, `pipeline.md`,
  or `depth.md` as appropriate.
- New command (`commands/*.md`) → frontmatter is exactly `description` + `argument-hint`, body
  is a thin router into the skill (10–17 lines), matching the existing seven.
- New agent (`agents/*.md`) → frontmatter is `name` + `description` + `tools`; body ends with
  `## 출력 스키마` (fenced ```json), `## 공통 규칙`, `## 입력 방식`, `## 출력 방식`. Also add
  it to `AGENT_ROSTER` (and `REVIEWER_CONCERNS` if it reviews), give it a `RESULT_SCHEMA`
  entry, teach `_next_<stage>`/`_advance_<stage>` its instruction and transition, and list it
  in `SKILL.md`, `references/roles.md`, and `templates/AGENTS.sdd.md` — an agent the roster
  never names will never be called.
- Bump `version` in **both** `.claude-plugin/plugin.json` and `.codex-plugin/plugin.json` for
  any change you want an already-installed copy to actually pick up — both hosts' `update`
  commands compare semver, not file content, and `scripts/validate.py` fails the build if the
  two versions drift apart.
- Anything added to `commands/`, `agents/`, or `hooks/` is Claude-Code-only by construction —
  Codex's plugin manifest has no field for any of the three. If a change needs to reach Codex
  users too, it has to happen in `skills/spec-driven-dev/SKILL.md` or `scripts/sdd.py`, since
  those are the only two things `.codex-plugin/plugin.json` exposes.

## What this repo deliberately does not do

- It does not enforce test coverage numerically — `config.json`'s `minCoverage` is a threshold
  handed to the Review Agent, not something `sdd.py` measures itself (coverage tooling is
  language/runner-specific).
- It does not cover `Bash` in the phase-gate hook matcher — false-positive cost was judged
  higher than the value of blocking shell-redirect bypasses. `sdd.py guard` catches those
  after the fact via `git diff`/`git status` instead.
- It does not overwrite a target project's existing `AGENTS.md`/`CLAUDE.md` — it appends or
  replaces only the `## Spec-Driven Development` section.
