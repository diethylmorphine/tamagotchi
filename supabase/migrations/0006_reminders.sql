-- Separate delivery state: game saves must never overwrite notification claims.
create table public.pet_reminders (
    telegram_id bigint primary key references public.pets(telegram_id) on delete cascade,
    enabled boolean not null default true,
    last_care_at timestamptz,
    sleep_notified_at timestamptz
);
alter table public.pet_reminders enable row level security;
revoke all on public.pet_reminders from anon, authenticated;
grant select, insert, update on public.pet_reminders to service_role;
