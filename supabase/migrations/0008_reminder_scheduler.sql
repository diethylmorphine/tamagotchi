-- Operational heartbeat, separate from each player's opt-in and delivery claims.
create table public.reminder_scheduler (
    id integer primary key check (id = 1),
    started_at timestamptz not null,
    completed_at timestamptz,
    sent integer not null default 0,
    failed integer not null default 0
);
alter table public.reminder_scheduler enable row level security;
revoke all on public.reminder_scheduler from anon, authenticated;
grant select, insert, update on public.reminder_scheduler to service_role;
