CREATE TABLE IF NOT EXISTS incidents (
  incident_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  score REAL NOT NULL,
  reasons_json TEXT NOT NULL,
  repeated_files_json TEXT NOT NULL,
  repeated_errors_json TEXT NOT NULL,
  triggering_event_ids_json TEXT NOT NULL,
  request_count INTEGER NOT NULL,
  recommendation TEXT NOT NULL,
  raw_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_incidents_created_at ON incidents(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_incidents_session_id ON incidents(session_id);

