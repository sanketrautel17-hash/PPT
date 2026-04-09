# Camping World PPT Generator

An agentic system that takes a Camping World master PPTX template + natural language prompt and produces a brand-consistent, presentation-ready `.pptx` file.

## Stack

| Layer | Technology |
|---|---|
| API | FastAPI |
| Pipeline | LangGraph (StateGraph) |
| LLM | Groq (`llama-3.3-70b-versatile` / `llama-3.1-8b-instant`) |
| Database | MongoDB + GridFS |
| DB Driver | Motor (async) |
| PPTX | python-pptx + lxml |

## Quick Start

```bash
# 1. Install dependencies
cd backend
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env and set GROQ_API_KEY and MONGO_DB_URL

# 3. Start MongoDB (if local)
mongod

# 4. Run the server
python main.py
# → http://localhost:8000
# → http://localhost:8000/docs  (Swagger UI)
```

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Health check + DB ping |
| `POST` | `/api/templates/upload` | Upload a `.pptx` template |
| `GET` | `/api/templates` | List all profiled templates |
| `GET` | `/api/templates/{id}` | Full template profile |
| `POST` | `/api/generate` | Start PPT generation |
| `GET` | `/api/generate/{id}/status` | SSE real-time progress stream |
| `GET` | `/api/generate/{id}/download` | Download the generated `.pptx` |

## Usage Example

```bash
# Upload a template
curl -X POST http://localhost:8000/api/templates/upload \
  -F "file=@my_template.pptx" \
  -F "name=Q1 Template"

# Start generation
curl -X POST http://localhost:8000/api/generate \
  -H "Content-Type: application/json" \
  -d '{"template_id": "<id from above>", "prompt": "Q1 business review for Good Sam RV Insurance"}'

# Stream progress (SSE)
curl -N http://localhost:8000/api/generate/<generation_id>/status

# Download result
curl -o result.pptx http://localhost:8000/api/generate/<generation_id>/download
```

## Project Structure

```
backend/
├── app/
│   ├── api/
│   │   ├── routes/          # HTTP route handlers
│   │   ├── dependencies.py  # FastAPI DI helpers
│   │   └── middleware.py    # CORS + exception handlers
│   ├── core/
│   │   ├── exceptions.py    # Custom exception types
│   │   └── logging.py       # Structured logging setup
│   ├── graph/
│   │   ├── nodes.py         # LangGraph node functions
│   │   ├── pipeline.py      # StateGraph wiring + retry routing
│   │   ├── state.py         # PipelineState TypedDict
│   │   └── prompts/         # LLM prompt templates (.txt)
│   ├── models/              # FastAPI request/response models
│   ├── schemas/             # Internal data contracts (Pydantic)
│   ├── services/            # Business logic orchestration
│   ├── tools/               # Standalone async tools
│   │   ├── template_parser.py    # PPTX structural extraction
│   │   ├── guidance_extractor.py # Groq slide classification
│   │   ├── validator.py          # Deterministic plan validation
│   │   ├── renderer.py           # Template-preserving PPTX render
│   │   └── storage.py            # GridFS upload/download
│   ├── config.py            # Pydantic settings
│   ├── database.py          # Motor client + GridFS buckets
│   └── main.py              # FastAPI app factory
├── tests/
│   ├── test_api/            # API integration tests
│   └── test_tools/          # Unit tests for tools
├── .env                     # Local env (git-ignored)
├── .env.example             # Example env template
├── main.py                  # Entrypoint (uvicorn runner)
├── pyproject.toml           # Project metadata + pytest config
└── requirements.txt         # Python dependencies
```

## Core Rules (Non-Negotiable)

- Template is **source of truth** for layout/styling
- Images/logos are **never modified**
- Chart styling is **preserved** — only data values replaced
- Validation is **100% deterministic** (no LLM in validator)
- Max **2 retries** on validation failure

## Configuration

All settings are in `.env` or environment variables:

| Key | Default | Description |
|---|---|---|
| `GROQ_API_KEY` | — | **Required.** Your Groq API key |
| `MONGO_DB_URL` | — | **Required.** MongoDB connection URI |
| `PLANNER_MODEL` | `llama-3.3-70b-versatile` | Groq model for content planning |
| `GUIDANCE_MODEL` | `llama-3.1-8b-instant` | Groq model for slide classification |
| `MAX_TEMPLATE_SIZE_MB` | `50` | Max PPTX upload size |
| `MAX_PROMPT_CHARS` | `8000` | Max generation prompt length |
| `MAX_RETRIES` | `2` | Max validation retry attempts |

## Running Tests

```bash
cd backend
pytest tests/ -v
```
