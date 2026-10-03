# Copy pass: words per screen of the main flow

Measured by `scripts/ui_copy_audit.py` (Playwright): visible words in the page's `<main>`, or in the open
dialog. The sidebar and header are excluded. A word is a token containing a letter or a digit; options
inside drop-down menus count too.

| Screen | Before | After | Reduction | Screenshots |
|---|---|---|---|---|
| رفع الملفات (نافذة) | 139 | 108 | 22% | [before](before/1-upload.png) · [after](after/1-upload.png) |
| ملف يحتاج تنظيفاً | 995 | 200 | 80% | [before](before/2-cleaning.png) · [after](after/2-cleaning.png) |
| الكشف (ملف نظيف) | 963 | 177 | 82% | [before](before/3-detection.png) · [after](after/3-detection.png) |
| تقرير النظير | 218 | 78 | 64% | [before](before/4-twin.png) · [after](after/4-twin.png) |
| المشاركة (نافذة) | 62 | 37 | 40% | [before](before/5-share.png) · [after](after/5-share.png) |
| صفحة المستلم | 142 | 72 | 49% | [before](before/6-received.png) · [after](after/6-received.png) |
| **Total** | **2519** | **672** | **73%** | |

**Rules applied:**
- at most one short helper line per screen;
- headings and buttons of 1-3 words;
- extra explanation moved to an "ⓘ" tooltip or a collapsed section, with nothing essential only there;
- numbers instead of sentences;
- required notices kept, each on one line;
- one primary button per screen, secondary actions visually quieter.

**Biggest cuts:**
- the column table shows identifier columns only (all columns one click away);
- each column's evidence sentence moved into an "ⓘ";
- the action menu labels were shortened;
- the long review list became the grouped «القرارات» section;
- the twin report's technical table and limitations sit under «تفاصيل للمختصين»;
- the recipient page states the token rule once.
