"use client"

import * as RadioGroupPrimitive from "@radix-ui/react-radio-group"
import { cn } from "@/lib/utils"

function RadioGroup({
  className,
  ...props
}: React.ComponentProps<typeof RadioGroupPrimitive.Root>) {
  return (
    <RadioGroupPrimitive.Root
      data-slot="radio-group"
      className={cn("grid gap-2", className)}
      {...props}
    />
  )
}

function RadioGroupItem({
  className,
  ...props
}: React.ComponentProps<typeof RadioGroupPrimitive.Item>) {
  return (
    <RadioGroupPrimitive.Item
      data-slot="radio-group-item"
      className={cn(
        "aspect-square size-4 shrink-0 rounded-full border border-input shadow-xs transition-shadow outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 data-[state=checked]:border-primary data-[state=checked]:bg-primary data-[state=checked]:text-primary-foreground dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40",
        className
      )}
      {...props}
    >
      <RadioGroupPrimitive.Indicator className="flex items-center justify-center text-current">
        <svg
          viewBox="0 0 8 8"
          className="size-2 fill-current"
          aria-hidden="true"
        >
          <circle cx="4" cy="4" r="3.5" />
        </svg>
      </RadioGroupPrimitive.Indicator>
    </RadioGroupPrimitive.Item>
  )
}

export { RadioGroup, RadioGroupItem }