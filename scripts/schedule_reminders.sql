-- Run AFTER 0006_reminders.sql. Enable pg_cron and pg_net in Supabase first.
-- Store reminder_base_url (https://your-project.vercel.app) and reminder_cron_secret
-- (the same value as CRON_SECRET in Vercel) in Supabase Vault before running this.
-- Fail immediately instead of silently scheduling requests with a NULL URL/token.
do $$
begin
    if not exists (select 1 from pg_extension where extname = 'pg_cron')
       or not exists (select 1 from pg_extension where extname = 'pg_net') then
        raise exception 'Enable pg_cron and pg_net first';
    end if;
    if (select count(*) from vault.decrypted_secrets
        where name = 'reminder_base_url' and decrypted_secret like 'https://%') <> 1
       or (select count(*) from vault.decrypted_secrets
           where name = 'reminder_cron_secret' and length(decrypted_secret) >= 32) <> 1 then
        raise exception 'Set reminder_base_url and reminder_cron_secret in Vault first';
    end if;
end $$;

select cron.schedule(
    'pet-reminders',
    '*/5 * * * *',
    $$
    select net.http_post(
        url := (select rtrim(decrypted_secret, '/') from vault.decrypted_secrets
                where name = 'reminder_base_url') || '/api/cron/reminders',
        headers := jsonb_build_object(
            'Content-Type', 'application/json',
            'Authorization', 'Bearer ' ||
                (select decrypted_secret from vault.decrypted_secrets
                 where name = 'reminder_cron_secret')
        ),
        body := '{}'::jsonb,
        timeout_milliseconds := 60000
    );
    $$
);
