import { cn } from "@/lib/utils"

export type BrandMarkProps = {
  size?: number
  labelled?: boolean
  className?: string
}

export function BrandMark({ size = 28, labelled = false, className }: BrandMarkProps) {
  return (
    <svg
      viewBox="0 0 40 40"
      width={size}
      height={size}
      role={labelled ? "img" : undefined}
      aria-label={labelled ? "HackaGen" : undefined}
      aria-hidden={labelled ? undefined : true}
      className={cn("shrink-0", className)}
    >
      <path d="M5 10v26h24" fill="none" stroke="currentColor" strokeWidth="2.5" />
      <path d="M10 4h18l7 7v24H10z" fill="var(--card)" stroke="currentColor" strokeWidth="2.5" />
      <path d="M28 4v8h7" fill="none" stroke="currentColor" strokeWidth="2.5" />
      <path d="M16 19h13M16 25h9" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
      <path d="M16 31h12" stroke="var(--accent-strong)" strokeWidth="3" strokeLinecap="round" />
    </svg>
  )
}
