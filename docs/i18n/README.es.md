<div align="center">
  <h1>MatrAIx</h1>
  <p><strong>Simulate before reality.</strong></p>
  <p>
    Infraestructura a escala poblacional y orientada a personas para evaluar
    sistemas de IA y productos interactivos con usuarios simulados heterogéneos.
  </p>
  <p>
    <a href="../../README.md">English</a> |
    <a href="README.ko.md">한국어</a> |
    <a href="README.zh-CN.md">简体中文</a> |
    <a href="README.zh-TW.md">繁體中文</a> |
    <a href="README.ja.md">日本語</a> |
    <a href="README.pt-BR.md">Português</a> |
    <strong>Español</strong>
  </p>
  <p>
    <a href="https://matraix.ai/"><img alt="Website" src="https://img.shields.io/badge/Website-matraix.ai-4f7cff?style=for-the-badge"></a>
    <a href="https://discord.gg/knVyQQnRFa"><img alt="Discord" src="https://img.shields.io/badge/Discord-join%20MatrAIx-5865F2?style=for-the-badge&logo=discord&logoColor=white"></a>
    <a href="https://x.com/MatrAIx2026"><img alt="X" src="https://img.shields.io/badge/X-%40MatrAIx2026-000000?style=for-the-badge&logo=x&logoColor=white"></a>
    <a href="https://www.linkedin.com/company/matraix"><img alt="LinkedIn" src="https://img.shields.io/badge/LinkedIn-MatrAIx-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white"></a>
    <a href="https://forms.gle/hwEHng5HGWRqcJue9"><img alt="Google Form" src="https://img.shields.io/badge/Google%20Form-join%20MatrAIx-4285F4?style=for-the-badge&logo=googleforms&logoColor=white"></a>
    <a href="../README.md"><img alt="Docs" src="https://img.shields.io/badge/Docs-Handbook-5b5b5b?style=for-the-badge"></a>
    <a href="https://huggingface.co/datasets/MatrAIx2026/MatrAIx_Persona_1M_Public_Release"><img alt="Hugging Face" src="https://img.shields.io/badge/Hugging%20Face-Persona%201M-ffcc4d?style=for-the-badge"></a>
    <a href="../../LICENSE"><img alt="License" src="https://img.shields.io/badge/License-MIT-c33b32?style=for-the-badge"></a>
    <a href="../quickstart.md#10-playground--play-tasks-visually"><img alt="Playground" src="https://img.shields.io/badge/Playground-Visual%20Runner-56b879?style=for-the-badge"></a>
  </p>
</div>

<div align="center">
  <a href="https://www.youtube.com/watch?v=cNFkz9Wo1y4&t=15s">
    <img src="https://img.youtube.com/vi/cNFkz9Wo1y4/maxresdefault.jpg" alt="Ver la demo de MatrAIx en YouTube" width="900">
  </a>
  <p>
    <a href="https://www.youtube.com/watch?v=cNFkz9Wo1y4&t=15s"><img alt="Ver la demo de MatrAIx en YouTube" src="https://img.shields.io/badge/%E2%96%B6%20Watch%20the%20demo-on%20YouTube-FF0000?style=for-the-badge&logo=youtube&logoColor=white"></a>
  </p>
</div>

---

**MatrAIx** es una infraestructura a escala poblacional y orientada a personas
para evaluar sistemas de IA y productos interactivos con usuarios simulados
heterogéneos. En lugar de probar contra un usuario genérico o intercambiable,
MatrAIx instancia registros de persona muestreados como agentes LLM y los
ejecuta en tareas reproducibles en cuatro entornos — **Survey**, **AI Chatbot**,
**Web** y **App** (escritorio y móvil nativos, incluidos macOS e iOS).

En su base hay un esquema compartido de **1.290 dimensiones categóricas** que
cubren trasfondo, psicología, capacidad y comportamiento. Las personas combinan
generación sintética consciente de dependencias con grounding humano basado en
evidencia; un coreset determinista y filtrado por calidad de **un millón de
personas** se publica para investigación en
[Hugging Face](https://huggingface.co/datasets/MatrAIx2026/MatrAIx_Persona_1M_Public_Release).
La telemetría compartida, la verificación propia de cada tarea y los informes
conectan respuestas y trayectorias individuales con hallazgos a nivel de
subgrupo y población.

El nombre alude a *The Matrix*: un mundo simulado útil para exploración,
pruebas de estrés y generación de hipótesis — **no un sustituto de la evidencia
de personas reales**.

## Requisitos

- [Docker](https://docs.docker.com/get-docker/)
- [uv](https://docs.astral.sh/uv/) y Python 3.12
- Node.js 20+ (solo frontends de Playground / viewer)
- Claves de API de modelo para ejemplos de agentes de persona — ver [agents.md](../environment/agents.md)

## Instalación

```bash
git clone <repo-url> && cd MatrAIx
uv venv --python 3.12
uv pip install -e .
uv pip install pytest pytest-asyncio httpx
uv pip install -e packages/playground
uv pip install -e packages/harbor-langsmith
uv pip install -e packages/rewardkit
```

Todos los comandos de Matraix Playground se ejecutan como **`uv run harbor …`**.

Configura la clave de API del modelo correspondiente a tu proveedor antes de
ejecutar tareas por GUI o CLI (el smoke test no la necesita):

```bash
export ANTHROPIC_API_KEY="sk-ant-..."   # modelos anthropic/claude-*
# export OPENAI_API_KEY="sk-..."        # modelos openai/gpt-*
```

Consulta la matriz completa de claves en [agents.md](../environment/agents.md).
Playground también puede cargar claves desde `application/playground/.env.local`.

### Importar Persona 1M (opcional)

```bash
huggingface-cli download MatrAIx2026/MatrAIx_Persona_1M_Public_Release \
  --repo-type dataset \
  --local-dir persona/datasets/matraix-persona-1m/release
```

Playground: Dataset → **`matraix-persona-1m`**. CLI: `--dataset persona/datasets/matraix-persona-1m`.
Detalles: [Handbook § Persona 1M](../README.md#3-persona-1m-optional).

## Inicio rápido

### Smoke test

No se requiere clave de API. **Requiere Docker** (el smoke job usa
`environment.type: docker`):

```bash
uv run harbor run -c configs/jobs/example-job-recipe/harbor-smoke-local.yaml
```

### Ejecuciones de tareas por GUI

Playground elige tareas, muestrea personas y lanza los mismos jobs de
Matraix Playground que el modo auto de la CLI.
Inicia API + frontend (dos terminales):

```bash
# Terminal A — API
VENV=.venv bash application/playground/backend/run_dev.sh

# Terminal B — frontend
cd application/playground/frontend && npm ci && npm run dev
```

Abre **http://localhost:5173** → Playground → elige una cohort de personas →
elige tareas Survey / Chat / Web / OS app → **Lock pipeline** → **Run eval**.
Detalles: [Playground §10](../quickstart.md#10-playground--play-tasks-visually).

### Desarrollo / ejecución por CLI

**Desarrollar** — copia una tarea de referencia en `application/tasks/`, edita
`task.toml` / `instruction.md` / `input/` / verifier y regístrala en Playground
([task-guide.md](../application/task-guide.md)):

```bash
cp -R application/tasks/example-survey_product-feedback \
  application/tasks/<your-task-name>
```

| Tipo | Tarea de referencia |
|------|---------------------|
| Survey | `application/tasks/example-survey_product-feedback` |
| Chat | `application/tasks/example-chat-api_support_chatbot` |
| Web | `application/tasks/example-web-playwright_quote-choice` |
| OS-app | `application/tasks/example-computer-use-linux_note-to-csv` |

**Ejecutar** — genera un job de Matraix Playground (fija agent + model) y ejecútalo:

```bash
uv run python application/scripts/generate_application_job.py \
  --task application/tasks/example-survey_product-feedback \
  --execution-mode auto \
  --persona-ids 0042 \
  --model-name anthropic/claude-sonnet-4-6

# Usa las líneas de export + la ruta del recipe que imprime el script, p. ej.:
uv run harbor run -c configs/jobs/application-task-job-recipe/example-survey-product-feedback-auto-n1.yaml
```

Lotes (`--sample-size N`), filtros y ejemplos chat / web / os-app:
[docs/quickstart.md](../quickstart.md).

## Docs

**[MatrAIx Handbook](../README.md)** — guías y docs de persona / application / environment.

<p align="center">
  <img src="../assets/matraix-architecture.png" alt="Arquitectura MatrAIx" width="900">
</p>

## Estructura del repositorio

```text
MatrAIx/
├── persona/                 Schema, datasets, pipelines de síntesis/curación/validación
│   ├── schema/              Schema de persona de 1.290 dimensiones
│   ├── datasets/            Pool de muestras de desarrollo y YAMLs de persona
│   ├── validation/          Suites de grounding / validación de calidad
│   └── scripts/             Helpers de job y pipeline de persona
├── application/
│   ├── tasks/               Specs de tareas Survey · chat · web · os-app
│   ├── task-spec/           Contratos compartidos de tarea
│   ├── playground/          Runner visual (API backend + frontend)
│   └── scripts/             generate_application_job.py y tooling de tareas
├── environment/
│   ├── runtime/             Runtime de Matraix Playground
│   ├── agents/              Agentes condicionados a persona
│   ├── task-environments/   Imágenes Docker / sidecars
│   └── adapters/            Adaptadores externos (p. ej. SimpleQA)
├── packages/                playground · rewardkit · harbor-langsmith
├── apps/viewer/             Frontend emparejado con `harbor view`
├── configs/jobs/            Recipes de job de Matraix Playground (curados y generados)
├── docs/                    Handbook — persona/ · application/ · environment/
├── examples/                Tareas de ejemplo mínimas
├── src/matraix/             Entry points del paquete Python
├── scripts/                 Helpers a nivel de repositorio
├── tests/                   Tests unitarios / de entorno
└── jobs/                    Salidas locales de Matraix Playground (gitignored)
```

Los datasets grandes generados quedan fuera de git (ver el release de Hugging Face arriba).

## Únete a la comunidad

[![Discord](https://img.shields.io/badge/Discord-join%20MatrAIx-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/knVyQQnRFa)
[![X](https://img.shields.io/badge/X-follow%20%40MatrAIx2026-000000?style=for-the-badge&logo=x&logoColor=white)](https://x.com/MatrAIx2026)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-follow%20MatrAIx-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/company/matraix)
[![Google Form](https://img.shields.io/badge/Google%20Form-join%20MatrAIx-4285F4?style=for-the-badge&logo=googleforms&logoColor=white)](https://forms.gle/hwEHng5HGWRqcJue9)

1. Únete a Discord — nickname **`Full Name - Affiliation`**. Completa el Google Form
   (trasfondo, intereses, autoría / agradecimientos en papers).
2. ¡Saluda! Nos gusta conectar a quienes comparten intereses o experiencia.
3. Participa en la comunidad de investigación MatrAIx para colaborar o contribuir.

## Licencia

MIT — ver [LICENSE](../../LICENSE).
