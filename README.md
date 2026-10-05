# Multi-Source Student Data Pipeline

A group project for the PAEP Data Engineering course: a Python ETL pipeline that collects student data from CSV, a REST API, and a database source (SQLite by default, or MongoDB), validates and cleans it, integrates it into one analysis-ready dataset, and produces valid and rejected outputs with logging, metrics, and lineage. A separate HTML-table scraper pipeline writes its own output and never joins the student pipeline.

The pipeline follows this flow:

```text
Student Pipeline (CSV | REST API | SQLite or MongoDB)
                    |
                 Extract
                    |
                 Validate
                    |
                  Clean
                    |
                Integrate
                    |
                Transform
                    |
             Final Validation
                    |
        +-----------+-----------+
        |                       |
  Valid Records          Invalid Records
        |                       |
final_dataset.csv      rejected_records.csv
```

## Project Overview

The same student exists in three different systems: identity data in a CSV file, academic data behind a REST API, and course enrollments in a SQLite database. This project builds one automated pipeline that:

- Extracts all three sources (the API source always works over real HTTP requests).
- Validates each source against the data quality rules before anything is merged.
- Cleans recoverable problems (duplicates, whitespace, inconsistent case).
- Integrates the sources on the shared `student_id` key (one row per student).
- Transforms the data: type handling, missing-value imputation from raw-API medians, and derived columns.
- Runs a final validation and splits the result into valid and rejected records.
- Writes the outputs and records stage-by-stage logs and pipeline metrics.
- Can use MongoDB documents as an alternative backend for the SQLite enrollment source.
- Runs an independent HTML-table scraper through `web_scraping_pipeline.py`; scraped records are never integrated with student records.

On the canonical dataset the pipeline produces **8 valid records** and **6 rejected records**, and asserts this end-to-end in the test suite. The intended final order is documented in [PROJECT_PLAN.md](PROJECT_PLAN.md); field schemas, quality rules, and expected values are defined in [DATA_CONTRACT.md](DATA_CONTRACT.md).

The included student names and academic values are synthetic training data. Do not place production credentials in configuration files; use the `MONGODB_URI` environment variable when connecting to an authenticated MongoDB deployment.

## Architecture

The project is a Python package structure — no stage lives inside `main.py`:

```text
student_data_pipeline/
├── app/
│   ├── sources/        # CSVSource, APISource, DatabaseSource, MongoDBSource, WebScrapingSource
│   ├── transformation/ # cleaner.py, transformer.py, integration.py
│   ├── validation/     # quality.py (source and final validation rules)
│   ├── output/         # csv_writer.py
│   └── utils/          # config_loader, logger, metrics, incremental, lineage
├── data/
│   ├── raw/            # canonical students.csv
│   ├── processed/      # final_dataset.csv (generated)
│   ├── rejected/       # rejected_records.csv (generated)
│   └── state/          # pipeline_state.json (incremental state, generated)
├── database/           # schema.sql, seed.sql, students.db
├── logs/               # pipeline.log (generated)
├── mock_api/           # local REST API serving the canonical seed data
├── tests/              # 294 tests
├── main.py             # orchestration only
├── web_scraping_pipeline.py # independent HTML-table pipeline
├── config.json         # runtime configuration
└── requirements.txt    # pandas, requests, pytest
```

`main.py` composes reusable modules only — extraction, source validation, cleaning, integration, transformation, lineage, final validation, incremental processing, metrics, logging, and output writing. `sources.database.backend` selects SQLite or MongoDB for the same database-source role. All configuration is loaded at runtime from `config.json` through `app/utils/config_loader.py`.

The scraper is an independent pipeline. It detects JSON responses or extracts one configured HTML table, flattens nested JSON fields with dot-separated names, applies the shared cleaner and transformer, checks configured required columns, and writes a separate CSV. It is configured for the JSONPlaceholder `/users` endpoint, which returns 10 sample users. For websites that render tables only with JavaScript, a site-specific browser-based extractor may still be needed.

## Data Sources

The three logical student sources share the `student_id` key. MongoDB is an alternative backend for the database source, not a fourth student source.

| Source | Location | Fields | Records |
| --- | --- | --- | --- |
| CSV | `data/raw/students.csv` | `student_id`, `student_name`, `age`, `major`, `city` | 14 |
| REST API | `http://localhost:8000/students` (served by `mock_api/server.py`) | `student_id`, `gpa`, `attendance`, `status` | 13 |
| SQLite | `database/students.db` (`courses` ⟕ `enrollments`) | `student_id`, `course_name`, `credit_hours`, `semester`, `score` | 12 joined |
| MongoDB alternative | Configured collection in `sources.mongodb` | `student_id`, `course_name`, `credit_hours`, `semester`, `score` | one document per joined enrollment |

- The CSV intentionally contains a blank ID, an extra exact duplicate, an out-of-range age, a missing major, and extra/inconsistent whitespace.
- The API source sends a real HTTP request, receives and parses JSON, and explicitly handles connection errors, timeouts, HTTP errors, invalid JSON, and empty responses. It never reads the seed file (`mock_api/students_academic.json`) directly.
- The SQLite source runs the integrated read-only JOIN query defined in `DATA_CONTRACT.md` and always closes the connection.
- MongoDB can replace SQLite by setting `sources.database.backend` to `mongodb`. Each collection document must already contain the five flattened enrollment fields listed above; `_id` is excluded from extraction.

## Separate Web Scraping Pipeline

The scraper is not part of `main.py` and does not merge with CSV, API, SQLite, or MongoDB data. It is configured for `https://jsonplaceholder.typicode.com/users`. JSON objects are flattened into columns such as `address.city` and `company.name`. Configure `scraping.url`, `format`, `column_mapping`, `required_columns`, and `output` in `config.json`, then run:

```bash
python web_scraping_pipeline.py
```

`column_mapping` maps the source column names to desired output names. `required_columns` is a list checked before and after transformation. The output defaults to `data/scraped/web_data.csv` and its log to `logs/web_scraping_pipeline.log`.

## ETL Pipeline

`main.py` executes the stages in the official order:

1. **Extract** — `load_data()` (CSV), `extract_api_data()` (HTTP), and either `extract_database()` (SQLite JOIN) or `extract_mongodb()` (MongoDB documents), each returning a raw `DataFrame`.
2. **Validate** — source validation enforces the quality rules per record; failures (missing ID, out-of-range values, IDs incompatible with the canonical CSV IDs) are collected for the rejected output.
3. **Clean** — exact duplicates removed, leading/trailing whitespace stripped, multiple internal spaces collapsed, text case normalized.
4. **Integrate** — the three cleaned sources are merged on `student_id`; a student must be present in all three contributing sources, giving one row per student.
5. **Transform** — missing GPA/attendance imputed with medians computed from the complete raw API source (3.0 and 85), types normalized, and derived columns `performance_level` and `attendance_status` added from the rule tables in `DATA_CONTRACT.md`.
6. **Final Validation** — the same quality rules applied to the transformed dataset; anything still invalid is split off.
7. **Load** — valid records to `data/processed/final_dataset.csv`, rejected records with their reasons to `data/rejected/rejected_records.csv`.

## Data Quality

Validation rules (checked at source validation and again at final validation):

| Rule | Constraint |
| --- | --- |
| `student_id` | not null; unique after exact-duplicate removal |
| `age` | 16 ≤ age ≤ 80 |
| `gpa` | 0 ≤ gpa ≤ 4 |
| `attendance` | 0 ≤ attendance ≤ 100 |
| `score` | 0 ≤ score ≤ 100 |
| cross-source IDs | API/Database IDs must be compatible with the canonical CSV IDs |

Recoverable problems are repaired before the final split; unrecoverable problems are rejected with an explicit reason.

**Rejected records on the canonical dataset (6):**

| Student ID | Rejection reason |
| --- | --- |
| `1005` | Invalid Age (`15`) |
| `1003` | Invalid Attendance (`105`) |
| `1004` | Invalid GPA (`4.5`) |
| `1010` | Invalid Score (`105`) |
| `1099` | Incompatible student_id |
| *(blank)* | Missing student_id |

## Reference Results (Canonical Run)

These are the documented expected outcomes of running the pipeline on the canonical dataset — they are reference values verified by tests, not hard-coded values in the pipeline code.

| Metric | Value |
| --- | --- |
| CSV records | 14 |
| API records | 13 |
| Database records (joined) | 12 |
| Duplicate records (extra copies removed) | 1 |
| Missing values (raw, before recovery) | 4 |
| Integrated / final valid records | 8 |
| Rejected records | 6 |

Imputation reference values, computed from the full raw API source before any rejection:

- Valid GPA median = **3.0** → student `1002` GPA becomes **3.0**.
- Valid attendance median = **85** → student `1011` attendance becomes **85**.

Final valid students: `1001, 1002, 1006, 1007, 1008, 1009, 1011, 1012`.

## Installation

Requires Python 3.12+.

```bash
pip install -r requirements.txt
```

Dependencies: `pandas`, `requests`, `pymongo`, and `pytest` (plus the Python standard library, including `sqlite3` and `html.parser`).

## Running

1. **Start the mock REST API** (serves `GET /students` on port 8000):

   ```bash
   python mock_api/server.py
   ```

2. **Run the pipeline** in a second terminal:

   ```bash
   python main.py
   ```

   The pipeline reads `config.json` by default and writes `data/processed/final_dataset.csv`, `data/rejected/rejected_records.csv`, `data/state/pipeline_state.json`, and `logs/pipeline.log`.

3. **Use MongoDB instead of SQLite (optional):** provide the database and collection under `sources.mongodb`, set `MONGODB_URI` in the process environment (or use the local default URI), then set `sources.database.backend` to `mongodb`. The documents must use the flattened five-field schema in `DATA_CONTRACT.md`. The final pipeline stages and lineage remain unchanged.

4. **Run the independent scraper (optional):** set the website URL and table settings under `scraping`, then run `python web_scraping_pipeline.py`. It writes only to the configured scraping output.

5. **Run the tests**:

   ```bash
   python -m pytest -q
   ```

   The test suite (294 tests) spins up its own mock API on a free port and uses local HTML/JSON fixtures and mocked MongoDB clients, so it does not need external services.

## Output

| File | Contents |
| --- | --- |
| `data/processed/final_dataset.csv` | 8 valid records, 15 columns: `student_id`, `student_name`, `age`, `major`, `city`, `gpa`, `attendance`, `status`, `course_name`, `credit_hours`, `semester`, `score`, `performance_level`, `attendance_status`, `source` |
| `data/rejected/rejected_records.csv` | 6 rejected records with their `error_reason` values |
| `logs/pipeline.log` | INFO log for every stage plus the pipeline metrics summary |
| `data/state/pipeline_state.json` | incremental processing state from the last run |

## Configuration

`config.json` defines the source paths, API endpoint, database backend, MongoDB connection settings, separate scraping settings, output/log paths, and incremental settings. The student pipeline loads it at runtime; an alternate config can be passed with `main(config_path=...)`. The standalone scraper reads the same config and uses its `scraping` section.

## Incremental Processing

When `incremental.enabled` is `true`, each run fingerprints the integrated data against the saved state in `data/state/pipeline_state.json`. New or changed students are fully reprocessed; unchanged students are reused from the previous final output. A change in the raw-API imputation medians is part of the fingerprint, so affected rows are reprocessed instead of reusing stale values. If the previous final output is missing or unusable, the run falls back to full processing, and a failed state save rolls both the output and the state back to their previous versions.

## Data Lineage

The final `source` column records where each row came from. Records built from all three sources carry the value `CSV|API|DATABASE`, as defined in `DATA_CONTRACT.md`.

## Pipeline Metrics

Every run logs a summary with total records per source, integrated, valid, rejected, duplicate, and missing-value counts, plus the measured processing time, for example:

```text
---
## PIPELINE EXECUTION SUMMARY

CSV Records : 14
API Records : 13
Database Records : 12
Integrated Records : 8
Valid Records : 8
Rejected Records : 6
Duplicate Records : 1
Missing Values : 4
Processing Time : 2.20 seconds
-----------------------------------
```

## Reusable Source Architecture

Sources implement one contract: `BaseSource` (abstract class in `app/sources/base_source.py`) with a single method `extract() -> pd.DataFrame`. `CSVSource`, `APISource`, `DatabaseSource`, `MongoDBSource`, and `WebScrapingSource` follow it. SQLite and MongoDB expose the same database-source schema; the scraper is invoked only by its separate runner.

## Testing

The suite has 294 tests covering the assignment's required checks and beyond:

- CSV loading, API extraction over real HTTP requests, SQLite extraction, MongoDB source behavior, and HTML-table/JSON scraping (including relevant error paths).
- Duplicate removal, missing-value handling and imputation, invalid-record rejection with reasons, source integration, and `final_dataset.csv` creation.
- End-to-end tests assert the expected 8 valid / 6 rejected result and confirm the MongoDB backend selection uses the same database stage. Scraper tests use a local HTML fixture and verify separate output. Other tests cover configuration, logging, metrics, incremental processing, lineage, cleaning, transformation, and output writing.

## Assignment Questions

Answers to the final student questions, based on this project.

### 1. Why do we need a data pipeline when dealing with multiple sources?

لأن الكيان الواحد في الواقع عادةً ما يكون موزعًا على أكثر من نظام. في هذا المشروع، بيانات هوية الطالب موجودة في ملف CSV، ومعدله (GPA) ونسبة حضوره خلف REST API، ومساراته الدراسية في قاعدة بيانات SQLite — بصيغ مختلفة وبمشاكل جودة مختلفة، ولا يمكن الإجابة على سؤال مثل «ما المواد التي يدرسها الطلاب المعرضون للخطر؟» دون دمج هذه المصادر. يقوم الـ Data Pipeline بأتمتة الاستخراج وفحوصات الجودة والدمج على المفتاح `student_id` في خطوة واحدة قابلة للتكرار، بحيث تنتج كل عملية تشغيل مجموعة بيانات واحدة موثوقة بدلًا من دمج يدوي هش يعتمد على النسخ واللصق.

### 2. What is the difference between raw data and processed data?

البيانات الخام هي ما تقدّمه المصادر تمامًا مع مشاكلها: ملف CSV لدينا يحتوي على `student_id` فارغ، ونسخة مكررة إضافية للطالب `1007`، وعمر `15`، وأسماء مثل `" Ahmed Ali "` بمسافات زائدة؛ بينما يحتوي الـ API على GPA بقيمة `null`، وحضور `attendance` بقيمة `105`، ومعرّف غير متوافق `1099`. أما البيانات المعالجة فهي ما يخرج من الـ pipeline: الملف `final_dataset.csv` يحتوي 8 صفوف، صف واحد لكل طالب، بنصوص منظّفة وقيم معوَّضة وأعمدة مشتقة وعمود `source` — جاهزة للتحميل إلى التحليل أو النموذج دون أي إصلاح إضافي.

### 3. What is the difference between Extract, Transform, and Load?

الـ Extract يقرأ البيانات من المصادر دون تغييرها: الدالة `load_data()` تقرأ ملف CSV، والدالة `extract_api_data()` تنفّذ طلب HTTP، والدالة `extract_database()` تنفّذ استعلام الـ SQL JOIN. والـ Transform يحوّل السجلات المستخرجة إلى شكلها التحليلي: التنظيف، وتعويض القيم المفقودة، وتوحيد الأنواع، والأعمدة المشتقة مثل `performance_level`. أما الـ Load فيكتب النتيجة إلى وجهتها: الدالة `write_csv()` تحفظ السجلات الصالحة في `final_dataset.csv` والسجلات الفاشلة في `rejected_records.csv`. في هذا المشروع تغلّف الـ Validation مراحل التحويل وفق الترتيب الرسمي: Validate → Clean → Integrate → Transform → Final Validation → Load.

### 4. What problems did you face while integrating the data?

كان لكل مصدر شكل مختلف ومشاكل مختلفة لنفس الطالب: احتوى الـ API على معرّف (`1099`) غير موجود ضمن معرّفات CSV المرجعية، فكان لا بد من رفضه بوصفه غير متوافق؛ والطالب `1006` كان بلا تخصص (`major`)، والـ API كان بلا GPA للطالب `1002` وبلا `attendance` للطالب `1011`، وإلا لانتج الدمج قيم null دون سياسة تعويض واضحة؛ كما أن المعرّف الفارغ في CSV جعل pandas يتعامل مع عمود المعرّفات بالكامل كنوع float، ولذلك يعيد الـ snapshot النهائي توحيد المعرّفات إلى أعداد صحيحة. وكان أدق هذه المشاكل أن وسائط التعويض (medians) يجب أن تُحسب من مصدر الـ API الخام الكامل — فقد كان حسابها من المجموعة الفرعية بعد الـ validation يعطي قيمًا خاطئة (2.9/80 بدلًا من 3.0/85).

### 5. How did you handle missing values?

باستراتيجية صريحة واحدة لكل حقل، موثقة في `DATA_CONTRACT.md`: الـ `major` المفقود غياب تصنيفي طبيعي ويصبح `Unknown`؛ أما الـ GPA والـ `attendance` المفقودان فيُعوَّضان بوسيط (median) القيم الصالحة من مصدر الـ API الخام الكامل (3.0 و85) — واخترنا الوسيط لأنه مقاوم للقيم الشاذة المزروعة (GPA بقيمة 4.5 وattendance بقيمة 105) التي كان المتوسط الحسابي سيمتصها. أما الـ `student_id` المفقود فلا يُعوَّض أبدًا — فالصف بلا مفتاح يمكن الاعتماد عليه ولا يمكن الوثوق به، لذلك يُرفض بسبب `Missing student_id`. ولا يجري أي تعويض بصمت: يسجّل الـ transformer عدد القيم التي عبّأها.

### 6. How did you handle duplicate records?

يميّز الـ pipeline بين التكرار المطابق تمامًا والتكرار المتضارب. الصف الإضافي المطابق تمامًا لنفس `student_id` (وهو موجود في ملف CSV لدينا كتكرار للطالب `1007`) مشكلة قابلة للإصلاح: تزيله الدالة `clean_data` وتبقى نسخة واحدة، ويسجّل عدّاد التكرارات القيمة 1 للبيانات المرجعية. أما تكرار المعرّف ببيانات *مختلفة* فيُعامَل كمشكلة غير قابلة للإصلاح — يُرفض بدلًا من حله بصمت، لأن الـ pipeline لا يستطيع معرفة أي النسختين صحيحة. وتتم إزالة التكرارات عند مستوى التفصيل المطلوب في المهمة: صف واحد لكل `student_id`.

### 7. How did you handle invalid records?

لا تُحذف السجلات غير الصالحة بصمت أبدًا. كل سجل يمرّ عبر الـ source validation ثم الـ final validation وفق قواعد الجودة؛ وأي سجل يفشل يُكتب في `data/rejected/rejected_records.csv` مع `error_reason` صريح — مثل `Invalid Age` للطالب `1005`، و`Invalid GPA` للطالب `1004`، و`Incompatible student_id` للطالب `1099`، و`Missing student_id` للصف ذي المعرّف الفارغ. أما المشاكل القابلة للإصلاح (major مفقود، GPA/attendance مفقود، تكرار مطابق، مسافات زائدة) فيُصلَح قبل التقسيم النهائي، لذلك يحتوي ملف المرفوضات على السجلات الست غير القابلة للإصلاح بالضبط، ويظهر عدد المرفوضات في مقاييس كل تشغيل.

### 8. Why should the extraction layer be separated from the transformation layer?

لأن كلًا منهما يتغيّر لأسباب مختلفة ويجب أن يبقى قابلاً للاختبار وإعادة الاستخدام بشكل مستقل. في هذا المشروع كل وحدة من وحدات المصادر تقوم بالاستخراج فقط — بل إن قواعد الملكية تمنع وجود أي منطق تنظيف داخل وحدات المصادر — بينما يقع التنظيف والتعويض والأعمدة المشتقة في طبقة الـ transformation. هذا الفصل هو ما سمح للمصادر الثلاثة بتطبيق عقد واحد (`BaseSource.extract()`)، وبتغيّر سياق الـ transformation (وسائط الـ API الخام) دون تعديل أي ملف مصدر، و باختبار معالجة أخطاء الاستخراج (timeouts، JSON غير صالح، قواعد بيانات مقفلة) دون أي منطق تحويل. أما `main.py` فيركّب المراحل معًا، فيمكن إعادة ترتيبها من مكان واحد.

### 9. Why is data validation an essential part of data engineering?

لأن المستهلكين في المصب يفترضون أن البيانات موثوقة، والـ Data Validation هو ما يجعل هذا الافتراض حقيقةً بدلًا من كونه افتراضًا فقط. تحتوي البيانات المرجعية عمدًا على عمر `15` وGPA بقيمة `4.5` وattendance بقيمة `105` وscore بقيمة `105` — لا شيء منها كان سيسبب انهيار pipeline ساذج، لكنها كلها كانت ستُفسد بصمت أي متوسط أو نموذج أو تقرير يُبنى عليها. يحوّل الـ Data Validation هذا التلف الصامت إلى رفض صريح مسبَّب، ويحمي مفتاح الدمج المشترك `student_id` (المعرّفات المفقودة أو غير المتوافقة)، ويجعل الجودة قابلة للقياس: يبلّغ الـ pipeline في كل تشغيل عن عدد السجلات الصالحة مقابل المرفوضة بدلًا من الأمل في صحة الناتج.

### 10. How can the pipeline be developed to run periodically and automatically?

البنية جاهزة لذلك أصلًا: `main(config_path=...)` نقطة دخول واحدة، وكل المسارات تأتي من ملف الإعدادات، والتنفيذ idempotent (يعطي النتيجة نفسها عند تكراره). الخطوة المتبقية تشغيلية: جدولة `python main.py` عبر cron أو GitHub Actions أو Windows Task Scheduler، ومراقبة `logs/pipeline.log` ورمز الخروج لاكتشاف الإخفاقات. والمعالجة التزايدية (Incremental Processing) هي ما تجعل التشغيل المتكرر عمليًا — فالحالة المحفوظة تعني أن كل تشغيل مجدول يعيد معالجة الطلاب الجدد أو المتغيّرين فقط بدل مجموعة البيانات كاملة. أما النسخة الإنتاجية فستضيف تنبيهات عند الإخفاق ولقطات مخرجات موقّتة زمنيًا.

### 11. How can the pipeline handle millions of records?

التنفيذ الحالي بسيط عمدًا — pandas DataFrames في الذاكرة — وهو مناسب لمجموعة البيانات هذه لكنه لن يتوسّع كما هو. مسار التوسّع يحافظ على المراحل نفسها ويغيّر المحرّكات: الاستخراج على دفعات (chunks) أو دفع عملية الـ JOIN الثقيلة إلى قاعدة البيانات نفسها بلغة SQL؛ نقل البيانات إلى تخزين عمودي/مقسّم مثل Parquet؛ استبدال pandas داخل الذاكرة بمحرك out-of-core أو موزّع (DuckDB أو Polars أو Spark) ينفّذ خطوتي الـ validation والتنظيف على هيئة stream؛ والاعتماد على المعالجة التزايدية المنفَّذة فعلًا بحيث يلمس كل تشغيل السجلات المتغيّرة فقط. أما قواعد الـ validation نفسها فتبقى كما هي — تتحوّل إلى predicates تُنفَّذ داخل المحرك القابل للتوسّع.

### 12. What is the difference between batch processing and streaming processing?

الـ Batch Processing ينفّذ على مجموعة بيانات محدودة ومكتملة وينتج ناتجه مرة واحدة لكل تشغيل — وهذا بالضبط ما يفعله هذا الـ pipeline: كل تنفيذ يقرأ المصادر كاملة، ويقارنها بالحالة المحفوظة، وينتج snapshot جديدًا من `final_dataset.csv`. أما الـ Streaming Processing فيستهلك أحداثًا مستمرة غير محدودة ويحدّث النتائج باستمرار وبزمن استجابة منخفض — لا يوجد فيه مفهوم «انتهى التشغيل»، ويجب تطبيق قواعد الجودة نفسها سجلًا بسجل مع وصول الأحداث. الـ Batch هو النموذج الأنسب عندما تكون الصحة والبساطة أهم من الطزاجة (التقارير، ومجموعات بيانات التدريب مثل مجموعتنا)؛ بينما يناسب الـ Streaming لوحات المتابعة الحيّة والتنبيهات والميزات الفورية.
