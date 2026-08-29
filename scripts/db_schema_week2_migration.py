#!/usr/bin/env python3
"""
Week 2, Task 2.3: Database Schema Migration

Add columns for Hybrid Pipeline support:
- Extraction metadata (method, risk level, confidence, latency)
- Human verification tracking
- Queue management tables
"""

import sqlite3
from pathlib import Path

print("\n" + "=" * 70)
print("Week 2, Task 2.3: Database Schema Migration")
print("=" * 70)

conn = sqlite3.connect("data/spese.db")
cursor = conn.cursor()

# Helper: Check if column exists
def column_exists(table_name, column_name):
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    return column_name in columns

# Helper: Add column safely
def add_column_if_missing(table_name, column_def):
    parts = column_def.split()
    col_name = parts[1]
    if not column_exists(table_name, col_name):
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_def}")
        print(f"  ✅ Added {table_name}.{col_name}")
    else:
        print(f"  ⏭️  {table_name}.{col_name} already exists")

print("\n📝 Adding columns to receipts table...")
add_column_if_missing("receipts", "extraction_flags TEXT DEFAULT NULL")
add_column_if_missing("receipts", "hybrid_method TEXT DEFAULT 'geometric'")
add_column_if_missing("receipts", "extraction_risk_level TEXT DEFAULT 'low'")
add_column_if_missing("receipts", "extraction_confidence REAL DEFAULT 0.0")
add_column_if_missing("receipts", "extraction_latency_ms INTEGER DEFAULT NULL")

print("\n📝 Adding columns to receipt_lines table...")
add_column_if_missing("receipt_lines", "verified_by_human BOOLEAN DEFAULT 0")
add_column_if_missing("receipt_lines", "verification_timestamp TIMESTAMP DEFAULT NULL")
add_column_if_missing("receipt_lines", "verified_by_user TEXT DEFAULT NULL")
add_column_if_missing("receipt_lines", "verification_notes TEXT DEFAULT NULL")
add_column_if_missing("receipt_lines", "is_hallucinated BOOLEAN DEFAULT 0")

print("\n📋 Creating extraction_queue table...")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS extraction_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        receipt_id INTEGER NOT NULL,
        task_id TEXT UNIQUE NOT NULL,
        method TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        started_at TIMESTAMP DEFAULT NULL,
        completed_at TIMESTAMP DEFAULT NULL,
        error_message TEXT DEFAULT NULL,
        result_json TEXT DEFAULT NULL,

        FOREIGN KEY (receipt_id) REFERENCES receipts(id) ON DELETE CASCADE
    )
""")
print("  ✅ extraction_queue created")

print("\n📋 Creating manual_review_queue table...")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS manual_review_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        receipt_id INTEGER NOT NULL,
        reason TEXT NOT NULL,
        extraction_method TEXT,
        errors TEXT,
        priority INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        started_at TIMESTAMP DEFAULT NULL,
        completed_at TIMESTAMP DEFAULT NULL,
        reviewed_by TEXT DEFAULT NULL,
        review_notes TEXT DEFAULT NULL,
        action_taken TEXT,

        FOREIGN KEY (receipt_id) REFERENCES receipts(id) ON DELETE CASCADE
    )
""")
print("  ✅ manual_review_queue created")

print("\n📋 Creating extraction_metrics table...")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS extraction_metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date DATE NOT NULL,
        method TEXT NOT NULL,
        count INTEGER DEFAULT 0,
        avg_accuracy REAL DEFAULT 0.0,
        avg_latency_ms INTEGER DEFAULT 0,
        hallucination_rate REAL DEFAULT 0.0,

        UNIQUE(date, method)
    )
""")
print("  ✅ extraction_metrics created")

print("\n🔍 Creating indexes...")
try:
    cursor.execute("CREATE INDEX idx_receipts_hybrid_method ON receipts(hybrid_method)")
    print("  ✅ idx_receipts_hybrid_method")
except sqlite3.OperationalError:
    print("  ⏭️  idx_receipts_hybrid_method already exists")

try:
    cursor.execute("CREATE INDEX idx_receipts_risk_level ON receipts(extraction_risk_level)")
    print("  ✅ idx_receipts_risk_level")
except sqlite3.OperationalError:
    print("  ⏭️  idx_receipts_risk_level already exists")

try:
    cursor.execute("CREATE INDEX idx_receipt_lines_verified ON receipt_lines(verified_by_human)")
    print("  ✅ idx_receipt_lines_verified")
except sqlite3.OperationalError:
    print("  ⏭️  idx_receipt_lines_verified already exists")

try:
    cursor.execute("CREATE INDEX idx_receipt_lines_hallucinated ON receipt_lines(is_hallucinated)")
    print("  ✅ idx_receipt_lines_hallucinated")
except sqlite3.OperationalError:
    print("  ⏭️  idx_receipt_lines_hallucinated already exists")

try:
    cursor.execute("CREATE INDEX idx_extraction_queue_status ON extraction_queue(status)")
    print("  ✅ idx_extraction_queue_status")
except sqlite3.OperationalError:
    print("  ⏭️  idx_extraction_queue_status already exists")

try:
    cursor.execute("CREATE INDEX idx_review_queue_created ON manual_review_queue(created_at)")
    print("  ✅ idx_review_queue_created")
except sqlite3.OperationalError:
    print("  ⏭️  idx_review_queue_created already exists")

conn.commit()

print("\n✅ Database migration completed successfully")
print("=" * 70)

conn.close()
