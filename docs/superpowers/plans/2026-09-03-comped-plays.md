# Comped Plays Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. The detailed tasks live in `comped-plays/part-*.md` next to this file; read this index first, then the part you are executing.

**Goal:** Ship three published rote Plays (`session-ledger`, `comped`, `wrong-turns`) on one stdlib-only Python core that reads local Claude Code, Codex, Pi and OpenCode logs and produces the Comped card, repeat offenders, Rote dividend and drafted rules, exactly as specified in `docs/SPEC.md`.

**Architecture:** One Python package `comped_core/` (no third-party deps, Python ≥ 3.9) with adapters → ledger → pricing → analyses → renderers, driven by `cli.py` subcommands that print JSON and write files under `out_dir`. Each Play is a directory under `plays/` holding a byte-identical copy of `comped_core/` and `resources/` (synced by a script, asserted by a test) plus the registry description and parameter table. Plays are captured inside rote by running the CLI subcommands as shell steps and settling with `/play settle`.

**Tech Stack:** Python 3.9+ stdlib only (`json`, `decimal`, `dataclasses`, `pathlib`, `re`, `hashlib`, `datetime`, `unittest`). rote CLI ≥ 0.78. Optional renderers: `qlmanage` (macOS), `rsvg-convert` (Linux). Optional conformance: `npx ccusage`.

## Global Constraints

- Runtime dependency set is exactly `python3` (≥ 3.9). No pip installs, no node in the Plays.
- `comped_core` must not import `urllib`, `http`, `socket`, `requests`, `ssl`. Only `render_png.py` may import `subprocess`, and only with a fixed argv list and `shell=False`.
- Never open `~/.claude.json`, `~/.codex/auth.json`, `~/.codex/config.toml`, or any path containing `auth`, `credential`, `token`, `keychain`. A test greps the source for these strings.
- All money arithmetic in `decimal.Decimal`; display rounding only at render time; two decimals for USD, one decimal for multipliers.
- All timestamps parsed to UTC-aware `datetime`; window filter uses the record's own timestamp.
- Every list in every output is explicitly sorted (by usd desc then name, or by timestamp) so reruns are byte-identical when `--now` is pinned.
- Human message text is stored truncated to 120 chars plus sha256 unless `redact=false`.
- Plays write only under `out_dir`; every written path is appended to `result["written"]`.
- Descriptions must contain the §9 privacy paragraph of SPEC.md verbatim and must not mention the hackathon.
- Commit after every task with a conventional message. Repo root: `/Users/rajkaria/Projects/comped`.
- Play slugs are exactly `session-ledger`, `comped`, `wrong-turns`. Step names snake_case as listed in SPEC §6.

## File structure (locked)

```
comped/
├── comped_core/
│   ├── __init__.py            version string, SCHEMA_VERSION
│   ├── models.py              UsageRecord, HumanMessage, ToolEvent, Source, Ledger
│   ├── jsonl.py               tolerant streaming JSONL reader
│   ├── timeutil.py            parse_ts, window bounds, now injection
│   ├── adapters/
│   │   ├── __init__.py        ADAPTERS registry, discover_and_parse(config)
│   │   ├── claude_code.py
│   │   ├── codex.py
│   │   ├── pi.py
│   │   └── opencode.py
│   ├── ledger.py              build_ledger, attribute_turns, write/read JSONL, summary
│   ├── prices.py              load_table, resolve_model, rate_for
│   ├── plans.py               load_plans, plan_cost
│   ├── pricing.py             price_ledger → PricedSummary, explain lines
│   ├── textnorm.py            normalize, shingles, jaccard, exclusion rules
│   ├── repeats.py             find_repeats → RepeatCluster[]
│   ├── wrongturns.py          classify → MistakeClass[], draft_rules
│   ├── baseline.py            load/save/delta
│   ├── render_terminal.py
│   ├── render_svg.py
│   ├── render_png.py
│   ├── render_report.py       markdown, explain, share text
│   └── cli.py                 argparse subcommands, JSON stdout
├── resources/
│   ├── prices.json            reduced LiteLLM snapshot with header
│   ├── plans.json
│   └── fixtures/
│       ├── claude/<proj>/<session>.jsonl + <session>/subagents/agent-*.jsonl
│       ├── codex/2026/09/01/rollout-*.jsonl
│       ├── pi/*.jsonl
│       └── opencode/storage/message/...
├── tools/
│   ├── build_prices.py        LiteLLM → resources/prices.json
│   ├── make_fixtures.py       real logs → synthetic fixtures
│   └── sync_plays.py          copy core+resources into plays/*/resources, verify identical
├── plays/
│   ├── session-ledger/{DESCRIPTION.md,PARAMETERS.json,STEPS.md,resources/}
│   ├── comped/...
│   └── wrong-turns/...
├── tests/                     unittest modules, one per core module + integration
├── docs/                      SPEC.md, research/, superpowers/plans/, adoption-log.md
├── .github/workflows/ci.yml   macOS + ubuntu, python 3.9 and 3.12
├── README.md  VISION.md  LICENSE  CLAUDE.md
```

## Task index

| # | Task | Part file | Depends on |
|---|---|---|---|
| 0 | Install rote, warm-up, verify Play format (GATE) | part-0-gate.md | — |
| 1 | Scaffold, models, JSONL reader, timeutil | part-1-core.md | — |
| 2 | Price table build + prices.py + plans.py | part-1-core.md | 1 |
| 3 | Claude Code adapter + Claude fixture generator | part-2-adapters.md | 1 |
| 4 | Codex adapter + Codex fixture generator | part-2-adapters.md | 1 |
| 5 | Pi + OpenCode best-effort adapters | part-2-adapters.md | 1 |
| 6 | Ledger assembly, turn attribution, summary, I/O | part-3-ledger-pricing.md | 3,4,5 |
| 7 | Pricing engine, windows, explain | part-3-ledger-pricing.md | 2,6 |
| 8 | Text normalisation + repeat offenders | part-4-analyses.md | 6,7 |
| 9 | Wrong turns + rule drafting | part-4-analyses.md | 6,7 |
| 10 | Baseline + delta | part-4-analyses.md | 7,8 |
| 11 | Renderers: terminal, report, explain, share, SVG, PNG | part-5-render-cli.md | 7,8,9,10 |
| 12 | CLI subcommands | part-5-render-cli.md | 11 |
| 13 | Cross-cutting tests: determinism, no-network, robustness, ccusage conformance, perf | part-5-render-cli.md | 12 |
| 14 | Play packaging, capture sessions, quality doctor, publish | part-6-plays-ship.md | 0,13 |
| 15 | Public repo: README, VISION, LICENSE, CI | part-6-plays-ship.md | 13 |
| 16 | Distribution, adoption log, judge loop | part-6-plays-ship.md | 14,15 |

Tasks 1–2 can start before Task 0 finishes. Tasks 3, 4, 5 run in parallel. Nothing in 14 starts until 0 has answered every unknown in `docs/research/LANDSCAPE.md` §Unknowns.

## Shared interfaces (every part refers to these exact names)

```python
# comped_core/models.py
@dataclass(frozen=True)
class UsageRecord:
    harness: str; session_id: str; record_id: str; timestamp: str; model: str
    input_tokens: int; cache_write_tokens: int; cache_read_tokens: int
    output_tokens: int; reasoning_tokens: int; project: str; is_subagent: bool; turn_id: str

@dataclass(frozen=True)
class HumanMessage:
    harness: str; session_id: str; message_id: str; timestamp: str
    text: str; text_sha256: str; project: str; origin: str   # origin: "human" | "unknown" | "automated"

@dataclass(frozen=True)
class ToolEvent:
    harness: str; session_id: str; event_id: str; timestamp: str; tool_name: str
    input_summary: str; is_error: bool; error_text: str; turn_id: str

@dataclass
class Source:
    harness: str; root: str; found: bool; files: int; lines: int; parsed: int
    duplicates: int; unparsed: int; note: str

@dataclass
class Ledger:
    records: list; humans: list; tools: list; sources: list; generated_at: str

# comped_core/adapters/__init__.py
def parse_all(config: dict) -> Ledger          # config keys: claude_dir, codex_dir, pi_dir, opencode_dir, include_subagents, redact, since (datetime), now (datetime)

# comped_core/pricing.py
@dataclass
class PricedSummary:
    total_usd: Decimal; per_model: list  # [{"model","key","usd","input","cache_write","cache_read","output","records","priced"}]
    unpriced: list; cache_share: Decimal; active_days: int; sessions: int
    per_turn_usd: dict   # turn_id -> Decimal
    plan_cost: Decimal | None; multiplier: Decimal | None; plan_ids: list; explain: list[str]
def price_ledger(ledger, table, plans, plan_ids, days_back, now) -> PricedSummary

# comped_core/repeats.py
@dataclass
class RepeatCluster:
    label: str; count: int; sessions: int; days: int; total_usd: Decimal; repeat_usd: Decimal
    dividend_98: Decimal; dividend_80: Decimal; capture_command: str; members: list[str]  # message_ids
def find_repeats(humans, per_turn_usd, threshold, handle) -> list[RepeatCluster]

# comped_core/wrongturns.py
@dataclass
class MistakeClass:
    kind: str  # "tool_error" | "correction" | "revert"
    confidence: str  # "high" | "medium"
    tool_name: str; signature: str; count: int; sessions: int; recovery_usd: Decimal
    evidence: str; rule_draft: str
def classify(ledger, per_turn_usd, min_recurrence, show_snippets) -> list[MistakeClass]

# comped_core/cli.py  (all print one JSON object to stdout; exit 0 on success, 2 on bad args, never traceback)
comped ledger    --claude-dir --codex-dir --pi-dir --opencode-dir --days-back --out-dir --include-subagents --redact [--now]
comped price     --out-dir --plan --rates-path --days-back [--now]
comped repeats   --out-dir --repeat-threshold --handle
comped card      --out-dir --card-theme
comped wrongturns --out-dir --min-recurrence --show-snippets
comped rules     --out-dir --rules-target
comped explain   --out-dir
comped verify    --out-dir       # re-prices ledger.jsonl and confirms totals in comped-report.md
```
