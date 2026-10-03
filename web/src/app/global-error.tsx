"use client"

export default function GlobalError({ reset }: { error: Error; reset: () => void }) {
  return (
    <html lang="ar" dir="rtl">
      <body style={{ fontFamily: "system-ui, sans-serif", display: "grid", placeItems: "center", minHeight: "100vh", margin: 0 }}>
        <div style={{ textAlign: "center", padding: 24 }}>
          <h1 style={{ fontSize: 24 }}>تعذّر تحميل هذه الصفحة</h1>
          <p style={{ color: "#555" }}>حدث خطأ غير متوقع. جرّب مرة أخرى.</p>
          <button type="button" onClick={reset} style={{ marginTop: 16, padding: "10px 18px", borderRadius: 8, border: 0, background: "#1e3a5f", color: "#fff" }}>
            أعد المحاولة
          </button>
        </div>
      </body>
    </html>
  )
}
