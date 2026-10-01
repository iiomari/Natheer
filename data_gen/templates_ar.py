"""Arabic claim-note templates for the demo generator.

Slots in {BRACES} are filled by make_demo_data.py, which records the exact
offsets of every planted identifier (golden labels) and every look-alike
(hard negatives).

Identifier slots:   NAME, FIRST, OTHER_NAME_M, OTHER_NAME_F, ID, OTHER_ID,
                    MOBILE, OTHER_MOBILE, IBAN, EMAIL
Hard-negative slots: INVOICE, ORDER (10 digits starting 1/2, bad checksum),
                    POLICY, AMOUNT, DATE, and NW:<word> (a name-like word
                    used as an ordinary word, e.g. "أمل" = hope)

These templates belong to the demo data only. Synthetic mode (5b) uses its own
template library in nazeer/text_templates.py, so the twin never reuses demo text.
"""

IDENTIFIER_SENTENCES = [
    "تواصل المستفيد {NAME} من الجوال {MOBILE} للاستفسار عن حالة المطالبة.",
    "تم التحقق من هوية المستفيد رقم {ID} وإحالة الطلب للمراجعة الطبية.",
    "يرجى تحويل مبلغ التعويض إلى الآيبان {IBAN} باسم {NAME}.",
    "صاحب المطالبة: {NAME}، رقم الهوية: {ID}، الجوال: {MOBILE}.",
    "اتصلت {OTHER_NAME_F} زوجة المستفيد وطلبت التواصل على الرقم {OTHER_MOBILE}.",
    "المراجع {FIRST} حضر إلى الفرع وقدم صورة من الهوية {ID}.",
    "أرسل العميل المستندات على البريد {EMAIL} وأكد رقم جواله {MOBILE}.",
    "رقم هوية المرافق {OTHER_ID} وجواله {OTHER_MOBILE}.",
    "الطبيب المعالج د. {OTHER_NAME_M} أوصى بإعادة الفحص بعد أسبوعين.",
    "طلب {FIRST} تحديث بيانات الحساب البنكي إلى {IBAN}.",
    "تم إبلاغ {NAME} بقرار الموافقة عبر رسالة نصية على {MOBILE}.",
    "المستفيد يطلب التواصل مع ابنه {OTHER_NAME_M} على الجوال {OTHER_MOBILE}.",
    "رقم الإقامة المسجل {ID} لا يطابق المرفقات، تم التواصل مع {FIRST}.",
    "للتواصل عبر البريد: {EMAIL}",
    "حوّل المبلغ لحساب {OTHER_NAME_M} رقم الآيبان {IBAN} بناء على تفويض المستفيد.",
    "ذكرت الممرضة {OTHER_NAME_F} أن المريض {FIRST} غادر المستشفى بعد الظهر.",
    "جوال بديل للمستفيد {OTHER_MOBILE} ورقم هويته {ID}.",
]

HARD_NEGATIVE_SENTENCES = [
    "فاتورة المستشفى رقم {INVOICE} بمبلغ {AMOUNT} ريال بتاريخ {DATE}.",
    "رقم الطلب {ORDER}، لا توجد ملاحظات إضافية.",
    "تمت الموافقة حسب وثيقة التأمين رقم {POLICY}.",
    "المطالبة مكررة مع الفاتورة {INVOICE}، يرجى التدقيق.",
    "مرجع العملية {ORDER} بتاريخ {DATE}.",
    "على {NW:أمل} الرد خلال يومين عمل.",
    "{NW:وعد} الفرع بإنهاء الإجراء خلال أسبوع.",
    "إجمالي المطالبة {AMOUNT} ريال حسب الفاتورة {INVOICE}.",
]

NEUTRAL_SENTENCES = [
    "تم الصرف بعد مراجعة التقرير الطبي.",
    "المطالبة قيد المراجعة لدى الإدارة الطبية.",
    "تم طلب مستندات إضافية من مقدم الخدمة.",
    "لا توجد ملاحظات.",
    "تمت المعالجة وفق جدول المنافع.",
    "رفضت المطالبة لعدم اكتمال المستندات.",
    "تم تحويل الملف إلى قسم الاعتراضات.",
]
