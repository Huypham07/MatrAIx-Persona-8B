<div align="center">
  <h1>MatrAIx</h1>
  <p><strong>Simulate before reality.</strong></p>
  <p>
    面向异构模拟用户的大规模、人格驱动基础设施，用于评估 AI 系统与交互式产品。
  </p>
  <p>
    <a href="../../README.md">English</a> |
    <a href="README.ko.md">한국어</a> |
    <strong>简体中文</strong> |
    <a href="README.zh-TW.md">繁體中文</a> |
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
    <img src="https://img.youtube.com/vi/cNFkz9Wo1y4/maxresdefault.jpg" alt="在 YouTube 上观看 MatrAIx 演示" width="900">
  </a>
  <p>
    <a href="https://www.youtube.com/watch?v=cNFkz9Wo1y4&t=15s"><img alt="在 YouTube 上观看 MatrAIx 演示" src="https://img.shields.io/badge/%E2%96%B6%20Watch%20the%20demo-on%20YouTube-FF0000?style=for-the-badge&logo=youtube&logoColor=white"></a>
  </p>
</div>

---

**MatrAIx** 是一套面向异构模拟用户的大规模、人格驱动基础设施，用于评估 AI 系统与交互式产品。它不依赖「通用」或可互换的用户假设，而是将抽样得到的人格记录实例化为 LLM Agent，并在四类环境中以可复现任务驱动运行 —— **Survey（问卷）**、**AI Chatbot（对话）**、**Web**，以及 **App**（原生桌面与移动端，含 macOS 与 iOS）。

其基础是一套共享的 **1,290 个类别维度** 人格 Schema，覆盖背景、心理、能力与行为。人格结合依赖感知的合成生成与证据感知的人类 grounding；经确定性、质量过滤的 **百万人格** 共集（coreset）已在
[Hugging Face](https://huggingface.co/datasets/MatrAIx2026/MatrAIx_Persona_1M_Public_Release)
公开发布，供研究使用。共享遥测、任务自有验证与报告能力，将个体响应与轨迹连接到子群体与总体层面的发现。

名称致敬 *The Matrix*：这是一个便于探索、压力测试与假设生成的模拟世界，**不能替代来自真实人群的证据**。

## 环境要求

- [Docker](https://docs.docker.com/get-docker/)
- [uv](https://docs.astral.sh/uv/) 与 Python 3.12
- Node.js 20+（仅 Playground / viewer 前端需要）
- 人格 Agent 示例所需的模型 API Key —— 见 [agents.md](../environment/agents.md)

## 安装

```bash
git clone <repo-url> && cd MatrAIx
uv venv --python 3.12
uv pip install -e .
uv pip install pytest pytest-asyncio httpx
uv pip install -e packages/playground
uv pip install -e packages/harbor-langsmith
uv pip install -e packages/rewardkit
```

所有 Matraix Playground 命令以 **`uv run harbor …`** 形式运行。

在 GUI 或 CLI 任务运行前，设置与你的提供商匹配的模型 API Key（smoke test 不需要）：

```bash
export ANTHROPIC_API_KEY="sk-ant-..."   # anthropic/claude-* 模型
# export OPENAI_API_KEY="sk-..."        # openai/gpt-* 模型
```

完整 Key 对照见 [agents.md](../environment/agents.md)。
Playground 也可从 `application/playground/.env.local` 加载 Key。

### 导入 Persona 1M（可选）

```bash
huggingface-cli download MatrAIx2026/MatrAIx_Persona_1M_Public_Release \
  --repo-type dataset \
  --local-dir persona/datasets/matraix-persona-1m/release
```

Playground：Dataset → **`matraix-persona-1m`**。CLI：`--dataset persona/datasets/matraix-persona-1m`。
详情：[Handbook § Persona 1M](../README.md#3-persona-1m-optional)。

## 快速开始

### Smoke test

无需 API Key。**需要 Docker**（smoke job 使用 `environment.type: docker`）：

```bash
uv run harbor run -c configs/jobs/example-job-recipe/harbor-smoke-local.yaml
```

### GUI 任务运行

Playground 可选择任务、抽样人格，并启动与 CLI auto 模式相同的 Matraix Playground job。
启动 API + 前端（两个终端）：

```bash
# 终端 A — API
VENV=.venv bash application/playground/backend/run_dev.sh

# 终端 B — 前端
cd application/playground/frontend && npm ci && npm run dev
```

打开 **http://localhost:5173** → Playground → 选择人格 cohort →
选择 Survey / Chat / Web / OS app 任务 → **Lock pipeline** → **Run eval**。
详情：[Playground §10](../quickstart.md#10-playground--play-tasks-visually)。

### CLI 任务开发 / 运行

**开发** — 复制 `application/tasks/` 下的参考任务，编辑
`task.toml` / `instruction.md` / `input/` / verifier，再注册到 Playground
（[task-guide.md](../application/task-guide.md)）：

```bash
cp -R application/tasks/example-survey_product-feedback \
  application/tasks/<your-task-name>
```

| 类型 | 参考任务 |
|------|----------|
| Survey | `application/tasks/example-survey_product-feedback` |
| Chat | `application/tasks/example-chat-api_support_chatbot` |
| Web | `application/tasks/example-web-playwright_quote-choice` |
| OS-app | `application/tasks/example-computer-use-linux_note-to-csv` |

**运行** — 生成 Matraix Playground job（固定 agent + model），再执行：

```bash
uv run python application/scripts/generate_application_job.py \
  --task application/tasks/example-survey_product-feedback \
  --execution-mode auto \
  --persona-ids 0042 \
  --model-name anthropic/claude-sonnet-4-6

# 使用脚本打印的 export 行与 recipe 路径，例如：
uv run harbor run -c configs/jobs/application-task-job-recipe/example-survey-product-feedback-auto-n1.yaml
```

批量（`--sample-size N`）、过滤条件，以及 chat / web / os-app 示例见：
[docs/quickstart.md](../quickstart.md)。

## 文档

**[MatrAIx Handbook](../README.md)** — 指南，以及 persona / application / environment 文档。

<p align="center">
  <img src="../assets/matraix-architecture.png" alt="MatrAIx 架构" width="900">
</p>

## 仓库结构

```text
MatrAIx/
├── persona/                 Schema、数据集、合成/策展/验证流水线
│   ├── schema/              1,290 维人格 Schema
│   ├── datasets/            开发样本池与人格 YAML
│   ├── validation/          Grounding / 质量验证套件
│   └── scripts/             人格 job 与流水线辅助脚本
├── application/
│   ├── tasks/               Survey · chat · web · os-app 任务规格
│   ├── task-spec/           共享任务契约
│   ├── playground/          可视化运行器（后端 API + 前端）
│   └── scripts/             generate_application_job.py 与任务工具
├── environment/
│   ├── runtime/             Matraix Playground runtime
│   ├── agents/              人格条件化 Agent
│   ├── task-environments/   Docker 镜像 / sidecar
│   └── adapters/            外部适配器（如 SimpleQA）
├── packages/                playground · rewardkit · harbor-langsmith
├── apps/viewer/             与 `harbor view` 配对的前端
├── configs/jobs/            策展与生成的 Matraix Playground job recipe
├── docs/                    Handbook — persona/ · application/ · environment/
├── examples/                最小示例任务
├── src/matraix/             Python 包入口
├── scripts/                 仓库级辅助脚本
├── tests/                   单元 / 环境测试
└── jobs/                    本地 Matraix Playground 运行输出（gitignore）
```

大型生成数据集不纳入 git（见上方 Hugging Face 发布）。

## 加入社区

[![Discord](https://img.shields.io/badge/Discord-join%20MatrAIx-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/knVyQQnRFa)
[![X](https://img.shields.io/badge/X-follow%20%40MatrAIx2026-000000?style=for-the-badge&logo=x&logoColor=white)](https://x.com/MatrAIx2026)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-follow%20MatrAIx-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/company/matraix)
[![Google Form](https://img.shields.io/badge/Google%20Form-join%20MatrAIx-4285F4?style=for-the-badge&logo=googleforms&logoColor=white)](https://forms.gle/hwEHng5HGWRqcJue9)

1. 加入 Discord —— 昵称格式 **`Full Name - Affiliation`**。填写 Google Form
   （背景、兴趣、论文署名 / 致谢意向）。
2. 来打个招呼！我们很乐意按共同兴趣或经历帮你对接。
3. 参与 MatrAIx 研究社区，一起协作或贡献！

## 许可证

MIT —— 见 [LICENSE](../../LICENSE)。
