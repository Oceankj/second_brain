begin;

-- CSRF tokens are now derived independently for each authorization request
-- from the browser session secret and request ID. Keep the legacy column for a
-- safe rolling deployment, but new sessions no longer need to populate it.
alter table oauth_login_sessions alter column csrf_token_hash drop not null;

commit;
