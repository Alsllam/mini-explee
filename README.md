# mini-explee

مشروع تعليمي: مساعد مبيعات ذكي مبسّط على غرار [Explee](https://explee.com/)، يُبنى خطوة بخطوة لتطبيق كل مبادئ كورس **The OpenAI API**.

> **تنبيه:** المشروع محاكاة كاملة. كل العملاء والردود فيه وهمية، ولا يحتوي أي دالة لإرسال بريد حقيقي.

## الخطوات

| الخطوة | الموضوع | دروس الكورس | الشرح |
| --- | --- | --- | --- |
| 0 | التأسيس: العميل الموحّد وأول استدعاء | 1.2–1.5، 2.1، 2.2، 5.1 | [docs/step-00-setup.md](docs/step-00-setup.md) |
| 1 | محلل الشركة | 2.2، 2.5، 3.2، 4.3 | [docs/step-01-company-analyzer.md](docs/step-01-company-analyzer.md) |
| 1ب | البحث على الويب: أداة مدمجة مقابل استدعاء الدوال (Tavily) | 4.2، 4.3 | [docs/step-01b-web-search.md](docs/step-01b-web-search.md) |
| 1ج | فحص التأسيس ومقاومة الهلوسة | 1.2، 2.5 | [docs/step-01c-grounding.md](docs/step-01c-grounding.md) |
| 2 | العميل المثالي (ICP): نموذج استدلال + محادثة | 2.3، 2.5، 2.6 | [docs/step-02-icp.md](docs/step-02-icp.md) |
| 3 | تقييم العملاء: Batch API والتخزين المؤقت | 2.1، 2.4، 2.5، 4.4 | [docs/step-03-lead-scoring.md](docs/step-03-lead-scoring.md) |
| 4 | كاتب الرسائل | 2.4، 3.1، 4.1، 5.2 | قريباً |
| 5 | معالج الردود والمنسّق | 4.2، 4.6 | قريباً |
| 6 | الصوت ولوحة التكلفة | 3.3–3.5، 4.5 | قريباً |
| 7 | مقارنة الأطر: LangGraph و CrewAI و AutoGen | 4.6 وما بعده | لاحقاً |

## التشغيل السريع

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # Windows: copy .env.example .env
# ضع مفتاحك في .env
pytest -v
python -m scripts.hello
```

## الأمان

- المفتاح في `.env` فقط، و`.env` في `.gitignore`.
- لا تلصق المفتاح في الكود أو في رسائل commit أو في أي محادثة.
- ضع حداً شهرياً للإنفاق في لوحة OpenAI.
