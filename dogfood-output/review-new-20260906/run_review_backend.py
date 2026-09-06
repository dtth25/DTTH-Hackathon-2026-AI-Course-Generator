"""Isolated review launcher. No product modules are modified; secrets stay in memory."""
import os
import sys
import re
import json
import secrets
import logging
import threading
import subprocess
import urllib.request
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[2]
RUN = Path(__file__).resolve().parent
BACKEND = ROOT / 'src/backend'
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)
from dotenv import dotenv_values
private = dotenv_values(ROOT / '.env')
for name, value in private.items():
    if value is not None:
        os.environ.setdefault(name, value)
os.environ.update({
    'DATABASE_URL': 'sqlite:///' + (RUN / 'runtime/app.db').as_posix(),
    'JWT_SECRET': secrets.token_urlsafe(48),
    'UPLOAD_DIR': str(RUN / 'runtime/uploads'),
    'OUTPUT_DIR': str(RUN / 'runtime/outputs'),
    'CHROMA_PERSIST_DIR': str(RUN / 'runtime/chroma'),
    'CHROMA_MODE': 'embedded',
    'EMBEDDING_CACHE_DIR': str(RUN / 'runtime/embedding-cache'),
    'ENVIRONMENT': 'local', 'JOB_QUEUE_PROVIDER': 'inline',
    'PROCESSING_EXECUTION_MODE': 'inline',
    'INLINE_PROCESSING_RECOVERY_ENABLED': 'false',
    'CREATE_DEFAULT_ADMIN': 'false',
    'SMTP_USER': '', 'SMTP_PASSWORD': '', 'EMAIL_DEV_FALLBACK': 'true',
    'ALLOWED_ORIGINS': '["http://127.0.0.1:3002","http://localhost:3002"]',
    'PYTHONIOENCODING': 'utf-8',
})
(RUN / 'runtime').mkdir(exist_ok=True)
resumed_password = None
if '--resume' in sys.argv:
    resumed_password = urllib.request.urlopen('http://127.0.0.1:8098/password').read().decode()
    import psutil
    for process in psutil.process_iter(['pid', 'cmdline']):
        args = process.info['cmdline'] or []
        if process.pid != os.getpid() and any(str(Path(__file__).resolve()).lower() == str(a).replace('/', '\\').lower() for a in args):
            process.terminate()
            process.wait(timeout=15)
state = {'password': resumed_password or secrets.token_urlsafe(24), 'otp': ''}
private_values = [v for k, v in os.environ.items() if any(s in k for s in ('SECRET','PASSWORD','API_KEY')) and len(v) > 5]

class SafeHandler(logging.Handler):
    def emit(self, record):
        message = record.getMessage()
        if '[EMAIL_DEV_FALLBACK]' in message:
            match = re.search(r': (\d{6}) ', message)
            if match:
                state['otp'] = match.group(1)
            message = 'Development email captured in memory; delivery not tested.'
        for value in private_values:
            message = message.replace(value, '[REDACTED]')
        message = re.sub(r'([?&]token=)[^\s"&]+', r'\1[REDACTED]', message)
        message = re.sub(r'Bearer\s+\S+', 'Bearer [REDACTED]', message)
        with (RUN / 'backend-redacted.log').open('a', encoding='utf-8') as out:
            out.write(f'{record.levelname} {record.name}: {message}\n')

class Bridge(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def do_GET(self):
        field = self.path.lstrip('/')
        if field not in state or not state[field]:
            self.send_response(409); self.end_headers(); return
        self.send_response(200); self.end_headers()
        self.wfile.write(state[field].encode())
    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
        field = data['field']
        if field not in state or not state[field]:
            self.send_response(409); self.end_headers(); return
        binary = Path(os.environ['APPDATA']) / 'npm/node_modules/agent-browser/bin/agent-browser-win32-x64.exe'
        result = subprocess.run([str(binary), '--session', 'hackagen-review-new', 'fill', data['selector'], state[field]], capture_output=True)
        self.send_response(200 if result.returncode == 0 else 500)
        self.end_headers()
        self.wfile.write(b'filled' if result.returncode == 0 else b'fill failed')

if __name__ == '__main__':
    from alembic.config import Config
    from alembic import command
    command.upgrade(Config(str(BACKEND / 'alembic.ini')), 'head')
    import main
    handler = SafeHandler()
    logging.getLogger().handlers = [handler]
    for name in list(logging.root.manager.loggerDict):
        logger = logging.getLogger(name)
        logger.disabled = False
        logger.handlers = []
        logger.propagate = True
    threading.Thread(target=ThreadingHTTPServer(('127.0.0.1', 8098), Bridge).serve_forever, daemon=True).start()
    import uvicorn
    uvicorn.run(main.app, host='127.0.0.1', port=8002, access_log=False, log_config=None)
