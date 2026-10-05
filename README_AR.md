# خط أنابيب بيانات الطلاب متعدد المصادر

[English](README.md) | [العربية](README_AR.md)

مشروع تدريبي لهندسة البيانات باستخدام Python. يستخرج بيانات الطلاب من CSV وREST API وقاعدة بيانات، ثم يتحقق منها وينظفها ويدمجها ويحوّلها. يحفظ السجلات النهائية والمرفوضة في ملفات CSV وMongoDB. كما يحتوي على مسار مستقل لاستخراج مستخدمي JSONPlaceholder وحفظهم في مجموعة منفصلة، من دون دمجهم مع بيانات الطلاب.

## نظرة عامة

يتكون المشروع من مسارين مستقلين:

1. **مسار الطلاب:** CSV + REST API + SQLite افتراضيًا (أو MongoDB كمصدر بديل للالتحاق بالمقررات) ← تحقق وتنظيف ودمج وتحويل ← ملفات CSV وMongoDB.
2. **مسار الويب:** JSON أو جدول HTML من الموقع المحدد ← تنظيف وتحويل وتحقق أساسي ← ملف CSV ومجموعة MongoDB منفصلة.

بيانات الموقع تصف مستخدمي JSONPlaceholder، ولا توجد علاقة بينها وبين `student_id` في بيانات الطلاب؛ لذلك تُحفظ في collection منفصلة ولا تُدمج كسجلات طلاب.

## محتويات المشروع

```text
app/
  sources/          مصادر CSV وAPI وSQLite وMongoDB واستخراج الويب
  transformation/  التنظيف والتحويل والدمج
  validation/      التحقق من جودة البيانات
  output/          الكتابة إلى CSV وMongoDB
  utils/            الإعدادات والسجلات والمقاييس والمعالجة التزايدية
data/               البيانات الخام ومخرجات CSV وحالة التشغيل
database/           مخطط SQLite وبياناته
mock_api/           خادم REST API وبياناته التجريبية
tests/              اختبارات المشروع
main.py             تشغيل خط الطلاب
web_scraping_pipeline.py  تشغيل خط استخراج الويب المستقل
config.json         إعدادات المصادر والمخرجات
```

## متطلبات التشغيل

- Python 3.12 أو أحدث.
- MongoDB محلي أو خدمة MongoDB يمكن الوصول إليها؛ حفظ المخرجات إلى MongoDB مفعّل افتراضيًا.
- اتصال بالإنترنت عند تشغيل scraper على JSONPlaceholder.

ثبّت حزم Python من مجلد المشروع:

```powershell
python -m pip install -r requirements.txt
```

الحزم الأساسية هي `pandas` و`requests` و`pymongo` و`pytest`.

## تشغيل MongoDB

إذا كانت خدمة MongoDB مثبتة على Windows، ابدأها من Services أو عبر PowerShell بصلاحيات مناسبة. أو شغّل خادمًا محليًا من نافذة طرفية مستقلة:

```powershell
New-Item -ItemType Directory -Force "$env:LOCALAPPDATA\StudentDataPipeline\MongoDBData"
mongod --dbpath "$env:LOCALAPPDATA\StudentDataPipeline\MongoDBData" --bind_ip 127.0.0.1
```

الإعداد الافتراضي يتصل بـ `mongodb://localhost:27017` ويستخدم قاعدة `student_pipeline`. عند استخدام MongoDB مستضاف، مرّر URI من متغير البيئة `MONGODB_URI` بدل وضع بيانات الدخول في ملفات المشروع:

```powershell
$env:MONGODB_URI = "<MongoDB connection URI>"
```

لا تشارك URI أو كلمة المرور، ولا تضفهما إلى Git.

## تشغيل خط الطلاب

1. ابدأ Mock REST API في نافذة طرفية:

   ```powershell
   python mock_api/server.py
   ```

2. تأكد من تشغيل MongoDB كما سبق.

3. شغّل خط الطلاب من مجلد المشروع:

   ```powershell
   python main.py
   ```

يقرأ `main.py` الإعدادات من `config.json`، ويطبق المراحل التالية:

1. استخراج CSV وREST API ومصدر قاعدة البيانات.
2. التحقق من كل مصدر وتسجيل السجلات غير الصالحة.
3. إزالة التكرارات المطابقة وتوحيد النصوص.
4. دمج المصادر باستخدام `student_id`.
5. تعويض GPA والحضور المفقودين، وتحويل الأنواع وإضافة الأعمدة المشتقة.
6. التحقق النهائي من السجلات.
7. حفظ CSV وتحديث snapshots الطلاب والمرفوضات في MongoDB.

SQLite هو مصدر قاعدة البيانات الافتراضي. لاستخدام MongoDB بدل SQLite كـ **مصدر** لبيانات المقررات، اضبط `sources.database.backend` إلى `mongodb`، ثم جهّز collection مستنداتها تحتوي الحقول `student_id` و`course_name` و`credit_hours` و`semester` و`score`. استخدام MongoDB لحفظ النتائج مستقل عن اختيار مصدر الإدخال.

## تشغيل استخراج الويب

الإعداد الافتراضي هو:

```text
https://jsonplaceholder.typicode.com/users
```

هذا endpoint يعيد JSON لمجموعة من 10 مستخدمين، وليس جدول HTML. يستطيع المصدر قراءة JSON أو جدول HTML، ويفرد الحقول المتداخلة إلى أسماء مفصولة بنقطة مثل `address.city` و`company.name`.

بعد تشغيل MongoDB، نفّذ:

```powershell
python web_scraping_pipeline.py
```

يقرأ scraper قسم `scraping` من `config.json`، وينظف البيانات ويحوّلها ويتحقق من `required_columns`، ثم يكتب:

- CSV إلى `data/scraped/web_data.csv`.
- snapshot مستقل إلى `student_pipeline.scraped_users` في MongoDB.
- سجل التشغيل إلى `logs/web_scraping_pipeline.log`.

يمكن تغيير `url` و`format` و`column_mapping` و`required_columns` و`output` في قسم `scraping`. قيمة `format` تكون `json` أو `html` أو `auto`. يعيد كل تشغيل استبدال snapshot المجموعة، فلا يضيف نسخة مكررة من مستخدمي التشغيل السابق.

## قاعدة MongoDB ومجموعاتها

يستخدم المساران قاعدة واحدة، مع إبقاء أنواع السجلات منفصلة:

| قاعدة البيانات والمجموعة | المحتوى المتوقع في البيانات المرجعية |
| --- | --- |
| `student_pipeline.processed_students` | 8 سجلات طلاب صالحة |
| `student_pipeline.rejected_students` | 6 سجلات مرفوضة مع أسباب الرفض |
| `student_pipeline.scraped_users` | 10 مستخدمين من JSONPlaceholder |

يستبدل كل مسار مجموعاته الخاصة فقط. لا يغيّر scraper مجموعات الطلاب، ولا يدمج المستخدمين مع الطلاب لأن المعرّفات تشير إلى كيانات مختلفة.

## المخرجات المرجعية

على البيانات التجريبية المرفقة، يتوقع المشروع:

- 14 صفًا خامًا من CSV، و13 سجلًا من API، و12 سجل التحاق من SQLite.
- 8 سجلات طلاب نهائية و6 سجلات مرفوضة.
- وسيط GPA يساوي `3.0` ووسيط الحضور يساوي `85`.
- مستخدمي الويب: 10 سجلات في `scraped_users`.

السجلات المرجعية في هذا المستودع بيانات تدريب اصطناعية. ملفات `pipeline_state.json` والسجلات ونتائج scraper ملفات تشغيل محلية وليست جزءًا من المصدر المنشور.

## الإعدادات

أهم الإعدادات في `config.json`:

| المسار | الغرض |
| --- | --- |
| `sources.csv.path` | ملف بيانات الطلاب الخام |
| `sources.api.url` و`timeout_seconds` | عنوان REST API ومهلة الاتصال |
| `sources.database.backend` | `sqlite` أو `mongodb` كمصدر لبيانات المقررات |
| `sources.mongodb` | URI أو اسم متغير البيئة، قاعدة Mongo، المجموعة ومهلة الاتصال |
| `output.mongodb.enabled` | تفعيل أو تعطيل حفظ النتائج في MongoDB |
| `output.mongodb.collections` | أسماء مجموعات الطلاب والمرفوضات والويب |
| `scraping` | عنوان الموقع وصيغة الاستجابة والحقول والوجهات الخاصة بالـscraper |
| `incremental` | تفعيل المعالجة التزايدية ومكان ملف الحالة |

يُحلّ المسار النسبي في الإعدادات نسبةً إلى مجلد ملف `config.json`.

## المعالجة التزايدية والنسب والمقاييس

- عند تفعيل `incremental.enabled`، تقارن بصمات البيانات بحالة التشغيل السابقة لإعادة معالجة السجلات الجديدة أو المتغيرة وإعادة استخدام السجلات التي لم تتغير.
- يضيف عمود `source` نسب السجل إلى مصادر الطلاب، وقيمته المرجعية `CSV|API|DATABASE`.
- يسجل `logs/pipeline.log` أعداد المصادر والسجلات الصالحة والمرفوضة والتكرارات والقيم المفقودة ومدة التشغيل.
- يكتب السجلات المرفوضة مع `error_reason` إلى `data/rejected/rejected_records.csv`.

## الاختبارات

شغّل الاختبارات من مجلد المشروع:

```powershell
python -m pytest -q
```

يحتوي الاختبار على 301 حالة، ويستخدم خادم API محليًا وHTML/JSON تجريبيًا وعميل MongoDB وهميًا؛ لذلك لا يحتاج تشغيل MongoDB أو الاتصال بالإنترنت أثناء الاختبارات.

## وثائق إضافية

- [خطة المشروع](PROJECT_PLAN.md)
- [عقد البيانات وقواعد الجودة](DATA_CONTRACT.md)
