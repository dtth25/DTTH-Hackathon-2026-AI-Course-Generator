export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const BACKEND_URL = process.env.BACKEND_URL || 'http://127.0.0.1:8000';

export async function GET() {
  try {
    const response = await fetch(`${BACKEND_URL}/health`, { cache: 'no-store' });
    const data = await response.json();
    return Response.json({ frontend: 'ok', backend: data }, { status: response.status });
  } catch (error) {
    return Response.json(
      { frontend: 'ok', backend: 'offline', error: String(error) },
      { status: 502 }
    );
  }
}
