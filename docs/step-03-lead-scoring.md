# الخطوة 3: تقييم العملاء — Batch API والتخزين المؤقت للموجّهات

> **دروس الكورس المطبّقة:** 4.4 Batch API · 2.4 التخزين المؤقت للموجّهات (Prompt Caching) · 2.1 اختيار النموذج · 2.5 المخرجات المهيكلة (مكتوبة يدوياً هذه المرة)

## ماذا سنبني في هذه الخطوة؟

لدينا الآن ملف العميل المثالي (ICP) لـ Lucidya من الخطوة 2. السؤال التالي في أي نظام مبيعات: **أمامي قائمة 200 شركة، أيّها يستحق أن نراسله؟**

الوكيل يقرأ كل شركة من القائمة ويعطيها:

| الحقل | المعنى |
| --- | --- |
| `segment` | أقرب شريحة من الـ ICP، أو `none` |
| `fit_score` | درجة الملاءمة من 0 إلى 100، حسب معايير ثابتة |
| `reasons` | 1–3 أسباب، كل سبب يذكر الحقل الذي اعتمد عليه |
| `missing_info` | ما لو عرفناه لتغيّرت الدرجة |
| `recommendation` | `contact` (راسِلها) أو `nurture` (تابِعها لاحقاً) أو `skip` (تجاهلها) |

الناتج ملف CSV مرتّب من الأفضل إلى الأسوأ، يُفتح في Excel مباشرة، وهو **مدخل الخطوة 4** (كاتب الرسائل).

### من أين تأتي الشركات؟

من ملف **وهمي بالكامل**: `data/leads_sample.csv`، فيه 200 شركة بأسماء مركّبة من مقاطع عشوائية (مثل `Zarnub Bank`)، ومواقع تنتهي بـ `.example`، وهو نطاق محجوز للأمثلة لا يملكه أحد. لا توجد شركة أو شخص حقيقي في المشروع. الملف يولّده السكربت `scripts/make_leads.py` بـ "بذرة عشوائية" ثابتة، فيعطي نفس الشركات في كل مرة.

القائمة مصمَّمة لتكون **مختلطة**: بنوك سعودية كبيرة تناسب Lucidya تماماً، ومصانع ألمانية صغيرة لا تناسبها أبداً، وحالات بينهما. هكذا نختبر هل يميّز النموذج فعلاً.

### طريقتان لنفس العمل

| | `--mode direct` | `--mode batch` |
| --- | --- | --- |
| كيف | استدعاء عادي لكل شركة، 4 بالتوازي | ملف واحد فيه كل الطلبات، يُرفع دفعة واحدة |
| الوقت | ثوانٍ إلى دقائق | دقائق إلى ساعات (حد أقصى 24 ساعة) |
| التكلفة | السعر العادي | **نحو النصف** |
| مناسب لـ | التجربة، الأعداد الصغيرة، ما تحتاجه الآن | الأعداد الكبيرة التي لا تستعجلها |

الطريقتان ترسلان **نفس الطلب بالضبط** (دالة واحدة `build_request()` تبنيه)، فالمقارنة بينهما عادلة.

---

## خطوات التشغيل

### 1. اسحب التحديث وشغّل الاختبارات

```powershell
git checkout main
git pull
pytest -v
```

59 اختباراً، بينها 15 جديدة.

### 2. تأكد من ملف الـ ICP

يجب أن يوجد `data/output/icp_lucidya.com.json` من الخطوة 2. ملف الشركات موجود في المستودع (`data/leads_sample.csv`). لإعادة توليده:

```powershell
python -m scripts.make_leads
```

### 3. الوضع المباشر أولاً، بعدد صغير

```powershell
python -m scripts.score_leads lucidya.com --mode direct --limit 20
```

ستظهر ملخصاً مثل:

```
Scored 20 leads: 6 contact, 5 nurture, 9 skip
    8 worth pursuing in: Saudi & UAE banks and financial services
    3 worth pursuing in: Retail, QSR and hospitality chains

Top 5:
   92  L014  Saudi & UAE banks and financial services  - industry: Banking matches ...
   ...

Tokens: 46000 in (35840 cached = 78%) / 1400 out, 20 requests
Estimated cost (direct): $0.0050
Same work through the Batch API:  $0.0025  (about half)
```

(الأرقام توضيحية.) أهم رقم هنا: **`cached = 78%`**، سنشرحه أدناه.

افتح `data/output/leads_scored_lucidya.com_direct.csv` في Excel وراجع: هل البنوك السعودية في الأعلى؟ هل المصانع في الأسفل؟

### 4. Batch API: جهّز النشر في Azure أولاً

**هذه خطوة لا يمكن تجاوزها على Azure:** الـ Batch API لا يعمل مع النشر العادي (Standard). يحتاج نشراً منفصلاً من نوع **Global Batch**.

1. في Azure AI Foundry، افتح **Deployments** ثم **Deploy model** ثم **Deploy base model**.
2. اختر `gpt-4o-mini`.
3. في **Deployment type** اختر **Global Batch**.
4. سمِّه باسم واضح، مثل `gpt-4o-mini-batch`.
5. أضف إلى `.env`:

```
MODEL_BATCH=gpt-4o-mini-batch
```

تحقق:

```powershell
python -m scripts.check_env
```

> **انتبه:** `MODEL_BATCH` يأخذ **اسم النشر** (كلمات قصيرة مثل `gpt-4o-mini-batch`)، **وليس المفتاح**. المفتاح مكانه الوحيد `OPENAI_API_KEY`. الكود يرفض أي قيمة تشبه مفتاحاً في أسطر `MODEL_*` دون أن يطبعها، لكن إن حدث الخطأ وظهر المفتاح في أي مكان، أعد توليده من بوابة Azure.

### 5. جرّب ملف الدفعة دون إرسال (مجاناً)

```powershell
python -m scripts.score_leads lucidya.com --mode batch --dry-run
```

يكتب `data/output/batch_input_lucidya.com.jsonl` دون أن يرسل شيئاً. افتحه وانظر: سطر JSON لكل شركة.

### 6. أرسل الدفعة

```powershell
python -m scripts.score_leads lucidya.com --mode batch
```

يرفع الملف، وينشئ الدفعة، ويحفظ رقمها في `data/output/batch_lucidya.com.json`، ثم **ينتهي فوراً**. الدفعة تعمل على خوادم Azure، ولا تحتاج أن يبقى جهازك مفتوحاً.

### 7. تابع الحالة

```powershell
python -m scripts.score_leads lucidya.com --check
```

أو انتظر حتى تنتهي (يسأل كل 30 ثانية):

```powershell
python -m scripts.score_leads lucidya.com --check --wait
```

عند الاكتمال تُحفظ النتائج في `data/output/leads_scored_lucidya.com_batch.csv`.

---

## المفاهيم

### اختيار النموذج: لماذا `fast`؟ (الدرس 2.1)

المهمة هنا **بسيطة ومتكررة**: قارن شركة بمعايير واضحة، 200 مرة. لا تحتاج استدلالاً عميقاً ولا كتابة جميلة. نستخدم أرخص نموذج (`MODEL_FAST`)، و`temperature=0` لأن التقييم يجب أن يكون ثابتاً: نفس الشركة، نفس الدرجة.

قارن بالخطوات السابقة:

| الخطوة | المهمة | عدد الاستدعاءات | النموذج |
| --- | --- | --- | --- |
| 1 | فهم موقع | 1–3 | `smart` |
| 2 | موازنة استراتيجية | 1–5 | `reasoning` |
| 3 | تقييم متكرر | **200** | `fast` |

لو استخدمنا نموذج الاستدلال هنا، لضربنا تكلفته وزمنه في 200.

### معايير ثابتة بدل "رأي" النموذج

لو سألنا "كم تناسب هذه الشركة من 100؟" دون معايير، سيعطي النموذج أرقاماً غير متسقة: 75 لشركة، و80 لشركة أفضل منها في مرة أخرى. لذلك أعطيناه **جدول نقاط**:

```
- Industry matches the segment's industries ............ 0-35
- Country/region matches the segment's regions ......... 0-25
- Employee count fits the segment's company_size ........ 0-20
- Lead signals match the segment's signals .............. 0-20
Then: if any segment disqualifier applies, the score is at most 20.
```

لاحظ أن المعايير مبنية على حقول الـ ICP نفسها: `industries` و `regions` و `company_size` و `signals` و `disqualifiers`. هذا ما صممنا الخطوة 2 من أجله.

### "لا تثق، تحقّق" مرة أخرى

```python
def parse_score(text: str, lead_id: str) -> LeadScore:
    score = LeadScore.model_validate_json(text)
    score.lead_id = lead_id
    score.fit_score = max(0, min(100, score.fit_score))
    score.recommendation = "contact" if score.fit_score >= 70 else "nurture" if score.fit_score >= 40 else "skip"
    return score
```

ثلاثة تصحيحات بالكود، على نمط الخطوة 1ج:

- **`lead_id`**: نأخذه من بياناتنا، لا من نسخة النموذج، حتى لو أخطأ في نسخه.
- **حصر الدرجة بين 0 و100**: المخرجات المهيكلة تضمن أنها **عدد صحيح**، لكنها لا تضمن **مداه**.
- **التوصية تُحسب من الدرجة**: فلا يحدث أبداً أن تكون الدرجة 85 والتوصية `skip`.

### التخزين المؤقت للموجّهات (الدرس 2.4)

هذا المفهوم يوفّر مالاً حقيقياً في هذه الخطوة. انظر ماذا نرسل في كل طلب من الـ 200:

| الجزء | الحجم التقريبي | يتغير بين الطلبات؟ |
| --- | --- | --- |
| المعايير + الـ ICP كاملاً (`instructions`) | 1,500–2,500 رمز | **لا، متطابق تماماً** |
| مخطط JSON للمخرجات (`text.format`) | ~200 رمز | لا |
| بيانات الشركة (`input`) | ~70 رمز | نعم |

أكثر من 95% من كل طلب **مكرر حرفياً**. التخزين المؤقت يعني: المزوّد يحفظ نتيجة معالجة البداية المتكررة، وفي الطلب التالي لا يعالجها من جديد. النتيجة:

- الرموز المخزّنة تظهر في `cached_tokens`، وسعرها **أقل** من الإدخال العادي (نصف السعر أو أقل حسب النموذج).
- الاستجابة **أسرع**.
- **يعمل تلقائياً**، ولا تحتاج تفعيله.

**لكن له شروط، وكلها طبّقناها في `build_request()`:**

1. **الجزء المتكرر في البداية، والمتغير في النهاية.** التخزين يعمل على **البادئة** (prefix): من أول الطلب حتى أول اختلاف. لو وضعنا بيانات الشركة أولاً ثم الـ ICP، لاختلف الطلب من أول سطر، ولما خُزّن شيء. لذلك الـ ICP في `instructions` (التي تأتي أولاً)، والشركة في `input` (بعدها).
2. **التطابق حرفي.** مسافة زائدة أو ترتيب مختلف في JSON يكسر التطابق. لهذا نبني `instructions_for(icp)` مرة بنفس الطريقة لكل الطلبات.
3. **حد أدنى 1,024 رمزاً.** البادئة الأقصر لا تُخزّن أبداً. ملف ICP حقيقي من الخطوة 2 يتجاوز ذلك بسهولة. إذا رأيت `cached = 0%`، فربما الـ ICP قصير جداً.
4. **الطلب الأول لا يستفيد.** هو الذي "يملأ" الذاكرة المؤقتة، والطلبات بعده تستفيد. والذاكرة تنتهي بعد دقائق من عدم الاستخدام.

**`prompt_cache_key`:** على OpenAI نرسل مفتاحاً (`icp-lucidya.com`) يساعد على توجيه الطلبات المتشابهة إلى نفس الخادم، فترتفع نسبة الإصابة. على Azure لا نرسله؛ التخزين هناك تلقائي.

**التمرين الأهم في هذه الخطوة:** شغّل `--mode direct --limit 20` وانظر نسبة `cached`. ستكون قريبة من الصفر في أول طلبات، ثم ترتفع.

### المخرجات المهيكلة بدون Pydantic في الطلب

في الخطوات السابقة استخدمنا `text_format=CompanyProfile` مع `responses.parse`، والـ SDK كان يحوّل الصنف إلى JSON Schema. لكن **ملف الدفعة نص JSON يُرفع إلى الخادم**، ولا يمكن أن يحمل صنف Python. لذلك نبني المخطط بأنفسنا:

```python
def text_format() -> dict:
    return {
        "format": {
            "type": "json_schema",
            "name": "LeadScore",
            "schema": to_strict_json_schema(LeadScore),
            "strict": True,
        }
    }
```

`to_strict_json_schema()` هي نفس الدالة التي يستخدمها الـ SDK داخلياً. هكذا نرى ما كان مخفياً في الخطوات السابقة: `text_format=` كانت تبني هذا القاموس بالضبط. وعند القراءة نحوّل النص بأنفسنا: `LeadScore.model_validate_json(text)`.

### Batch API (الدرس 4.4)

الفكرة: بدل 200 طلب منفصل تنتظر كلاً منها، ترسل **ملفاً واحداً** فيه الـ 200 طلب، والمزوّد ينفّذها حين يكون لديه سعة فائضة، ويعطيك مقابل ذلك **خصماً نحو 50%**. الثمن أنك **لا تعرف متى تنتهي**، والحد الأقصى 24 ساعة.

دورة حياة الدفعة:

| المرحلة | ماذا يحدث | الكود |
| --- | --- | --- |
| 1. كتابة الملف | سطر JSON لكل طلب | `write_batch_file()` |
| 2. رفع الملف | `files.create(purpose="batch")` | `submit_batch()` |
| 3. إنشاء الدفعة | `batches.create(input_file_id=..., endpoint="/v1/responses", completion_window="24h")` | `submit_batch()` |
| 4. الانتظار | الحالة: `validating` ثم `in_progress` ثم `finalizing` ثم `completed` | `--check` |
| 5. تحميل النتائج | `files.content(output_file_id)` | `--check` |
| 6. قراءة النتائج | سطر JSON لكل رد | `read_batch_output()` |

**شكل سطر في ملف الإدخال:**

```json
{"custom_id": "L001", "method": "POST", "url": "/v1/responses", "body": {"model": "gpt-4o-mini-batch", "instructions": "...", "input": "LEAD:\nlead_id: L001\n...", "text": {"format": {...}}, "temperature": 0}}
```

| الحقل | دوره |
| --- | --- |
| `custom_id` | **رقمك أنت** لكل طلب. النتائج ترجع **بترتيب عشوائي**، و `custom_id` هو الطريقة الوحيدة لمعرفة أي رد لأي شركة |
| `url` | أي API ينفّذ الطلب؛ هنا Responses API |
| `body` | نفس ما ترسله في استدعاء عادي تماماً |

**شكل سطر في ملف النتائج:**

```json
{"custom_id": "L001", "response": {"status_code": 200, "body": {"output": [...], "usage": {...}}}, "error": null}
```

`body` هنا هو الرد الخام كـ JSON، دون مساعدات الـ SDK. لا يوجد `response.output_text` جاهز، لذلك تجمع `_output_text()` أجزاء النص بنفسها. هذا يكشف لك البنية الحقيقية التي كان الـ SDK يخفيها.

**أخطاء جزئية:** الدفعة قد "تكتمل" وبعض طلباتها فشل. الطلبات الفاشلة تأتي في `error_file_id` منفصل، أو بـ `status_code` غير 200. نجمعها في قائمة `errors` ونطبعها، ولا نوقف قراءة الباقي.

**حفظ الحالة:** بعد الإرسال نحفظ رقم الدفعة في `batch_lucidya.com.json`. لماذا؟ لأن `--check` قد تشغّله بعد ساعات، في نافذة PowerShell جديدة. البرنامج يحتاج أن يتذكر أي دفعة يسأل عنها.

### Azure: نشر منفصل للدفعات

```python
def batch_model() -> str:
    if config.IS_AZURE and not config.MODEL_BATCH:
        raise ValueError(
            "On Azure the Batch API needs a 'Global Batch' deployment. ..."
        )
    return config.MODEL_BATCH or config.model_for("fast")
```

على OpenAI، أي نموذج يعمل مع الـ Batch API. على Azure، نوع النشر هو ما يحدد: Standard للاستدعاءات العادية، و**Global Batch** للدفعات. نفشل مبكراً برسالة واضحة، قبل كتابة الملف أو رفعه.

---

## التكلفة: `core/cost.py`

السكربت يقدّر التكلفة من الرموز:

```python
cost = (uncached * price_in + usage.cached_tokens * price_cached + usage.output_tokens * price_out) / 1e6
return cost * (BATCH_DISCOUNT if batch else 1.0)
```

ثلاثة أسعار مختلفة: إدخال عادي، وإدخال مخزّن (أرخص)، وإخراج (أغلى). ثم خصم 50% للدفعات. الأسعار في الملف تقريبية؛ إذا عرفت أسعارك الفعلية في Azure، ضعها في `.env`:

```
PRICE_INPUT_PER_M=0.15
PRICE_CACHED_PER_M=0.075
PRICE_OUTPUT_PER_M=0.60
```

**تقدير لـ 200 شركة** مع `gpt-4o-mini` وبادئة 2,000 رمز:

| السيناريو | رموز الإدخال | التكلفة التقريبية |
| --- | --- | --- |
| مباشر، بلا تخزين | 200 × 2,300 = 460,000 | ~0.08 $ |
| مباشر، مع تخزين 80% | 460,000 (368,000 منها مخزّنة) | ~0.05 $ |
| دفعة | 460,000 | ~0.04 $ |

المبالغ صغيرة هنا لأن النموذج رخيص والعدد صغير. لكن النسب هي المهمة: في نظام حقيقي يقيّم 100,000 شركة شهرياً، الفرق بين أول سطر وآخره هو الفرق بين 40 و20 دولاراً شهرياً، أو بين 4,000 و2,000 مع نموذج أغلى.

---

## تحسينات بعد أول تشغيل حقيقي (الخطوة 3ب)

أول تشغيل على 20 شركة (مباشر ودفعة) أعطى نتائج صحيحة، لكنه كشف ثلاث مشاكل. هذا الجدول يلخص الأرقام الحقيقية:

| ما رأيناه | الرقم | السبب |
| --- | --- | --- |
| التخزين المؤقت | 72% | أول 4 طلبات أُرسلت **معاً** والذاكرة فارغة: 16 طلباً × 1,800 رمز مخزّن = 28,800 بالضبط |
| الأسباب | `- industry` | طلبنا "اذكر الحقل"، فذكر **اسم الحقل فقط** |
| الدرجات | 85، 85، 85، 85، 80 | النموذج يعطي أرقاماً "مستديرة" حين يُطلب منه **مجموع** |

### 1) تسخين الذاكرة المؤقتة

```python
first = one(leads[0])
with ThreadPoolExecutor(max_workers=workers) as pool:
    rest = list(pool.map(one, leads[1:]))
return [first, *rest], usage
```

الطلب الأول يُرسل **وحده** وننتظر انتهاءه، فيملأ الذاكرة المؤقتة بالبادئة. بعدها تنطلق الطلبات المتوازية وكلها تجد البادئة جاهزة. ثمن ذلك ثانية أو ثانيتان إضافيتان، ومقابله نسبة تخزين أعلى (المتوقع 85%+ مع 20 شركة، و95%+ مع 200).

**في وضع الدفعة لا نتحكم في الترتيب**؛ المزوّد ينفّذ الطلبات كما يشاء. ومع ذلك رأينا 76% مخزّناً، لأن الدفعة تُنفَّذ على مراحل لا كلها في لحظة واحدة.

### 2) النموذج يحكم، والكود يحسب

بدل أن يعطي النموذج درجة واحدة، صار يعطي **نقاطاً لكل معيار** (`LeadAssessment`):

```json
{"industry_points": 35, "region_points": 25, "size_points": 10, "signals_points": 7, "disqualifier": ""}
```

والكود يجمعها ويطبّق القواعد في `to_score()`:

```python
points = {name: max(0, min(top, getattr(a, name))) for name, top in MAX_POINTS.items()}
total = sum(points.values())
if disqualifier:
    total = min(total, DISQUALIFIED_CAP)
if segment.lower() == "none":
    total = min(total, NO_SEGMENT_CAP)
```

| | قبل | بعد |
| --- | --- | --- |
| من يجمع؟ | النموذج | **الكود** |
| الحساب | قد يخطئ النموذج في الجمع | مضمون دائماً |
| قاعدة الاستبعاد (حد 20) | النموذج "يتذكرها" أو لا | **تُطبّق دائماً** |
| حدود كل معيار (35/25/20/20) | لا تُفحص | **تُحصر بالكود** |
| الشفافية | رقم واحد | تعرف أين خسرت الشركة نقاطها |

لاحظ أن المخطط الذي نرسله للنموذج **لا يحتوي** `fit_score` ولا `recommendation`. لو تركناهما، لملأهما النموذج ثم تجاهلناهما، فيضيع رموز إخراج بلا فائدة. والاختبار `test_model_schema_has_points_but_no_total` يتحقق من ذلك.

**لماذا تتحسن الدرجات؟** حين تطلب من النموذج "درجة من 100" يميل إلى 80 و85 و90. حين تطلب "كم من 35 تستحق الصناعة؟" يحكم على سؤال أضيق وأوضح، ومجموع أربعة أحكام صغيرة أدق من حكم واحد كبير. أضفنا أيضاً في المعايير **أمثلة للنقاط الوسطى** ("about 20 = closely related") لأن النماذج بدونها تميل للطرفين: صفر أو الحد الأقصى.

السكربت يطبع الآن:

```
Distinct scores: 14 among 20 leads (more = finer ranking)
```

كلما زاد هذا الرقم، كان الترتيب أدق. قارنه بالتشغيل السابق.

### 3) أسباب مفيدة: المثال أوضح من الشرح

```python
reasons: list[str] = Field(
    description="1-3 reasons, each 'field: what you saw and why it matters', e.g. "
    "'industry: Banking is one of the segment industries' or "
    "'signals: no Arabic social media, a disqualifier'."
)
```

التعليمة القديمة "name the field" كانت صحيحة لكنها غامضة، فنفّذها النموذج حرفياً. **مثالان ملموسان** يحددان الشكل المطلوب أوضح من أي شرح.

### ملف CSV الجديد

أُضيفت أعمدة: `industry_pts` و `region_pts` و `size_pts` و `signals_pts` و `disqualifier`. في Excel يمكنك الآن الفرز حسب أي معيار، مثلاً: الشركات التي حصلت على 35 في الصناعة لكن صفراً في المنطقة، أي شركات مناسبة في دول لا نستهدفها بعد.

## الاختبارات الجديدة (`tests/test_scorer.py`)

| الاختبار | ماذا يثبت |
| --- | --- |
| `test_prefix_is_identical_and_lead_comes_last` | البادئة متطابقة بين الطلبات، والشركة في النهاية: شرط التخزين |
| `test_text_format_is_a_strict_json_schema` | المخطط صارم وقابل للكتابة في ملف JSON |
| `test_no_cache_key_on_azure` | لا نرسل `prompt_cache_key` إلى Azure |
| `test_code_adds_points_and_sets_recommendation` | الكود يجمع النقاط ويحدد التوصية |
| `test_each_criterion_is_clamped_to_its_maximum` | 99 في الصناعة تصبح 35 |
| `test_disqualifier_caps_score_at_20` | الاستبعاد يحد الدرجة عند 20 دائماً |
| `test_no_segment_caps_score_below_20` | `none` تحد الدرجة عند 19 |
| `test_model_schema_has_points_but_no_total` | النموذج لا يُطلب منه المجموع |
| `test_first_request_runs_alone_to_warm_the_cache` | الطلب الأول ينتهي قبل أن يبدأ أي طلب آخر |
| `test_score_direct_keeps_order_and_sums_usage` | التوازي لا يخلط الترتيب، والرموز والمخزّن تُجمع صحيحاً |
| `test_batch_file_has_one_request_per_line` | سطر لكل شركة، و `custom_id` و `url` صحيحان |
| `test_azure_batch_needs_its_own_deployment` | على Azure بلا `MODEL_BATCH`: رسالة واضحة |
| `test_read_batch_output_matches_by_custom_id_and_collects_errors` | نتائج بترتيب عشوائي + طلب فاشل |
| `test_submit_uploads_then_creates_batch` | الرفع ثم الإنشاء بالمعاملات الصحيحة |
| `test_batch_costs_half_and_cached_tokens_cost_less` | حساب التكلفة |
| `test_make_leads_is_fictional_and_repeatable` | البيانات وهمية (`.example`) ومتطابقة في كل توليد |
| `test_script_direct` / `test_script_batch_submit_then_check` / `test_script_batch_dry_run_submits_nothing` | السكربت كاملاً في الأوضاع الثلاثة |

---

## أخطاء شائعة وحلولها

| ما تراه | السبب | الحل |
| --- | --- | --- |
| `ValueError: MODEL_BATCH in .env looks like an API KEY` | وضعت المفتاح في سطر اسم النشر | ضع **اسم النشر** (مثل `gpt-4o-mini-batch`). وإن ظهر المفتاح في أي مكان (شاشة، صورة، ملف)، **أعد توليده فوراً** من Keys and Endpoint |
| `FileNotFoundError ... Run step 2 first` | لا يوجد `icp_lucidya.com.json` | شغّل الخطوة 2 |
| `ValueError: ... Global Batch deployment` | Azure بلا `MODEL_BATCH` | أنشئ نشر Global Batch (خطوة التشغيل 4) |
| `BadRequestError` عند إنشاء الدفعة يذكر `model` أو `deployment` | `MODEL_BATCH` نشر عادي، أو اسم خاطئ | تأكد أن نوع النشر Global Batch |
| الدفعة `failed` فوراً | خطأ في ملف الإدخال (نادراً مع كودنا) | افتح `batch.errors` المطبوعة |
| الدفعة `in_progress` لساعات | طبيعي؛ المزوّد ينفّذ حين تتوفر سعة | انتظر، أو استخدم `--mode direct` للعاجل |
| `cached = 0%` | الـ ICP قصير (أقل من 1,024 رمز للبادئة)، أو العدد صغير جداً | جرّب `--limit 30`؛ أو راجع طول الـ ICP |
| `RateLimitError` في الوضع المباشر | 4 طلبات متوازية تتجاوز حصة النشر | `--workers 2`، أو ارفع حصة TPM للنشر |
| `BadRequestError` يذكر `temperature` | `MODEL_FAST` نموذج استدلال | اترك `SCORING_TEMPERATURE=` فارغاً |

---

## تمرين لك (30 دقيقة)

1. **راقب التخزين:** شغّل `--mode direct --limit 30`، ثم افتح `logs/calls.jsonl` وانظر `cached_tokens` في أول 5 أسطر وآخر 5. متى بدأ التخزين؟
2. **اكسر التخزين عمداً:** في `build_request()` اجعل `"input": instructions_for(icp)` و `"instructions": lead_text(lead)`، أي اعكس الترتيب. شغّل `--limit 10`. ماذا حدث لنسبة `cached`؟ لماذا؟ أعِد الترتيب بعدها.
3. **قارن الطريقتين:** شغّل نفس الـ 20 شركة مباشرة وبالدفعة (`--mode batch --limit 20`). هل الدرجات متطابقة؟ (مع `temperature=0` يجب أن تكون متقاربة جداً.) كم استغرقت الدفعة؟
4. **راجع كإنسان:** افتح ملف CSV، وخذ 5 شركات بتوصية `contact` و5 بـ `skip`. هل توافق النموذج؟ اكتب حالة واحدة لا توافقه فيها، ولماذا.

أرسل لي ملخص الوضع المباشر (من `Scored` حتى `Same work through the Batch API`)، ونتيجة التمرين 2.

---

## الخطوة القادمة

**الخطوة 4 — كاتب الرسائل:** يأخذ الشركات ذات التوصية `contact`، ويكتب لكل منها رسالة بريد مخصصة من Lucidya، مستخدماً `named_customers` كدليل اجتماعي. ثم نفحص كل رسالة بـ **Moderations API** (الدرس 5.2) قبل وضعها في الصادر، ونجرّب **الضبط الدقيق** (الدرس 4.1) لتعليم نموذج صغير أسلوب الشركة.

ملاحظة: أسماء النماذج والأسعار تتغير باستمرار؛ راجع وثائق OpenAI الرسمية للتحديثات.
