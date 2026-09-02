import Image from "next/image"
import Link from "next/link"
import { ArrowRight } from "lucide-react"

import { BrandMark } from "@/components/brand/BrandMark"
import { buttonVariants } from "@/components/ui/button"
import { getRenderableClaims, LANDING_COPY, MARKETING_CLAIMS } from "@/content/brand.vi"
import { CONTAINER_WIDE } from "@/lib/layout"
import { cn } from "@/lib/utils"

const renderableClaims = getRenderableClaims(MARKETING_CLAIMS)
const formatsClaim = renderableClaims.find((claim) => claim.id === "formats")
const outputsClaim = renderableClaims.find((claim) => claim.id === "outputs")
const courseSourceClaim = renderableClaims.find((claim) => claim.id === "course-source")
const documentSourceClaim = renderableClaims.find((claim) => claim.id === "document-source")

export function LandingIntro() {
  return (
    <section id="workspace" aria-labelledby="landing-title" className="border-b border-border">
      <div
        className={cn(
          CONTAINER_WIDE,
          "grid gap-x-8 gap-y-12 py-14 sm:py-18 lg:grid-cols-12 lg:items-center lg:py-24"
        )}
      >
        <div className="lg:col-span-5 lg:pr-4">
          <div className="mb-6 flex items-center gap-3 text-xs font-semibold tracking-[0.14em] text-primary">
            <BrandMark size={24} className="text-primary" />
            <span>{LANDING_COPY.eyebrow}</span>
          </div>

          <h1
            id="landing-title"
            className="font-display max-w-[17ch] text-[2.625rem] font-semibold leading-[1.03] tracking-[-0.025em] text-foreground sm:text-5xl lg:text-[4rem]"
          >
            {LANDING_COPY.headline}
          </h1>
          {formatsClaim && outputsClaim && documentSourceClaim ? (
            <p className="mt-7 max-w-[62ch] text-base leading-7 text-muted-foreground sm:text-lg sm:leading-8">
              <span data-marketing-claim-id={formatsClaim.id}>{formatsClaim.text}</span>{" "}
              <span data-marketing-claim-id={documentSourceClaim.id}>
                {documentSourceClaim.text}
              </span>
              , rồi dựng{" "}
              <span data-marketing-claim-id={outputsClaim.id}>{outputsClaim.text}</span> để bạn học
              tiếp.
            </p>
          ) : null}

          <div className="mt-9 flex flex-col items-start gap-3 sm:flex-row sm:items-center">
            <Link
              href="/register"
              className={buttonVariants({
                size: "lg",
                className: "h-11 px-5 text-sm sm:text-base",
              })}
            >
              {LANDING_COPY.primaryCta}
              <ArrowRight aria-hidden="true" className="ml-1 size-4" />
            </Link>
            <Link
              href="#process"
              className={buttonVariants({
                variant: "link",
                size: "lg",
                className: "h-11 px-1 text-sm text-foreground sm:text-base",
              })}
            >
              {LANDING_COPY.secondaryCta}
            </Link>
          </div>
        </div>

        <div className="relative lg:col-span-7 lg:col-start-6 lg:pl-5">
          <figure className="overflow-hidden rounded-[10px] border border-border bg-card shadow-[var(--shadow-sm)]">
            <Image
              src="/product/course-workspace.png"
              alt="Không gian khóa học minh họa với Study Guide, slide, quiz và video"
              width={1200}
              height={760}
              priority
              sizes="(max-width: 1023px) 100vw, 58vw"
              className="aspect-[12/7.6] w-full object-cover object-top"
            />
            <figcaption className="border-t border-border px-3 py-2 text-xs text-muted-foreground">
              Minh họa giao diện
            </figcaption>
          </figure>

          {courseSourceClaim ? (
            <aside
              className="mt-4 border-l-2 border-accent-strong bg-background px-4 py-3 text-sm leading-6 text-foreground lg:absolute lg:-bottom-7 lg:right-6 lg:mt-0 lg:max-w-[19rem] lg:shadow-[var(--shadow-xs)]"
            >
              <span className="mb-1 block font-mono text-[0.68rem] uppercase tracking-[0.16em] text-ring">
                Ghi chú nguồn
              </span>
              <span data-marketing-claim-id={courseSourceClaim.id}>{courseSourceClaim.text}</span>
            </aside>
          ) : null}
        </div>
      </div>
    </section>
  )
}
