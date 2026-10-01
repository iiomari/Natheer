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
1. **تحميل البيانات:** بيانات العرض، أو رفع ملفات CSV، أو الاتصال بـ MySQL (قراءة فقط).
2. **ما اكتشفه نظير:** وسوم الأعمدة، ومقارنة نظير بالأداة البسيطة على النص الحر، وعرض ملاحظة
   واحدة بالتلوين. تستطيع مراجعة الوسوم وتعديلها، وكل تعديل يُسجَّل في التقرير.
3. **توليد التوأم:** مقنّع أو اصطناعي، مع خيار الكتابة في قاعدة تطوير منفصلة.
4. **الأدلة:** الحكم، وكل فحص بنتيجته، والأصل بجانب التوأم، واقتراحات k-anonymity مع زر التطبيق،
   والتنزيل.
5. **تبويب "لماذا ينجح":** لكل سبب جذري المكوّنُ الذي يعالجه والرقم المقاس من تشغيلك الحالي.

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
- نموذج الأسماء العربي بطيء على المعالج (نحو 0.2 ثانية لكل ملاحظة)، لذلك الوضع الافتراضي يستخدم
  قوائم الأسماء.
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
1. **Load data:** the demo dataset, CSV upload, or a read-only MySQL connection.
2. **What Nazeer found:** column tags, a free-text comparison of Nazeer vs the baseline, and a
   highlighted note. Review or override any tag; every change is recorded in the report.
3. **Generate the twin:** masked or synthetic, optionally written to a separate development database.
4. **Evidence:** the verdict, every check, original vs twin, k-anonymity fixes with an Apply button,
   and the download.
5. **"Why it works" tab:** each root cause, the component that addresses it, and the metric measured
   in your current run.

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
- The Arabic NER model is slow on CPU (about 0.2 s per note), so the default uses the name lists.
- SDV and its dependencies are licensed BUSL-1.1.
