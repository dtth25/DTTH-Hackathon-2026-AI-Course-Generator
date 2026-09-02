import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import LoginPage from "./page";
import { ApiRequestError, apiLogin } from "@/lib/api";

const navigation = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock("next/navigation", () => ({
  useRouter: () => navigation,
}));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  apiLogin: vi.fn(),
}));

vi.mock("@/lib/auth", () => ({
  setToken: vi.fn(),
  setStoredUser: vi.fn(),
}));

describe("login error copy", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders safe allowlisted credentials copy instead of backend detail", async () => {
    vi.mocked(apiLogin).mockRejectedValue(
      new ApiRequestError(
        "Email hoặc mật khẩu không chính xác.",
        401,
        { code: "invalid_credentials", message: "Failed to fetch" },
        "invalid_credentials"
      )
    );
    const user = userEvent.setup();
    render(<LoginPage />);

    await user.type(screen.getByLabelText("Email"), "user@example.com");
    await user.type(screen.getByLabelText("Mật khẩu"), "password");
    await user.click(screen.getByRole("button", { name: "Đăng nhập" }));

    expect(await screen.findByText("Email hoặc mật khẩu không chính xác.")).toBeVisible();
    expect(screen.queryByText("Failed to fetch")).not.toBeInTheDocument();
  });
});
