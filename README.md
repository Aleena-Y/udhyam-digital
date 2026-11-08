# Udyam Digital

Udyam Digital is a demo Accel Business platform for discovering MSME connectivity, cloud and security solutions. The FastAPI backend loads its catalogue, lead dataset and KYC registries from [`backend/app/data`](./backend/app/data), while the React frontend consumes those APIs.

## Architecture

- `frontend/`: mobile-first React/TypeScript/Vite PWA. It calls the backend for profile persistence, deterministic recommendations, quotes, KYC, order tracking and streaming chat.
- `backend/app/routers/`: REST boundaries for auth, chat, business profiles, recommendations, quotes, KYC, orders, leads and analytics.
- `backend/app/services/`: CSV loading, deterministic catalogue eligibility/pricing, OCR extraction, registry validation, recovery scoring and analytics.
- `backend/app/models/`: SQLAlchemy models for businesses, conversations, quotes, orders, KYC, consent, leads and partner assignments.
- `backend/app/data/`: the supplied synthetic datasets. No production customer data or external paid API is required.

The LLM is deliberately advisory only. Eligibility, prices, KYC registry results, recovery scores and order state transitions are enforced by backend code.

## Requirements

- Python 3.11+
- Node.js 18+
- Ollama with access to `gemma4:31b-cloud`

## Run the backend

```powershell
cd backend
if (-not (Test-Path .venv\Scripts\python.exe)) { py -3 -m venv .venv }
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Using `.\.venv\Scripts\python.exe` explicitly is intentional: it prevents PowerShell from starting Uvicorn with a different global Python installation that does not contain the backend dependencies. If you prefer activation, run `.\.venv\Scripts\Activate.ps1` first and verify `python -c "import sys; print(sys.executable)"` points into `backend\.venv`.

If PowerShell blocks activation scripts, the explicit commands above work without changing execution policy.

The API is available at http://localhost:8000 and its interactive docs are at http://localhost:8000/docs.

## Set up Ollama AI

Install Ollama from https://ollama.com/download, start the Ollama application, and sign in if your Ollama account is required for cloud models. Then pull the configured model:

```powershell
ollama pull gemma4:31b-cloud
ollama list
```

The backend defaults to:

```text
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma4:31b-cloud
```

To override either value, create `backend/.env`:

```dotenv
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma4:31b-cloud
```

Verify the connection with http://localhost:8000/chat/health. The chat window in the frontend uses the backend streaming endpoint, so the Ollama URL is never exposed to the browser. The model is used for conversation and explanations only; catalogue eligibility, pricing, KYC and lead recovery remain deterministic backend rules.

## Run the frontend

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. If the backend runs on another URL, create `frontend/.env`:

```dotenv
VITE_API_URL=http://localhost:8000
```

The customer experience is at `/`. The main page includes a compact dataset-backed admin snapshot and links to the separate operations dashboard at http://localhost:5173/admin (or the alternate Vite port shown in the terminal), which contains funnel and drop-off charts, recovery candidates, and the KYC review desk.

After a customer adds an eligible recommended product, the secure onboarding section becomes available for quote creation, consent, registry checks and document uploads. The advisor can also expose catalogue product IDs in its response; the **Select plan from this advice** action adds those eligible products to the same onboarding flow. The header language control provides deterministic English, Hindi and Tamil translations for the customer UI and also sets the advisor conversation language. Product and legal source text is kept unchanged when no verified local translation is available.

## Validate

```powershell
cd backend
python -m pytest app/tests -q

cd ..\frontend
npm test
npm run build
```

The frontend profile form creates a business through the API, recommendations are calculated from the CSV catalogue and the advisor stores conversation history in SQLite.

## Demo credentials

These accounts are seeded for local demonstration:

| Role | Email | Password |
| --- | --- | --- |
| Admin | `admin@accel.demo` | `admin123` |
| Channel partner | `partner@accel.demo` | `partner123` |
| Customer | `customer@accel.demo` | `customer123` |

All data is synthetic. Partner commissions and order progress are explicitly labelled simulated.

## Main API surfaces

- `POST /business/` and `POST /recommend/` for onboarding and catalogue-driven recommendations
- `POST /quotes/` and `POST /quotes/{quote_id}/checkout` for deterministic pricing and simulated checkout
- `POST /kyc/consent`, `/kyc/validate-gstin`, `/kyc/validate-udyam`, and `/kyc/upload-document`
- `GET /orders/{order_id}` and `POST /orders/{order_id}/advance` for simulated tracking
- `GET /leads/recovery-candidates` and `POST /leads/{lead_id}/assign` for partner recovery
- `GET /dashboard/summary` plus the detailed dashboard analytics endpoints
- `POST /chat/message` and `GET /chat/health` for the Ollama-backed advisor

Uploaded documents are stored under the configured backend upload directory with generated filenames, not original names. The KYC delete endpoint, `DELETE /kyc/data/{business_id}`, purges the business KYC records, consent records and uploaded files.
