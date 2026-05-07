import sqlite3
from datetime import datetime, timedelta
import os
import sys

# Add current directory to path
sys.path.append(os.getcwd())

from app.api.endpoints.diagnosis.process_diagnosis import ProcessDiagnosis
from app.db.database import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.models import DiagnosisRequest, User, RepeatRow

# Setup in-memory DB
engine = create_engine('sqlite:///:memory:')
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)
db = TestingSessionLocal()

# Setup test data
user = User(email='test@example.com', hashed_password='pw')
db.add(user)
db.commit()

request = DiagnosisRequest(
    user_id=user.id,
    patient_name='Test',
    status='processing',
    repeat_count=2,
    created_at=datetime.utcnow()
)
db.add(request)
db.commit()

# Adding repeat rows
for i in range(2):
    db.add(RepeatRow(request_id=request.id, status='completed', result='Diagnosis part ' + str(i)))
db.commit()

# Execution and Capture
processor = ProcessDiagnosis(db, request.id)
repeat_rows = db.query(RepeatRow).filter(RepeatRow.request_id == request.id).all()
print(f"Fetched repeat rows count: {len(repeat_rows)}")

progress = processor.summarize_loop_progress(repeat_rows)
print(f"summarize_loop_progress output: {progress}")
