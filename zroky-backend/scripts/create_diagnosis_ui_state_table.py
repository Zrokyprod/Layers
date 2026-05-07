import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".data", "zroky.db")

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

sql = '''
CREATE TABLE IF NOT EXISTS diagnosis_ui_state (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  diagnosis_id TEXT NOT NULL,
  assigned_subject TEXT,
  snoozed_until DATETIME,
  dismissed INTEGER NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
'''

indexes = [
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_diagnosis_ui_state_tenant_diagnosis ON diagnosis_ui_state(tenant_id, diagnosis_id);",
    "CREATE INDEX IF NOT EXISTS ix_diagnosis_ui_state_tenant_updated ON diagnosis_ui_state(tenant_id, updated_at);",
    "CREATE INDEX IF NOT EXISTS ix_diagnosis_ui_state_diagnosis_id ON diagnosis_ui_state(diagnosis_id);",
]

print(f"Using DB at: {DB_PATH}")
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
cur.executescript(sql)
for idx in indexes:
    cur.execute(idx)
conn.commit()
print("Created table and indexes (if not present).")
conn.close()
