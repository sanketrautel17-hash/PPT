# PPT Project — Slide-by-Slide Implementation Plan

**Date:** April 9, 2026  
**Version:** 1.0 (Project-Specific Execution Plan)

---

## Table of Contents

1. [Objective](#1-objective)
2. [Current Baseline (As-Is)](#2-current-baseline-as-is)
3. [Target Architecture (To-Be)](#3-target-architecture-to-be)
4. [Slide-by-Slide Generation Design](#4-slide-by-slide-generation-design)
5. [Node-by-Node Plan](#5-node-by-node-plan)
6. [Schema and Contract Updates](#6-schema-and-contract-updates)
7. [Frontend Alignment Plan](#7-frontend-alignment-plan)
8. [Renderer and Validation Plan](#8-renderer-and-validation-plan)
9. [Phase-by-Phase Implementation Roadmap](#9-phase-by-phase-implementation-roadmap)
10. [Risks and Mitigations](#10-risks-and-mitigations)
11. [Definition of Done](#11-definition-of-done)

---

## 1. Objective

Build a reliable, production-ready **slide-by-slide PPT generation pipeline** for this repository by evolving the current monolithic content planning flow into a parallel per-slide workflow while preserving template fidelity.

Primary goals:
- Generate one slide at a time with targeted retries
- Keep template styling intact (fonts, spacing, chart styling, images)
- Align frontend and backend API contracts end-to-end
- Maintain deterministic validation and robust progress streaming

---

## 2. Current Baseline (As-Is)

The project already has:
- FastAPI backend with routes for health, template upload/list/get, generation start/status/download
- LangGraph pipeline: `load_profile -> plan_outline -> plan_content -> validate -> render -> store`
- Deterministic validator and template-preserving renderer using `python-pptx`
- MongoDB + GridFS storage model
- React frontend (Vite) with Dashboard, Templates, Generate, History pages

Current blockers to resolve before/with slide-by-slide rollout:
- Frontend expects `_id` but backend returns `id`
- Frontend expects `current_step/completed_steps` but backend streams `stage/progress/message`
- Dashboard expects richer health payload than backend currently returns
- Minor backend quality gaps (theme filtering robustness, ambiguous `slide_types` field semantics)

---

## 3. Target Architecture (To-Be)

### Generation Flow (Target)

`load_profile -> plan_outline -> fan-out per slide -> plan_single_slide -> validate_single_slide -> aggregate -> aggregate_validation -> render -> store`

Key behavior changes:
- Outline is planned once
- Each slide is generated independently and retried independently
- Aggregation builds final ordered deck plan
- Deck-level validation runs after fan-in
- Rendering remains deterministic and template-safe

---

## 4. Slide-by-Slide Generation Design

### Why this design
- Reduces token pressure by avoiding one giant response
- Prevents full-deck retries caused by one invalid slide
- Improves latency with parallel slide generation
- Makes errors explainable at the slide level

### Per-slide loop
For each outline item:
1. Build slide-scoped prompt with exact layout constraints
2. Generate `SlideContent`
3. Run deterministic validation for that slide only
4. If invalid, retry this slide with structured error context (`max_retries`)
5. Emit validated/best-effort slide result to reducer

---

## 5. Node-by-Node Plan

### Node 1: `load_profile_node`
- Keep as-is
- Ensure profile includes only ready templates and usable layout metadata

### Node 2: `plan_outline_node`
- Keep outline planning responsibilities
- Output becomes canonical list of `SlideOutlineItem`

### Node 3: fan-out edge (`Send`)
- Add `Send` fan-out from outline to per-slide workers
- Create `SlideState` per outline item

### Node 4: `plan_single_slide_node` (new)
- Replace monolithic `plan_content_node`
- Generate content for one slide only

### Node 5: `validate_single_slide_node` (new)
- Validate one slide against one selected layout
- Retry only failed slide when needed

### Node 6: `aggregate_node` (new)
- Collect reducer outputs
- Sort by `slide_index`
- Build `SlidePlan`

### Node 7: `aggregate_validation_node` (new)
- Validate deck-level rules:
  - no duplicate template layout assignment
  - no missing indices in final plan
  - slide count consistency vs outline

### Node 8: `render_node`
- Keep deterministic rendering with template preservation
- Continue chart data replacement via `replace_data()`

### Node 9: `store_node`
- Keep GridFS upload + generation record finalization

---

## 6. Schema and Contract Updates

### Backend state/schema updates
- Add `SlideState` TypedDict in `graph/state.py`
- Update `PipelineState` for reducer-style `completed_slides`
- Add/adjust outline schema if needed (`SlideOutlineItem` explicit model)
- Split validator APIs:
  - `validate_single_slide(...)`
  - `validate_aggregate_plan(...)`

### API response contract alignment
- Standardize template list item shape to include **both** `id` and `_id` temporarily for compatibility window, then remove `_id` after frontend migration
- Standardize generation status payload to include:
  - `stage` (backend canonical)
  - optional `current_step` alias during transition
  - `progress`, `message`, `status`, `error`
- Expand `/api/health` response to include configured model names and limits used by UI cards

---

## 7. Frontend Alignment Plan

### Templates page
- Switch all template references from `t._id` to `t.id`
- Use `total_slides` instead of non-existent `slide_count`

### Generate page
- Replace `current_step/completed_steps` assumptions with backend `stage/progress/message`
- Keep graceful fallback UI during transition aliases

### Dashboard page
- Consume expanded health payload fields
- Keep safe defaults when backend omits optional values

### History page
- No architecture change required; ensure stored generation IDs still map to download route

---

## 8. Renderer and Validation Plan

### Renderer
- Keep current template-preserving behavior as baseline
- Add focused regression tests for:
  - placeholder text replacement fidelity
  - chart data replacement preserving chart style
  - out-of-range slide handling behavior

### Validator
- Preserve deterministic checks already implemented
- Split into per-slide and aggregate phases for fan-out architecture
- Keep retry-context message generation for LLM repair loops

---

## 9. Phase-by-Phase Implementation Roadmap

### Phase 1: Contract Stabilization (Backend + Frontend)
- Fix template ID and status payload mismatches
- Expand health payload
- Update frontend field mappings
- Verify current monolithic pipeline works with aligned contracts

### Phase 2: State and Schema Refactor
- Add `SlideState`
- Update `PipelineState` reducer fields
- Introduce explicit outline item schema

### Phase 3: Per-slide Nodes
- Implement `plan_single_slide_node`
- Implement `validate_single_slide_node`
- Implement per-slide retry loop

### Phase 4: Fan-out/Fan-in Pipeline Rewire
- Replace `plan_content` branch with `Send`-based parallel flow
- Add `aggregate_node` and `aggregate_validation_node`

### Phase 5: Validator Split and Hardening
- Move deck-level checks to aggregate validator
- Keep strong error context generation for retry prompts

### Phase 6: UI Progress and Observability
- Ensure SSE stream cleanly reflects `stage`, `progress`, and terminal states
- Add richer stage messages for user trust and debugging

### Phase 7: Test and Regression Suite
- Update existing tests for new contracts and flow
- Add tests for per-slide retry behavior and aggregate validation failures
- Add API integration tests for completed and failed generation paths

### Phase 8: Performance and Reliability Pass
- Add concurrency caps for fan-out slide generation
- Add timeout/retry handling for LLM calls
- Add structured logs for per-slide durations and retry counts

---

## 10. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Parallel fan-out overloads LLM backend | Slow/fail requests | Concurrency cap + backoff |
| Slide coherence weakens when generated independently | Narrative inconsistency | Provide full outline context to each slide prompt |
| Frontend/backed payload drift reappears | Broken UI states | Single versioned response contract + integration tests |
| Retry loops hide persistent schema mismatch | Silent quality drop | Hard cap retries + explicit failure states |
| Template edge cases break rendering | Output corruption | Keep deterministic validator and add fixture-based regression tests |

---

## 11. Definition of Done

This migration is complete when:
- Slide-by-slide fan-out/fan-in pipeline is active in production flow
- Per-slide retry works without full-deck retry
- Aggregate validator enforces deck-level constraints
- Frontend works end-to-end with canonical backend payloads
- Upload -> analyze -> generate -> stream -> download journey is stable
- Test suite passes for API, validator, renderer, and pipeline regression cases

