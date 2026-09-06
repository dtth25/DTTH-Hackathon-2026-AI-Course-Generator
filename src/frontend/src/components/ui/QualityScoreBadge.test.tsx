import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { QualityScoreBadge } from "./QualityScoreBadge";

describe("QualityScoreBadge", () => {
  it("renders an absent measurement without inventing a score", () => {
    render(<QualityScoreBadge />);
    expect(screen.getByText("Chưa đánh giá chất lượng")).toBeVisible();
    expect(screen.queryByText(/85|chất lượng cao|đại học/iu)).not.toBeInTheDocument();
  });

  it("labels legacy numbers as structural compatibility checks", () => {
    render(<QualityScoreBadge score={90} />);
    expect(screen.getByText("Kiểm tra cấu trúc (cũ) • 90/100")).toBeVisible();
    expect(screen.queryByText(/chất lượng cao/iu)).not.toBeInTheDocument();
  });

  it("shows extraction completion and indexed chunks without claiming faithfulness", () => {
    render(<QualityScoreBadge report={{ extraction_complete: true, indexed_chunk_count: 12, faithfulness: null }} />);
    expect(screen.getByText("Trích xuất hoàn tất • 12 đoạn nguồn • Độ trung thực: chưa đánh giá")).toBeVisible();
    expect(screen.getByTitle(/độ trung thực.*chưa được đánh giá/iu)).toBeVisible();
  });
});
