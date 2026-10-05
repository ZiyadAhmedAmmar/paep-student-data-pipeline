# Project Overview

PAEP Student Data Pipeline is a group training project for the PAEP Data Engineering course. The team will build a multi-source ETL and data integration pipeline for student data while practicing source ownership, collaboration through GitHub, code review, and automated testing.

# Project Goal

The pipeline will collect student data from:

- CSV
- REST API
- SQLite (default database backend) or MongoDB (alternative backend with the same enrollment-record contract)
- A separately run HTML-table scraper whose records are not merged into the student dataset

The official pipeline order is:

Extract → Source Validation → Clean → Integrate → Transform → Final Validation → Load

The completed pipeline will produce:

- Valid records → `data/processed/final_dataset.csv`
- Invalid records → `data/rejected/rejected_records.csv`
- Pipeline logs: `logs/pipeline.log`

# Team Members and Responsibilities

## لؤي

### Ownership

- `app/utils/logger.py`
- `app/output/csv_writer.py`
- `app/transformation/integration.py`
- `main.py`
- `config.json` and `app/utils/config_loader.py`
- Integration, end-to-end, and output tests when created

### Responsibilities

- Repository and GitHub Project coordination
- Logging
- Output writing
- Data integration
- End-to-end pipeline orchestration
- Final README coordination
- Integration/pipeline testing
- Advanced requirement: Pipeline Configuration through `config.json` and `app/utils/config_loader.py`

## عمران

### Ownership

- `app/sources/csv_source.py`
- `app/transformation/cleaner.py`
- `app/utils/metrics.py`
- CSV and cleaning tests

### Responsibilities

- CSV extraction
- CSV input handling
- Data cleaning
- Duplicate handling
- Text normalization
- Extra spaces/case normalization
- Advanced requirement: Pipeline Metrics through `app/utils/metrics.py`

## زياد

### Ownership

- `app/sources/api_source.py`
- `app/transformation/transformer.py`
- Mock REST API server implementation in `mock_api/` (canonical seed data is governed by the Canonical Data Policy)
- `app/utils/incremental.py`
- API and transformation tests

### Responsibilities

- REST API extraction
- Build a real Mock REST API that serves the canonical seed data over HTTP
- API error handling
- Data transformation
- Data types
- Missing-value transformation strategy
- Derived columns
- Advanced requirement: Incremental Processing through `app/utils/incremental.py` and pipeline state

## العنسي

### Ownership

- `app/sources/database_source.py`
- `app/validation/quality.py`
- SQLite and validation tests

### Responsibilities

- SQLite extraction from the canonical database
- Source validation
- Final validation
- Quality rules
- Rejected-record classification and error reasons
- Advanced requirement: Data Lineage, collaborating with لؤي on integration and final dataset construction so the final `source` field records source lineage

# Canonical Data Policy

لؤي prepares the official project data as a canonical baseline before the team begins implementation. Team members must use that baseline and must not independently create alternative project datasets.

The official source files are:

- `data/raw/students.csv`
- `mock_api/students_academic.json`
- `database/students.db`
- `database/schema.sql`
- `database/seed.sql`

[DATA_CONTRACT.md](DATA_CONTRACT.md) is the official reference for schemas, rules, and expected values. Any change to canonical data or `DATA_CONTRACT.md` must go through a dedicated, agreed-upon Issue/PR. Members must not change the data to make their own code pass.

# Data Contract Reference

`PROJECT_PLAN.md` defines ownership, workflow, implementation phases, and delivery requirements. [DATA_CONTRACT.md](DATA_CONTRACT.md), supplied with the canonical baseline, defines the data behavior that implementations and tests must follow:

- Source schemas
- The shared `student_id` key
- Validation ranges
- Missing-value policies
- Intentional bad records
- Expected valid IDs
- Expected rejected cases
- Derived columns
- Final dataset columns
- Lineage format

Keep these data definitions in `DATA_CONTRACT.md` rather than duplicating them in this plan. Each source module must return structured data that can be integrated using the shared `student_id` key.

# REST API Rule

`mock_api/students_academic.json` is seed data only. The final pipeline must not read that JSON file directly. زياد will build a real Mock REST API that serves the seed data over HTTP.

`app/sources/api_source.py` must send an HTTP request, receive JSON, validate the response, and convert it into structured data. It must explicitly handle connection errors, timeouts, HTTP errors, invalid JSON, and empty responses.

# Source Architecture

`app/sources/base_source.py` represents the shared source contract/interface. CSV, REST API, SQLite, MongoDB, and web scraping sources implement the same `extract() -> DataFrame` contract. MongoDB is an alternative backend for the existing database-source role and must return the same flattened enrollment columns as the SQLite JOIN. The web scraper runs through `web_scraping_pipeline.py` and must keep its output separate from student integration.

The goal is to allow future sources to be added without rewriting the whole pipeline. Keep the interface simple and avoid unnecessary abstractions or extra complexity. MongoDB support is optional at runtime; install the declared `pymongo` dependency to use it. The scraper targets a configured static HTML table and may require a site-specific parser if the chosen site is JavaScript-rendered or has no HTML table.

# Advanced Requirements

The project targets all advanced requirements in the assignment:

| Requirement | Implementation and expected behavior | Responsibility |
| --- | --- | --- |
| Pipeline Configuration | `config.json` + `app/utils/config_loader.py`; the pipeline loads and uses configuration at runtime. | لؤي |
| Incremental Processing | `app/utils/incremental.py` + pipeline state; subsequent runs identify and process new or changed data according to that state. | زياد |
| Data Lineage | The final `source` field preserves contributing source lineage in the format defined by `DATA_CONTRACT.md`. | العنسي, collaborating with لؤي on integration/output |
| Pipeline Metrics | `app/utils/metrics.py`; report total, valid, rejected, duplicate, and missing counts, plus measured processing time. | عمران |
| Reusable Architecture | `app/sources/base_source.py` and a consistent extraction contract used by CSV, REST API, SQLite, MongoDB, and the independent web scraper. | All source owners, coordinated with لؤي for pipeline integration |
| MongoDB Backend | `app/sources/mongodb_source.py`; an optional MongoDB backend returns the existing database source schema and follows the same validation, integration, lineage, and output stages. | Database source owner and pipeline coordinator |
| Independent Web Scraping | `app/sources/web_scraping_source.py` + `web_scraping_pipeline.py`; fetches a configured HTML table, applies shared cleaning/transformation, validates configured required columns, and writes a separate CSV without joining the student pipeline. | Scraping source owner |

The presence of files alone does not complete these requirements. Every feature must work in the integrated pipeline and be verified before delivery.

# Development Phases

| Phase | Scope |
| --- | --- |
| Phase 0 | Repository/Foundation |
| Phase 1 | Canonical Data & Data Contract |
| Phase 2 | Source Extraction: CSV / REST API / SQLite / MongoDB backend / independent web scraper |
| Phase 3 | Cleaning / Transformation / Validation / Integration |
| Phase 4 | Pipeline orchestration + output + logging |
| Phase 5 | Advanced requirements: Configuration, Incremental Processing, Lineage, Metrics, reusable architecture, MongoDB backend, and independent scraper verification |
| Phase 6 | End-to-end tests + README + final verification |

These are development phases; runtime execution follows the official pipeline order above.

# Ownership Boundaries

- Each team member works primarily on the files they own.
- A member should not modify another member's owned file within their issue unless there is a clear need and agreement.
- Cleaning logic does not belong in source modules.
- Validation logic does not belong in `integration.py`.
- CSV writing does not belong in `quality.py`.
- `main.py` is responsible for orchestration, not the implementation details of each stage.
- Keep every module focused on a single responsibility.

# Branch Strategy

`main` is the stable branch. Direct development on `main` is not allowed after the workflow setup is complete.

Every issue must use a separate branch created from the latest `main`. Branch names follow these patterns:

- `feature/<name>`
- `fix/<name>`
- `test/<name>`
- `docs/<name>`
- `chore/<name>`

# GitHub Workflow

Issue → Assign owner → Todo → Update local `main` → Create branch → In Progress → Implement issue scope → Tests → Commit → Push → Pull Request → In Review → Teammate review → Changes if requested → Approval → Merge → Delete branch → Done

# Pull Request Rules

Every pull request must:

- Link to a clear issue.
- Stay limited to the issue scope.
- Contain no unrelated changes.
- Explain the summary.
- Explain the testing performed.
- Request the designated reviewer.
- Remain unmerged until reviewed.
- Be merged by someone other than its author.
- Delete its branch after merging when safe.

# Reviewer Rotation

- لؤي PR → عمران reviews, approves, and merges.
- عمران PR → زياد reviews, approves, and merges.
- زياد PR → العنسي reviews, approves, and merges.
- العنسي PR → لؤي reviews, approves, and merges.

If the primary reviewer is unavailable, a third team member may review and merge. A pull request author must never approve or merge their own work.

# Code Review Checklist

The reviewer verifies:

- Issue requirements fulfilled
- Scope respected
- No unrelated changes
- Ownership boundaries respected
- Readable code
- Sensible naming
- Expected error handling
- Appropriate tests
- Tests pass
- No secrets or machine-specific paths
- No unnecessary dependencies

# Commit Convention

Use Conventional Commits with these types:

- `feat:`
- `fix:`
- `test:`
- `docs:`
- `refactor:`
- `chore:`

Examples:

- `feat: add csv source extraction`
- `feat: add api student source`
- `feat: add sqlite extraction`
- `feat: add data cleaning rules`
- `feat: add data quality validation`
- `test: add csv source tests`
- `docs: document team workflow`
- `chore: configure project workflow`

# Testing Strategy

Each member is responsible for testing the part they own. Future tests should cover the core assignment requirements:

- CSV loading
- API extraction
- SQLite extraction
- Duplicate removal
- Missing-value handling
- Invalid-record rejection
- Source integration
- `final_dataset.csv` creation

These tests are part of later implementation work and are not included in the workflow setup.

# Error Handling

Expected errors must be handled explicitly. Avoid unnecessary catch-all exception handling that hides the original failure or makes diagnosis difficult.

The API source should later handle:

- Connection errors
- Timeouts
- HTTP errors
- Invalid JSON
- Empty responses

The CSV and SQLite sources must also handle the expected errors specific to their input and connection operations.

# Definition of Done

An issue becomes Done only when:

- Scope is complete.
- Required tests exist and pass.
- There are no unrelated changes.
- The branch is published.
- A pull request is open.
- Another team member has reviewed it.
- Review comments are resolved.
- The pull request is approved.
- The work is merged into `main`.
- The branch is deleted when safe.
- GitHub Project status is Done.

# GitHub Project Status Meaning

## Backlog

A planned task that is not ready for implementation.

## Todo

A task that is ready to start.

## In Progress

Active work has started on a branch.

## In Review

A pull request is open and under review.

## Done

The work has been approved and merged into `main`.

# Final Deliverables

The completed project will include:

- `final_dataset.csv`
- `rejected_records.csv`
- `pipeline.log`
- `README.md`
- Tests
- Source code
