"""Read-only provider counters; save allowlisted numeric fields only."""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
import httpx
from dotenv import dotenv_values

root = Path(__file__).resolve().parents[2]
key = dotenv_values(root / '.env').get('OPENROUTER_API_KEY', '')
result = {'time_utc': datetime.now(timezone.utc).isoformat()}
try:
    response = httpx.get('https://openrouter.ai/api/v1/key', headers={'Authorization': 'Bearer ' + key}, timeout=20)
    result['http_status'] = response.status_code
    if response.is_success:
        data = response.json().get('data', {})
        result['counters'] = {k: data.get(k) for k in ('usage','limit','limit_remaining','limit_reset')}
except Exception as exc:
    result['error_type'] = type(exc).__name__
path = Path(__file__).resolve().parent / (sys.argv[1] + '.json')
path.write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result))
