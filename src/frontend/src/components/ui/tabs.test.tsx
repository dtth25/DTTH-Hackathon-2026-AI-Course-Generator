import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Tabs, TabsList, TabsTrigger } from "./tabs";

describe("TabsTrigger contrast", () => {
  it("uses the full foreground token for inactive tab labels", () => {
    render(
      <Tabs defaultValue="book">
        <TabsList aria-label="Loại học liệu">
          <TabsTrigger value="book">Study Guide</TabsTrigger>
          <TabsTrigger value="video">Video</TabsTrigger>
        </TabsList>
      </Tabs>
    );

    const inactiveTab = screen.getByRole("tab", { name: "Video" });
    expect(inactiveTab).toHaveClass("text-foreground");
    expect(inactiveTab).not.toHaveClass("text-foreground/60");
    expect(inactiveTab).not.toHaveClass("dark:text-muted-foreground");
  });
});
