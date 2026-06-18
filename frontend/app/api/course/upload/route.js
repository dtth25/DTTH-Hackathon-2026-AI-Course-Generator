export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const BACKEND_URL = process.env.BACKEND_URL || 'http://127.0.0.1:8000';
const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;
const WINDOW_MS = 60 * 1000;
const MAX_REQUESTS_PER_WINDOW = 8;

const buckets = new Map();

function getClientKey(request) {
  return (
    request.headers.get('x-forwarded-for')?.split(',')[0]?.trim() ||
    request.headers.get('x-real-ip') ||
    'local-dev'
  );
}

function checkRateLimit(key) {
  const now = Date.now();
  const current = buckets.get(key);

  if (!current || now > current.resetAt) {
    buckets.set(key, { count: 1, resetAt: now + WINDOW_MS });
    return true;
  }

  current.count += 1;
  return current.count <= MAX_REQUESTS_PER_WINDOW;
}

function jsonError(message, status = 400, detail = undefined) {
  return Response.json(
    { status: 'error', message, detail },
    { status }
  );
}

export async function POST(request) {
  const clientKey = getClientKey(request);
  if (!checkRateLimit(clientKey)) {
    return jsonError('Bạn upload quá nhanh. Chờ khoảng 1 phút rồi thử lại.', 429);
  }

  let formData;
  try {
    formData = await request.formData();
  } catch (error) {
    return jsonError('Request không phải multipart/form-data hợp lệ.', 400, String(error));
  }

  const file = formData.get('file');
  if (!file || typeof file === 'string') {
    return jsonError('Thiếu file PDF.', 400);
  }

  if (!file.name?.toLowerCase().endsWith('.pdf')) {
    return jsonError('Hiện tại chỉ hỗ trợ file PDF.', 400);
  }

  if (file.size > MAX_UPLOAD_BYTES) {
    return jsonError('File vượt quá 50MB.', 400);
  }

  const backendForm = new FormData();
  backendForm.append('file', file, file.name);

  try {
    const backendResponse = await fetch(`${BACKEND_URL}/api/course/upload`, {
      method: 'POST',
      body: backendForm,
      cache: 'no-store',
    });

    const payload = await backendResponse.json().catch(() => null);

    if (!backendResponse.ok) {
      return Response.json(
        {
          status: 'error',
          message: payload?.detail || payload?.message || 'Backend xử lý PDF thất bại.',
          detail: payload,
        },
        { status: backendResponse.status }
      );
    }

    return Response.json(payload, { status: 200 });
  } catch (error) {
    return jsonError(
      'Không kết nối được backend Python. Hãy chạy run_backend.bat trước.',
      502,
      String(error)
    );
  }
}
