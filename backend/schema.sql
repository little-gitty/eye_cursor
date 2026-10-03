create extension if not exists pgcrypto;

create table if not exists public.eye_devices (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null,
    label text not null default 'Windows computer',
    token_hash text not null unique,
    settings jsonb not null default '{"yaw_range_degrees":20,"pitch_range_degrees":15,"smoothing_window":8,"pose_smoothing_alpha":0.35}'::jsonb,
    status jsonb not null default '{"connected":false,"face_detected":false,"mouse_enabled":false}'::jsonb,
    created_at timestamptz not null default now(),
    last_seen_at timestamptz
);

create table if not exists public.eye_pairing_codes (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null,
    code_hash text not null unique,
    expires_at timestamptz not null,
    used_at timestamptz,
    created_at timestamptz not null default now()
);

alter table public.eye_devices enable row level security;
alter table public.eye_pairing_codes enable row level security;

create or replace function public.consume_eye_pairing_code(p_code_hash text)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
    claimed_user_id uuid;
begin
    update public.eye_pairing_codes
       set used_at = now()
     where code_hash = p_code_hash
       and used_at is null
       and expires_at > now()
    returning user_id into claimed_user_id;

    return claimed_user_id;
end;
$$;

revoke all on function public.consume_eye_pairing_code(text) from public, anon, authenticated;
grant execute on function public.consume_eye_pairing_code(text) to service_role;
