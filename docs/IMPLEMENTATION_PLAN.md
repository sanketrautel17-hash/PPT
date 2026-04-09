# Camping World PPT Generator Implementation Plan

Date: 2026-04-07  
Reference: `bedb4493-90de-4bb7-b84a-d57f386a29d1.pdf`

## 1. Objective

Build an agentic system that takes:

- a profiled master PPTX template, and
- a natural language prompt

and outputs a presentation-ready PPTX while preserving original template design fidelity.

## 2. Core Principles

- Template is source of truth for layout, typography, theme, and visual structure.
- Images/logos/decorative assets are never modified.
- Chart styling is preserved; only data values are updated.
- LLM usage is limited to guidance extraction and content planning.
- Validation, rendering, and storage are deterministic Python steps.

## 3. Target Stack

- Backend: FastAPI
- Pipeline orchestration: LangGraph
- Database: MongoDB + GridFS
- DB driver: Motor (async)
- PPTX processing: python-pptx + lxml
- LLM integration: LangChain `init_chat_model()`
- Guidance model: Sonnet-class
- Content planning model: Opus-class
- Frontend (later): Next.js

## 4. System Architecture

1. Template upload and profiling pipeline
2. Generation pipeline (`template_id + prompt -> slide plan -> validated render`)
3. Storage and retrieval of template/generated binaries in GridFS
4. SSE-based generation status streaming

## 5. Implementation Phases

## Phase 0: Foundation (Week 1)

Deliverables:

- Project scaffolding for `backend/app/...`
- `config.py` with environment-driven settings
- `database.py` with Motor client and GridFS bucket setup
- Middleware, exception handling, structured logging
- `GET /health` route with DB ping

Exit Criteria:

- App starts successfully
- MongoDB connectivity verified
- Health endpoint returns success

## Phase 1: Template Parser (Week 1-2)

Deliverables:

- `tools/template_parser.py` that extracts:
- slide placeholders (type, idx, style, bounds, text)
- chart metadata (type, series/categories, sample values)
- image and table metadata
- theme colors/fonts from XML (`theme1.xml`)
- placeholder max-char estimates
- `schemas/template_profile.py` with typed profile contracts
- parser unit tests with fixture templates

Exit Criteria:

- Profile output is consistent and complete for sample templates

## Phase 2: Guidance Extraction + Template APIs (Week 2-3)

Deliverables:

- `tools/guidance_extractor.py`:
- classify slides into `guidance` vs `content_layout`
- extract brand/tone/formatting rules
- build usable slide pools (guidance excluded)
- `services/template_service.py` to orchestrate profiling
- API routes:
- `POST /api/templates/upload`
- `GET /api/templates`
- `GET /api/templates/{id}`
- profile persistence in MongoDB + template binary in GridFS

Exit Criteria:

- Uploaded templates are profiled and queryable
- Guidance slides are correctly excluded from generation pools

## Phase 3: Content Planner (Week 3-4)

Deliverables:

- Prompt files:
- `graph/prompts/planner_outline.txt`
- `graph/prompts/planner_populate.txt`
- `schemas/slide_plan.py` with strict structured output contracts
- LangGraph planner nodes:
- `plan_outline` (slide count, arc, selected layouts)
- `plan_content` (text/chart/table content)

Exit Criteria:

- Planner returns schema-valid `SlidePlan` for varied prompts

## Phase 4: Deterministic Validator (Week 4)

Deliverables:

- `tools/validator.py` checks:
- char limits per placeholder
- required field completeness
- chart/table structural compatibility
- duplicate layout variant constraints
- outline/plan slide count consistency
- retry feedback payload for planner correction (max 2 retries)

Exit Criteria:

- Invalid plans are consistently rejected with clear, actionable errors

## Phase 5: Renderer + Storage (Week 4-5)

Deliverables:

- `tools/renderer.py`:
- open original template
- keep selected slides only; delete others in reverse index order
- replace placeholder text preserving formatting
- replace chart data only (`replace_data`)
- preserve images/decorative elements untouched
- clean obvious placeholder boilerplate
- `tools/storage.py` for generated file upload/download via GridFS

Exit Criteria:

- Rendered PPTX opens correctly and preserves template fidelity

## Phase 6: LangGraph Integration + Generation APIs (Week 5-6)

Deliverables:

- `graph/state.py` typed `PipelineState`
- `graph/nodes.py`: load, outline, populate, validate, render, store
- `graph/pipeline.py` with conditional retry routing
- `services/generation_service.py` orchestration + streaming hooks
- API routes:
- `POST /api/generate`
- `GET /api/generate/{id}/status` (SSE)
- `GET /api/generate/{id}/download`

Exit Criteria:

- End-to-end flow works: upload/profile -> generate -> stream -> download

## Phase 7: Testing and Hardening (Week 6-7)

Deliverables:

- Integration tests for full lifecycle
- Retry-path tests (validation failure then recovery)
- Edge-case tests (long prompt, sparse prompt, malformed data)
- Limits and safeguards:
- upload size cap
- prompt length guardrails
- generation concurrency cap
- robust error mapping and structured stage logs

Exit Criteria:

- Stable E2E behavior under normal and edge conditions

## Phase 8: Frontend (Week 7-9, optional after backend stabilization)

Deliverables:

- Next.js app pages for:
- template upload + analysis status
- template gallery/list
- generation prompt form
- SSE progress display
- download and history views

Exit Criteria:

- Non-technical user can complete both journeys:
- Upload template + generate
- Select existing template + generate

## 6. API Contract Summary

- `POST /api/templates/upload` -> upload and start profiling
- `GET /api/templates` -> list templates and readiness
- `GET /api/templates/{id}` -> full profile details
- `POST /api/generate` -> start generation
- `GET /api/generate/{id}/status` -> SSE progress
- `GET /api/generate/{id}/download` -> final PPTX binary

## 7. Acceptance Gates

1. Parser Gate: extracted metadata matches expected fixtures.
2. Guidance Gate: guidance classification and brand rules are usable.
3. Planner Gate: structured slide plans are schema-valid.
4. Validator Gate: all invalid scenarios are caught deterministically.
5. Renderer Gate: generated PPTX preserves visual fidelity.
6. E2E Gate: complete API journey works reliably.

## 8. Risks and Mitigations

- Content overflow in placeholders:
- Deterministic validation + retry with explicit errors + optional controlled font reduction.
- Unusual template structures:
- parser fallback heuristics and explicit logging of unsupported elements.
- Chart mismatch:
- enforce strict chart schema before render.
- Guidance misclassification:
- combine LLM classification with fallback heuristics.
- Concurrent load spikes:
- queue and concurrency caps in generation service.

## 9. Definition of Done

- All acceptance gates pass.
- Unit and integration tests cover happy path and critical edge cases.
- Operational logging includes stage, duration, IDs, retries, and errors.
- Generated files are retrievable and open correctly in PowerPoint.

