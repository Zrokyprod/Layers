import sqlite3
conn = sqlite3.connect('.data/zroky.db')
ver = conn.execute("SELECT version_num FROM alembic_version").fetchall()
print("Alembic version:", ver)
conn.close()
