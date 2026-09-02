import Image from "next/image"

import { getRenderableClaims, MARKETING_CLAIMS } from "@/content/brand.vi"
import { CONTAINER_WIDE } from "@/lib/layout"
import { cn } from "@/lib/utils"

const renderableClaims = new Map(
  getRenderableClaims(MARKETING_CLAIMS).map((claim) => [claim.id, claim])
)
const fixtureEvidenceClaim = renderableClaims.get("fixture-evidence")
const bookEvidenceClaim = renderableClaims.get("book-evidence")
const videoEvidenceClaim = renderableClaims.get("video-evidence")

export function ProductEvidence() {
  if (!fixtureEvidenceClaim || !bookEvidenceClaim || !videoEvidenceClaim) return null

  return (
    <section id="evidence" aria-labelledby="evidence-title" className="bg-secondary/45">
      <div className={cn(CONTAINER_WIDE, "py-18 sm:py-22 lg:py-24")}>
        <div className="grid gap-5 lg:grid-cols-12 lg:items-end">
          <div className="lg:col-span-6">
            <p className="font-mono text-xs uppercase tracking-[0.18em] text-ring">
              Sản phẩm đang chạy
            </p>
            <h2
              id="evidence-title"
              className="font-display mt-4 max-w-[20ch] text-3xl font-semibold leading-tight sm:text-4xl"
            >
              Nhìn vào không gian học, không nhìn vào lời hứa
            </h2>
          </div>
          <p
            className="max-w-[48ch] text-sm leading-6 text-muted-foreground lg:col-span-4 lg:col-start-9"
            data-marketing-claim-id={fixtureEvidenceClaim.id}
          >
            {fixtureEvidenceClaim.text}
          </p>
        </div>

        <div className="mt-12 grid gap-x-8 gap-y-14 lg:grid-cols-12 lg:items-start">
          <figure className="lg:col-span-7">
            <div className="overflow-hidden rounded-[10px] border border-border bg-card shadow-[var(--shadow-xs)]">
              <Image
                src="/product/book-reading.png"
                alt="Study Guide minh họa với mục lục, phần tóm tắt và nút tải PDF"
                width={944}
                height={459}
                sizes="(max-width: 1023px) 100vw, 58vw"
                className="h-auto w-full"
              />
            </div>
            <figcaption className="mt-4 grid gap-2 sm:grid-cols-[10rem_1fr]">
              <span className="font-mono text-[0.68rem] uppercase tracking-[0.14em] text-ring">
                Minh họa giao diện
              </span>
              <span
                className="text-sm leading-6 text-muted-foreground"
                data-marketing-claim-id={bookEvidenceClaim.id}
              >
                {bookEvidenceClaim.text}
              </span>
            </figcaption>
          </figure>

          <figure className="lg:col-span-5 lg:mt-20">
            <div className="overflow-hidden rounded-[10px] border border-border bg-card shadow-[var(--shadow-sm)]">
              <Image
                src="/product/video-progress.png"
                alt="Không gian video minh họa với lựa chọn định dạng, giọng đọc và tiến độ dựng"
                width={944}
                height={633}
                sizes="(max-width: 1023px) 100vw, 42vw"
                className="h-auto w-full"
              />
            </div>
            <figcaption className="mt-4 grid gap-2 sm:grid-cols-[10rem_1fr] lg:grid-cols-1">
              <span className="font-mono text-[0.68rem] uppercase tracking-[0.14em] text-ring">
                Minh họa giao diện
              </span>
              <span
                className="text-sm leading-6 text-muted-foreground"
                data-marketing-claim-id={videoEvidenceClaim.id}
              >
                {videoEvidenceClaim.text}
              </span>
            </figcaption>
          </figure>
        </div>
      </div>
    </section>
  )
}
