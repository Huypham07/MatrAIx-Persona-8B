<div align="center">
  <h1>MatrAIx</h1>
  <p><strong>Simulate before reality.</strong></p>
  <p>
    面向異構模擬使用者的大規模、人格驅動基礎設施，用於評估 AI 系統與互動式產品。
  </p>
  <p>
    <a href="../../README.md">English</a> |
    <a href="README.ko.md">한국어</a> |
    <a href="README.zh-CN.md">简体中文</a> |
    <strong>繁體中文</strong> |
    <a href="README.ja.md">日本語</a> |
    <a href="README.pt-BR.md">Português</a> |
    <a href="README.es.md">Español</a>
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
    <img src="https://img.youtube.com/vi/cNFkz9Wo1y4/maxresdefault.jpg" alt="在 YouTube 上觀看 MatrAIx 示範" width="900">
  </a>
  <p>
    <a href="https://www.youtube.com/watch?v=cNFkz9Wo1y4&t=15s"><img alt="在 YouTube 上觀看 MatrAIx 示範" src="https://img.shields.io/badge/%E2%96%B6%20Watch%20the%20demo-on%20YouTube-FF0000?style=for-the-badge&logo=youtube&logoColor=white"></a>
  </p>
</div>

---

**MatrAIx** 是一套面向異構模擬使用者的大規模、人格驅動基礎設施，用於評估 AI 系統與互動式產品。它不依賴「通用」或可互換的使用者假設，而是將抽樣得到的人格記錄實例化為 LLM Agent，並在四類環境中以可重現任務驅動執行 —— **Survey（問卷）**、**AI Chatbot（對話）**、**Web**，以及 **App**（原生桌面與行動裝置，含 macOS 與 iOS）。

其基礎是一套共用的 **1,290 個類別維度** 人格 Schema，涵蓋背景、心理、能力與行為。人格結合依賴感知的合成生成與證據感知的人類 grounding；經確定性、品質過濾的 **百萬人格** 共集（coreset）已在
[Hugging Face](https://huggingface.co/datasets/MatrAIx2026/MatrAIx_Persona_1M_Public_Release)
公開發布，供研究使用。共用遙測、任務自有驗證與報告能力，將個體回應與軌跡連接到子群體與總體層面的發現。

名稱致敬 *The Matrix*：這是一個便於探索、壓力測試與假設生成的模擬世界，**不能取代來自真實人群的證據**。

## 動態

- **[2026-08-10]** 登上 [X Trending Story](https://x.com/i/trending/2086626337561911419)：*Harvard and MIT Unveil MatrAIx with 8.3 Billion Virtual Personas*。科技媒體亦有報導，包括 [AI Era](https://www.36kr.com/p/3932853833759876)、[Numerama](https://www.numerama.com/tech/2308727-ces-chercheurs-ont-cree-83-milliards-dhumains-virtuels-pour-tester-des-produits-a-notre-place.html)、[Infobae](https://www.infobae.com/tecno/2026/08/10/asi-prueba-la-ia-un-mundo-con-8300-millones-de-personas-digitales-matraix-es-el-metaverso/)、[AI타임스](https://www.aitimes.com/news/articleView.html?idxno=213824)、[CryptoBriefing](https://cryptobriefing.com/matraix-simulation-harvard-mit-ai-personas/)、[Startup Fortune](https://startupfortune.com/harvard-and-mit-built-an-ai-model-of-83-billion-people-to-test-products-on/) 等。
- **[2026-08-04]** 技術報告發布於 arXiv：[MatrAIx: Simulating the World with 8.3 Billion Persona Agents](https://arxiv.org/abs/2608.04205)（`2608.04205`）。
- **[2026-08-01]** 在 Hugging Face 發布 [Persona 1M](https://huggingface.co/datasets/MatrAIx2026/MatrAIx_Persona_1M_Public_Release)（約 100 萬條品質過濾人格）。
- **[2026-07-31]** 開源 Playground 與任務庫：[MatrAIx-Persona-8B](https://github.com/MatrAIx-ai/MatrAIx-Persona-8B)。
- **[2026-07-29]** 立場短文：[From Personas to Simulated Users](https://matraix.ai/research/survey-from-personas-to-simulated-users.html)。

## 環境需求

- [Docker](https://docs.docker.com/get-docker/)
- [uv](https://docs.astral.sh/uv/) 與 Python 3.12
- Node.js 20+（僅 Playground / viewer 前端需要）
- 人格 Agent 範例所需的模型 API Key —— 見 [agents.md](../environment/agents.md)

## 安裝

```bash
git clone <repo-url> && cd MatrAIx
uv venv --python 3.12
uv pip install -e .
uv pip install pytest pytest-asyncio httpx
uv pip install -e packages/playground
uv pip install -e packages/harbor-langsmith
uv pip install -e packages/rewardkit
```

所有 Matraix Playground 指令以 **`uv run harbor …`** 形式執行。

在 GUI 或 CLI 任務執行前，設定與你的提供者相符的模型 API Key（smoke test 不需要）：

```bash
export ANTHROPIC_API_KEY="sk-ant-..."   # anthropic/claude-* 模型
# export OPENAI_API_KEY="sk-..."        # openai/gpt-* 模型
```

完整 Key 對照見 [agents.md](../environment/agents.md)。
Playground 也可從 `application/playground/.env.local` 載入 Key。

### 匯入 Persona 1M（可選）

```bash
huggingface-cli download MatrAIx2026/MatrAIx_Persona_1M_Public_Release \
  --repo-type dataset \
  --local-dir persona/datasets/matraix-persona-1m/release
```

Playground：Dataset → **`matraix-persona-1m`**。CLI：`--dataset persona/datasets/matraix-persona-1m`。
詳情：[Handbook § Persona 1M](../README.md#3-persona-1m-optional)。

## 快速開始

### Smoke test

無需 API Key。**需要 Docker**（smoke job 使用 `environment.type: docker`）：

```bash
uv run harbor run -c configs/jobs/example-job-recipe/harbor-smoke-local.yaml
```

### GUI 任務執行

Playground 可選擇任務、抽樣人格，並啟動與 CLI auto 模式相同的 Matraix Playground job。
啟動 API + 前端（兩個終端機）：

```bash
# 終端機 A — API
VENV=.venv bash application/playground/backend/run_dev.sh

# 終端機 B — 前端
cd application/playground/frontend && npm ci && npm run dev
```

開啟 **http://localhost:5173** → Playground → 選擇人格 cohort →
選擇 Survey / Chat / Web / OS app 任務 → **Lock pipeline** → **Run eval**。
詳情：[Playground §10](../quickstart.md#10-playground--play-tasks-visually)。

### CLI 任務開發 / 執行

**開發** — 複製 `application/tasks/` 下的參考任務，編輯
`task.toml` / `instruction.md` / `input/` / verifier，再註冊到 Playground
（[task-guide.md](../application/task-guide.md)）：

```bash
cp -R application/tasks/example-survey_product-feedback \
  application/tasks/<your-task-name>
```

| 類型 | 參考任務 |
|------|----------|
| Survey | `application/tasks/example-survey_product-feedback` |
| Chat | `application/tasks/example-chat-api_support_chatbot` |
| Web | `application/tasks/example-web-playwright_quote-choice` |
| OS-app | `application/tasks/example-computer-use-linux_note-to-csv` |

**執行** — 產生 Matraix Playground job（固定 agent + model），再執行：

```bash
uv run python application/scripts/generate_application_job.py \
  --task application/tasks/example-survey_product-feedback \
  --execution-mode auto \
  --persona-ids 0042 \
  --model-name anthropic/claude-sonnet-4-6

# 使用腳本列印的 export 行與 recipe 路徑，例如：
uv run harbor run -c configs/jobs/application-task-job-recipe/example-survey-product-feedback-auto-n1.yaml
```

批次（`--sample-size N`）、過濾條件，以及 chat / web / os-app 範例見：
[docs/quickstart.md](../quickstart.md)。

## 文件

**[MatrAIx Handbook](../README.md)** — 指南，以及 persona / application / environment 文件。

<p align="center">
  <img src="../assets/matraix-architecture.png" alt="MatrAIx 架構" width="900">
</p>

## 儲存庫結構

```text
MatrAIx/
├── persona/                 Schema、資料集、合成/策展/驗證流水線
│   ├── schema/              1,290 維人格 Schema
│   ├── datasets/            開發樣本池與人格 YAML
│   ├── validation/          Grounding / 品質驗證套件
│   └── scripts/             人格 job 與流水線輔助腳本
├── application/
│   ├── tasks/               Survey · chat · web · os-app 任務規格
│   ├── task-spec/           共用任務契約
│   ├── playground/          視覺化執行器（後端 API + 前端）
│   └── scripts/             generate_application_job.py 與任務工具
├── environment/
│   ├── runtime/             Matraix Playground runtime
│   ├── agents/              人格條件化 Agent
│   ├── task-environments/   Docker 映像 / sidecar
│   └── adapters/            外部適配器（如 SimpleQA）
├── packages/                playground · rewardkit · harbor-langsmith
├── apps/viewer/             與 `harbor view` 配對的前端
├── configs/jobs/            策展與產生的 Matraix Playground job recipe
├── docs/                    Handbook — persona/ · application/ · environment/
├── examples/                最小範例任務
├── src/matraix/             Python 套件入口
├── scripts/                 儲存庫級輔助腳本
├── tests/                   單元 / 環境測試
└── jobs/                    本機 Matraix Playground 執行輸出（gitignore）
```

大型產生資料集不納入 git（見上方 Hugging Face 發布）。

## 加入社群

[![Discord](https://img.shields.io/badge/Discord-join%20MatrAIx-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/knVyQQnRFa)
[![X](https://img.shields.io/badge/X-follow%20%40MatrAIx2026-000000?style=for-the-badge&logo=x&logoColor=white)](https://x.com/MatrAIx2026)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-follow%20MatrAIx-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/company/matraix)
[![Google Form](https://img.shields.io/badge/Google%20Form-join%20MatrAIx-4285F4?style=for-the-badge&logo=googleforms&logoColor=white)](https://forms.gle/hwEHng5HGWRqcJue9)

1. 加入 Discord —— 暱稱格式 **`Full Name - Affiliation`**。填寫 Google Form
   （背景、興趣、論文署名 / 致謝意向）。
2. 來打個招呼！我們很樂意按共同興趣或經歷幫你對接。
3. 參與 MatrAIx 研究社群，一起協作或貢獻！

## 引用

若你使用 MatrAIx、Persona 1M 資料集或本倉庫中的結果，請引用：

```bibtex
@article{li2026matraix,
  title         = {MatrAIx: Simulating the World with 8.3 Billion Persona Agents},
  author        = {Li, Xiaomin and Hao, Yuexing and Hou, Jianheng and Huang, Jintao
                   and Wen, Qianfeng and Huang, Shirley and Liu, Yifan and Liu, Xiaoyi
                   and Fan, Yilan and Wang, Yijun and others},
  year          = {2026},
  eprint        = {2608.04205},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url           = {https://arxiv.org/abs/2608.04205}
}
```

論文：[arXiv:2608.04205](https://arxiv.org/abs/2608.04205) ·
完整作者名單：GitHub **Cite this repository**（`CITATION.cff`） ·
資料集：[Persona 1M on Hugging Face](https://huggingface.co/datasets/MatrAIx2026/MatrAIx_Persona_1M_Public_Release)。

## Star History

<a href="https://www.star-history.com/?repos=MatrAIx-ai%2FMatrAIx-Persona-8B&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=MatrAIx-ai/MatrAIx-Persona-8B&type=date&theme=dark&legend=top-left&sealed_token=Yg8UrFwz3ELwyx6wW2CobWIwzUg_VZv53wOwlLji13fApPKuro445vOLW1W5Vy_NfU4NUON-ARepltF9i1-YiNiuSzMK4BVrFHURZLQMoAkeeh4uaxqysfKvTrPQ1cW6zXotcAwoUlKv5Ana5kuWGQj0e-wZoNDaJ6QVL7c8adFut281xX5Quo0c07Y7" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=MatrAIx-ai/MatrAIx-Persona-8B&type=date&legend=top-left&sealed_token=Yg8UrFwz3ELwyx6wW2CobWIwzUg_VZv53wOwlLji13fApPKuro445vOLW1W5Vy_NfU4NUON-ARepltF9i1-YiNiuSzMK4BVrFHURZLQMoAkeeh4uaxqysfKvTrPQ1cW6zXotcAwoUlKv5Ana5kuWGQj0e-wZoNDaJ6QVL7c8adFut281xX5Quo0c07Y7" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=MatrAIx-ai/MatrAIx-Persona-8B&type=date&legend=top-left&sealed_token=Yg8UrFwz3ELwyx6wW2CobWIwzUg_VZv53wOwlLji13fApPKuro445vOLW1W5Vy_NfU4NUON-ARepltF9i1-YiNiuSzMK4BVrFHURZLQMoAkeeh4uaxqysfKvTrPQ1cW6zXotcAwoUlKv5Ana5kuWGQj0e-wZoNDaJ6QVL7c8adFut281xX5Quo0c07Y7" />
 </picture>
</a>

## 授權條款

MIT —— 見 [LICENSE](../../LICENSE)。
