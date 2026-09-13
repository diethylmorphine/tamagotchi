-- Run AFTER 0006_reminders.sql. Enable pg_cron and pg_net in Supabase first.
-- Store reminder_base_url (https://your-project.vercel.app) and reminder_cron_secret
-- (the same value as CRON_SECRET in Vercel) in Supabase Vault before running this.
select cron.schedule(
    'pet-reminders',
    '*/5 * * * *',
    $$
    select net.http_post(
        url := (select decrypted_secret from vault.decrypted_secrets
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
