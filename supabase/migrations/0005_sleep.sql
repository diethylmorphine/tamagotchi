-- Persist sleep across reloads and offline sessions.
alter table public.pets add column sleep_started_at timestamptz;
