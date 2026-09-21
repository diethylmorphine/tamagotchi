-- Read-only diagnostics in Supabase SQL Editor. Does not send messages or expose secrets.
select extname from pg_extension where extname in ('pg_cron', 'pg_net');

select name, count(*) as configured
from vault.secrets
where name in ('reminder_base_url', 'reminder_cron_secret')
group by name;

select jobid, jobname, schedule, active
from cron.job where jobname = 'pet-reminders';

select d.start_time, d.end_time, d.status, d.return_message
from cron.job_run_details d join cron.job j using (jobid)
where j.jobname = 'pet-reminders'
order by d.start_time desc limit 10;

-- pg_cron success only means the HTTP request was enqueued. Inspect actual HTTP results.
-- pg_net retains responses temporarily; run this soon after a scheduled tick.
select id, created, status_code, timed_out, error_msg,
       case when status_code = 200 then content else null end as delivery_summary
from net._http_response order by created desc limit 10;

select count(*) as subscriptions,
       count(*) filter (where enabled) as enabled,
       max(last_care_at) as latest_care_claim,
       max(sleep_notified_at) as latest_sleep_claim
from public.pet_reminders;

select started_at, completed_at, sent, failed from public.reminder_scheduler;
