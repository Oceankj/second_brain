begin;

create table if not exists oauth_clients (
  client_id text primary key,
  client_name text,
  redirect_uris text[] not null check (cardinality(redirect_uris) > 0
    and array_position(redirect_uris, null) is null),
  token_endpoint_auth_method text not null default 'none'
    check (token_endpoint_auth_method = 'none'),
  created_at timestamptz not null default now(),
  revoked_at timestamptz
);

create table if not exists oauth_login_sessions (
  session_hash text primary key check (session_hash ~ '^[0-9a-f]{64}$'),
  csrf_token_hash text not null check (csrf_token_hash ~ '^[0-9a-f]{64}$'),
  user_id text references users(id),
  created_at timestamptz not null default now(),
  expires_at timestamptz not null check (expires_at > created_at),
  revoked_at timestamptz
);

create table if not exists oauth_authorization_requests (
  request_hash text primary key check (request_hash ~ '^[0-9a-f]{64}$'),
  session_hash text not null references oauth_login_sessions(session_hash),
  client_id text not null references oauth_clients(client_id),
  redirect_uri text not null,
  resource text not null,
  scopes text[] not null check (array_position(scopes, null) is null),
  state text,
  code_challenge text not null check (code_challenge ~ '^[A-Za-z0-9_-]{43}$'),
  code_challenge_method text not null default 'S256' check (code_challenge_method = 'S256'),
  created_at timestamptz not null default now(),
  expires_at timestamptz not null check (expires_at > created_at),
  consumed_at timestamptz
);

create table if not exists oauth_authorization_codes (
  code_hash text primary key check (code_hash ~ '^[0-9a-f]{64}$'),
  request_hash text not null unique references oauth_authorization_requests(request_hash),
  client_id text not null references oauth_clients(client_id),
  user_id text not null references users(id),
  redirect_uri text not null,
  resource text not null,
  scopes text[] not null check (array_position(scopes, null) is null),
  code_challenge text not null check (code_challenge ~ '^[A-Za-z0-9_-]{43}$'),
  code_challenge_method text not null default 'S256' check (code_challenge_method = 'S256'),
  created_at timestamptz not null default now(),
  expires_at timestamptz not null check (expires_at > created_at),
  consumed_at timestamptz
);

-- A family groups every refresh rotation and the access tokens it issued.
create table if not exists oauth_token_families (
  id uuid primary key default gen_random_uuid(),
  client_id text not null references oauth_clients(client_id),
  user_id text not null references users(id),
  resource text not null,
  scopes text[] not null check (array_position(scopes, null) is null),
  created_at timestamptz not null default now(),
  expires_at timestamptz not null check (expires_at > created_at),
  revoked_at timestamptz,
  unique (id, client_id, user_id, resource)
);

create table if not exists oauth_refresh_tokens (
  token_hash text primary key check (token_hash ~ '^[0-9a-f]{64}$'),
  family_id uuid not null references oauth_token_families(id),
  parent_token_hash text unique,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null check (expires_at > created_at),
  consumed_at timestamptz,
  revoked_at timestamptz,
  unique (token_hash, family_id),
  foreign key (parent_token_hash, family_id)
    references oauth_refresh_tokens(token_hash, family_id),
  check (parent_token_hash is null or parent_token_hash <> token_hash)
);

-- One initial refresh token per family; one child per rotated token.
create unique index if not exists oauth_refresh_tokens_root_idx
  on oauth_refresh_tokens(family_id) where parent_token_hash is null;

create table if not exists oauth_access_tokens (
  token_hash text primary key check (token_hash ~ '^[0-9a-f]{64}$'),
  family_id uuid not null,
  client_id text not null,
  user_id text not null,
  resource text not null,
  scopes text[] not null check (array_position(scopes, null) is null),
  created_at timestamptz not null default now(),
  expires_at timestamptz not null check (expires_at > created_at),
  revoked_at timestamptz,
  foreign key (family_id, client_id, user_id, resource)
    references oauth_token_families(id, client_id, user_id, resource)
);

create index if not exists oauth_login_sessions_expiry_idx on oauth_login_sessions(expires_at);
create index if not exists oauth_login_sessions_user_idx on oauth_login_sessions(user_id);
create index if not exists oauth_authorization_requests_expiry_idx
  on oauth_authorization_requests(expires_at);
create index if not exists oauth_authorization_requests_session_idx
  on oauth_authorization_requests(session_hash);
create index if not exists oauth_authorization_requests_client_idx
  on oauth_authorization_requests(client_id);
create index if not exists oauth_authorization_codes_expiry_idx
  on oauth_authorization_codes(expires_at);
create index if not exists oauth_authorization_codes_user_idx on oauth_authorization_codes(user_id);
create index if not exists oauth_authorization_codes_client_idx
  on oauth_authorization_codes(client_id);
create index if not exists oauth_token_families_expiry_idx on oauth_token_families(expires_at);
create index if not exists oauth_token_families_user_idx on oauth_token_families(user_id);
create index if not exists oauth_token_families_client_idx on oauth_token_families(client_id);
create index if not exists oauth_refresh_tokens_family_idx on oauth_refresh_tokens(family_id);
create index if not exists oauth_refresh_tokens_expiry_idx on oauth_refresh_tokens(expires_at);
create index if not exists oauth_access_tokens_family_idx on oauth_access_tokens(family_id);
create index if not exists oauth_access_tokens_expiry_idx on oauth_access_tokens(expires_at);
create index if not exists oauth_access_tokens_user_idx on oauth_access_tokens(user_id);
create index if not exists oauth_access_tokens_client_idx on oauth_access_tokens(client_id);

-- Server-only tables: no access through Supabase's public Data API.
alter table oauth_clients enable row level security;
alter table oauth_login_sessions enable row level security;
alter table oauth_authorization_requests enable row level security;
alter table oauth_authorization_codes enable row level security;
alter table oauth_token_families enable row level security;
alter table oauth_refresh_tokens enable row level security;
alter table oauth_access_tokens enable row level security;

revoke all on oauth_clients, oauth_login_sessions, oauth_authorization_requests,
  oauth_authorization_codes, oauth_token_families, oauth_refresh_tokens,
  oauth_access_tokens from public;

do $$
declare api_role text;
begin
  foreach api_role in array array['anon', 'authenticated'] loop
    if exists (select 1 from pg_roles where rolname = api_role) then
      execute format('revoke all on oauth_clients, oauth_login_sessions,
        oauth_authorization_requests, oauth_authorization_codes, oauth_token_families,
        oauth_refresh_tokens, oauth_access_tokens from %I', api_role);
    end if;
  end loop;
end;
$$;

commit;
