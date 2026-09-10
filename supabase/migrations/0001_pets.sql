-- Run in Supabase SQL Editor, or via supabase db push in a configured CLI project.
create table public.pets (
    telegram_id bigint primary key check (telegram_id > 0),
    name text not null default 'Моти' check (char_length(name) between 1 and 32),
    satiety double precision not null default 80 check (satiety between 0 and 100),
    happiness double precision not null default 80 check (happiness between 0 and 100),
    energy double precision not null default 80 check (energy between 0 and 100),
    hygiene double precision not null default 80 check (hygiene between 0 and 100),
    xp bigint not null default 0 check (xp >= 0),
    version bigint not null default 0 check (version >= 0),
    updated_at timestamptz not null default now(),
    last_action_at timestamptz,
    created_at timestamptz not null default now()
);

alter table public.pets enable row level security;
-- Telegram auth is checked by our backend; browser roles have no access.
revoke all on public.pets from anon, authenticated;
grant select, insert, update on public.pets to service_role;

