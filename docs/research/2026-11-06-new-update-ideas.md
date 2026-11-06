---
title: New update ideas for Tamagotchi FWN
status: Draft
version: 1
date: 2026-11-06
related: [docs/plans/2026-09-12-0206-pet-growth-roadmap.md, docs/research/2026-09-12-0206-feature-opportunities-review.md, docs/CHANGELOG.md]
---

# New update ideas for Tamagotchi FWN

Ideas for the next updates, collected after the September 2026 release (moods, friendship milestones, sleep, cat and fox, leaderboard, reminders). These are proposals, not commitments. Sizes are rough guesses: S is 1-2 engineering days, M is 3-5, L is 5-8, excluding art.

## Already shipped

Moods and friendship titles (roadmap A1-A2), timed sleep, cat and fox species, leaderboard, per-category reminders, admin tools.

## Planned but not built

| # | Idea | What the player gets | Size | Depends on |
|---|---|---|---|---|
| 1 | Daily quests with leaf currency (roadmap A3-A6) | A short goal for every visit | M | Atomic action log, see ADR-0001 |
| 2 | Walks and a finds album, then a room with decor (roadmap B) | A collection to fill and a place to spend leaves | M-L | Idea 1; reuses the sleep timer pattern |
| 3 | "Catch the firefly" mini-game | A 30-second active game | L | Server-side sessions, reward caps |
| 4 | Friend visits and a shareable pet card | Social play, a way to bring in new players | L | Opt-in public profile, rate limits |

## New ideas (not on the roadmap)

| # | Idea | What the player gets | Size | Depends on |
|---|---|---|---|---|
| 5 | No-penalty streaks | Bonus rewards for consecutive days; a missed day costs nothing, which fits the soft-care rule | S | Idea 1 |
| 6 | Webhook dedup by `update_id` | Fixes repeated `/start` handling (known limitation) | S | None |
| 7 | Rate limiting and error monitoring | Safer to grow the user base (known limitation) | M | None |
| 8 | Add the snow leopard (ирбис) as a pet species | A new selectable mountain-dwelling companion | M | Six mood sprites and a visual theme; extend the species model and picker. **Status: implemented on branch `feat/snow-leopard` with generated sprites. |

## Suggested order

1. Idea 6 as a quick fix, since it is a small known bug.
2. Idea 1, because ideas 2, 3 and 5 build on it.
3. Idea 5 on top of the quests.
4. Idea 2 once leaves exist.
5. Idea 7 before any push to grow the player base.
6. Ideas 3 and 4 later, after real usage data.
7. Add the snow leopard when its sprite set and visual theme are ready; it can ship independently of the economy features.

## Open question

Which goal matters most for the next update: retention, growth, depth, or stability? The answer decides whether idea 1 or idea 6/7 goes first.

## Out of scope

Payments, trading, paid random rewards, penalties for missed days, pet death, and multiple pets per account. The roadmap rules these out.

## Request for Codex: database migration after the update is pushed

Codex, once the new update has been pushed to `main`, please check whether the database needs a migration and, if it does, prepare it.

1. Compare `supabase/migrations/` with the migrations already applied to the Supabase project. List any file that has not been applied yet, in filename order. The latest numbered file today is `0009_reminder_preferences.sql`.
2. If the update changed the schema (for example a new species such as `snow_leopard` in the `pets.species` check constraint, or new tables or columns for quests, leaves or streaks) and no migration covers it, write a new additive migration with the next free number. Do not edit or renumber existing migrations.
3. Keep the migration safe to run on live data: additive changes only, no data loss, existing pets keep their progress, and the closed-permissions pattern from earlier migrations is kept.
4. Check the live constraint or column names before writing a `drop constraint` or `alter` statement, rather than guessing them.
5. Apply the migrations in filename order in the Supabase SQL Editor, as the README describes. Applying them needs access to the Supabase project, so if you do not have it, stop and give me the SQL to run by hand.
6. After applying, check that the app still works against the new schema (`pytest`, `ruff`, and a read of `/api/pet`) and tell me what you ran and what the results were.
7. If no migration is needed, say so explicitly and list what you checked.

Never print or store API keys, the service role key, or other secrets in the migration, the report or this document.
