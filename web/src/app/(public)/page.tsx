import Link from "next/link"
import {
  ArrowLeft,
  Ban,
  Building2,
  FileCheck2,
  FileSearch,
  KeyRound,
  Link2Off,
  Lock,
  Mail,
  ScanSearch,
  Share2,
  ShieldCheck,
  Trash2,
  Upload,
  UserRoundX,
} from "lucide-react"

import { Chip, Num } from "@/components/nz"
import { buttonVariants } from "@/components/ui/button"
import { cn } from "@/lib/utils"

const PROBLEMS = [
  {
    icon: Ban,
    title: "نسخ بيانات الإنتاج مخالفة",
    text: "إعطاء الفرق أو الشركاء نسخة من البيانات الحقيقية يعرّض الأشخاص للخطر ويخالف أنظمة حماية البيانات.",
  },
  {
    icon: Link2Off,
    title: "البيانات العشوائية لا تصلح",
    text: "القيم المختلَقة عشوائياً تفشل في التحقق الرسمي، وتكسر الروابط بين الجداول، فلا يُبنى عليها اختبار ولا تحليل.",
  },
  {
    icon: FileSearch,
    title: "المعرّفات تختبئ في النص",
    text: "أرقام الهوية والجوالات تُكتب داخل الملاحظات العربية، بأرقام عربية ومسافات، فتفوت الأدوات العامة.",
  },
]

const STEPS = [
  { icon: Upload, title: "ارفع بياناتك", text: "ملفات CSV أو Excel، أو اتصال بقاعدة MySQL للقراءة فقط." },
  { icon: ScanSearch, title: "اكتشف البيانات الشخصية", text: "في الأعمدة وداخل النص العربي الحر، مع مراجعة بشرية لكل عمود." },
  { icon: FileCheck2, title: "ولّد النظير وأثبت أمانه", text: "كل شخص يُستبدل ببديل صالح ومتّسق، ثم فحوصات ناجح/راسب واضحة." },
  { icon: Share2, title: "شارك النظير فقط", text: "مع موظفيك أو جهات خارجية، واستلم نتائجهم وأعد ربطها بسجلاتك." },
]

const PRINCIPLES = [
  { icon: Trash2, title: "الأصول تُحذف فوراً", text: "تُعالَج البيانات الأصلية في مساحة مؤقتة ثم تُحذف. لا تُخزَّن ولا يراها أي مستلم." },
  { icon: ShieldCheck, title: "لا مشاركة لنظير راسب", text: "إذا فشل أي فحص حاسم يُمنع المشاركة من الواجهة ومن الخادم معاً." },
  { icon: KeyRound, title: "بلا جدول ربط محفوظ", text: "إعادة الربط لمدير المنشأة فقط، بمفتاح المنشأة السري، وتُحسب في الذاكرة ثم تُنسى." },
  { icon: Building2, title: "عزل تام بين المنشآت", text: "كل طلب مقيَّد بمنشأته. لا يستطيع أي مستخدم الوصول إلى بيانات منشأة أخرى." },
  { icon: Lock, title: "سجلات بلا قيم", text: "سجل التدقيق والرسائل والأخطاء تذكر من فعل ماذا ومتى، ولا تحتوي أي قيمة من البيانات." },
  { icon: UserRoundX, title: "لا ادعاءات مبالغ فيها", text: "التقرير يذكر حدوده بصراحة، ولا يصف النظير المقنّع بأنه مجهول الهوية تماماً." },
]

const FAQ = [
  {
    q: "ما الفرق بين النظير المقنّع والاصطناعي؟",
    a: "المقنّع يحتفظ بنفس الصفوف ويستبدل كل معرّف ببديل صالح ومتّسق، فيصلح للاختبار وتطوير الأنظمة. الاصطناعي يولّد صفوفاً جديدة بنفس الأنماط الإحصائية، وهو ميزة تجريبية.",
  },
  {
    q: "هل تبقى بياناتي الأصلية على الخادم؟",
    a: "لا. تُعالَج في مساحة مؤقتة وتُحذف فور انتهاء المعالجة. ما يُحفظ هو النظير فقط، مشفّراً.",
  },
  {
    q: "كيف أربط نتائج الشريك بسجلاتي الحقيقية؟",
    a: "يعيد مدير المنشأة رفع المفاتيح الأصلية لحظة الربط، فيعيد نَظير حساب البدائل بمفتاح المنشأة في الذاكرة، ثم يحذف ما رُفع.",
  },
  {
    q: "ما الصيغ السعودية التي يتعرّف عليها؟",
    a: "الهوية الوطنية والإقامة، والجوال بكل صيغه، والآيبان السعودي، والأسماء العربية، والأرقام العربية والفارسية، والبريد الإلكتروني.",
  },
  {
    q: "أين يُنصح بتشغيله؟",
    a: "داخل المنشأة نفسها. النسخة المستضافة للتجربة والعرض، ويُرجى استخدام بيانات تجريبية فيها.",
  },
]

function Container({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("mx-auto max-w-6xl px-4 sm:px-6", className)}>{children}</div>
}

function SectionHead({ eyebrow, title, text }: { eyebrow: string; title: string; text?: string }) {
  return (
    <div className="max-w-2xl">
      <p className="text-sm font-bold text-twin">{eyebrow}</p>
      <h2 className="mt-2 text-[1.75rem] leading-tight font-bold">{title}</h2>
      {text ? <p className="lead mt-3">{text}</p> : null}
    </div>
  )
}

function SamplePreview() {
  // A static illustration of the idea: the same record, before and after. Fictional values.
  const rows = [
    { k: "الاسم", before: "مصعب الحمدان", after: "فارس المنيف", type: "اسم" },
    { k: "الهوية", before: <Num>1738914553</Num>, after: <Num>1890121252</Num>, type: "هوية" },
    { k: "الجوال", before: <Num>0505642024</Num>, after: <Num>0583213008</Num>, type: "جوال" },
    { k: "المدينة", before: "مكة المكرمة", after: "مكة المكرمة", type: null },
  ]
  return (
    <div className="rounded-xl border border-border bg-card shadow-raised">
      <div className="flex items-center justify-between border-b border-border px-5 py-3.5">
        <span className="text-sm font-bold">سجل عميل · قبل وبعد</span>
        <Chip tone="twin" icon={ShieldCheck}>نظير ناجح</Chip>
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-muted-foreground">
            <th className="px-5 py-2.5 text-start font-semibold">الحقل</th>
            <th className="px-5 py-2.5 text-start font-semibold">الأصل</th>
            <th className="px-5 py-2.5 text-start font-semibold">النظير</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.k} className="border-t border-border">
              <td className="px-5 py-3 font-semibold">{r.k}</td>
              <td className="px-5 py-3">
                <span className="inline-flex items-center gap-2">
                  {r.before}
                  {r.type ? <Chip tone="sensitive">{r.type}</Chip> : null}
                </span>
              </td>
              <td className={cn("px-5 py-3", r.type && "font-semibold text-twin")}>{r.after}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="border-t border-border px-5 py-3 text-xs text-muted-foreground">
        قيم توضيحية لأشخاص غير حقيقيين. البدائل تجتاز التحقق الرسمي، والروابط بين الجداول تبقى سليمة.
      </p>
    </div>
  )
}

export default function Landing() {
  return (
    <>
      {/* hero */}
      <section className="border-b border-border bg-surface">
        <Container className="grid items-center gap-12 py-16 md:py-24 lg:grid-cols-[1.05fr_1fr]">
          <div>
            <Chip tone="primary">للمنشآت وفرقها وشركائها</Chip>
            <h1 className="mt-5 text-[2.25rem] leading-[1.25] font-bold md:text-[2.75rem]">
              شارك بيانات واقعية،
              <br />
              بلا أي شخص حقيقي.
            </h1>
            <p className="lead mt-5 max-w-xl text-[1.0625rem] leading-8">
              نَظير يكتشف البيانات الشخصية في جداولك وملاحظاتك العربية، ويولّد نسخة نظيرة صالحة ومتّسقة،
              ويثبت أمانها بفحوصات واضحة قبل أن تشاركها.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link href="/signup" className={buttonVariants({ size: "lg" })}>
                أنشئ حساب منشأة
                <ArrowLeft data-icon="inline-end" />
              </Link>
              <Link href="/#how" className={buttonVariants({ size: "lg", variant: "outline" })}>
                كيف يعمل
              </Link>
            </div>
          </div>
          <SamplePreview />
        </Container>
      </section>

      {/* problem */}
      <section className="py-20">
        <Container>
          <SectionHead eyebrow="المشكلة" title="الفرق تحتاج بيانات واقعية، والأشخاص يحتاجون الحماية" />
          <div className="mt-10 grid gap-5 md:grid-cols-3">
            {PROBLEMS.map((p) => (
              <div key={p.title} className="rounded-xl border border-border bg-card p-6 shadow-card">
                <span className="grid size-10 place-items-center rounded-lg bg-sensitive-soft text-sensitive">
                  <p.icon className="size-5" aria-hidden="true" />
                </span>
                <h3 className="mt-4 text-lg font-bold">{p.title}</h3>
                <p className="mt-2 text-[0.9375rem] leading-7 text-muted-foreground">{p.text}</p>
              </div>
            ))}
          </div>
        </Container>
      </section>

      {/* how */}
      <section id="how" className="scroll-mt-20 border-y border-border bg-surface py-20">
        <Container>
          <SectionHead eyebrow="كيف يعمل" title="أربع خطوات، ونتيجة يمكن إثباتها" />
          <ol className="mt-10 grid gap-5 md:grid-cols-4">
            {STEPS.map((s, i) => (
              <li key={s.title} className="relative rounded-xl border border-border bg-card p-6 shadow-card">
                <div className="flex items-center justify-between">
                  <span className="grid size-10 place-items-center rounded-lg bg-accent text-accent-foreground">
                    <s.icon className="size-5" aria-hidden="true" />
                  </span>
                  <span className="text-sm font-bold text-muted-foreground">
                    الخطوة <Num>{i + 1}</Num>
                  </span>
                </div>
                <h3 className="mt-4 text-lg font-bold">{s.title}</h3>
                <p className="mt-2 text-[0.9375rem] leading-7 text-muted-foreground">{s.text}</p>
              </li>
            ))}
          </ol>
        </Container>
      </section>

      {/* security */}
      <section id="security" className="scroll-mt-20 py-20">
        <Container>
          <SectionHead
            eyebrow="مبادئ الأمان"
            title="مبادئ لا تُكسر"
            text="هذه القواعد مطبّقة في الخادم ومختبرة آلياً، وليست وعوداً في الواجهة فقط."
          />
          <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {PRINCIPLES.map((p) => (
              <div key={p.title} className="flex gap-4 rounded-xl border border-border bg-card p-6 shadow-card">
                <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-twin-soft text-twin">
                  <p.icon className="size-5" aria-hidden="true" />
                </span>
                <div>
                  <h3 className="font-bold">{p.title}</h3>
                  <p className="mt-1.5 text-[0.9375rem] leading-7 text-muted-foreground">{p.text}</p>
                </div>
              </div>
            ))}
          </div>
        </Container>
      </section>

      {/* faq */}
      <section id="faq" className="scroll-mt-20 border-y border-border bg-surface py-20">
        <Container className="grid gap-10 lg:grid-cols-[1fr_1.6fr]">
          <SectionHead eyebrow="الأسئلة الشائعة" title="إجابات مباشرة" />
          <div className="divide-y divide-border rounded-xl border border-border bg-card shadow-card">
            {FAQ.map((f) => (
              <details key={f.q} className="group px-6 py-5 [&_summary::-webkit-details-marker]:hidden">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-bold">
                  {f.q}
                  <span className="text-xl leading-none text-muted-foreground transition-transform group-open:rotate-45" aria-hidden="true">+</span>
                </summary>
                <p className="mt-3 text-[0.9375rem] leading-7 text-muted-foreground">{f.a}</p>
              </details>
            ))}
          </div>
        </Container>
      </section>

      {/* contact */}
      <section id="contact" className="scroll-mt-20 py-20">
        <Container>
          <div className="flex flex-col items-start justify-between gap-6 rounded-xl border border-border bg-card p-8 shadow-card md:flex-row md:items-center">
            <div>
              <h2 className="section-title">تريد تجربة نَظير في منشأتك؟</h2>
              <p className="lead mt-2">أنشئ حساباً للتجربة، أو راسلنا لترتيب تشغيله داخل بيئتك.</p>
            </div>
            <div className="flex flex-wrap gap-3">
              <Link href="/signup" className={buttonVariants({ size: "lg" })}>أنشئ حساباً</Link>
              <a href={`mailto:${process.env.NEXT_PUBLIC_CONTACT_EMAIL ?? "hello@example.com"}`} className={buttonVariants({ size: "lg", variant: "outline" })}>
                <Mail data-icon="inline-start" />
                راسلنا
              </a>
            </div>
          </div>
        </Container>
      </section>
    </>
  )
}
