CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  title TEXT,
  description TEXT,
  status TEXT CHECK(status IN ('PENDING','PLANNING','RUNNING','WAITING','COMPLETED','FAILED','CANCELLED')) DEFAULT 'PENDING',
  priority TEXT CHECK(priority IN ('LOW','MEDIUM','HIGH')) DEFAULT 'MEDIUM',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  current_step_index INTEGER DEFAULT 0,
  progress_notes JSON,
  delegation_depth INTEGER DEFAULT 0,
  delegation_chain JSON,
  result TEXT,
  error TEXT,
  metadata JSON
);

CREATE TABLE IF NOT EXISTS task_steps (
  id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  description TEXT,
  tool TEXT,
  parameters JSON,
  status TEXT CHECK(status IN ('pending','running','done','failed')) DEFAULT 'pending',
  result TEXT,
  error TEXT,
  retry_count INTEGER DEFAULT 0,
  worker TEXT CHECK(worker IN ('general','research','automation','system')) DEFAULT 'general',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  completed_at DATETIME,
  FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
);
