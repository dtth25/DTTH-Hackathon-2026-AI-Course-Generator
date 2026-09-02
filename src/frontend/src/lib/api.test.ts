import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiNetworkError,
  ApiRequestError,
  apiFetch,
  apiGetCourseStatus,
  apiGetCurrentUser,
  apiGetJob,
  apiDeleteAccount,
  apiLogin,
  apiRetryDocument,
  apiUploadFiles,
  apiVerifyEmail,
} from "./api";
import { removeToken } from "@/lib/auth";
import { normalizePublicError } from "@/lib/types";

vi.mock("@/lib/auth", () => ({
  getAuthHeaders: () => ({}),
  getToken: () => null,
  removeToken: vi.fn(),
}));

const NETWORK_MESSAGE =
  "Không thể kết nối đến máy chủ. Vui lòng kiểm tra backend và thử lại.";

describe("apiFetch network errors", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("normalizes every network TypeError into the stable public error", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    vi.stubGlobal("fetch", fetchMock);

    for (const request of [
      () => apiGetCourseStatus("course-1"),
      () => apiRetryDocument("course-1"),
      () => apiGetJob("job-1"),
    ]) {
      await expect(request()).rejects.toMatchObject({
        name: "ApiNetworkError",
        code: "NETWORK_UNAVAILABLE",
        message: NETWORK_MESSAGE,
      });
    }
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("preserves structured HTTP errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ detail: { code: "DOCUMENT_RETRY_NOT_ALLOWED", message: "Không thể thử lại." } }),
          { status: 409, headers: { "Content-Type": "application/json" } }
        )
      )
    );

    await expect(apiRetryDocument("course-1")).rejects.toEqual(
      expect.objectContaining<ApiRequestError>({
        status: 409,
        detail: { code: "DOCUMENT_RETRY_NOT_ALLOWED", message: "Không thể thử lại." },
      })
    );
  });

  it("never promotes an arbitrary backend detail into the public error message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Failed to fetch" }), { status: 500 })
      )
    );

    await expect(apiFetch("/api/auth/me")).rejects.toMatchObject({
      name: "ApiRequestError",
      status: 500,
      detail: "Failed to fetch",
      message: "Đã xảy ra lỗi. Vui lòng thử lại.",
    });
  });

  it("uses the safe Vietnamese message mapped for an allowlisted retry code", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: {
              code: "DOCUMENT_RETRY_NOT_ALLOWED",
              message: "arbitrary backend text must not be displayed",
            },
          }),
          { status: 409, headers: { "Content-Type": "application/json" } }
        )
      )
    );

    await expect(apiRetryDocument("course-1")).rejects.toMatchObject({
      code: "DOCUMENT_RETRY_NOT_ALLOWED",
      message: "Tài liệu chưa ở trạng thái có thể thử lại.",
    });
  });

  it("rethrows AbortError without converting it to a visible network failure", async () => {
    const abort = new DOMException("The operation was aborted.", "AbortError");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(abort));

    await expect(apiGetCourseStatus("course-1")).rejects.toBe(abort);
    await expect(apiGetCourseStatus("course-1")).rejects.not.toBeInstanceOf(ApiNetworkError);
  });

  it("uses encoded backend paths for document retry and job status", async () => {
    const fetchMock = vi.fn().mockImplementation(
      () => Promise.resolve(new Response(JSON.stringify({}), { status: 200 }))
    );
    vi.stubGlobal("fetch", fetchMock);

    await apiRetryDocument("course/id ?");
    await apiGetJob("job/id ?");

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      expect.stringMatching(/\/api\/documents\/course%2Fid%20%3F\/retry$/u),
      expect.objectContaining({ method: "POST" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      expect.stringMatching(/\/api\/jobs\/job%2Fid%20%3F$/u),
      expect.any(Object)
    );
  });

  it("normalizes closed status codes and falls back for unknown envelopes", () => {
    expect(normalizePublicError("INLINE_PROCESSING_INTERRUPTED")).toBe(
      "Tác vụ xử lý trước đó bị gián đoạn. Vui lòng thử lại."
    );
    expect(normalizePublicError("UNKNOWN_BACKEND_ERROR", "Tạo học liệu thất bại.")).toBe(
      "Tạo học liệu thất bại."
    );
    expect(normalizePublicError("BOOK_GENERATION_FAILED")).toBe(
      "Không thể tạo sách ôn tập. Vui lòng thử lại."
    );
    expect(normalizePublicError("VIDEO_GENERATION_FAILED")).toBe(
      "Không thể tạo video. Vui lòng thử lại."
    );
  });
});

class MockXmlHttpRequest {
  static instance: MockXmlHttpRequest | null = null;
  status = 0;
  responseText = "";
  withCredentials = false;
  upload = { addEventListener: vi.fn() };
  private readonly listeners = new Map<string, () => void>();

  constructor() {
    MockXmlHttpRequest.instance = this;
  }

  open = vi.fn();
  setRequestHeader = vi.fn();
  addEventListener = vi.fn((event: string, callback: () => void) => {
    this.listeners.set(event, callback);
  });
  send = vi.fn();

  dispatch(event: string) {
    this.listeners.get(event)?.();
  }
}

describe("apiUploadFiles progress transport", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    MockXmlHttpRequest.instance = null;
  });

  it("uses the shared safe HTTP error mapping instead of a backend detail", async () => {
    vi.stubGlobal("XMLHttpRequest", MockXmlHttpRequest);
    const request = apiUploadFiles([new File(["pdf"], "notes.pdf")], vi.fn());
    const xhr = MockXmlHttpRequest.instance!;
    xhr.status = 500;
    xhr.responseText = JSON.stringify({ detail: "Failed to fetch" });
    xhr.dispatch("load");

    await expect(request).rejects.toMatchObject({
      name: "ApiRequestError",
      status: 500,
      detail: "Failed to fetch",
      message: "Đã xảy ra lỗi. Vui lòng thử lại.",
    });
  });

  it("keeps a structured scheduling code without rendering an object", async () => {
    vi.stubGlobal("XMLHttpRequest", MockXmlHttpRequest);
    const request = apiUploadFiles([new File(["pdf"], "notes.pdf")], vi.fn());
    const xhr = MockXmlHttpRequest.instance!;
    xhr.status = 503;
    xhr.responseText = JSON.stringify({
      detail: { code: "DOCUMENT_SCHEDULING_FAILED", message: "backend detail" },
    });
    xhr.dispatch("load");

    await expect(request).rejects.toMatchObject({
      code: "DOCUMENT_SCHEDULING_FAILED",
      message: "Không thể bắt đầu xử lý tài liệu. Vui lòng thử lại.",
    });
  });

  it("normalizes XHR network and malformed-success failures safely", async () => {
    vi.stubGlobal("XMLHttpRequest", MockXmlHttpRequest);
    const networkRequest = apiUploadFiles([new File(["pdf"], "notes.pdf")], vi.fn());
    MockXmlHttpRequest.instance!.dispatch("error");
    await expect(networkRequest).rejects.toBeInstanceOf(ApiNetworkError);

    const malformedRequest = apiUploadFiles([new File(["pdf"], "notes.pdf")], vi.fn());
    const xhr = MockXmlHttpRequest.instance!;
    xhr.status = 201;
    xhr.responseText = "not json";
    xhr.dispatch("load");
    await expect(malformedRequest).rejects.toMatchObject({
      name: "ApiRequestError",
      code: "UNKNOWN_ERROR",
      message: "Đã xảy ra lỗi. Vui lòng thử lại.",
    });
  });
});

describe("auth error mappings", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => vi.unstubAllGlobals());

  it("renders known auth codes safely and never exposes server-provided text", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: { code: "invalid_credentials", message: "Failed to fetch" },
          }),
          { status: 401, headers: { "Content-Type": "application/json" } }
        )
      )
    );

    await expect(apiVerifyEmail({ email: "user@example.com", code: "000000" })).rejects.toMatchObject({
      code: "invalid_credentials",
      message: "Email hoặc mật khẩu không chính xác.",
      detail: { code: "invalid_credentials", message: "Failed to fetch" },
    });
  });

  it("uses only a bounded structured remaining-attempt count for OTP copy", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: {
              code: "EMAIL_VERIFICATION_FAILED",
              message: "untrusted server error",
            },
          }),
          { status: 400, headers: { "Content-Type": "application/json" } }
        )
      )
    );

    await expect(apiLogin({ email: "user@example.com", password: "wrong" })).rejects.toMatchObject({
      code: "EMAIL_VERIFICATION_FAILED",
      message: "Không thể xác thực email. Vui lòng kiểm tra email và mã rồi thử lại.",
    });
  });

  it("clears and redirects on a protected GET /api/auth/me 401", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Failed to fetch" }), { status: 401 })
      )
    );

    await expect(apiGetCurrentUser()).rejects.toMatchObject({
      code: "UNAUTHENTICATED",
      message: "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.",
    });
    expect(removeToken).toHaveBeenCalled();
    expect(document.body.textContent).not.toContain("Failed to fetch");
  });

  it("preserves session only for a structured wrong-password account deletion", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ detail: { code: "wrong_password", message: "untrusted" } }),
        { status: 401 }
      )
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiDeleteAccount("wrong")).rejects.toMatchObject({
      code: "wrong_password",
      message: "Mật khẩu không chính xác.",
    });
    expect(removeToken).not.toHaveBeenCalled();
  });

  it("clears session when account deletion fails authentication dependency", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: { code: "UNAUTHENTICATED", message: "expired dependency diagnostic" },
          }),
          { status: 401 }
        )
      )
    );

    await expect(apiDeleteAccount("password123")).rejects.toMatchObject({
      code: "UNAUTHENTICATED",
      message: "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.",
    });
    expect(removeToken).toHaveBeenCalledOnce();
  });
});
