---
name: camping-world-ppt-implementation
description: Implement the Camping World PPT Generator backend and optional frontend in phased milestones using FastAPI, MongoDB/GridFS, LangGraph, python-pptx, and deterministic validation/rendering. Use this skill when building or extending the template-to-presentation pipeline from prompt plus template profile.
---

# Camping World PPT Implementation

Use this skill when the user wants to build, continue, or audit the implementation plan for the PPT generator system.

## Outcomes

- Template upload and profiling pipeline is working.
- Prompt-to-PPT generation pipeline is working end to end.
- Deterministic validation and rendering preserve template styling.
- API supports status streaming and download.

## Non-Negotiable Rules

- Template is source of truth for layout/styling.
- Do not alter images/logos/decorative assets.
- Only replace chart data values; keep chart styling/type.
- Keep validation deterministic (no LLM in validator).
- Retry content population at most 2 times on validation failure.

## Recommended Build Order

1. Foundation
2. Template parser
3. Guidance extraction + template APIs
4. Content planner
5. Validator
6. Renderer + storage
7. LangGraph integration + generation APIs
8. Hardening + tests
9. Frontend (optional after backend is stable)

## Phase Workflow

For each phase:

1. Define files to add/update.
2. Implement minimal production path first.
3. Add tests for the phase.
4. Run tests and fix regressions.
5. Record phase status and blockers.

Do not start frontend work before backend end-to-end generation is stable.

## File-Level Targets

- `backend/app/config.py`: env settings and defaults.
- `backend/app/database.py`: Motor client, GridFS buckets, lifecycle hooks.
- `backend/app/api/routes/templates.py`: upload/list/detail template endpoints.
- `backend/app/api/routes/generate.py`: generate/status/download endpoints.
- `backend/app/schemas/template_profile.py`: template profile contracts.
- `backend/app/schemas/slide_plan.py`: planner output contracts.
- `backend/app/tools/template_parser.py`: structural extraction and theme parsing.
- `backend/app/tools/guidance_extractor.py`: slide classification and brand rules.
- `backend/app/tools/validator.py`: deterministic constraints.
- `backend/app/tools/renderer.py`: template-preserving PPT rendering.
- `backend/app/graph/state.py`: `PipelineState` typed state.
- `backend/app/graph/nodes.py`: graph nodes.
- `backend/app/graph/pipeline.py`: node wiring and conditional retries.
- `backend/app/services/template_service.py`: template pipeline orchestration.
- `backend/app/services/generation_service.py`: generation orchestration + streaming.

## Acceptance Gates

1. Parser gate: extracted placeholders/charts/images/theme match expected fixtures.
2. Guidance gate: guidance slides excluded, brand rules populated.
3. Planner gate: structured output valid against `SlidePlan`.
4. Validator gate: invalid plans rejected with actionable errors.
5. Renderer gate: output PPTX opens and keeps formatting.
6. E2E gate: upload -> generate -> stream progress -> download works.

## API Expectations

- `POST /api/templates/upload`
- `GET /api/templates`
- `GET /api/templates/{id}`
- `POST /api/generate`
- `GET /api/generate/{id}/status` (SSE)
- `GET /api/generate/{id}/download`

## LLM Usage Policy

- Use Sonnet-class model for guidance extraction/classification.
- Use Opus-class model for outline/content planning.
- Keep LLM calls limited to planning/classification nodes.
- Enforce strict structured outputs using schema-driven parsing.

## Validation Checklist (Run Before Marking Done)

- Text length respects placeholder `max_chars`.
- Required placeholders are populated.
- Chart series/category counts match template metadata.
- Pie chart totals and value constraints are valid.
- No duplicate layout variant use when disallowed.
- Slide count aligns with outline decision.

## Rendering Checklist

- Keep only selected slides; delete others in reverse index order.
- Preserve run-level formatting when replacing text.
- Apply chart `replace_data` only.
- Leave images and non-content decorative elements unchanged.
- Clean obvious placeholder boilerplate text.

## Definition of Done

- All acceptance gates passed.
- Failing and edge-case tests added.
- Logs include stage, IDs, duration, retries.
- Errors surfaced with clear user-facing messages.
- Output PPTX consistently opens in PowerPoint.

