# Project milestones

This is a short history of shipped milestones. Current setup and behavior are documented in the [project README](../README.md).

## September 2026

- Added named pets, cat and fox species, mood states, and friendship titles at selected levels.
- Added timed sleep, wake behavior, leaderboard, and reminder delivery for care needs and full energy.
- Added administrator tools for reviewing player pets and updating levels or stats.
- Added per-category reminder preferences and Telegram bot menu controls.

## Current limitations

- Inventory, shop, quests, and economy are planned, not implemented.
- The app does not yet have distributed rate limiting or production error monitoring.
- Telegram webhook updates are not deduplicated by `update_id`; repeated delivery can repeat `/start` handling.
- The project needs configured external services for end-to-end use; see the [local setup](../README.md#run-locally).
