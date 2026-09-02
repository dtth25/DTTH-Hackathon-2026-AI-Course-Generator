import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiNetworkError,
  ApiRequestError,
  apiGetCourseStatus,
  apiGetJob,
  apiRetryDocument,
} from "./api";

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
});
