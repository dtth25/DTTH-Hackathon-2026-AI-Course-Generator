import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { VersionSwitcher } from "./VersionSwitcher";

describe("VersionSwitcher accessibility", () => {
  it("exposes version choices as pressed buttons in a labelled group", () => {
    render(
      <VersionSwitcher
        versions={[
          {
            version_id: "version-1",
            label: "Bản đầu",
            options: {},
            status: "ready",
            progress: 100,
          },
          {
            version_id: "version-2",
            label: "Bản đang soạn",
            options: {},
            status: "processing",
            progress: 40,
          },
        ]}
        activeVersion="version-1"
        viewedVersion="version-1"
        onSwitch={vi.fn()}
      />
    );

    expect(screen.getByRole("group", { name: "Phiên bản học liệu" })).toBeInTheDocument();
    expect(screen.queryByRole("tablist", { name: "Phiên bản học liệu" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Bản đầu/u })).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    expect(screen.getByRole("button", { name: /Bản đang soạn/u })).toHaveAttribute(
      "aria-pressed",
      "false"
    );
  });
});
