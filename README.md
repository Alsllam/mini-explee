# mini-explee

مشروع تعليمي: مساعد مبيعات ذكي مبسّط على غرار [Explee](https://explee.com/)، يُبنى خطوة بخطوة لتطبيق كل مبادئ كورس **The OpenAI API**.

> **تنبيه:** المشروع محاكاة كاملة. كل العملاء والردود فيه وهمية، ولا يحتوي أي دالة لإرسال بريد حقيقي.

## الخطوات

| الخطوة | الموضوع | دروس الكورس | الشرح |
| --- | --- | --- | --- |
| 0 | التأسيس: العميل الموحّد وأول استدعاء | 1.2–1.5، 2.1، 2.2، 5.1 | [docs/step-00-setup.md](docs/step-00-setup.md) |
| 1 | محلل الشركة | 2.2، 2.5، 3.2، 4.3 | [docs/step-01-company-analyzer.md](docs/step-01-company-analyzer.md) |
| 2 | العميل المثالي (ICP) | 2.3، 2.5، 2.6 | قريباً |
| 3 | تقييم العملاء | 2.4، 2.5، 4.4 | قريباً |
| 4 | كاتب الرسائل | 2.4، 3.1، 4.1، 5.2 | قريباً |
| 5 | معالج الردود والمنسّق | 4.2، 4.6 | قريباً |
| 6 | الصوت ولوحة التكلفة | 3.3–3.5، 4.5 | قريباً |

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
