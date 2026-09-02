import { getRenderableClaims, MARKETING_CLAIMS } from "@/content/brand.vi"
import { CONTAINER_WIDE } from "@/lib/layout"
import { cn } from "@/lib/utils"

const renderableClaims = new Map(
  getRenderableClaims(MARKETING_CLAIMS).map((claim) => [claim.id, claim])
)
const processDetailsClaim = renderableClaims.get("process-details")

const PROCESS_ROWS = [
  {
    number: "01",
    claimId: "course-files",
    label: "TỆP",
    title: "Tệp nguồn",
    titleClass: "lg:col-span-3",
    descriptionClass: "lg:col-span-5 lg:col-start-8",
  },
  {
    number: "02",
    claimId: "indexing",
    label: "CHUẨN BỊ",
    title: "Đọc và lập chỉ mục",
    titleClass: "lg:col-span-4",
    descriptionClass: "lg:col-span-4 lg:col-start-7",
  },
  {
    number: "03",
    claimId: "output-selection",
    label: "LỰA CHỌN",
    title: "Chọn học liệu",
    titleClass: "lg:col-span-3 lg:col-start-4",
    descriptionClass: "lg:col-span-5 lg:col-start-8",
  },
  {
    number: "04",
    claimId: "delivery",
    label: "SỬ DỤNG",
    title: "Học và tải xuống",
    titleClass: "lg:col-span-4",
    descriptionClass: "lg:col-span-5 lg:col-start-7",
  },
] as const

export function ProcessLedger() {
  return (
    <section id="process" aria-labelledby="process-title" className="scroll-mt-20">
      <div className={cn(CONTAINER_WIDE, "py-20 sm:py-24 lg:py-28")}>
        <div className="grid gap-5 pb-10 lg:grid-cols-12 lg:items-end">
          <div className="lg:col-span-7">
            <p className="font-mono text-xs uppercase tracking-[0.18em] text-ring">
              Từ tệp đến buổi học
            </p>
            <h2
              id="process-title"
              className="font-display mt-4 max-w-[22ch] text-3xl font-semibold leading-tight sm:text-4xl"
            >
              Một tài liệu đi qua HackaGen như thế nào
            </h2>
          </div>
          {processDetailsClaim ? (
            <p
              className="max-w-[48ch] text-sm leading-6 text-muted-foreground lg:col-span-4 lg:col-start-9"
              data-marketing-claim-id={processDetailsClaim.id}
            >
              {processDetailsClaim.text}
            </p>
          ) : null}
        </div>

        <ol className="border-b border-border">
          {PROCESS_ROWS.filter((row) => renderableClaims.has(row.claimId)).map((row) => (
            <li
              key={row.number}
              className="grid gap-x-6 gap-y-3 border-t border-border py-7 sm:grid-cols-[4rem_1fr] lg:grid-cols-12 lg:items-baseline lg:py-8"
            >
              <div className="flex items-baseline justify-between gap-2 sm:block lg:col-span-2">
                <span className="font-display text-2xl font-semibold text-accent-strong">
                  {row.number}
                </span>
                <span className="font-mono text-[0.65rem] tracking-[0.16em] text-muted-foreground sm:mt-2 sm:block">
                  {row.label}
                </span>
              </div>
              <h3
                className={cn(
                  "font-display text-xl font-semibold leading-snug sm:col-start-2 lg:col-start-auto",
                  row.titleClass
                )}
              >
                {row.title}
              </h3>
              <p
                className={cn(
                  "max-w-[56ch] text-sm leading-6 text-muted-foreground sm:col-start-2 lg:col-start-auto",
                  row.descriptionClass
                )}
                data-marketing-claim-id={row.claimId}
              >
                {renderableClaims.get(row.claimId)?.text}
              </p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  )
}
