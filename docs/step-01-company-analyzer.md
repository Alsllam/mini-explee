# الخطوة 1: محلل الشركة — من رابط موقع إلى ملف JSON منظّم

> **دروس الكورس المطبّقة:** 2.2 Responses API (رسائل متعددة الأجزاء) · 2.5 المخرجات المهيكلة · 3.2 الرؤية · 4.3 الأدوات المدمجة · وتذكير بالدرس 1.2 (الرموز)

## ماذا سنبني في هذه الخطوة؟

أول "وكيل" في المشروع. تعطيه رابط موقع شركة، فيقرأ الصفحة ويُرجع **ملفاً منظماً** عنها:

الناتج المتوقع لشركة وهمية (مثال):

```json
{
  "name": "Acme Logistics",
  "website": "https://acme.example",
  "one_liner": "Fleet tracking software for delivery companies.",
  "offering": ["Real-time fleet tracking", "Fuel usage reports"],
  "value_props": ["Lower fuel costs", "Fewer late deliveries"],
  "target_customers": ["Delivery companies", "Mid-size logistics firms"],
  "competitors": [],
  "language": "mixed",
  "evidence": ["cut fuel costs by 20%", "حلول تتبع الأساطيل"],
  "confidence": "medium"
}
```

هذا الملف هو **مدخل الخطوة 2**: وكيل العميل المثالي سيقرأ `offering` و `target_customers` مباشرة ليستنتج من نستهدف. لهذا يجب أن يكون الشكل ثابتاً دائماً، وليس فقرة نصية يتغير شكلها في كل مرة.

كيف تمر البيانات:

1. `core/web.py` يحمّل الصفحة وينظّفها من الأكواد ويحوّلها إلى نص قصير.
2. `agents/researcher.py` يبني رسالة فيها النص، ومعه لقطة شاشة إن أعطيته واحدة.
3. `ask()` ترسلها مع المخطط `CompanyProfile`، فيُجبَر النموذج على الرد بهذا الشكل بالضبط.
4. السكربت يحفظ النتيجة في `data/output/company_<domain>.json`.

---

## خطوات التشغيل

### 1. اسحب الخطوة وثبّت المكتبات الجديدة

بعد دمج طلب الدمج، اسحب التحديث وثبّت المكتبتين الجديدتين (`requests` و `beautifulsoup4`):

```powershell
git checkout main
git pull
pip install -r requirements.txt
```

### 2. شغّل الاختبارات

17 اختباراً، بلا مفتاح وبلا إنترنت:

```powershell
pytest -v
```

### 3. حلّل موقع شركة

اختر موقع شركة حقيقية عامة (شركتك مثلاً، أو أي شركة من ملف المنتجات الذي أرسلته في البداية):

```powershell
python -m scripts.analyze_company https://lucidya.com/ar
```

ستظهر النتيجة وتُحفظ في مجلد `data/output/`. هذا المجلد في `.gitignore`، فلا تُرفع النتائج إلى GitHub.

### 4. أضف لقطة شاشة (الدرس 3.2)

خذ لقطة شاشة للصفحة الرئيسية (على Windows: `Win + Shift + S`)، واحفظها باسم `home.png` في مجلد المشروع، ثم:

```powershell
python -m scripts.analyze_company https://lucidya.com/ar --screenshot home.png
```

قارن النتيجتين: هل تغيّر `confidence`؟ هل ظهرت معلومات من الصورة لم تكن في النص؟

**أسهل طريقة:** التقط الصورة بـ `Win + PrtScn` (تُحفظ تلقائياً في `Pictures\Screenshots`)، ثم اطلب أحدث صورة مباشرة دون نسخ:

```powershell
python -m scripts.analyze_company https://lucidya.com/ar --screenshot latest
```

سيطبع السكربت مسار الصورة التي اختارها في أول سطر، فتتأكد أنها الصحيحة.

### 5. البحث على الويب (الدرس 4.3) — OpenAI فقط

```powershell
python -m scripts.analyze_company https://lucidya.com/ar --web
```

**على Azure سيظهر لك خطأ واضح** بأن الأداة غير متاحة، وهذا مقصود. أداة `web_search` المدمجة موجودة في OpenAI فقط، وAzure لا يوفرها في Responses API حالياً. شرحتُ البديل أدناه.

---

## المفاهيم: ماذا تعلّمنا من الكورس هنا؟

### المخرجات المهيكلة Structured Outputs (الدرس 2.5)

**المشكلة:** لو طلبت من النموذج "أعطني JSON"، سيعطيك JSON غالباً، لكن ليس دائماً. قد يضيف جملة قبله، أو ينسى حقلاً، أو يكتب `"high "` بمسافة، أو يسمّي الحقل `products` بدل `offering`. كل واحدة من هذه تكسر الخطوة التالية.

**الحل:** المخرجات المهيكلة تجعل الـ API نفسه **يُجبر** النموذج على مخطط JSON محدد. النموذج لا يستطيع تقنياً أن يكتب حرفاً خارج المخطط.

عرّفنا المخطط كصنف Pydantic في `core/schemas.py`:

```python
class CompanyProfile(BaseModel):
    name: str = Field(description="Company name as written on the website.")
    ...
    language: Literal["ar", "en", "mixed"] = Field(description="Main language of the website.")
    confidence: Literal["high", "medium", "low"] = Field(
        description="low if the page had little text or was mostly images/scripts."
    )
```

ثلاثة أشياء مهمة في هذا المخطط:

| العنصر | لماذا |
| --- | --- |
| `Literal["high", "medium", "low"]` | يحصر القيمة في خيارات محددة. مستحيل أن يكتب النموذج `"very high"` |
| `Field(description=...)` | الوصف يُرسل إلى النموذج كجزء من المخطط، فهو **تعليمات** لكل حقل. اكتبه بعناية |
| لا قيم افتراضية | في الوضع الصارم كل حقل إلزامي. لما قد يكون مجهولاً نطلب قائمة فارغة `[]` أو نصاً فارغاً |

ولاحظ حقلين أضفناهما عمداً لمحاربة **الهلوسة** (أن يخترع النموذج معلومات):

- `evidence`: اقتباسات حرفية من الصفحة تدعم التحليل. إذا رأيت فيها جملة غير موجودة في الموقع، فهذه إشارة أن النموذج يخترع.
- `confidence`: النموذج نفسه يقول لنا إن كانت الصفحة فقيرة بالمعلومات.

**الإرسال في الكود:** أضفنا للدالة `ask()` معاملاً جديداً اسمه `text_format`. إذا أُعطي، نستدعي `responses.parse` بدل `responses.create`:

```python
if text_format is not None:
    response = client.responses.parse(text_format=text_format, **params)
else:
    response = client.responses.create(**params)
```

`responses.parse` تفعل ثلاثة أشياء: تحوّل صنف Pydantic إلى JSON Schema صارم، وترسله في الطلب، ثم تقرأ الرد وتحوّله إلى كائن Python جاهز في `response.output_parsed`. لذلك نكتب `profile.offering` مباشرة، دون `json.loads` ودون التحقق يدوياً من وجود الحقول.

**متى تكون `output_parsed` فارغة؟** في حالتين: إذا رفض النموذج الطلب، أو إذا انقطع الرد قبل اكتمال JSON بسبب حد `max_output_tokens`. عالجنا ذلك برسالة خطأ تذكر `status`:

```python
profile = response.output_parsed
if profile is None:
    raise RuntimeError(f"No structured output. Status: {getattr(response, 'status', '?')}")
```

### رسالة متعددة الأجزاء (الدرس 2.2)

في الخطوة 0 أرسلنا `input` كنص بسيط. الآن نرسل **قائمة رسائل**، وكل رسالة تحتوي عدة **أجزاء** (content parts):

الرسالة التي يبنيها `build_input()`:

```python
[
    {
        "role": "user",
        "content": [
            {"type": "input_text", "text": "URL: ...\n\nTITLE: ...\n\nPAGE TEXT: ..."},
            {"type": "input_text", "text": "Screenshot of the homepage:"},
            {"type": "input_image", "image_url": "data:image/png;base64,iVBOR...", "detail": "low"},
        ],
    }
]
```

| الجزء | المعنى |
| --- | --- |
| `role: "user"` | الرسالة من المستخدم. التعليمات العامة في `instructions` وليست هنا |
| `input_text` | جزء نصي |
| `input_image` | جزء صورة (الدرس 3.2) |

الفصل بين `instructions` (من أنت وما القواعد) و `input` (المادة التي تعمل عليها) يجعل التعليمات ثابتة ويسهّل التخزين المؤقت لاحقاً (الدرس 2.4، الخطوة 3).

### الرؤية Vision (الدرس 3.2)

النموذج يستطيع "رؤية" الصور. نفيد من ذلك لأن كثيراً من المواقع الحديثة تضع رسالتها الأساسية في صور أو شعارات أو تصميم، لا في نص يقرؤه `BeautifulSoup`.

الـ API يقبل الصورة بطريقتين: **رابط https** عام، أو **Data URL** بصيغة base64. الصورة على جهازك ليس لها رابط عام، فنحوّلها:

```python
def image_part(path: str | Path) -> dict:
    path = Path(path)
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return {
        "type": "input_image",
        "image_url": f"data:{mime};base64,{data}",
        "detail": "low",
    }
```

- **base64:** طريقة لتحويل بيانات ثنائية (بايتات الصورة) إلى نص عادي يمكن وضعه داخل JSON.
- **`detail`:** يتحكم في دقة قراءة الصورة وتكلفتها:

| القيمة | متى يُستخدم | الاعتبارات |
| --- | --- | --- |
| `low` | فهم عام للصورة: ما نوع الموقع، ما الرسالة الرئيسية | تكلفة رموز ثابتة وصغيرة |
| `high` | قراءة نص صغير أو تفاصيل دقيقة | يقسّم الصورة لمربعات؛ تكلفة أعلى بكثير |
| `auto` | يترك القرار للنموذج | غير متوقع التكلفة |

اخترنا `low` لأن لقطة صفحة رئيسية تكفيها نظرة عامة.

**مفاجأة `gpt-4o-mini` مع الصور:** في `gpt-4o` تكلّف الصورة بدقة `low` نحو 85 رمزاً فقط، أما في `gpt-4o-mini` فتُحسب نحو **2,833 رمزاً**. السبب أن OpenAI جعلت سعر الصورة بالدولار متقارباً في النموذجين، وبما أن رمز `mini` أرخص بكثير، ارتفع عدد الرموز المحسوبة للصورة. لذلك لا تحكم على التكلفة بعدد الرموز وحده؛ احسبها بالدولار.

### الأدوات المدمجة Built-in Tools (الدرس 4.3)

بعض الأدوات ينفّذها OpenAI على خوادمه دون أن تكتب لها أي كود: البحث على الويب (`web_search`)، والبحث في الملفات (`file_search`)، وتشغيل كود Python (`code_interpreter`). تفعّلها بسطر واحد:

```python
extra["tools"] = [{"type": "web_search"}]
```

النموذج يقرر بنفسه متى يبحث وماذا يبحث. أضفنا في التعليمات حداً: "مرتين على الأكثر"، لأن كل بحث له تكلفة إضافية.

**لماذا لا تعمل على Azure؟** الأدوات المدمجة تعمل على خوادم مزوّد الخدمة، وAzure لا يوفر `web_search` في Responses API حالياً (بينما يوفر `code_interpreter`). لذلك:

```python
if use_web_search and config.IS_AZURE:
    raise ValueError(
        "web_search is not available on Azure OpenAI. Run without --web, "
        "or use an OpenAI key (see docs/step-01-company-analyzer.md)."
    )
```

`config.IS_AZURE` قيمته `True` إذا كان في `OPENAI_BASE_URL` كلمة `azure`. هذا مثال على مبدأ مهم: **افشل مبكراً وبرسالة واضحة**، بدل أن ترسل طلباً تعرف مسبقاً أنه سيُرفض بخطأ غامض.

**البديل على Azure:** في الخطوة 5 سنتعلم **استدعاء الدوال** (الدرس 4.2)، وهو أن تكتب أنت دالة بحث وتعطيها للنموذج. عندها يمكن كتابة دالة `search_web()` خاصة بنا تعمل مع أي مزوّد.

### الرموز وتكلفة الصفحة (تذكير بالدرس 1.2)

صفحة رئيسية عادية فيها 100 ألف حرف أو أكثر من HTML، معظمها سكربتات وتنسيقات. لو أرسلناها كما هي لدفعنا عشرات آلاف الرموز مقابل كود لا يفيد النموذج. `core/web.py` يحذف كل ذلك، ويقصّ النص عند 12 ألف حرف:

```python
MAX_CHARS = 12_000
```

الحرف الإنجليزي حوالي ربع رمز، والعربي أكثر قليلاً، فالصفحة تكلّف بين 3 و6 آلاف رمز إدخال تقريباً. ستجد العدد الحقيقي في آخر سطر يطبعه السكربت، وفي `logs/calls.jsonl`.

---

## شرح الكود ملفاً ملفاً

### `core/web.py` — تنظيف الصفحة

إزالة العناصر التي لا يقرؤها الزائر:

```python
for tag in soup(["script", "style", "noscript", "svg", "iframe", "template"]):
    tag.decompose()
```

`decompose()` تحذف العنصر ومحتواه من الشجرة نهائياً.

استخراج الوصف من وسم `meta`، مع بديل Open Graph الذي تستخدمه مواقع كثيرة:

```python
meta = soup.find("meta", attrs={"name": "description"}) or soup.find(
    "meta", attrs={"property": "og:description"}
)
```

العناوين `h1` و `h2` و `h3` مهمة لأنها غالباً تلخّص رسالة الشركة ("Track every truck")، فنرسلها في قسم منفصل ليراها النموذج بوضوح.

ملاحظة عن الترميز في الصفحات العربية:

```python
resp.encoding = resp.apparent_encoding or resp.encoding
```

بعض المواقع لا تعلن ترميزها بشكل صحيح، فتظهر العربية حروفاً غريبة. `apparent_encoding` يخمّن الترميز من المحتوى نفسه.

`as_prompt()` تجمع الأجزاء بعناوين واضحة (`TITLE:` و `HEADINGS:` و `PAGE TEXT:`). النموذج يفهم النص المُعنوَن أفضل من كتلة واحدة.

### `agents/researcher.py` — الوكيل

التعليمات، وهي أهم جزء في أي وكيل:

```python
INSTRUCTIONS = """You are a B2B market analyst.
You receive the text of a company's website, and sometimes a screenshot of it.
Fill in the company profile using ONLY what the sources say.

Rules:
- Do not invent facts, numbers, customers or competitors.
- If something is not in the sources, use an empty list or say so in plain words.
- Keep every list item short (under 12 words).
- Write the profile in English, even if the website is in Arabic;
  copy the evidence quotes in their original language.
"""
```

- **"ONLY what the sources say"** و **"Do not invent"**: أقوى سلاح ضد الهلوسة، إضافة إلى حقل `evidence`.
- **"Write the profile in English"**: قرار تصميم. الوكلاء التاليون سيعملون على هذا الملف، وتوحيد لغته يجعل سلوكهم أكثر ثباتاً. الاقتباسات تبقى بلغتها الأصلية لتتمكن من مراجعتها.

لاحظ أن الدالة تطلب `task="smart"`، لأن التحليل يحتاج فهماً جيداً. على Azure، هذا يعني النشر الذي وضعته في `MODEL_SMART`.

الدالة `analyze_company()` تقبل `page` و `client` اختيارياً. في التشغيل العادي لا نمررهما، فيحمّل الصفحة الحقيقية ويستخدم العميل الحقيقي. في الاختبارات نمرر صفحة جاهزة وعميلاً مزيفاً، وهذا نفس أسلوب **حقن الاعتماديات** من الخطوة 0.

### `tests/test_researcher.py` — 11 اختباراً جديداً

| الاختبار | ماذا يثبت |
| --- | --- |
| `test_parse_html_keeps_content_and_drops_scripts` | يبقى العنوان والوصف والنص العربي، وتختفي السكربتات والتنسيقات |
| `test_parse_html_truncates_long_pages` | الصفحات الطويلة تُقصّ ويُذكر ذلك للنموذج |
| `test_analyze_sends_structured_request` | الطلب يحمل `text_format=CompanyProfile` والنموذج `smart` ولا أدوات |
| `test_screenshot_becomes_base64_image_part` | الصورة تتحول إلى Data URL صحيح يمكن فكّه لنفس البايتات |
| `test_web_search_adds_tool_on_openai` | `--web` يضيف الأداة والتعليمات الخاصة بها |
| `test_web_search_refused_on_azure` | على Azure نرفض قبل إرسال أي طلب |
| `test_missing_parsed_output_raises` | الرد الناقص يعطي خطأ واضحاً |
| `test_schema_is_valid_for_strict_structured_outputs` | المخطط صالح للوضع الصارم: كل الحقول إلزامية ولا حقول إضافية |

الاختبار الأخير مفيد جداً: إذا أضفت حقلاً بقيمة افتراضية مثلاً، سيفشل هنا مجاناً بدل أن يفشل عند OpenAI.

---

## أخطاء شائعة وحلولها

| ما تراه | السبب | الحل |
| --- | --- | --- |
| `Screenshot not found` | أداة القص في Windows (`Win + Shift + S`) تنسخ الصورة للحافظة فقط، أو تحفظها في `Pictures\Screenshots` | الصق الصورة في Paint واحفظها باسم `home.png` داخل مجلد المشروع، أو مرّر المسار الكامل بين علامتي تنصيص |
| `requests.exceptions.HTTPError: 403` | الموقع يحجب الطلبات الآلية | جرّب موقعاً آخر، أو استخدم `--screenshot` وحده مع صفحة محفوظة |
| `confidence: "low"` ونص شبه فارغ | الموقع مبني بـ JavaScript ولا يحتوي نصاً في HTML | أضف `--screenshot` ليعتمد النموذج على الصورة |
| `BadRequestError` يذكر `json_schema` أو `text.format` | نموذج أو نشر قديم لا يدعم المخرجات المهيكلة | استخدم `gpt-4o-mini` (إصدار 2024-07-18) أو أحدث |
| `BadRequestError` يذكر `image` | النموذج في النشر لا يدعم الصور | استخدم نموذجاً يدعم الرؤية مثل `gpt-4o-mini` |
| `ValueError: web_search is not available on Azure` | استخدمت `--web` مع Azure | شغّل بدون `--web` |
| `RuntimeError: No structured output. Status: incomplete` | انقطع الرد قبل اكتمال JSON | نادر هنا؛ تأكد أنك لم تضف `max_output_tokens` صغيراً |
| عربية مشوّهة في `evidence` | ترميز الصفحة غير معلن | افتح Issue وأرسل لي الرابط |

---

## تمرين لك (20 دقيقة)

1. **قارن الرؤية بالنص:** حلّل نفس الموقع مرتين، مرة بدون صورة ومرة مع `--screenshot`. قارن `input_tokens` في المرتين. كم رمزاً كلّفت الصورة بـ `detail: "low"`؟
2. **جرّب الهلوسة:** احذف السطر `- Do not invent facts, numbers, customers or competitors.` من `INSTRUCTIONS` مؤقتاً، وحلّل موقعاً صغيراً. هل ظهر منافسون لم يُذكروا في الموقع؟ أعِد السطر بعدها.
3. **وسّع المخطط:** أضف إلى `CompanyProfile` حقلاً جديداً `pricing_model` بقيم `Literal["subscription", "one_time", "usage_based", "unknown"]`. شغّل `pytest` ثم حلّل موقعاً. هل تحتاج تعديل أي كود آخر؟ (الجواب: لا، وهذه قوة المخرجات المهيكلة.)

أرسل لي ناتج تحليل موقع واحد على الأقل، وسأراجع الجودة معك قبل الخطوة 2.

---

## الخطوة القادمة

**الخطوة 2 — وكيل العميل المثالي (ICP):** يأخذ `CompanyProfile` ويستخدم **نموذج استدلال** (الدرس 2.6) ليقترح 2–3 شرائح عملاء مستهدفة. ثم تحاوره لتعديلها ("ركّز على البنوك") عبر `previous_response_id` (الدرس 2.3)، دون أن تعيد إرسال كل شيء.

ملاحظة: أسماء النماذج والأسعار تتغير باستمرار؛ راجع وثائق OpenAI الرسمية للتحديثات.
