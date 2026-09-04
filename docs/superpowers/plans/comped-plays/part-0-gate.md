# Part 0 — Task 0: Install rote, warm up, verify the Play format (GATE)

Nothing in Part 6 starts until every unknown below has a written answer in `docs/research/ROTE-FORMAT.md`. Tasks 1–13 may proceed in parallel with this task because the core is Play-format-agnostic by design.

**Files:**
- Create: `docs/research/ROTE-FORMAT.md`
- Create: `docs/adoption-log.md`

**Interfaces:**
- Produces: the answers that Part 6 consumes (step format, resources layout, parameter passing, fixtures key, tags, composition, declaredWrites semantics).

## Steps

- [x] **Step 0 (done 2026-09-03): Inspect the installer chain and dry-run the plan.** Findings are in `docs/research/ROTE-FORMAT.md` §Install facts. The unattended install (`PLAY_INSTALL_YES=1 PLAY_APPROVE_REMOTE_INSTALLER=1`) was blocked by the Claude Code permission classifier, so Step 1 is run by the user in their own terminal.

- [x] **Step 1 (done 2026-09-04, by the user): Install the rote CLI. User runs this in a terminal (interactive wizard; press Enter for guided setup, choose Claude Code, approve the Rote remote installer when asked, then sign in with Google or GitHub in the browser and claim the handle).**

```bash
curl -fsSL https://getrote.dev/playoffs/install.sh | sh
```

Expected: the wizard shows the same plan as the dry run (Play 0.4.87 → Claude Code Rote skills; Rote v0.79.0 to `~/.local/bin/rote`), verifies, and reports where it saved the install report. Restart Claude Code afterwards so the `/play` skill and hooks load.

- [x] **Step 2 (done 2026-09-04): Confirm the binary and version.** `rote 0.79.0`, `/Users/rajkaria/.local/bin/rote`. Signed in as `the handle owner's Google account`; handle `rajkaria` reserved via `rote profile set-handle` (not part of the OAuth flow, contrary to Step 3's expectation).

```bash
rote --version && which rote
```

Expected: version ≥ 0.78.0 (authors in the registry are on 0.77–0.78).

- [ ] **Step 3: Open a fresh Claude Code conversation in `/Users/rajkaria/Projects/comped` and run the harness command.**

```
/play what's new
```

Expected: sign-in prompt (Google or GitHub), then a handle claim. Claim the handle you will publish under; it becomes the URI prefix `play.modiqo.ai/<handle>/...`. Record the handle in `ROTE-FORMAT.md`.

- [ ] **Step 4: Run Hello, then one more public Play, then one practice Play, then post "warmed up" in the Modiqo Discord.**

```bash
rote play run https://play.modiqo.ai/modiqo/hello
rote play run https://play.modiqo.ai/dotisacat/playoffs-standings author=<handle>
```

Practice Play: in the harness, `/play explore "count lines of code per language in this repo"`, then do the work with two or three shell commands inside rote, then `/play settle <handle> "lines of code per language"`. Do **not** publish it to Community (choose Skip or Team). Record what the settle flow asked, verbatim, in `ROTE-FORMAT.md`.

- [ ] **Step 5: Pull and unpack the three reference Plays to read their archives.**

```bash
mkdir -p /private/tmp/claude-501/-Users-rajkaria-Projects-random/fb31da3b-d6ff-4121-a347-a1c757fd206b/scratchpad/plays && cd "$_"
rote play inspect https://play.modiqo.ai/sidships/token-tab@0.1.0 --json > token-tab.json
rote play inspect https://play.modiqo.ai/modiqo/agent-work-daily-close@1.0.1 --json > awdc.json
rote play inspect https://play.modiqo.ai/himanshu-jha/play-quality-doctor@0.2.1 --json > pqd.json
rote how
rote guidance
```

Then find where rote caches downloaded archives (try `find ~/.rote ~/.local/share/rote ~/Library/Application\ Support/rote -name '*.flow*' -o -name '*.yml' -o -name '*.yaml' 2>/dev/null | head`) and read the token-tab archive end to end: the manifest/frontmatter file, the step definitions, and how `resources/` files are addressed.

- [ ] **Step 6: Answer every unknown and write `docs/research/ROTE-FORMAT.md` with this exact structure.**

```markdown
# rote Play format, verified on <date> with rote <version>

## Handle
<handle>

## Archive layout
<tree of the token-tab archive, verbatim>

## Step definition
<one step copied verbatim; state whether it is a recorded shell string, a script path, or a JS/Python step; state how stdout becomes the step result and whether `out.result()` exists>

## Parameter passing
<how a parameter reaches a shell step: env var name pattern, template syntax, or argv substitution; one verbatim example>

## Resources
<how a step references resources/x.py: relative path from the archive root? an env var like $ROTE_PLAY_DIR? verbatim example>

## Fixtures, tags, license, output schema keys
<the frontmatter keys the quality rubric reads; copied from play-quality-doctor's prescribe output when run against our practice Play>

## Composition
<can a Play depend on another Play? command or key if yes; "no, bundle copies" if not>

## declaredWrites
<does it cover local files? what does token-tab declare vs what it writes>

## Settle flow
<verbatim prompts from /play settle; where the description, parameters, tags and license are entered; how a wrong turn is kept>

## Publishing
<exact commands: rote play release ..., rote registry play push ..., how Community is selected>

## Decisions taken for Part 6
- steps are: ...
- comped_core is referenced as: ...
- composition: yes/no → ...
```

- [ ] **Step 7: Run play-quality-doctor against the practice Play and paste its full output into `ROTE-FORMAT.md` under "Fixtures, tags, license, output schema keys".**

```bash
rote play run https://play.modiqo.ai/himanshu-jha/play-quality-doctor play=<path-or-ref-of-practice-play> owner=<handle>
```

- [ ] **Step 8: Create the adoption log.**

```markdown
# Adoption log

| date (IST) | play | version | downloads (manifest) | delta | notes (posts, Discord, asks) |
|---|---|---|---|---|---|
```

- [ ] **Step 9: Commit.**

```bash
cd /Users/rajkaria/Projects/comped && git add docs/research/ROTE-FORMAT.md docs/adoption-log.md && git commit -m "docs: verified rote play format and warm-up record"
```

## Exit criteria

Every heading in `ROTE-FORMAT.md` has content copied from a real artefact, not inferred. If composition is unsupported, the "Decisions" section says "bundle copies" and Part 6 uses `tools/sync_plays.py`.
