
-- Task Manager Schema

-- Tasks Table
create table if not exists tasks (
  id uuid primary key default gen_random_uuid(),
  user_id text not null,
  title text not null,
  description text,
  status text not null default 'PENDING',
  priority text default 'MEDIUM',
  plan jsonb default '[]'::jsonb,
  current_step int default 0,
  progress_notes text[] default '{}',
  result text,
  error text,
  metadata jsonb default '{}'::jsonb,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- Task Logs Table
create table if not exists task_logs (
  id uuid primary key default gen_random_uuid(),
  task_id uuid references tasks(id) on delete cascade,
  message text not null,
  timestamp timestamptz default now()
);

-- Indexes for performance
create index if not exists idx_tasks_user_status on tasks(user_id, status);
create index if not exists idx_task_logs_task_id on task_logs(task_id);
