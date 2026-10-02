# نَظير · Nazeer

**English below ↓**

## نظير بالعربي

### المشكلة
الجهات السعودية تحتاج بيانات واقعية للتطوير والاختبار والتحليل وتدريب نماذج الذكاء الاصطناعي، لكن
قواعد بياناتها مليئة بالبيانات الشخصية: الأسماء، وأرقام الهوية والإقامة، والجوالات، والآيبانات. نسخ
بيانات الإنتاج إلى بيئة التطوير يخالف أنظمة حماية البيانات الشخصية. والبيانات العشوائية المزيفة تكسر
قواعد التحقق والعلاقات بين الجداول، فلا تصلح للتحليل. والأصعب أن المعرّفات تختبئ داخل الملاحظات
العربية الحرة، مكتوبة بأرقام عربية مثل ٠٥٠ ٣٣١ ٨٨٤٢ ومع مسافات وبصيغة +966، فتفوت الأدوات العامة.

### ما الذي يفعله نظير
يعمل نظير **داخل بيئة الإنتاج** ويشغّله مالك البيانات نفسه، ولا تخرج أي بيانات من الجهاز. يأخذ
جداول (مجلد CSV أو قاعدة MySQL) ويُخرج شيئين:
1. **توأم للبيانات بلا أشخاص حقيقيين**، يحافظ على الصيغ والتوزيعات والعلاقات بين الجداول. له نوعان:
   - **التوأم المقنّع (5a):** نفس الصفوف بعد استبدال المعرّفات بقيم وهمية صالحة ومتسقة. مناسب
     لاختبار الأنظمة.
   - **التوأم الاصطناعي (5b):** صفوف جديدة يولّدها نموذج تعلّم من 80% من البيانات. مناسب للتحليل
     وتدريب النماذج.
2. **تقرير أدلة (PASS/FAIL)** يقيس الخصوصية والفائدة بأرقام فعلية، ويذكر الإخفاقات صراحة.

### من يستخدمه
- **مالك البيانات أو فريق البيانات:** يشغّله داخل بيئة الإنتاج.
- **مسؤول حماية البيانات:** يقرأ تقرير الأدلة قبل الموافقة على نقل التوأم.
- **فرق التطوير والتحليل:** تستلم التوأم في قاعدة تطوير منفصلة أو كملفات CSV.

### كيف يعمل (المكوّنات)
| المكوّن | الملف | ما يفعله |
|---|---|---|
| المعرّفات السعودية | `nazeer/saudi_ids.py` | توحيد الأرقام العربية والفارسية مع خريطة مواقع، والتحقق من الهوية والإقامة (رقم التحقق) والجوال والآيبان (mod-97)، وتوليد قيم وهمية صالحة |
| تحليل البنية | `nazeer/profiling.py` | أنواع الأعمدة والمفاتيح الأساسية والأجنبية |
| الاكتشاف | `nazeer/detect.py`, `nazeer/ner.py` | اكتشاف المعرّفات في الأعمدة وداخل النص العربي الحر، مع مقارنة بأداة بسيطة |
| السياسة | `config/policy.yaml`, `nazeer/policy.py` | ماذا نفعل بكل عمود، مع مراجعة بشرية تُسجَّل في التقرير |
| التحويل | `nazeer/transform.py` | استبدال بمفتاح سري (HMAC) بلا جدول ربط محفوظ، يحافظ على شكل الرقم ويُبقي العلاقات بين الجداول |
| التوليد الاصطناعي | `nazeer/synth.py` | نموذج Gaussian copula مقسّم حسب الفئة، يُدرَّب بعد فصل 20% من البيانات |
| التقييم | `nazeer/evaluate.py`, `nazeer/kanon.py` | فحص التسرّب، والنسخ المطابقة، وk-anonymity، وDCR، والفائدة (TSTR) |
| التقرير | `nazeer/report.py` | تقرير JSON بحكم PASS/FAIL |
| الواجهة | `nazeer/app.py` | واجهة Streamlit محلية |

### التثبيت (PowerShell، Python 3.11)
```powershell
cd $HOME\Desktop\nazeer
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest
python scripts\download_models.py      # اختياري ومرة واحدة: نموذج أسماء عربي (CamelBERT)
```

### التشغيل
```powershell
$env:NAZEER_KEY = "<32 حرفًا عشوائيًا على الأقل>"
python -m data_gen.make_demo_data --seed 42 --n 3000
python -m nazeer.pipeline --csv data\demo --mode masked --apply-fix auto --out out\masked
python -m nazeer.pipeline --csv data\demo --mode synthetic --target "is_large_claim=amount>p90" --out out\synthetic
streamlit run nazeer\app.py
```
قاعدة MySQL (من الإنتاج إلى التطوير): انسخ `.env.example` إلى `.env` وضع فيه بيانات الدخول، ثم:
```powershell
python -m data_gen.load_mysql
python -m nazeer.pipeline --mysql-db nazeer_prod_demo --mysql-target nazeer_dev --mode masked --apply-fix auto --out out\mysql_masked
```

### الواجهة خطوة بخطوة
الواجهة عربية من اليمين لليسار، بخط كبير يصلح للعرض على الشاشة، وتعمل بالوضعين الفاتح والداكن، ولا
تطلب أي شيء من الإنترنت (الخط مضمَّن في `nazeer/static/`). شريط في الأعلى يبيّن الخطوة الحالية:
**١. البيانات ← ٢. الكشف ← ٣. النظير ← ٤. الإثبات**، ولكل خطوة زر رئيسي واحد.
1. **البيانات:** زر «تحميل بيانات العرض» يحمّل بيانات العرض مع مفتاح عرض جاهز، فلا يُكتب شيء. يظهر
   الجدولان، ومعهما «تتبّع عميل» يظلّل صفوف عميل واحد في كل الجداول ويبقى معك في كل الخطوات.
2. **الكشف:** رقمان كبيران (ما وجدته الأداة التقليدية مقابل نظير، والإنذارات الكاذبة لكل منهما)، ثم نفس
   الملاحظة جنبًا إلى جنب. كل تظليل له لون **ونص** معًا: هوية، جوال، آيبان، بريد، اسم، للمراجعة، رُفض.
3. **النظير:** «ولّد النظير» ثم مقارنة قبل/بعد لنفس العميل ومطالباته، والخلايا التي تغيّرت معلَّمة،
   مع التحقق من أن الأعداد والمجاميع والروابط لم تتغير.
4. **الإثبات:** النتيجة وأربع بطاقات: التسريب، صلاحية البدائل، سلامة الروابط، خطر التعرّف بالتركيب
   (k). يظهر فشل k أولًا مع زر «طبّق الإصلاح المقترح». وزر «ازرع تسريبًا» يزرع هوية حقيقية في نسخة من
   النظير ليُريك أن فحص التسريب يلتقطها.
5. **تبويب «ليش يشتغل؟»:** خمسة صفوف: السبب الجذري ← المكوّن ← رقم مقاس من تشغيلك.
6. **تبويب «جرّب نصّك»:** اكتب ملاحظة وشاهد الأداة التقليدية ونظير والنص بعد الإخفاء.

**«إعدادات متقدمة»** (مطويّة أسفل الصفحة): رفع ملفات CSV، والاتصال بـ MySQL، وكشف الأسماء بـ CamelBERT،
والنظير الاصطناعي (تجريبي)، والكتابة في قاعدة تطوير منفصلة، ومراجعة وسوم الأعمدة وتعديلها. مفتاح العرض
الجاهز يُستخدم فقط مع بيانات العرض المولَّدة؛ بياناتك تحتاج `NAZEER_KEY`.

### معنى المقاييس
- **الاكتشاف (recall):** نسبة المعرّفات التي وجدها نظير.
- **الدقة (precision):** نسبة ما علّمه نظير وكان معرّفًا فعلًا.
- **فحص التسرّب:** يبحث عن كل معرّف أصلي في كل خلية من التوأم، بالمكتشِف وببحث شامل مستقل. أي
  وجود يعني FAIL ويُحجب التوأم.
- **النسخ المطابقة:** صفوف في التوأم مطابقة لصف حقيقي، ويجب أن تكون 0.
- **k-anonymity:** أصغر مجموعة من الأشخاص يتشاركون نفس (المدينة، العمر، الجنس). الحد الأدنى 5.
- **DCR:** المسافة لأقرب سجل حقيقي. يجب ألا يكون التوأم أقرب إلى بيانات التدريب من صفوف حقيقية
  لم يرها النموذج.
- **TSTR:** ندرّب نفس النموذج مرة على البيانات الحقيقية ومرة على التوأم، ونختبر الاثنين على بيانات
  حقيقية محجوزة. انخفاض AUC الصغير يعني أن التوأم مفيد.
- **التطابق الإحصائي:** اختبار KS للأعمدة الرقمية، والمسافة الكلية (TVD) للفئوية، ومقياس جودة
  SDMetrics.

### نتائج العرض (بيانات مولَّدة بلا أشخاص حقيقيين)
الأرقام من `out\METRICS_SUMMARY.md`: 3,000 عميل و7,160 مطالبة، وفيها 15,989 معرّفًا مزروعًا داخل الملاحظات.
| المقياس | النتيجة |
|---|---|
| اكتشاف المعرّفات في النص الحر | نظير **99.2%** بدقة **100%**، مقابل **18.7%** للأداة البسيطة بدقة 80.9% |
| أرقام تشبه الهوية (فواتير وطلبات) عُلِّمت خطأً | نظير **0** من 6,756، والأداة البسيطة 707 |
| التوأم المقنّع | **0** تسرّب في 63,960 خلية، و**0** نسخ مطابقة، و**100%** من الهويات والجوالات الوهمية صالحة، و**0** مفاتيح أجنبية يتيمة |
| k-anonymity | **1 (FAIL)** قبل الإصلاح، ثم **5** بعد الإصلاح المقترح (43 صفًا من 3,000 أُخفيت قيمها) |
| التوأم الاصطناعي (TSTR) | AUC من **0.984 إلى 0.983** (انحدار لوجستي)، ومن **0.984 إلى 0.981** (غابة عشوائية)، وجودة SDMetrics **94.2%** |
| DCR | ناجح في التشغيل الرئيسي، و**1 من 5** في اختبار المتانة (انظر القيود) |

هذه أرقام على بيانات مولَّدة، ولا تتنبأ بالأداء على بيانات حقيقية.

### المنصّة على الويب (قيد البناء)
يُبنى حول المحرّك موقعٌ متعدد المنشآت: منشآت ترفع بياناتها وتولّد النظير وتشاركه مع موظفيها أو جهات
خارجية، ويعيد المستلمون نتائجهم ليربطها مدير المنشأة بسجلاته الحقيقية. **النشر المقصود في الواقع داخل
المنشأة نفسها (on-premise)**؛ النسخة المستضافة للعرض فقط.

**خطر معروف:** مفاتيح المنشآت مشفّرة في قاعدة البيانات بمفتاح رئيسي محفوظ في بيئة الخادم، فلو اختُرق
الخادم بالكامل أمكن فك المفاتيح وإعادة التعرّف على النظائر المقنّعة. هذا مقبول لنسخة العرض، وهو سبب أن
النشر الحقيقي داخل المنشأة.

**إعادة النتائج وإعادة الربط:** كل ملف نظير مقنّع يُنزَّل ومعه عمود `nazeer_ref` بجانب مفتاح السجل. يعيد
المستلم ملف نتائجه محتفظاً بالعمودين، فيرفض نَظير الملف إن لم يطابق المفتاح مرجعه في أكثر من 1% من الصفوف
(أو إن كانت أكثر من 5% من الصفوف بمفاتيح غير موجودة أو فارغة أو مكررة). **`nazeer_ref` يكشف التلاعب
بالمفاتيح، لا التعديل على قيم النتائج نفسها.** إعادة الربط لمدير المنشأة فقط: يرفع الملفات الأصلية نفسها
بأسمائها وصفوفها، فيعيد نَظير الحساب بمفتاح المنشأة في الذاكرة ويتحقق أنه يطابق النظير المشارَك تماماً، ثم
يربط. لا يُخزَّن أي جدول ربط؛ والملف الناتج متاح لذلك المدير 30 دقيقة ثم يُحذف.

### القيود المعروفة (بصراحة)
- الاكتشاف ليس كاملًا أبدًا. ما يفوت المكتشِف في النص الحر لا يُستبدل ولا يستطيع فحص التسرّب العثور
  عليه.
- أرقام الاكتشاف على البيانات المولَّدة تقيس الصيغ التي زرعناها، ولا تتنبأ بالأداء على بيانات
  حقيقية. أسماء العرض مأخوذة من نفس قوائم الأسماء، لذلك نسبة اكتشاف الأسماء فيها متفائلة.
- **التوأم المقنّع يبقى غالبًا بيانات شخصية نظامًا**، لأن كل صف يقابل شخصًا حقيقيًا ومن يملك المفتاح
  يستطيع الربط. التوأم الاصطناعي أقوى لكنه ليس "مجهول الهوية" بشكل مُثبت.
- قيمة وهمية صالحة الصيغة قد تطابق صدفةً شخصًا حقيقيًا خارج البيانات.
- في التوأم الاصطناعي على بيانات العرض، تحقق شرط DCR في التشغيل الرئيسي، لكنه تحقق في تشغيل واحد
  فقط من 5 تقسيمات مختلفة: التوأم أقرب قليلًا (نحو 4%) إلى بيانات التدريب من البيانات المحجوزة.
  التفاصيل في التقرير.
- نموذج الأسماء العربي (CamelBERT مع القوائم) يرفع اكتشاف الأسماء على بيانات العرض من 98.1% إلى 99.4%،
  لكنه بطيء على المعالج (نحو 0.12 ثانية لكل ملاحظة، أي قرابة 15 دقيقة لـ 7,160 ملاحظة)، لذلك
  الوضع الافتراضي يستخدم قوائم الأسماء.
- SDV ومكتباته بترخيص BUSL-1.1.

---

## Nazeer in English

### The problem
Saudi organizations need realistic data for development, testing, analytics and AI training. Their
databases are full of personal data: names, national ID and iqama numbers, mobiles and IBANs.
- Copying production data outside production violates data-protection rules.
- Random fake data breaks validation rules and table relationships, so it is useless for analysis.
- Identifiers also hide inside free-text Arabic notes, written with Arabic-Indic digits, spaces and
  `+966`, where generic tools miss them.

### What Nazeer does
Nazeer runs **inside the production environment**, operated by the data owner, and no data leaves the
machine. It takes tables (a CSV folder or a MySQL database) and produces two things:
1. **A twin with no real people** that keeps formats, distributions and cross-table relationships:
   - the **masked twin (5a):** the same rows, with identifiers replaced by valid, consistent fakes;
     used for system testing;
   - the **synthetic twin (5b):** new rows from a model trained on 80% of the data; used for
     analytics and AI.
2. **A PASS/FAIL evidence report** with measured privacy and utility. Failures are stated plainly.

### Who uses it
- **The data owner or data team** runs it inside production.
- **The data-protection officer** reads the evidence report before approving the twin.
- **Development and analytics teams** receive the twin, in a separate development database or as CSV.

### How it works (components)
| Component | File | What it does |
|---|---|---|
| Saudi identifiers | `nazeer/saudi_ids.py` | Arabic-Indic/Persian digit normalization with an offset map; validators (ID/iqama checksum, mobile, IBAN mod-97); valid fake generators |
| Profiling | `nazeer/profiling.py` | Column types, primary and foreign keys |
| Detection | `nazeer/detect.py`, `nazeer/ner.py` | Identifiers in columns and inside Arabic free text, plus a naive baseline for comparison |
| Policy | `config/policy.yaml`, `nazeer/policy.py` | What happens to each column; human overrides are recorded |
| Transform | `nazeer/transform.py` | Keyed HMAC pseudonyms with no stored mapping table; format-preserving; joins kept |
| Synthesis | `nazeer/synth.py` | Stratified Gaussian copula trained after a 20% holdout split |
| Evaluation | `nazeer/evaluate.py`, `nazeer/kanon.py` | Leak scan, exact copies, k-anonymity, DCR, TSTR utility |
| Report | `nazeer/report.py` | JSON report with a PASS/FAIL verdict |
| UI | `nazeer/app.py` | Local Streamlit app |

### Install (PowerShell, Python 3.11)
```powershell
cd $HOME\Desktop\nazeer
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest
python scripts\download_models.py      # optional, once: Arabic NER model (CamelBERT)
```

### Run
```powershell
$env:NAZEER_KEY = "<at least 32 random characters>"
python -m data_gen.make_demo_data --seed 42 --n 3000
python -m nazeer.pipeline --csv data\demo --mode masked --apply-fix auto --out out\masked
python -m nazeer.pipeline --csv data\demo --mode synthetic --target "is_large_claim=amount>p90" --out out\synthetic
streamlit run nazeer\app.py
```
For MySQL (production → development), copy `.env.example` to `.env`, fill in the credentials, then:
```powershell
python -m data_gen.load_mysql
python -m nazeer.pipeline --mysql-db nazeer_prod_demo --mysql-target nazeer_dev --mode masked --apply-fix auto --out out\mysql_masked
```
Independent check on hand-written notes: see `docs\HOW_TO_WRITE_NOTES.md`, then run
`python -m nazeer.eval_human`.

### Using the UI
The UI is Arabic and right-to-left, sized for a projector, works in light and dark mode, and makes no
network requests (the font is bundled in `nazeer/static/`). A progress bar shows the four steps:
**1. Data → 2. Detection → 3. Twin → 4. Proof**, each with one primary button.
1. **Data:** "Load demo data" loads the demo dataset with a preset demo key, so nothing is typed. Both
   tables are shown; "Track a customer" highlights one customer's rows in every table and keeps that
   selection through all steps.
2. **Detection:** two big numbers (found and false alarms, generic tool vs Nazeer), then the same note side
   by side. Every highlight has a color **and** a text label (ID, mobile, IBAN, email, name, needs review,
   rejected).
3. **Twin:** "Generate the twin", then a before/after view of the tracked customer and their claims with
   changed cells marked, and a check that counts, totals and links are unchanged.
4. **Proof:** the verdict and four cards: leaks, validity of the fakes, link integrity, and re-identification
   risk (k). k-anonymity first shows its FAIL with an "Apply the suggested fix" button. "Plant a leak" puts a
   real ID into a copy of the twin to show that the leak scan catches it.
5. **"Why it works" tab:** five rows: root cause → component → live metric from your run.
6. **"Try your text" tab:** type a note and compare the generic tool, Nazeer, and the masked result.

**Advanced settings** (collapsed at the bottom): CSV upload, MySQL, CamelBERT name detection, the synthetic
twin (experimental), writing to a separate development database, and reviewing column tags. The preset demo
key is used only with the generated demo dataset; your own data needs `NAZEER_KEY`.

### What the metrics mean
- **Recall / precision:** share of identifiers found / share of flags that were real identifiers.
- **Leak scan:** every original identifier is searched for in every twin cell, by the detector and by
  an independent exhaustive search. Any hit means FAIL, and the twin is withheld.
- **Exact copies:** twin rows identical to a real row. Must be 0.
- **k-anonymity:** the smallest group of people sharing the same (city, age band, gender). Minimum 5.
- **DCR:** distance to the closest real record. The twin must not be closer to the training data than
  real rows the model never saw.
- **TSTR:** the same model is trained on real data and on the twin, and both are tested on held-out
  real data. A small AUC drop means the twin is useful.
- **Fidelity:** KS (numeric), total variation distance (categorical), SDMetrics quality score.

### Demo results (generated data, no real people)
From `out\METRICS_SUMMARY.md`: 3,000 customers, 7,160 claims, and 15,989 identifiers planted in notes.
| Metric | Result |
|---|---|
| Identifiers found in free text | Nazeer **99.2%** recall, **100%** precision; baseline **18.7%**, 80.9% |
| Look-alike invoice/order numbers wrongly flagged | Nazeer **0** of 6,756; baseline 707 |
| Masked twin | **0** leaks in 63,960 cells, **0** exact copies, **100%** of fake IDs and mobiles valid, **0** orphan foreign keys |
| k-anonymity | **1 (FAIL)** before the fix → **5** after the suggested fix (43 of 3,000 rows suppressed) |
| Synthetic twin (TSTR) | AUC **0.984 → 0.983** (logistic regression), **0.984 → 0.981** (random forest); SDMetrics quality **94.2%** |
| DCR | passes on the main run; **1 of 5** in the robustness check (see limitations) |

These numbers come from generated data and do not predict performance on real production text.

### Web platform (in progress)
A multi-tenant website is being built around the engine. Organizations upload data, generate a twin and
share it with employees or third parties; recipients return their results and an organization admin
re-links them to the real records. **The intended real-world deployment is on-premise, inside the
organization**; the hosted version is for demonstration.

**Known risk:** organization keys are encrypted in the database under a master key held in the backend
environment, so a full backend compromise could decrypt the keys and re-identify masked twins. This is
acceptable for the hosted demo, and it is why the real deployment is on-premise.

**Returns and re-linking:** every masked twin export carries a `nazeer_ref` column next to the record key.
A recipient returns results keeping both columns. Nazeer refuses the file if the key does not match its
reference in more than 1% of rows (or if more than 5% of rows have unknown, empty or duplicate keys).
**`nazeer_ref` detects tampering with keys, not edits to the result values themselves.** Re-linking is for
organization admins only: the admin uploads the very same original files (same names, same rows); Nazeer
recomputes the twin with the organization key in memory, checks it reproduces the shared twin exactly,
then joins. No mapping table is stored; the output is available to that admin for 30 minutes, then deleted.
Python cannot guarantee that freed memory is wiped: the key and the in-memory dictionary are released when
the job ends, not overwritten.

Run the API locally (PowerShell; SQLite is enough for a first try):
```powershell
pip install -r requirements-api.txt
$env:DATABASE_URL = "sqlite:///nazeer_app.db"
$env:NAZEER_MASTER_KEY = python -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
$env:COOKIE_SECURE = "0"; $env:MAIL_BACKEND = "memory"
alembic -c nazeer_api\alembic.ini upgrade head
uvicorn nazeer_api.main:app --port 8000      # in a second window: python -m nazeer_api.worker
cd web; npm install; npm run dev             # the website on http://localhost:3000 (proxies /api/*)
```
Hosted deployment (Vercel + Railway + managed MySQL + Resend): see `docs/DEPLOY.md`.

### Known limitations (stated plainly)
- Detection is never complete. What the detector misses in free text is not replaced, and the leak
  scan cannot find it.
- Detection numbers on generated data measure the formats we planted, not real-data performance.
  The demo names come from the same name lists the gazetteer uses, so name recall on the demo is
  optimistic.
- **The masked twin is most likely still personal data:** each row maps to a real person, and the key
  holder can re-identify. The synthetic twin is stronger but not proven anonymous.
- A format-valid fake may coincide with a real person's value outside the dataset.
- On the demo synthetic twin, the DCR rule holds on the main run but in only 1 of 5 different
  holdout splits. The twin is slightly (about 4%) closer to the training data than held-out rows.
  Details are in the report.
- The Arabic NER model (CamelBERT + name lists) raises demo name recall from 98.1% to 99.4%, but
  it is slow on CPU (about 0.12 s per note, about 15 minutes for 7,160 notes), so the default uses
  the name lists.
- SDV and its dependencies are licensed BUSL-1.1.
