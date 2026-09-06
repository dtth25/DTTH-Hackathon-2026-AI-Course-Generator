"""Read-only, allowlisted evidence for the isolated AI_for_A0 review course."""
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COURSE = "7de35d382f3a"
db = sqlite3.connect((ROOT.parent / "runtime/app.db").as_uri() + "?mode=ro", uri=True)
db.row_factory = sqlite3.Row

def rows(query):
    return [dict(row) for row in db.execute(query, (COURSE,))]

result = {
    "time_utc": datetime.now(timezone.utc).isoformat(),
    "course": rows("SELECT id,status,stage,progress,chunk_count,embedding_status,error_code,can_retry,extraction_coverage_json FROM courses WHERE id=?"),
    "jobs": rows("SELECT id,job_type,status,product_stage,progress,attempts,failure_attempts,error_code,created_at,updated_at,completed_at FROM processing_jobs WHERE course_id=? ORDER BY created_at"),
    "calls": rows("SELECT job_id,job_attempt,provider_attempt,feature,stage,model,state,outcome,cost,input_tokens,output_tokens,elapsed_ms,created_at,completed_at FROM provider_calls WHERE course_id=? ORDER BY created_at"),
}
for course in result["course"]:
    value = course.pop("extraction_coverage_json")
    course["extraction_coverage"] = json.loads(value) if value else None
result["known_cost_usd"] = sum(call["cost"] or 0 for call in result["calls"]) / 1e9
result["unknown_cost_rows"] = sum(call["cost"] is None for call in result["calls"])
if len(sys.argv) > 1:
    filename = Path(sys.argv[1]).name
    if not filename.endswith(".json"):
        raise SystemExit("Evidence filename must end in .json")
    (ROOT / filename).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
