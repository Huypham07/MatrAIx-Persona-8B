# MatrAIx Playground with Local Qwen3-14B & 3 Simulation Environments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy and customize the MatrAIx Playground web app to run simulations on 3 environments (Survey, Chatbot, Web) with a local Qwen3-14B LLM, dynamic persona selection, and complete evaluation scorecards.

**Architecture:** Integrate a dedicated Local LLM provider in the backend model client that uses Basic Auth and specific parameters for Qwen3-14B. Wire in-process runners for Survey, Chatbot, and Web simulations so they run without requiring complex Docker dependencies, outputting structured evaluation artifacts. Refine the React frontend to remove the OS-App environment, default to Qwen3-14B, and support dynamic persona ID selection.

**Tech Stack:** Python 3.9, FastAPI, Uvicorn, Pydantic v2, React 18, Vite, TypeScript, TailwindCSS.

**Spec:** `docs/superpowers/specs/2026-08-22-playground-qwen3-3env-design.md`

## Global Constraints
- Target LLM: Configured via `LOCAL_LLM_BASE_URL` (`http://localhost:8000/v1` default), `LOCAL_LLM_AUTH_HEADER`, model: `Qwen3-14B`, `chat_template_kwargs: {"enable_thinking": false}`.
- In-Scope Environments: Survey, Chatbot, Web.
- Out-of-Scope: OS-App / CUA / Mobile / AppWorld.
- Output: Every run must produce structured scorecard metrics (`structured_output.json`, satisfaction, completion).

---

### Task 1: Local Qwen3-14B LLM Integration & Preflight Probe

**Files:**
- Modify: `packages/playground/src/playground/openai_client.py`
- Modify: `packages/playground/src/playground/model_client.py`
- Modify: `packages/playground/src/playground/persona_model.py`
- Modify: `src/matraix/provider_credentials.py`
- Modify: `application/playground/backend/service/config.py`
- Modify: `application/playground/backend/api/app.py`
- Modify: `application/playground/.env.local`
- Create: `tests/unit/test_local_qwen_client.py`

**Interfaces:**
- Consumes: `LOCAL_LLM_BASE_URL`, `LOCAL_LLM_AUTH_HEADER`, `LOCAL_LLM_MODEL` from environment.
- Produces: `build_json_client("local/qwen3-14b")` returning a functioning JSON client; `preflight_checks()` returning `ready: True`.

- [ ] **Step 1: Write test for local Qwen3-14B client**

```python
# tests/unit/test_local_qwen_client.py
import pytest
from playground.model_client import build_json_client
from playground.openai_client import OpenAIChatClient

def test_local_qwen_client_init():
    client = build_json_client("local/qwen3-14b")
    assert isinstance(client, OpenAIChatClient)
    assert client.model == "Qwen3-14B"
```

- [ ] **Step 2: Update `packages/playground/src/playground/openai_client.py`**
Support `default_headers` (for `Authorization: Basic ...`) and `extra_body` (for `chat_template_kwargs: {"enable_thinking": False}`) in `OpenAIChatClient`.

- [ ] **Step 3: Update `packages/playground/src/playground/model_client.py`**
Add support for `local/*` and `qwen3-14b` prefix, pulling endpoint and auth from `LOCAL_LLM_BASE_URL` (`http://localhost:8000/v1` default) and `LOCAL_LLM_AUTH_HEADER`.

- [ ] **Step 4: Update `src/matraix/provider_credentials.py` and `backend/service/config.py`**
Add `local/qwen3-14b` to recognized persona models and make it the default.

- [ ] **Step 5: Update `application/playground/backend/api/app.py` preflight probe**
Include local LLM endpoint probe in `preflight_checks()`.

- [ ] **Step 6: Run tests and verify**
Run: `.venv/bin/pytest tests/unit/test_local_qwen_client.py -v`

---

### Task 2: Survey Simulation Environment & Evaluation Output

**Files:**
- Modify: `packages/playground/src/playground/inprocess/survey_eval.py`
- Modify: `packages/playground/src/playground/survey_task_content.py`
- Modify: `application/playground/backend/service/harbor_job_service.py`
- Create: `tests/unit/test_survey_eval_qwen.py`

**Interfaces:**
- Consumes: `Persona`, `SurveyInstrument`, `SurveyEvalConfig`.
- Produces: `SurveyEvalResult` with answers, completion rate, Likert scores, and `structured_output.json`.

- [ ] **Step 1: Write test for survey runner with local Qwen**

```python
# tests/unit/test_survey_eval_qwen.py
import pytest
from playground.inprocess.survey_eval import InprocessSurveyEvalRunner
from playground.types import Persona
from backend.service.survey_types import SurveyInstrument, SurveyQuestion

def test_survey_eval_runner():
    persona = Persona(id="test_p1", name="Test Persona", context="I am a budget-conscious parent.")
    instrument = SurveyInstrument(
        id="test_survey",
        title="Candy Land Survey",
        questions=[
            SurveyQuestion(id="q1", text="Would you buy Candy Land for $25?", type="single_choice", options=["yes", "no", "hesitate"])
        ]
    )
    runner = InprocessSurveyEvalRunner()
    result = runner(persona=persona, instrument=instrument, created_at="2026-08-22T00:00:00Z", persona_yaml_path="persona/datasets/matraix-persona-dev-sample/test.yaml")
    assert len(result.answers) == 1
    assert result.completion.valid is True
```

- [ ] **Step 2: Ensure robust prompt assembly & JSON extraction in `survey_eval.py`**
Ensure persona narrative and question options are formatted clearly so Qwen3-14B generates answers with `choice`, `rationale`, and `confidence`.

- [ ] **Step 3: Run test and verify**
Run: `.venv/bin/pytest tests/unit/test_survey_eval_qwen.py -v`

---

### Task 3: Chatbot Simulation Environment & Conversational SUT

**Files:**
- Modify: `packages/playground/src/playground/inprocess/chatbot_eval.py`
- Modify: `packages/playground/src/playground/harbor/chat_eval.py`
- Modify: `packages/playground/src/playground/scoring.py`
- Create: `packages/playground/src/playground/inprocess/chatbot_sut_adapter.py`
- Create: `tests/unit/test_chatbot_eval_qwen.py`

**Interfaces:**
- Consumes: `PlaygroundConfig`, `Persona`, `ChatbotTaskConfig`.
- Produces: Multi-turn dialogue trajectory, state transitions, satisfaction score, and `Scorecard` debrief view.

- [ ] **Step 1: Create `chatbot_sut_adapter.py`**
Implement an in-process fallback SUT that acts as the conversational assistant (e.g. nutrition consultant or support bot) using Qwen3-14B when external sidecar is not active.

- [ ] **Step 2: Update `chatbot_eval.py` and `scoring.py`**
Ensure multi-turn loop executes cleanly between persona user and SUT, writing transcript and evaluating satisfaction.

- [ ] **Step 3: Write test and verify**
Run: `.venv/bin/pytest tests/unit/test_chatbot_eval_qwen.py -v`

---

### Task 4: Web Simulation Environment & In-Process Evaluator

**Files:**
- Modify: `packages/playground/src/playground/harbor/web_eval.py`
- Modify: `application/playground/backend/service/harbor_job_service.py`
- Create: `packages/playground/src/playground/inprocess/web_eval.py`
- Create: `tests/unit/test_web_eval_qwen.py`

**Interfaces:**
- Consumes: Task instruction, web page options/DOM.
- Produces: `WebResult` (`overallExperienceRating`, `needSatisfaction`, `easeOfUse`, `selectedProductName`, `reason`).

- [ ] **Step 1: Implement in-process Web runner in `packages/playground/src/playground/inprocess/web_eval.py`**
Simulate web decision tasks (e.g., MIT OCW course choice, Notion plan comparison) by feeding page contents to Qwen3-14B persona agent and evaluating the choice and rationale.

- [ ] **Step 2: Update `harbor_job_service.py`**
Route web auto trials to in-process web evaluator when running locally.

- [ ] **Step 3: Write test and verify**
Run: `.venv/bin/pytest tests/unit/test_web_eval_qwen.py -v`

---

### Task 5: Frontend UI Tidy-Up & Persona Selection Enhancement

**Files:**
- Modify: `application/playground/frontend/src/components/cockpit/TaskTypeSwitch.tsx`
- Modify: `application/playground/frontend/src/components/TaskGalleryContent.tsx`
- Modify: `application/playground/frontend/src/lib/personaAgentCatalog.ts`
- Modify: `application/playground/frontend/src/components/cockpit/setup/cockpitPersonaSetupStorage.ts`
- Modify: `application/playground/frontend/src/components/cockpit/setup/useSetupPersonaSampling.ts`
- Modify: `application/playground/frontend/src/components/PersonaStoreContent.tsx`
- Modify: `application/playground/frontend/src/lib/types.ts`

**Interfaces:**
- Consumes: Backend `/api/config/options`, `/api/persona-pool/personas`.
- Produces: 3-tab segmented control (Survey, Chatbot, Web), Qwen3-14B default model, dynamic persona picker, clean error-free TypeScript build.

- [ ] **Step 1: Update `TaskTypeSwitch.tsx` and `TaskGalleryContent.tsx`**
Remove `os-app` option, leaving Survey, Chatbot, Web.

- [ ] **Step 2: Update `personaAgentCatalog.ts` and storage defaults**
Add `local/qwen3-14b` with label `"Qwen3-14B (Local)"` as default persona model.

- [ ] **Step 3: Fix TypeScript compilation errors in `PersonaStoreContent.tsx` and `lib/types.ts`**

- [ ] **Step 4: Build and test frontend**
Run: `npm --prefix application/playground/frontend run build`

---

### Task 6: End-to-End App Deployment & Verification

**Files:**
- Modify: `application/playground/run_demo.sh`
- Modify: `application/playground/backend/requirements.txt`
- Modify: `application/playground/.env.local`

**Interfaces:**
- Produces: Running Playground server on `http://127.0.0.1:8765` serving API + built SPA.

- [ ] **Step 1: Fix `requirements.txt` (remove non-existent `openai-agents>=0.17.6`)**
- [ ] **Step 2: Configure `.env.local` with local Qwen3-14B settings**
- [ ] **Step 3: Build frontend and start the server using `run_demo.sh`**
- [ ] **Step 4: Verify all 3 simulation environments (Survey, Chatbot, Web) run and display complete scorecards**

