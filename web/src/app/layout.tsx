import type { Metadata, Viewport } from "next"
import localFont from "next/font/local"

import { ThemeProvider } from "@/components/theme"
import { DirectionProvider } from "@/components/ui/direction"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import "./globals.css"

// IBM Plex Sans Arabic, SIL Open Font License 1.1 (./fonts/OFL-IBM-Plex-Sans-Arabic.txt).
// Served from this app: no font CDN, no external request at runtime. The Arabic and Latin
// subsets are separate files; the browser falls back between the two families per glyph.
const plexArabic = localFont({
  src: [
    { path: "./fonts/ibm-plex-sans-arabic-arabic-400-normal.woff2", weight: "400", style: "normal" },
    { path: "./fonts/ibm-plex-sans-arabic-arabic-700-normal.woff2", weight: "700", style: "normal" },
  ],
  variable: "--font-plex-ar",
  display: "swap",
})
const plexLatin = localFont({
  src: [
    { path: "./fonts/ibm-plex-sans-arabic-latin-400-normal.woff2", weight: "400", style: "normal" },
    { path: "./fonts/ibm-plex-sans-arabic-latin-700-normal.woff2", weight: "700", style: "normal" },
  ],
  variable: "--font-plex-latin",
  display: "swap",
})

export const metadata: Metadata = {
  title: { default: "نَظير · بيانات واقعية بلا أشخاص حقيقيين", template: "%s · نَظير" },
  description:
    "نَظير يكتشف البيانات الشخصية في جداولك وملاحظاتك العربية، ويولّد نسخة نظيرة صالحة ومتّسقة، ويثبت أمانها قبل مشاركتها.",
}

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f3f5f7" },
    { media: "(prefers-color-scheme: dark)", color: "#0d131b" },
  ],
}

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ar" dir="rtl" className={`${plexArabic.variable} ${plexLatin.variable} h-full`} suppressHydrationWarning>
      <body className="min-h-full">
        <ThemeProvider>
          <DirectionProvider direction="rtl">
            <TooltipProvider>
              {children}
              <Toaster position="bottom-left" dir="rtl" richColors closeButton />
            </TooltipProvider>
          </DirectionProvider>
        </ThemeProvider>
      </body>
    </html>
  )
}
