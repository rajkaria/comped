# Comped: product vision

## What we built (hackathon scope)

Three rote Plays that read the agent logs already on a developer's machine and return, with no credentials and the logs never leaving the machine, a priced card, a rank on the gotcomped.com leaderboard, the repeated asks worth turning into Plays, and drafted rules from the agent's recurring mistakes. One parser, three published entry points.

## What this becomes

### Month 1: the shared parser
- `session-ledger` becomes the dependency other Play authors declare instead of re-parsing logs. Adapters for Gemini CLI, Goose, Cline/Roo/Kilo and Aider land the same way the first four did: fixture first, best-effort labelled, promoted to verified when a real install confirms the schema.
- First users: the Playoffs participants who ran it during the week, then the ccusage and CodexBar communities, who already care about these numbers.

### Month 3: the card spreads
- The opt-in, aggregate-only leaderboard from the earlier product draft ships beside the Play, never inside it: `npx comped` prints the same card the Play prints and asks, once, whether to post a signed aggregate. Boards by multiplier, surface, provider and plan tier.
- Server-rendered share cards, badges for READMEs, a monthly season recap.

### Month 6: rules feed back into Plays
- `wrong-turns` classes become Play preconditions: a Play that failed on "no such file" three times gains a check step generated from the drafted rule. The loop closes on Modiqo's own thesis, that a mistake captured once should not recur.

## Why the rote integration deepens over time

- **Hackathon**: the Plays run on rote, are inspectable on the registry, and the repeat-offender output ends in a `/play settle` command.
- **Month 3**: `comped` composes `session-ledger`; every dependent Play pulls the primitive; the registry's adoption signal becomes the parser's distribution.
- **Month 6**: drafted rules ship as Play preconditions; Comped becomes the place a team sees which Plays paid for themselves.

## Revenue model

None inside the Plays, ever. The hosted board, team views and private team boards are the business, at a price a team lead can expense.

## What the hackathon validated

- The parser: dedup on real logs (41% duplicate lines measured), Codex counter differencing, subagent attribution.
- The pricing: a bundled, provenance-carrying price table with honest unknowns.
- The hypothesis still open: whether the card spreads on its own. The adoption log answers it by the end of the week.

## The ask

- A registry stats endpoint for authors, so Plays like `playoffs-standings` and this one stop scraping.
- Composition between Plays if it is not already supported, so `session-ledger` can be a true dependency.
- Feedback from the Modiqo team on the 98% figure applied to measured repeats.
