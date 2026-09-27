# الخطوة 0: التأسيس — العميل الموحّد وأول استدعاء

> **دروس الكورس المطبّقة:** 1.2 المفاهيم الأساسية · 1.3 مفتاح API · 1.4 بيئة التطوير · 1.5 نماذج API · 2.1 اختيار النموذج · 2.2 Responses API · 5.1 معالجة الأخطاء

## ماذا سنبني في هذه الخطوة؟

قبل أن نكتب أي "وكيل" ذكي، نحتاج أساساً يقف عليه المشروع كله. في هذه الخطوة نبني **باباً واحداً** تمر منه كل استدعاءات OpenAI في المشروع: الدالة `ask()` في الملف `core/client.py`.

لماذا باب واحد وليس استدعاء الـ SDK مباشرة من كل ملف؟ لأن كل استدعاء في المشروع يحتاج نفس الأشياء الأربعة:

1. اختيار النموذج المناسب للمهمة.
2. إعادة المحاولة عند الأخطاء المؤقتة.
3. تسجيل عدد الرموز (tokens) والزمن لحساب التكلفة لاحقاً.
4. رسالة واضحة إذا كان المفتاح غير موجود.

لو كتبنا هذه الأشياء في كل وكيل، سنكررها ثماني مرات ونخطئ في واحدة منها حتماً. بوضعها في مكان واحد، أي تحسين نضيفه لاحقاً (مثل التخزين المؤقت في الخطوة 3) يستفيد منه المشروع كله فوراً.

بنهاية الخطوة سيكون لديك:

- مشروع Python يعمل في بيئة افتراضية معزولة.
- مفتاح API محفوظ بأمان خارج Git.
- أول استدعاء حقيقي لـ Responses API يرد بالعربية.
- سجل لكل استدعاء في `logs/calls.jsonl`.
- ستة اختبارات تعمل بدون مفتاح وبدون إنترنت.

---

## خطوات التشغيل (نفّذها بالترتيب)

### 1. استنسخ المستودع وادخل إليه

استنساخ المستودع من GitHub إلى جهازك:

```bash
git clone https://github.com/Alsllam/mini-explee.git
cd mini-explee
git checkout step-00-setup
```

> بعد دمج طلب الدمج (Pull Request) في `main`، لن تحتاج السطر الأخير.

### 2. أنشئ بيئة افتراضية وفعّلها

إنشاء بيئة افتراضية في مجلد `.venv`:

```bash
python -m venv .venv
```

تفعيلها على Windows:

```bash
.venv\Scripts\activate
```

تفعيلها على macOS أو Linux:

```bash
source .venv/bin/activate
```

**لماذا بيئة افتراضية؟** كل مشروع Python يحتاج إصدارات محددة من المكتبات. البيئة الافتراضية تعزل مكتبات هذا المشروع عن باقي جهازك، فلا يكسر تحديثٌ في مشروع آخر هذا المشروع. ستعرف أنها مفعّلة عندما ترى `(.venv)` في بداية سطر الأوامر.

### 3. ثبّت المكتبات

تثبيت كل ما يحتاجه المشروع من ملف `requirements.txt`:

```bash
pip install -r requirements.txt
```

| المكتبة | دورها |
| --- | --- |
| `openai` | الـ SDK الرسمي للتعامل مع OpenAI API |
| `python-dotenv` | قراءة ملف `.env` وتحويله إلى متغيرات بيئة |
| `pytest` | تشغيل الاختبارات |

### 4. جهّز ملف المفتاح `.env`

نسخ ملف القالب إلى ملف حقيقي (Windows):

```bash
copy .env.example .env
```

أو على macOS و Linux:

```bash
cp .env.example .env
```

ثم افتح `.env` في محرر النصوص وضع مفتاحك مكان `sk-...`:

```
OPENAI_API_KEY=sk-...
```

تحصل على المفتاح من لوحة OpenAI في قسم API keys. **لا تلصق المفتاح في أي مكان آخر**: لا في الكود، ولا في المحادثة، ولا في رسالة commit.

### 5. شغّل الاختبارات أولاً

تشغيل الاختبارات (لا تحتاج مفتاحاً ولا إنترنت):

```bash
pytest -v
```

يجب أن ترى `6 passed`. إذا نجحت الاختبارات فالكود سليم، وأي مشكلة لاحقة ستكون في المفتاح أو الشبكة وليست في الكود. هذه عادة جيدة: **اختبر ما تستطيع اختباره مجاناً قبل أن تدفع مقابل استدعاء حقيقي.**

### 6. اعرف النماذج المتاحة لمفتاحك

عرض النماذج التي يستطيع مفتاحك استخدامها، مع تصفية بكلمة:

```bash
python -m scripts.list_models mini
```

أسماء النماذج تتغير باستمرار، والنماذج المتاحة تختلف من حساب لآخر. إذا ظهر لك نموذج أحدث وأرخص، ضع اسمه في `.env` في المتغير `MODEL_FAST`.

### 7. أول استدعاء حقيقي

تشغيل السكربت الذي يرسل سؤالاً واحداً عبر `ask()`:

```bash
python -m scripts.hello
```

ستظهر إجابة بالعربية، ثم رقم الاستجابة (`resp_...`) وعدد رموز الإدخال والإخراج. افتح الملف `logs/calls.jsonl` وسترى سطراً يصف هذا الاستدعاء.

> **لماذا `python -m scripts.hello` وليس `python scripts/hello.py`؟** الصيغة `-m` تشغّل الملف كوحدة من جذر المشروع، فيستطيع أن يستورد `core` و `config`. الصيغة الثانية ستفشل بخطأ `ModuleNotFoundError`.

---

## المفاهيم: ماذا تعلّمنا من الكورس هنا؟

### المفاهيم الأساسية (الدرس 1.2)

- **الرمز (Token):** النموذج لا يقرأ كلمات بل "رموزاً"، وهي أجزاء من الكلمات. الكلمة الإنجليزية غالباً رمز أو رمزان، والعربية عادة أكثر لأن الكلمة الواحدة تحمل سوابق ولواحق. **التكلفة تُحسب بالرموز**: رموز الإدخال (ما ترسله) ورموز الإخراج (ما يكتبه النموذج)، والإخراج أغلى عادة.
- **نافذة السياق (Context window):** أقصى عدد رموز يستطيع النموذج استقباله في طلب واحد. سيهمّنا هذا في الخطوة 1 عندما نمرر محتوى موقع كامل.
- **عدم الحتمية:** نفس السؤال قد يعطي إجابات مختلفة. لهذا نختبر منطقنا بعميل مزيف (انظر الاختبارات) وليس بالنموذج نفسه.

### أمان المفتاح (الدرس 1.3)

المفتاح مثل كلمة سر لحساب بنكي: أي شخص يملكه يستطيع الاستهلاك على حسابك. في مستودع **عام** مثل مستودعنا، هذا أهم من أي شيء آخر. طبّقنا ثلاث طبقات حماية:

| الطبقة | أين | ماذا تفعل |
| --- | --- | --- |
| المفتاح في `.env` فقط | ملف `.env` | الكود لا يحتوي المفتاح أبداً، بل يقرؤه من البيئة |
| `.env` في `.gitignore` | ملف `.gitignore` | يمنع Git من رفع الملف حتى لو كتبت `git add .` |
| قالب بلا قيمة حقيقية | ملف `.env.example` | يوضح لغيرك أي المتغيرات مطلوبة، بقيمة `sk-...` فقط |

**إذا تسرّب المفتاح بالخطأ:** ألغِه فوراً من لوحة OpenAI وأنشئ غيره. حذف الملف من GitHub لا يكفي، لأن المفتاح يبقى في تاريخ Git، وهناك برامج آلية تمسح GitHub بحثاً عن المفاتيح خلال دقائق.

نصيحة إضافية: ضع **حداً شهرياً للإنفاق** (budget limit) في لوحة OpenAI، مثلاً 10 دولارات، فحتى أسوأ خطأ لن يتجاوزه.

### بيئة التطوير (الدرس 1.4)

`load_dotenv()` في أول `config.py` تقرأ ملف `.env` وتضع كل سطر فيه كمتغير بيئة. بعدها يقرأ الـ SDK المتغير `OPENAI_API_KEY` تلقائياً عند إنشاء `OpenAI()`، دون أن نمرره يدوياً.

### اختيار النموذج (الدرسان 1.5 و 2.1)

الخطأ الشائع هو استخدام "أقوى نموذج" لكل شيء. الصحيح أن تختار حسب **المهمة**:

| نوع المهمة | المتغير | متى يُستخدم في المشروع | الاعتبارات |
| --- | --- | --- | --- |
| `fast` | `MODEL_FAST` | تقييم مئات العملاء، تصنيف الردود | الأرخص والأسرع؛ الكمية كبيرة والمهمة بسيطة |
| `smart` | `MODEL_SMART` | تحليل موقع الشركة، كتابة الرسائل | جودة الكتابة والفهم أهم من السعر |
| `reasoning` | `MODEL_REASONING` | استنتاج الشرائح المستهدفة (الخطوة 2) | يفكر قبل أن يجيب؛ أبطأ وأغلى، لمهام تحتاج خطوات منطقية |

وضعنا الأسماء الثلاثة في `.env` وليس في الكود، لسببين: الأسماء تتغير باستمرار، وتستطيع تجربة نموذج جديد دون تعديل سطر كود واحد. حالياً جعلناها كلها نفس النموذج الرخيص، وسنرفع `smart` و `reasoning` عندما نصل لمهام تحتاجها.

### Responses API (الدرس 2.2)

هذه هي الواجهة الحديثة التي يعتمدها الكورس. شكل الاستدعاء الأساسي:

الاستدعاء المباشر بالـ SDK، كما يعلّمه الكورس:

```python
from openai import OpenAI

client = OpenAI()
response = client.responses.create(
    model="gpt-4o-mini",
    instructions="You are a concise assistant. Answer in Arabic.",
    input="In two sentences, explain what a B2B sales outreach assistant does.",
)
print(response.output_text)
```

| الحقل | المعنى |
| --- | --- |
| `model` | أي نموذج يجيب |
| `instructions` | توجيهات عامة للنموذج (دوره، لغته، أسلوبه). أولويتها أعلى من `input` |
| `input` | السؤال أو المحتوى. نص، أو قائمة رسائل (سنستخدم القوائم في الخطوة 2) |
| `response.output_text` | النص النهائي مجمّعاً، أسهل طريقة لقراءة الإجابة |
| `response.id` | رقم الاستجابة؛ سنستخدمه في الخطوة 2 مع `previous_response_id` لمتابعة المحادثة |
| `response.usage` | عدد الرموز: `input_tokens` و `output_tokens` |

### معالجة الأخطاء (الدرس 5.1)

أي تطبيق يتحدث مع API عبر الإنترنت سيواجه أخطاء. السؤال المهم لكل خطأ: **هل تفيد إعادة المحاولة؟**

| الخطأ | السبب | المعالجة الموصى بها |
| --- | --- | --- |
| `RateLimitError` (HTTP 429) بنوع `rate_limit_exceeded` | طلبات أو رموز كثيرة في الدقيقة | انتظر ثم أعد المحاولة بتأخير متزايد |
| `RateLimitError` (HTTP 429) بنوع `insufficient_quota` | الرصيد انتهى | **لا تُعِد المحاولة**؛ أضف رصيداً أولاً |
| `APIConnectionError` | انقطاع الشبكة قبل وصول الرد | أعد المحاولة |
| `APITimeoutError` | لم يصل رد خلال المهلة | أعد المحاولة |
| `InternalServerError` (HTTP 5xx) | مشكلة عند OpenAI | أعد المحاولة |
| `AuthenticationError` (HTTP 401) | مفتاح خاطئ أو ملغى | لا تُعِد المحاولة؛ أصلح المفتاح |
| `BadRequestError` (HTTP 400) | معامل خاطئ أو اسم نموذج غير موجود | لا تُعِد المحاولة؛ أصلح الطلب |

**التأخير الأسّي مع العشوائية (exponential backoff with jitter):** بعد الفشل الأول ننتظر نحو ثانية، ثم ثانيتين، ثم 4، ثم 8، بحد أقصى 30 ثانية. نضرب كل مدة برقم عشوائي بين 0.5 و 1. السبب: إذا فشل ألف عميل في نفس اللحظة وانتظروا نفس المدة بالضبط، سيعودون معاً في نفس اللحظة ويسببون ازدحاماً جديداً. العشوائية توزّعهم.

---

## شرح الكود ملفاً ملفاً

### `config.py` — مكان واحد للإعدادات

قراءة `.env` ثم تعريف قاموس النماذج:

```python
load_dotenv()

MODELS = {
    "fast": os.getenv("MODEL_FAST", "gpt-4o-mini"),
    "smart": os.getenv("MODEL_SMART", "gpt-4o-mini"),
    "reasoning": os.getenv("MODEL_REASONING", "gpt-4o-mini"),
}
```

`os.getenv("MODEL_FAST", "gpt-4o-mini")` تعني: اقرأ القيمة من البيئة، وإن لم توجد فاستخدم القيمة الافتراضية. هكذا يعمل المشروع حتى لو نسيت سطراً في `.env`.

دالة صغيرة تمنع الأخطاء الإملائية في أسماء المهام:

```python
def model_for(task: str) -> str:
    if task not in MODELS:
        raise ValueError(f"Unknown task kind {task!r}. Use one of: {', '.join(MODELS)}")
    return MODELS[task]
```

لو كتب أحدهم `task="smrt"` بالخطأ، سيحصل على رسالة واضحة فوراً بدل سلوك غامض.

### `core/client.py` — الباب الواحد

**1) إنشاء العميل مرة واحدة:**

الدالة `get_client()` تنشئ العميل عند أول طلب وتعيد استخدامه:

```python
def get_client() -> OpenAI:
    global _client
    if _client is None:
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        _client = OpenAI(max_retries=0)
    return _client
```

- نتحقق من المفتاح قبل أي استدعاء، لنعطي رسالة مفهومة بدل خطأ 401 غامض.
- `max_retries=0`: الـ SDK يعيد المحاولة من تلقاء نفسه مرتين افتراضياً. أطفأنا ذلك لنبني حلقتنا الخاصة ونراها تعمل ونختبرها. في مشروع إنتاجي حقيقي، إعادة المحاولة المدمجة في الـ SDK كافية غالباً، لكن الهدف هنا التعلم.

**2) حساب مدة الانتظار:**

```python
def backoff_delay(attempt: int, base: float = 1.0, cap: float = 30.0) -> float:
    return min(cap, base * (2 ** attempt)) * random.uniform(0.5, 1.0)
```

| المحاولة `attempt` | `2 ** attempt` | مدة الانتظار الفعلية |
| --- | --- | --- |
| 0 | 1 | بين 0.5 و 1 ثانية |
| 1 | 2 | بين 1 و 2 ثانية |
| 2 | 4 | بين 2 و 4 ثوانٍ |
| 3 | 8 | بين 4 و 8 ثوانٍ |
| 5 وما بعدها | 32 أو أكثر | لا تتجاوز 30 ثانية |

**3) الدالة `ask()` — قلب الملف:**

بناء معاملات الطلب، مع إرسال `instructions` فقط إن وُجدت:

```python
params: dict[str, Any] = {"model": model, "input": input, **kwargs}
if instructions is not None:
    params["instructions"] = instructions
```

`**kwargs` تعني أن أي معامل إضافي تمرره لـ `ask()` (مثل `temperature` أو `tools` في الخطوات القادمة) يصل كما هو إلى `responses.create`. هكذا لن نحتاج تعديل `ask()` كلما تعلمنا ميزة جديدة.

حلقة المحاولات:

```python
for attempt in range(attempts):
    started = time.monotonic()
    try:
        response = client.responses.create(**params)
    except RETRYABLE_ERRORS as err:
        if attempt == attempts - 1:
            _log_call(task, model, None, started, attempt + 1, error=err)
            raise
        wait = backoff_delay(attempt)
        print(f"[retry] {type(err).__name__} - attempt {attempt + 1}/{attempts}, waiting {wait:.1f}s")
        sleep(wait)
        continue
    except Exception as err:
        _log_call(task, model, None, started, attempt + 1, error=err)
        raise

    _log_call(task, model, response, started, attempt + 1)
    return response
```

اقرأها هكذا:

1. جرّب الاستدعاء.
2. إن فشل بخطأ **مؤقت** ولم تنفد المحاولات: اطبع تنبيهاً، وانتظر، وكرّر.
3. إن فشل بخطأ مؤقت في **آخر** محاولة: سجّل الفشل وارفع الخطأ للمستدعي.
4. إن فشل بخطأ **غير مؤقت** (مفتاح خاطئ مثلاً): سجّله وارفعه فوراً دون تكرار.
5. إن نجح: سجّله وأعد الاستجابة.

لاحظ `time.monotonic()` بدل `time.time()`: ساعة الجهاز قد تتغير (مزامنة الوقت مثلاً)، أما `monotonic` فتتقدم دائماً للأمام، فهي الصحيحة لقياس المدد.

لاحظ أيضاً أن `ask()` تقبل `client` و `sleep` كمعاملات. في التشغيل العادي لا نمررهما فتُستخدم القيم الحقيقية. في الاختبارات نمرر عميلاً مزيفاً ودالة `sleep` لا تنتظر، فتعمل الاختبارات في أقل من ثانية وبلا مفتاح. هذا الأسلوب اسمه **حقن الاعتماديات (dependency injection)**.

**4) سجل الاستدعاءات:**

كل استدعاء يضيف سطر JSON واحداً إلى `logs/calls.jsonl`. مثال على شكل السطر:

```json
{"time": "2026-09-27T10:15:02+00:00", "task": "fast", "model": "gpt-4o-mini", "response_id": "resp_...", "input_tokens": 41, "cached_tokens": 0, "output_tokens": 87, "latency_ms": 1320, "attempts": 1, "error": null}
```

صيغة JSONL (سطر JSON لكل سجل) مناسبة للسجلات لأننا نضيف في نهاية الملف دون قراءته كله. سنبني على هذا الملف لوحة التكلفة في الخطوة 6، ونقارنه بأرقام Usage API. الحقل `cached_tokens` سيبدأ يرتفع في الخطوة 3 عندما نطبق التخزين المؤقت (الدرس 2.4).

**5) نوعان مختلفان من الخطأ 429:**

نفس رقم الخطأ `429` له معنيان مختلفان تماماً، ونفرّق بينهما من حقل `type` و `code` في جسم الخطأ:

```python
QUOTA_ERROR_MARKERS = {"insufficient_quota", "credit_balance_exhausted"}


def is_retryable(err: Exception) -> bool:
    if not isinstance(err, RETRYABLE_ERRORS):
        return False
    if isinstance(err, RateLimitError):
        markers = {getattr(err, "type", None), getattr(err, "code", None)}
        if markers & QUOTA_ERROR_MARKERS:
            return False
    return True
```

- `rate_limit_exceeded`: أرسلت كثيراً في وقت قصير. الانتظار يحلّها، فنعيد المحاولة.
- `insufficient_quota`: الرصيد انتهى. الانتظار لن يغيّر شيئاً، فنتوقف فوراً ونُظهر الخطأ.

هذا درس عملي من الدرس 5.1: **لا يكفي النظر إلى رقم الخطأ؛ اقرأ نوعه.** النسخة الأولى من الكود كانت تعيد المحاولة 4 مرات على خطأ الرصيد، فتضيع نحو 12 ثانية دون فائدة.

### `tests/test_client.py` — اختبار بلا مفتاح

عميل مزيف يرمي الأخطاء التي نحددها بالترتيب، ثم ينجح:

```python
class FakeClient:
    def __init__(self, errors=()):
        self.errors = list(errors)
        self.calls = []
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **params):
        self.calls.append(params)
        if self.errors:
            raise self.errors.pop(0)
        return fake_response()
```

`self.responses = SimpleNamespace(create=...)` تجعل `fake.responses.create(...)` تعمل تماماً كما في العميل الحقيقي، فلا تعرف `ask()` الفرق.

| الاختبار | ماذا يثبت |
| --- | --- |
| `test_success_first_try_logs_tokens` | النجاح من أول مرة يُسجَّل بعدد الرموز الصحيح، و`instructions` لا تُرسل إن لم تُعطَ |
| `test_retries_rate_limit_then_succeeds` | بعد خطأين مؤقتين تنجح المحاولة الثالثة، مع انتظارين |
| `test_gives_up_after_max_retries` | لا نكرر للأبد؛ نتوقف بعد `MAX_RETRIES` ونرفع الخطأ |
| `test_bad_request_is_not_retried` | الخطأ الدائم لا يُكرَّر |
| `test_backoff_grows_and_is_capped` | مدة الانتظار ضمن الحدود المتوقعة دائماً |
| `test_unknown_task_kind_is_rejected` | اسم مهمة خاطئ يعطي خطأ واضحاً |

---

## استخدام Azure OpenAI بدل OpenAI

المشروع يعمل مع Azure OpenAI دون تغيير أي كود؛ التغيير كله في ملف `.env`. نستخدم واجهة Azure الجديدة (v1 API) التي تقبل عميل `OpenAI()` العادي، فلا حاجة لـ `AzureOpenAI` ولا لـ `api_version`.

إعدادات `.env` لـ Azure:

```
OPENAI_API_KEY=<your Azure OpenAI key>
OPENAI_BASE_URL=https://YOUR-RESOURCE.openai.azure.com/openai/v1/
MODEL_FAST=my-gpt4o-mini-deployment
MODEL_SMART=my-gpt4o-mini-deployment
MODEL_REASONING=my-gpt4o-mini-deployment
```

| الإعداد | من أين تحصل عليه في بوابة Azure |
| --- | --- |
| `OPENAI_API_KEY` | صفحة مورد Azure OpenAI ← Keys and Endpoint ← KEY 1 |
| `OPENAI_BASE_URL` | نفس الصفحة ← Endpoint، ثم أضف في آخره `openai/v1/` |
| `MODEL_*` | Azure AI Foundry ← Deployments ← عمود **Name** (اسم النشر، وليس اسم النموذج) |

**أهم فرق:** في OpenAI تكتب اسم النموذج (`gpt-4o-mini`)، أما في Azure فتكتب **اسم النشر (deployment)** الذي اخترته أنت عند نشر النموذج. إذا أخطأت فيه سيظهر خطأ `NotFoundError` أو `DeploymentNotFound`.

**كيف يعمل في الكود؟** `config.py` يقرأ `OPENAI_BASE_URL`، و`get_client()` يمرره للعميل:

```python
_client = OpenAI(base_url=config.OPENAI_BASE_URL, max_retries=0)
```

إذا كان المتغير فارغاً تكون القيمة `None` فيذهب الطلب إلى OpenAI، وإذا كان فيه رابط يذهب الطلب إلى Azure.

**ملاحظات:**
- سكربت `list_models` على Azure يعرض النماذج المتاحة في المنطقة، وليس عمليات النشر الخاصة بك؛ اعتمد على صفحة Deployments.
- ميزات بعض الخطوات القادمة (مثل `web_search` و Realtime والضبط الدقيق) تختلف إتاحتها على Azure حسب المنطقة؛ سأنبّه عليها في كل خطوة.
- رسالة `429` على Azure غالباً تعني أن حصة النشر (TPM) صغيرة؛ يمكن رفعها من إعدادات النشر.

---

## أخطاء شائعة وحلولها

**قبل أي شيء، شغّل أداة الفحص.** تعرض ملف `.env` الذي قُرئ، والرابط الذي ستذهب إليه الطلبات، ونوع المفتاح وطوله دون إظهاره، وأسماء النماذج. لا تستدعي الـ API، فهي مجانية:

```bash
python -m scripts.check_env
```

ملاحظة: `config.py` يقرأ `.env` بالخيار `override=True`، أي أن قيم `.env` تتقدّم على أي متغير `OPENAI_*` مضبوط في إعدادات النظام. بدون هذا الخيار، متغير قديم في إعدادات Windows قد يطغى على ملفك دون أن تنتبه.

| ما تراه | السبب | الحل |
| --- | --- | --- |
| `RuntimeError: OPENAI_API_KEY is not set` | لا يوجد `.env`، أو المتغير باسم مختلف | تأكد أن الملف اسمه `.env` بالضبط في جذر المشروع |
| `AuthenticationError` / 401 | المفتاح خاطئ أو ملغى أو فيه مسافة زائدة | انسخ المفتاح من جديد دون مسافات أو علامات تنصيص |
| `NotFoundError` أو `BadRequestError` عن النموذج | اسم نموذج غير متاح لحسابك | شغّل `python -m scripts.list_models` وعدّل `.env` |
| `RateLimitError` فوري مع `insufficient_quota` أو `credit_balance_exhausted` | الرصيد صفر أو لم تُضف وسيلة دفع | أضف رصيداً في لوحة Billing، أو استخدم Azure |
| الخطأ يذكر `platform.openai.com` رغم أنك تستخدم Azure | `OPENAI_BASE_URL` غير مضبوط، فذهب الطلب إلى OpenAI | ضع رابط Azure في `.env` (قسم Azure أعلاه) |
| `ModuleNotFoundError: No module named 'core'` | شغّلت الملف بمساره بدل `-m` | شغّل من جذر المشروع: `python -m scripts.hello` |
| `pytest` غير معروف | البيئة الافتراضية غير مفعّلة | فعّلها (الخطوة 2) ثم أعد المحاولة |

---

## تمرين لك (15 دقيقة)

1. غيّر `instructions` في `scripts/hello.py` ليرد النموذج بأسلوب رسمي جداً، ثم بأسلوب عامي. قارن عدد رموز الإخراج في `logs/calls.jsonl` بين المرتين.
2. أضف المعامل `max_output_tokens=20` إلى استدعاء `ask()` في `hello.py` (سيصل عبر `**kwargs`). ماذا يحدث للإجابة؟ وما قيمة `response.status`؟
3. **(للتفكير)** لماذا لم نضع `AuthenticationError` في `RETRYABLE_ERRORS`؟ ماذا سيحدث لو وضعناه؟

أرسل لي نتيجة `python -m scripts.hello` (بدون المفتاح طبعاً) وإجاباتك، ثم ننتقل للخطوة 1.

---

## الخطوة القادمة

**الخطوة 1 — محلل الشركة:** نعطيه رابط موقع شركة، فيبحث عنها عبر أداة `web_search` المدمجة (الدرس 4.3)، ويقرأ لقطة شاشة صفحتها الرئيسية (الدرس 3.2)، ويعيد ملفاً منظماً عنها بمخطط JSON ثابت اسمه `CompanyProfile` (الدرس 2.5).

ملاحظة: أسماء النماذج والأسعار تتغير باستمرار؛ راجع وثائق OpenAI الرسمية للتحديثات.
