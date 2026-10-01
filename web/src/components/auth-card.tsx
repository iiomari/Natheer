import { cn } from "@/lib/utils"

export function AuthCard({
  title,
  description,
  children,
  footer,
  className,
}: {
  title: string
  description?: React.ReactNode
  children: React.ReactNode
  footer?: React.ReactNode
  className?: string
}) {
  return (
    <div className={cn("rounded-xl border border-border bg-card shadow-raised", className)}>
      <div className="px-8 pt-8">
        <h1 className="text-2xl leading-tight font-bold">{title}</h1>
        {description ? <p className="mt-2 text-[0.9375rem] leading-7 text-muted-foreground">{description}</p> : null}
      </div>
      <div className="px-8 pt-6 pb-8">{children}</div>
      {footer ? <div className="border-t border-border px-8 py-4 text-center text-sm text-muted-foreground">{footer}</div> : null}
    </div>
  )
}
