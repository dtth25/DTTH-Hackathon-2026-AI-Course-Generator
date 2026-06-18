# StudyHack.AI Course Compiler v5.5

Bản v5.5 tập trung sửa lỗi upload/Gemini khó debug:

- Thêm `/health` báo rõ backend có đọc được API key không, key có giống format Google API key không.
- Thêm `AUTO_DEMO_ON_AI_ERROR=true`: nếu Gemini key/quota/network lỗi, app vẫn tạo một **demo course fallback** để frontend chạy được, không còn crash trắng.
- Course fallback được đánh dấu rõ trong `debug.generation_mode` và `quality_report`.
- Giữ frontend Next.js + Material UI, server-side route, không lộ API key ở client.
- Giữ UI v5.4 graphic polish và slide preview học thuật.

## Chạy nhanh trên Windows

### CMD 1 — Backend

```bat
cd /d "C:\CP\studyhack_ai_course_compiler_v5_5\studyhack_ai_course_compiler_v5_5"
copy .env.example .env
notepad .env
run_backend.bat
```

Trong `.env`, điền:

```env
GOOGLE_API_KEY=YOUR_GEMINI_API_KEY
```

Nếu key Gemini lỗi, app vẫn fallback demo vì:

```env
AUTO_DEMO_ON_AI_ERROR=true
```

### CMD 2 — Frontend

```bat
cd /d "C:\CP\studyhack_ai_course_compiler_v5_5\studyhack_ai_course_compiler_v5_5\frontend"
npm config set registry https://registry.npmjs.org/
npm install
npm run dev
```

Mở:

```txt
http://127.0.0.1:3000
```

## Kiểm tra

Backend:

```txt
http://127.0.0.1:8000/health
```

Frontend gọi backend:

```txt
http://127.0.0.1:3000/api/health
```

## Lưu ý API key

Gemini API key của Google thường bắt đầu bằng `AIza...`. Nếu key không đúng, backend sẽ fallback demo và hiện `debug.api_key_looks_like_google_key=false`.
