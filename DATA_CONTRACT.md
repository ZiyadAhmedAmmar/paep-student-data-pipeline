# Purpose

This file is the official data reference for the PAEP Student Data Pipeline.
It defines the canonical datasets, schemas, and rules that all team members
must follow. These are the only reference datasets for this assignment. Keep
their intentional raw problems intact; the rules below describe the implemented
pipeline's behavior, not cleaning to perform on these baseline files.

# Canonical Sources

| Source | Canonical files | Role |
| --- | --- | --- |
| CSV | `data/raw/students.csv` | Raw student identity and demographic data |
| REST API seed | `mock_api/students_academic.json` | Seed/reference data served by the Mock REST API (`mock_api/server.py`) |
| SQLite | `database/students.db`, built from `database/schema.sql` and `database/seed.sql` | Default database backend: raw courses and enrollments |
| MongoDB (optional) | Configured `sources.mongodb` database and collection | Alternative database backend; flattened enrollment documents |
| Web scraper (separate) | Configured `scraping.url` and HTML `table_index` | Independent table extraction; never integrated into the student dataset |

The Mock REST API is implemented in `mock_api/server.py`. The pipeline's
`app/sources/api_source.py` extracts from that API over a real HTTP request; it
must not read the seed JSON directly. The configured endpoint is
`http://localhost:8000/students`.

# Shared Key

`student_id` is the shared key across sources. The canonical base IDs are the
nonblank CSV IDs, `1001` through `1012`, before rejecting invalid field values.

# Source Schemas

Fields are listed in source order:

| Source | Fields |
| --- | --- |
| CSV | `student_id`, `student_name`, `age`, `major`, `city` |
| API | `student_id`, `gpa`, `attendance`, `status` |
| SQLite integrated query | `student_id`, `course_name`, `credit_hours`, `semester`, `score` |
| MongoDB document | `student_id`, `course_name`, `credit_hours`, `semester`, `score` |

CSV contains textual fields with numeric representations for `student_id` and
`age`; missing values are empty fields. API data is a JSON array of objects with
integer IDs, numeric GPA and attendance (or JSON `null`), and text status.

SQLite tables:

| Table | Column | Definition |
| --- | --- | --- |
| `courses` | `course_id` | `INTEGER PRIMARY KEY` |
| `courses` | `course_name` | `TEXT NOT NULL` |
| `courses` | `credit_hours` | `INTEGER NOT NULL` |
| `enrollments` | `student_id` | `INTEGER NOT NULL` |
| `enrollments` | `course_id` | `INTEGER NOT NULL`, foreign key to `courses(course_id)` |
| `enrollments` | `semester` | `TEXT NOT NULL` |
| `enrollments` | `score` | `REAL` |

The integrated SQLite query is:

```sql
SELECT e.student_id, c.course_name, c.credit_hours, e.semester, e.score
FROM enrollments AS e
JOIN courses AS c ON c.course_id = e.course_id
ORDER BY e.student_id;
```

It returns 12 records for this baseline. The deliberately invalid score remains
in the raw database and is handled by the pipeline's validation.

## MongoDB Backend Contract

Set `sources.database.backend` to `mongodb` to use MongoDB instead of SQLite.
The configured collection must contain one flattened document per enrollment
with all five fields in the MongoDB schema above. The source excludes MongoDB's
`_id` field and returns columns in the same order as the SQLite JOIN. Documents
must preserve raw values so the existing source validation can classify invalid
scores and incompatible student IDs. The MongoDB backend does not join multiple
collections; prepare the flattened collection before running the pipeline.

## Separate Web Scraping Contract

`web_scraping_pipeline.py` supports JSON object/array responses and HTML tables.
JSON objects are flattened with dot-separated nested field names (for example,
`address.city`); `scraping.column_mapping` can rename source fields, and
`scraping.required_columns` defines the expected fields. The configured
JSONPlaceholder `/users` endpoint returns 10 sample user records. The scraper
runs shared cleaning and transformation, performs generic non-empty and
required-column checks, and writes to `scraping.output`. It is deliberately not
merged with the canonical student sources. JavaScript-rendered pages and
site-specific business validation need additional source-specific behavior.

# Final Dataset Granularity

The final dataset contains one row per `student_id` for this assignment.
The current SQLite seed has one enrollment per student to support that
granularity. The schema allows multiple course enrollments in the future:
`enrollments.student_id` is not a primary key or a unique column. Future changes
to enrollment granularity will require an explicit integration policy.

# Data Quality Rules

| Field | Rule |
| --- | --- |
| `student_id` | Not null; unique after exact duplicate removal at this assignment's granularity |
| `age` | `16 <= age <= 80` |
| `gpa` | `0 <= gpa <= 4` |
| `attendance` | `0 <= attendance <= 100` |
| `score` | `0 <= score <= 100` |

API and database student IDs must be compatible with the canonical CSV IDs.
An unrecoverable problem in any contributing source excludes that student from
the final valid dataset. Rejection counts refer to the offending raw records,
not every otherwise valid row for that student in other sources.

# Recoverable Data Problems

| Problem | Required handling |
| --- | --- |
| Exact duplicate | Remove the duplicate and retain one copy |
| Leading/trailing whitespace | Strip |
| Multiple internal spaces | Collapse to one space |
| Text case inconsistencies | Normalize consistently |
| Missing major | Use `Unknown` |
| Missing GPA | Impute using the median of valid GPA values in the API source |
| Missing attendance | Impute using the median of valid attendance values in the API source |

Calculate each median independently over the complete raw API source, excluding
null and out-of-range values for that field. Invalid/out-of-range values must
NOT participate in that field's median calculation. Compute these medians before
rejecting records for other fields, incompatible IDs, or cross-source problems.
Thus, an in-range field value still contributes even if its record has another
problem; this includes the in-range values for API student `1099`.

- Valid GPA values, sorted: `1.8, 2.3, 2.6, 2.7, 2.9, 3.0, 3.1, 3.2, 3.6, 3.8, 3.9`.
- Expected GPA median for this canonical dataset: **3.0**.
- Student `1002` GPA becomes `3.0` after imputation.
- Valid attendance values, sorted: `68, 72, 76, 80, 84, 85, 88, 90, 90, 95, 98`.
- Expected attendance median: **85**.
- Student `1011` attendance becomes `85` after imputation.

# Non-Recoverable Problems

Reject records with:

- Missing `student_id`.
- Age outside the allowed range.
- GPA outside the allowed range.
- Attendance outside the allowed range.
- Score outside the allowed range.
- Source `student_id` incompatible with canonical CSV IDs.
- Duplicate `student_id` with conflicting data instead of an exact duplicate.

# Intentional Invalid Records

| Source | Student ID | Intentional problem | Handling |
| --- | --- | --- | --- |
| CSV | `1005` | Age `15` | Reject |
| CSV | blank | Missing ID | Reject |
| CSV | `1007` | One extra exact duplicate | Recoverable; retain one copy |
| CSV | `1006` | Missing major | Recoverable; use `Unknown` |
| API | `1002` | Missing GPA | Recoverable; impute `3.0` |
| API | `1003` | Attendance `105` | Reject |
| API | `1004` | GPA `4.5` | Reject |
| API | `1011` | Missing attendance | Recoverable; impute `85` |
| API | `1099` | Incompatible student ID | Reject |
| DATABASE | `1010` | Score `105` | Reject |

The raw sources also intentionally preserve extra whitespace and inconsistent
text case, including student `1006`'s name and API status.

# Derived Columns

For valid, recovered numeric values, evaluate the following performance rules
from top to bottom, taking the first match:

| `gpa` condition | `performance_level` |
| --- | --- |
| `gpa >= 3.5` | `Excellent` |
| `gpa >= 3.0` | `Very Good` |
| `gpa >= 2.5` | `Good` |
| `gpa >= 2.0` | `Acceptable` |
| `gpa < 2.0` | `At Risk` |

| `attendance` condition | `attendance_status` |
| --- | --- |
| `attendance >= 75` | `Good` |
| `attendance < 75` | `Low` |

# Final Dataset Columns

The required column order is:

1. `student_id`
2. `student_name`
3. `age`
4. `major`
5. `city`
6. `gpa`
7. `attendance`
8. `status`
9. `course_name`
10. `credit_hours`
11. `semester`
12. `score`
13. `performance_level`
14. `attendance_status`
15. `source`

# Data Lineage

For records built from all three sources, the final `source` value is exactly
`CSV|API|DATABASE`. Lineage is applied during final dataset construction: the
`app/utils/lineage.py` module adds the `source` column to the integrated data.

# Expected Final Valid Students

`1001, 1002, 1006, 1007, 1008, 1009, 1011, 1012`

Expected final valid record count: **8**.

# Expected Rejected Records

| Student ID | Expected reason |
| --- | --- |
| `1005` | `Invalid Age` |
| `1003` | `Invalid Attendance` |
| `1004` | `Invalid GPA` |
| `1010` | `Invalid Score` |
| `1099` | `Incompatible student_id` |
| blank | `Missing student_id` |

Expected rejected count: **6**. The exact duplicate for `1007` is not a rejected
record; it is cleaned and counted in duplicate metrics.

# Expected Raw Metrics

| Metric | Expected value |
| --- | --- |
| CSV records (excluding header) | 14 |
| API records | 13 |
| Database courses | 4 |
| Database enrollment records | 12 |
| SQLite joined records | 12 |
| Duplicate records (extra copies) | 1 |
| Missing values across canonical raw sources | 4 |
| Expected final valid records | 8 |
| Expected rejected records | 6 |

The four missing values are the blank CSV student ID, CSV student `1006`'s
major, API student `1002`'s GPA, and API student `1011`'s attendance. Measure them
before any recovery. Processing Time has no fixed expected value; it must be
measured for each pipeline run.
