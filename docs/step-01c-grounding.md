# الخطوة 1ج: فحص التأسيس ومقاومة الهلوسة

> **دروس الكورس المطبّقة:** 1.2 عدم حتمية النماذج و `temperature` · 2.5 المخرجات المهيكلة (وصف الحقول كتعليمات) · ومبدأ عام في بناء أنظمة الذكاء الاصطناعي: **لا تثق، تحقّق**

## ماذا سنبني في هذه الخطوة؟

في تحليل Lucidya مع البحث ظهرت أربع ملاحظات. هذه الخطوة تعالجها كلها:

| الملاحظة | المعالجة | من يعالج؟ |
| --- | --- | --- |
| 1. هل المنافسون موجودون فعلاً في المصادر؟ | **فحص التأسيس** يبحث عن كل اسم في نصوص نتائج البحث | كود Python، بلا نموذج |
| 2. علامات تنصيص زائدة واقتباسات قصيرة | تنظيف آلي + وصف أدق لحقل `evidence` + فحص وجود كل اقتباس في الموقع | كود + تعليمات |
| 3. النتائج تتغير بين التشغيلات | `temperature=0.2` + حفظ الملف والبناء عليه | إعداد + منهجية |
| 4. خلط ما تقوله الشركة بما يقوله الآخرون | فصل الحقل إلى `target_customers_site` و `target_customers_external` | المخطط |

الفكرة الأساسية: **قلنا للنموذج "لا تخترع"، لكن القول ليس تحققاً.** الآن نتحقق بكود عادي، مجاني وحتمي، من أن كل اقتباس وكل منافس يمكن تتبعه إلى مصدر.

---

## خطوات التشغيل

### 1. اسحب التحديث

```powershell
git checkout main
git pull
pytest -v
```

34 اختباراً، بينها 10 جديدة.

### 2. أضف إلى `.env` (اختياري؛ القيمة الافتراضية 0.2)

```
ANALYSIS_TEMPERATURE=0.2
```

### 3. حلّل مع البحث

```powershell
python -m scripts.analyze_company https://lucidya.com/ar --web tavily
```

في آخر الناتج سيظهر قسم جديد، مثل هذا:

```
Grounding check
  Evidence found on the website : 4/5
    NOT FOUND: Lucidya is the leading platform in the region
  Competitors found in sources  : 6/7
    ok  Brandwatch  <- https://www.cbinsights.com/company/lucidya
    ok  Sprinklr  <- https://www.cbinsights.com/company/lucidya
    NOT FOUND Neticle
    ...
```

وسيُحفظ ملفان:

| الملف | المحتوى | من يستخدمه |
| --- | --- | --- |
| `data/output/company_lucidya.com.json` | الملف النظيف `CompanyProfile` | الخطوة 2 |
| `data/output/company_lucidya.com.grounding.json` | تقرير الفحص: كل عنصر، هل وُجد، وأين | أنت، للمراجعة |

### 4. جرّب الوضع الصارم

```powershell
python -m scripts.analyze_company https://lucidya.com/ar --web tavily --strict
```

`--strict` يحذف من الملف المحفوظ كل اقتباس ومنافس لم يُعثر عليه في المصادر.

---

## المفاهيم

### ما هو "التأسيس" (Grounding)؟

المعلومة **مؤسَّسة** إذا أمكن إرجاعها إلى مصدر محدد أُعطي للنموذج. المعلومة **غير المؤسَّسة** قد تكون صحيحة (من ذاكرة النموذج)، وقد تكون هلوسة، ولا نستطيع التمييز بينهما دون فحص.

في المشروع عندنا مصدران، وكل نوع معلومة يُفحص في مصدره:

| المعلومة | يُبحث عنها في | لماذا هناك |
| --- | --- | --- |
| `evidence` | نص الموقع (`page.as_prompt()`) | طلبنا أن تكون اقتباسات حرفية من الموقع |
| `competitors` | نص الموقع ثم نصوص نتائج البحث | المنافسون يأتون عادة من البحث |

لاحظ أن الفحص **لا يستخدم نموذجاً**. استدعاء نموذج آخر ليحكم على الأول سيكلّف مالاً، وقد يخطئ هو أيضاً. البحث عن نص داخل نص عملية مجانية ونتيجتها واحدة دائماً.

### لماذا نحتاج `normalize()`؟

لو قارنّا النصوص حرفياً، سنحصل على إنذارات كاذبة كثيرة. مثال حقيقي من تشغيليك لـ Lucidya:

- التشغيل الأول أعطى: `الأسرع نموًا` (التنوين على الواو)
- التشغيل الثاني أعطى: `الأسرع نمواً` (التنوين على الألف)

الجملتان متطابقتان للقارئ، لكنهما مختلفتان حرفياً للحاسوب. `normalize()` تزيل هذه الفروق التي لا تغيّر المعنى:

```python
def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = ARABIC_MARKS.sub("", text).replace(TATWEEL, "")
    text = re.sub("[أإآ]", "ا", text)  # أ إ آ -> ا
    text = text.replace("ى", "ي")  # ى -> ي
    text = text.translate({ord(c): " " for c in QUOTE_CHARS})
    return re.sub(r"\s+", " ", text).strip()
```

| السطر | يعالج | مثال |
| --- | --- | --- |
| `NFKC` و `lower()` | أشكال Unicode المختلفة للحرف نفسه، والأحرف الكبيرة | `BRANDWATCH` = `Brandwatch` |
| `ARABIC_MARKS` | الحركات والتنوين والشدة | `نمواً` = `نموًا` = `نموا` |
| `TATWEEL` | حرف المد `ـ` | `اصطـناعي` = `اصطناعي` |
| الهمزات | `أ` و `إ` و `آ` تصبح `ا` | `الإصطناعي` = `الاصطناعي` |
| الألف المقصورة | `ى` تصبح `ي` | فرق شائع في الكتابة |
| المسافات | عدة مسافات تصبح مسافة واحدة | نصوص HTML مليئة بالمسافات |

نطبّق `normalize()` على الطرفين (الاقتباس والمصدر) ثم نبحث بـ `in`.

### التنظيف بالكود أفضل من الطلب من النموذج

طلبنا في وصف الحقل: "Do not add quotation marks". لكن النموذج قد ينسى أحياناً. لذلك نضيف طبقة ثانية لا تنسى أبداً:

```python
profile.evidence = [strip_quotes(q) for q in profile.evidence]
```

`strip_quotes()` تزيل العلامات **حول** الاقتباس فقط، وتُبقي أي علامات داخله. هذه قاعدة عامة مفيدة: **كل ما يستطيع الكود فعله بشكل مضمون، لا تعتمد فيه على النموذج.**

### إنذار، لا حكم

الفحص يقول "لم أجد هذا في المصادر"، ولا يقول "هذا كذب". قد يكون الاسم مكتوباً بطريقة مختلفة في المصدر (مثل `AIM Tech` بدل `AIM Technologies`)، أو قد يكون النموذج اختصر جملة من الموقع. لذلك قررنا:

| الوضع | ماذا يحدث للعناصر غير الموجودة | متى تستخدمه |
| --- | --- | --- |
| الافتراضي | تبقى في الملف، مع إنذار في الشاشة والتقرير | أثناء التطوير والمراجعة البشرية |
| `--strict` | تُحذف من الملف المحفوظ | عندما يمر الملف لخطوات آلية دون مراجعة |

المبدأ: **لا تحذف بصمت.** حتى في الوضع الصارم، التقرير يذكر ما حُذف ولماذا.

**حالة خاصة:** مع `--web openai`، الأداة المدمجة لا تعطينا نصوص النتائج، بل الإجابة فقط. لذلك لا نستطيع فحص المنافسين، والتقرير يقول ذلك صراحة (`cannot verify`)، ولا يعطي إنذارات كاذبة. هذه ميزة إضافية لاستدعاء الدوال على الأداة المدمجة: **نملك البيانات الخام، فنستطيع التحقق.**

### `temperature` وعدم الحتمية (الدرس 1.2)

عندما يكتب النموذج، يختار كل كلمة من بين عدة احتمالات. `temperature` تتحكم في هذا الاختيار:

| القيمة | السلوك | مناسبة لـ |
| --- | --- | --- |
| `0` إلى `0.3` | يختار الكلمات الأرجح غالباً؛ تنوع قليل | استخراج البيانات، التحليل، التصنيف |
| `0.7` إلى `1` | تنوع أكبر | الكتابة الإبداعية، رسائل البريد (الخطوة 4) |

اخترنا `0.2` للتحليل. **لكنها لا تجعل النتائج متطابقة تماماً**، فالتنوع يقل ولا يختفي. لذلك الحل الحقيقي للنقطة 3 منهجي وليس تقنياً: **حلّل مرة، راجع، احفظ، وابنِ على الملف المحفوظ.** الخطوة 2 ستقرأ `company_lucidya.com.json` ولن تعيد التحليل.

**تنبيه عن نماذج الاستدلال:** نماذج مثل `o3` وعائلة `gpt-5` ترفض المعامل `temperature` وتعطي `BadRequestError`. إذا غيّرت `MODEL_SMART` إلى نموذج منها، اترك `ANALYSIS_TEMPERATURE=` فارغاً في `.env`، فلا يُرسل المعامل:

```python
_temp = os.getenv("ANALYSIS_TEMPERATURE", "0.2").strip()
ANALYSIS_TEMPERATURE = float(_temp) if _temp else None
```

### وصف الحقل تعليمات (تذكير بالدرس 2.5)

غيّرنا وصف `evidence` من:

> 2-5 short quotes copied from the page

إلى:

> 2-5 full sentences copied WORD FOR WORD from the website text, in their original language, that support the analysis. At least 5 words each. Do not add quotation marks around them.

كل إضافة تعالج مشكلة رأيناها: "full sentences" و "At least 5 words" ضد اقتباسات مثل `"لكل مجال"`، و"WORD FOR WORD" لأن الفحص يبحث عن تطابق، و"Do not add quotation marks" ضد `"\"لحظة بلحظة\""`.

وفصلنا `target_customers` إلى حقلين، مع قاعدة صريحة في التعليمات:

```
- Customer types stated on the website go in target_customers_site.
  Customer types found ONLY in web search results go in target_customers_external.
```

هكذا يعرف وكيل الخطوة 2 ما تستهدفه الشركة **بإعلانها هي**، وما يُنسب إليها من الخارج، ويعطي الأول وزناً أكبر.

---

## شرح الكود الجديد

### `core/grounding.py`

الدالة الرئيسية:

```python
def check_grounding(
    evidence: list[str],
    competitors: list[str],
    website_text: str,
    searches: list[dict],
    search_results_available: bool = True,
) -> GroundingReport:
```

للمنافسين نبحث أولاً في الموقع، ثم في نتائج البحث بالترتيب، ونسجّل **رابط أول نتيجة** وُجد فيها الاسم:

```python
where = "website" if needle in site else ""
if not where:
    where = next((url for url, text in result_texts if needle in text), "")
```

`next(..., "")` تعيد أول عنصر يحقق الشرط، أو `""` إن لم يوجد. هكذا يعرض التقرير بجانب كل منافس المصدر الذي ذكره، فتستطيع فتح الرابط والتأكد بنفسك.

`GroundingReport` يجمع النتائج، مع خصائص مختصرة: `unverified_evidence` و `unverified_competitors` و `ok`. أما `to_dict()` فتحوّله إلى JSON للحفظ.

### `agents/researcher.py`

`analyze_company()` صارت تعيد كائناً واحداً بدل ثلاث قيم:

```python
@dataclass
class AnalysisResult:
    profile: CompanyProfile
    response: object          # the last API response (for token counts)
    searches: list[dict]      # every search made, with its results
    grounding: GroundingReport
```

عندما تكثر القيم المُعادة، يصبح الكائن ذو الأسماء (`result.grounding`) أوضح من ترتيب مواقع (`profile, response, searches, grounding = ...`) يسهل الخطأ فيه.

---

## تحسينات بعد أول تشغيل حقيقي

أول تشغيل على `lucidya.com` أعطى: المنافسون **6/6** موجودون في المصادر، لكن الاقتباسات **2/5** فقط. عند الفحص تبيّن أن معظم "الاقتباسات المفقودة" **إنذارات كاذبة من كود الفحص نفسه**، وليست هلوسة. هذا درس مهم: **أداة التحقق تحتاج هي أيضاً إلى تحقق.**

### 1) علامات الترقيم

بطاقات المواقع وعناوينها عادة بلا نقطة في آخرها، والنموذج يضيف نقطة لأنه يكتب "جملاً". فرق حرف واحد كان يكفي لرفض الاقتباس:

| الموقع | النموذج | قبل الإصلاح |
| --- | --- | --- |
| `قدّم دعمًا فوريًا ومخصصًا يعزز الرضا والكفاءة` | `قدّم دعمًا فوريًا ومخصصًا يعزز الرضا والكفاءة.` | مفقود ✗ |

الإصلاح في `normalize()`: كل علامة ترقيم (فئة `P` في Unicode، وتشمل `.` و `،` و `؛` و `؟` وعلامات التنصيص) تصبح مسافة:

```python
text = "".join(" " if unicodedata.category(ch).startswith("P") else ch for ch in text)
```

### 2) حالة ثالثة: "قريب"

النموذج أضاف كلمة واحدة ("وثقة") في آخر جملة حقيقية. هذا ليس اقتباساً حرفياً، لكنه ليس اختراعاً أيضاً. صار لكل عنصر ثلاث حالات بدل اثنتين:

| الحالة | المعنى | ماذا تفعل |
| --- | --- | --- |
| `exact` | موجود حرفياً (بعد التطبيع) | لا شيء |
| `close` | 80% على الأقل من كلماته موجودة بنفس الترتيب | قارن بالموقع؛ النموذج عدّل كلمة أو اثنتين |
| `missing` | غير موجود | راجع يدوياً؛ قد يكون مخترعاً |

نقيس "القرب" بـ `SequenceMatcher` من مكتبة Python القياسية `difflib`، على مستوى **الكلمات** لا الحروف:

```python
matcher = SequenceMatcher(None, q, s, autojunk=False)
blocks = matcher.get_matching_blocks()
matched = sum(b.size for b in blocks)
longest = max((b.size for b in blocks), default=0)
return matched / len(q), longest / len(q)
```

- **`matched / len(q)`**: نسبة كلمات الاقتباس التي وُجدت بنفس الترتيب.
- **`longest / len(q)`**: طول أطول مقطع متصل. نشترط أن يغطي نصف الاقتباس على الأقل، وإلا فقد تكون جملة "مركّبة" من كلمات شائعة متفرقة في الصفحة، وهذا ما يثبته الاختبار `test_sentence_of_common_words_in_wrong_order_is_missing`.
- **`autojunk=False`**: افتراضياً يتجاهل `SequenceMatcher` الكلمات الكثيرة التكرار في النصوص الطويلة، مثل "في" و"من"، فيفسد القياس على صفحة كاملة.

`--strict` يُبقي `close` ويحذف `missing` فقط.

### 3) العملاء المعروفون `named_customers`

النموذج وضع أسماء شركات (بنك الاستثمار السعودي، الراجحي...) في `target_customers_external` المخصص **لأنواع** العملاء. بدل منعه، أعطيناها حقلاً خاصاً:

```python
named_customers: list[str] = Field(
    description="Names of real organizations the sources say are customers of this company "
    "(logos, case studies, news). Exact names as written in the source. Never guess. "
    "Empty list if none."
)
```

وتُفحص مثل المنافسين تماماً، لأن ذكر عميل غير حقيقي في رسالة بريد (الخطوة 4) خطأ محرج ومضر بالسمعة.

## الاختبارات الجديدة (`tests/test_grounding.py`)

| الاختبار | ماذا يثبت |
| --- | --- |
| `test_strip_quotes_removes_wrapping_marks_only` | تُزال العلامات حول الاقتباس فقط، لا داخله |
| `test_normalize_ignores_arabic_diacritics_and_alef_forms` | `نمواً` = `نموًا`، و`إصطـناعي` = `اصطناعي` |
| `test_evidence_found_despite_small_differences` | الاقتباس الحقيقي من Lucidya يُقبل رغم اختلاف التنوين |
| `test_invented_evidence_is_flagged` | جملة مخترعة تُكتشف |
| `test_competitors_checked_against_search_results_with_url` | المنافس الموجود يُربط برابطه، وغير الموجود يُعلَّم |
| `test_competitors_unverifiable_without_result_texts` | مع الأداة المدمجة: لا إنذارات كاذبة |
| `test_report_to_dict_has_summary_fields` | التقرير المحفوظ يحتوي الملخص |
| `test_default_keeps_items_but_flags_them` | الوضع الافتراضي لا يحذف شيئاً |
| `test_strict_drops_unverified_items` | `--strict` يحذف غير الموجود فقط |
| `test_temperature_can_be_disabled_for_reasoning_models` | إفراغ الإعداد يمنع إرسال `temperature` |
| `test_added_final_period_is_still_exact` | حالة حقيقية من Lucidya: النقطة المضافة لا تُفشل الفحص |
| `test_one_added_word_is_close_not_missing` | حالة حقيقية: كلمة مضافة = `close` لا `missing` |
| `test_sentence_of_common_words_in_wrong_order_is_missing` | كلمات صحيحة بترتيب مخترع = `missing` |
| `test_named_customers_checked_like_competitors` | العملاء يُربطون برابط مصدرهم، والمخترع يُعلَّم |

---

## أخطاء شائعة وحلولها

| ما تراه | السبب | الحل |
| --- | --- | --- |
| `BadRequestError` يذكر `temperature` | `MODEL_SMART` نموذج استدلال | اجعل `ANALYSIS_TEMPERATURE=` فارغاً في `.env` |
| منافس معروف معلَّم `NOT FOUND` | الاسم مكتوب بطريقة أخرى في المصدر | افتح `sources` وتحقق يدوياً؛ لا تستخدم `--strict` هنا |
| اقتباس صحيح معلَّم `NOT FOUND` | النموذج اختصر الجملة أو عدّل كلمة | طبيعي أحياناً؛ التقرير يدلّك على ما تراجعه |
| `Evidence found 0/5` | الموقع يعتمد على الصورة (`--screenshot`) والاقتباسات منها | الفحص يقارن بنص HTML فقط؛ الاقتباسات من الصورة لن تُوجد فيه |

---

## تمرين لك (15 دقيقة)

1. **قِس الثبات:** شغّل التحليل 3 مرات بدون بحث، واحفظ الملف بعد كل مرة باسم مختلف. ثم غيّر `ANALYSIS_TEMPERATURE=1.0` وكرّر. في أي الحالتين تشابهت `offering` أكثر؟
2. **اختبر الفحص:** افتح `company_lucidya.com.json`، وأضف يدوياً إلى `evidence` جملة من اختراعك. كيف تتحقق منها دون استدعاء النموذج؟ (تلميح: `from core.grounding import check_grounding`)
3. **(للتفكير)** فحصنا `evidence` و `competitors`. أي حقل آخر يستحق فحصاً مماثلاً؟ وهل يمكن فحص `one_liner` بنفس الطريقة؟ لماذا لا؟

---

## الخطوة القادمة

**الخطوة 2 — وكيل العميل المثالي (ICP):** يقرأ `company_lucidya.com.json` المحفوظ، ويستخدم **نموذج استدلال** (الدرس 2.6) ليقترح 2–3 شرائح عملاء مستهدفة، ثم تحاوره لتعديلها عبر `previous_response_id` (الدرس 2.3).

ملاحظة: أسماء النماذج والأسعار تتغير باستمرار؛ راجع وثائق OpenAI الرسمية للتحديثات.
