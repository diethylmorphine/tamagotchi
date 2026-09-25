alter table public.pet_reminders
    add column if not exists notify_hunger boolean not null default true,
    add column if not exists notify_mood boolean not null default true,
    add column if not exists notify_hygiene boolean not null default true,
    add column if not exists notify_sleep boolean not null default true;
