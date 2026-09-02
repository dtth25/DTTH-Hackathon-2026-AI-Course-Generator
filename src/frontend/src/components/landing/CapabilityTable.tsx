import { getRenderableClaims, MARKETING_CLAIMS } from "@/content/brand.vi"
import { CONTAINER_WIDE } from "@/lib/layout"
import { cn } from "@/lib/utils"

const renderableClaims = getRenderableClaims(MARKETING_CLAIMS)
const claimsById = new Map(renderableClaims.map((claim) => [claim.id, claim]))
const capabilityScopeClaim = claimsById.get("capability-scope")
const courseUploadClaim = claimsById.get("course-upload")

const OUTPUT_ROWS = [
  { title: "Study Guide", format: "PDF", claimId: "book-delivery" },
  { title: "Slide", format: "PPTX, PDF", claimId: "slide-formats" },
  { title: "Quiz", format: "PDF đáp án", claimId: "quiz-delivery" },
  { title: "Video", format: "MP4", claimId: "video-delivery" },
] as const

export function CapabilityTable() {
  return (
    <section id="capabilities" aria-labelledby="capabilities-title">
      <div className={cn(CONTAINER_WIDE, "py-20 sm:py-24")}>
        <div className="grid gap-5 lg:grid-cols-12 lg:items-end">
          <h2
            id="capabilities-title"
            className="font-display max-w-[18ch] text-3xl font-semibold leading-tight sm:text-4xl lg:col-span-6"
          >
            Định dạng đi vào và học liệu đi ra
          </h2>
          {capabilityScopeClaim ? (
            <p
              className="max-w-[48ch] text-sm leading-6 text-muted-foreground lg:col-span-4 lg:col-start-9"
              data-marketing-claim-id={capabilityScopeClaim.id}
            >
              {capabilityScopeClaim.text}
            </p>
          ) : null}
        </div>

        <div
          className="mt-10 overflow-x-auto border-y border-border"
          role="group"
          aria-label="Cuộn ngang bảng định dạng"
          tabIndex={0}
        >
          <table
            className="w-full min-w-[46rem] border-collapse text-left text-sm"
            aria-label="Định dạng và học liệu hiện có"
          >
            <thead>
              <tr className="border-b border-border font-mono text-[0.68rem] uppercase tracking-[0.14em] text-muted-foreground">
                <th scope="col" className="w-1/4 px-3 py-4 font-medium sm:px-5">
                  Hạng mục
                </th>
                <th scope="col" className="w-1/4 px-3 py-4 font-medium sm:px-5">
                  Định dạng
                </th>
                <th scope="col" className="px-3 py-4 font-medium sm:px-5">
                  Cách dùng hiện có
                </th>
              </tr>
            </thead>
            <tbody>
              {courseUploadClaim ? (
                <tr className="border-b border-border">
                  <th scope="row" className="px-3 py-5 font-semibold text-foreground sm:px-5">
                    Đầu vào
                  </th>
                  <td className="px-3 py-5 font-mono text-xs text-foreground sm:px-5">
                    PDF, DOCX, TXT
                  </td>
                  <td
                    className="px-3 py-5 text-muted-foreground sm:px-5"
                    data-marketing-claim-id={courseUploadClaim.id}
                  >
                    {courseUploadClaim.text}
                  </td>
                </tr>
              ) : null}
              {OUTPUT_ROWS.filter(({ claimId }) => claimsById.has(claimId)).map(
                ({ title, format, claimId }) => (
                    <tr
                      key={title}
                      className="border-b border-border last:border-b-0"
                    >
                      <th
                        scope="row"
                        className="px-3 py-5 font-semibold text-foreground sm:px-5"
                      >
                        {title}
                      </th>
                      <td className="px-3 py-5 font-mono text-xs text-foreground sm:px-5">
                        {format}
                      </td>
                      <td
                        className="px-3 py-5 text-muted-foreground sm:px-5"
                        data-marketing-claim-id={claimId}
                      >
                        {claimsById.get(claimId)?.text}
                      </td>
                    </tr>
                  )
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  )
}
