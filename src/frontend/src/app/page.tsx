import type { Metadata } from "next"
import Link from "next/link"
import { FileText } from "lucide-react"

import { RedirectIfAuthed } from "@/components/auth/RedirectIfAuthed"
import { CapabilityTable } from "@/components/landing/CapabilityTable"
import { LandingIntro } from "@/components/landing/LandingIntro"
import { ProcessLedger } from "@/components/landing/ProcessLedger"
import { ProductEvidence } from "@/components/landing/ProductEvidence"
import { buttonVariants } from "@/components/ui/button"
import { getRenderableClaims, LANDING_COPY, MARKETING_CLAIMS } from "@/content/brand.vi"
import { CONTAINER_WIDE } from "@/lib/layout"
import { cn } from "@/lib/utils"

export const metadata: Metadata = {
  title: { absolute: "HackaGen | Học liệu từ tài liệu của bạn" },
  description: "Tạo Study Guide, slide, quiz và video từ PDF, DOCX hoặc TXT của bạn.",
}

const startUploadClaim = getRenderableClaims(MARKETING_CLAIMS).find(
  (claim) => claim.id === "start-upload"
)

export default function WelcomePage() {
  return (
    <RedirectIfAuthed>
      <div className="overflow-x-clip">
        <LandingIntro />
        <ProcessLedger />
        <ProductEvidence />
        <CapabilityTable />

        <section id="start" aria-labelledby="start-title" className="border-t border-border">
          <div
            className={cn(
              CONTAINER_WIDE,
              "grid gap-8 py-14 sm:py-16 lg:grid-cols-12 lg:items-center"
            )}
          >
            <div className="flex items-start gap-4 lg:col-span-4">
              <FileText aria-hidden="true" className="mt-0.5 size-5 text-accent-strong" />
              <div>
                <p className="font-mono text-[0.68rem] uppercase tracking-[0.15em] text-muted-foreground">
                  Tệp mẫu
                </p>
                <p className="mt-2 text-sm font-medium text-foreground">de-cuong-mon-hoc.pdf</p>
              </div>
            </div>
            <div className="lg:col-span-4 lg:col-start-5">
              <h2 id="start-title" className="font-display text-2xl font-semibold sm:text-3xl">
                Bắt đầu bằng một tệp đang có
              </h2>
              {startUploadClaim ? (
                <p
                  className="mt-3 max-w-[44ch] text-sm leading-6 text-muted-foreground"
                  data-marketing-claim-id={startUploadClaim.id}
                >
                  {startUploadClaim.text}
                </p>
              ) : null}
            </div>
            <div className="lg:col-span-3 lg:col-start-10 lg:text-right">
              <Link
                href="/register"
                className={buttonVariants({
                  size: "lg",
                  className: "h-11 px-5 text-sm sm:text-base",
                })}
              >
                {LANDING_COPY.primaryCta}
              </Link>
            </div>
          </div>
        </section>
      </div>
    </RedirectIfAuthed>
  )
}
