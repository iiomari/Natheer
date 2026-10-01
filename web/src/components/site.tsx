import Link from "next/link"

import { Brand } from "@/components/nz"
import { ThemeToggle } from "@/components/theme"
import { buttonVariants } from "@/components/ui/button"
import { cn } from "@/lib/utils"

const NAV = [
  { href: "/#how", label: "كيف يعمل" },
  { href: "/#security", label: "مبادئ الأمان" },
  { href: "/#faq", label: "الأسئلة الشائعة" },
  { href: "/#contact", label: "تواصل معنا" },
]

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-surface/90 backdrop-blur supports-[backdrop-filter]:bg-surface/75">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-6 px-4 sm:px-6">
        <Brand />
        <nav aria-label="التنقل الرئيسي" className="hidden items-center gap-1 md:flex">
          {NAV.map((n) => (
            <Link key={n.href} href={n.href} className="rounded-md px-3 py-2 text-[0.9375rem] font-medium text-muted-foreground hover:bg-muted hover:text-foreground">
              {n.label}
            </Link>
          ))}
        </nav>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          <Link href="/login" className={cn(buttonVariants({ variant: "ghost" }), "hidden sm:inline-flex")}>
            تسجيل الدخول
          </Link>
          <Link href="/signup" className={buttonVariants()}>
            ابدأ الآن
          </Link>
        </div>
      </div>
    </header>
  )
}

export function SiteFooter() {
  return (
    <footer className="border-t border-border bg-surface">
      <div className="mx-auto grid max-w-6xl gap-8 px-4 py-12 sm:px-6 md:grid-cols-[1.4fr_1fr_1fr]">
        <div className="space-y-3">
          <Brand />
          <p className="max-w-sm text-sm leading-6 text-muted-foreground">
            بيانات واقعية لفرقك وشركائك، بلا أي شخص حقيقي. صُمّم ليعمل داخل المنشأة نفسها.
          </p>
        </div>
        <div className="space-y-3 text-sm">
          <h3 className="font-bold">المنتج</h3>
          <ul className="space-y-2 text-muted-foreground">
            <li><Link className="hover:text-foreground" href="/#how">كيف يعمل</Link></li>
            <li><Link className="hover:text-foreground" href="/#security">مبادئ الأمان</Link></li>
            <li><Link className="hover:text-foreground" href="/#faq">الأسئلة الشائعة</Link></li>
          </ul>
        </div>
        <div className="space-y-3 text-sm">
          <h3 className="font-bold">قانوني</h3>
          <ul className="space-y-2 text-muted-foreground">
            <li><Link className="hover:text-foreground" href="/privacy">سياسة الخصوصية</Link></li>
            <li><Link className="hover:text-foreground" href="/terms">الشروط والأحكام</Link></li>
          </ul>
        </div>
      </div>
      <div className="border-t border-border">
        <p className="mx-auto max-w-6xl px-4 py-5 text-xs text-muted-foreground sm:px-6">
          © <bdi>2026</bdi> نَظير. جميع الحقوق محفوظة.
        </p>
      </div>
    </footer>
  )
}
