# LexPilot 第一阶段实施计划

## 验收优先级

1. 可离线运行并通过测试。
2. 统一状态与真实 Policy 路由闭环。
3. 劳动争议 Demo 可交互、可解释、可追踪。
4. Random / Rule-Based / DQN 可在同一环境比较。
5. 复用现有 RAG、FastAPI 与 Streamlit，避免无关重写。

## 分阶段实施

| Phase | 交付内容 | 验证方式 |
|---|---|---|
| 0 | `REPO_AUDIT.md`、本计划 | 架构与模块清单审阅 |
| 1 | `CaseState`、六类劳动争议模型 | 状态更新与领域配置测试 |
| 2 | Evidence Gap、Active Inquiry | 四种证据状态与问题优先级测试 |
| 3 | `LegalAction`、Action Mapping、Rule/Random/RL Policy | 映射完整性与策略顺序测试 |
| 4 | LangGraph Policy Router | 每个离散动作路由到真实节点；状态回流 |
| 5 | Opponent、结构化 Judge | 风险、缺证与 `can_stop` 测试 |
| 6 | Gymnasium 风格 `LegalDecisionEnv` | `reset/step`、终止和截断测试 |
| 7 | 8 维 Observation、独立 Reward | 归一化与 reward breakdown 测试 |
| 8 | 60 个合成劳动争议案例 | Schema 校验、难度分层、人工审核标记 |
| 9 | Policy Evaluation | JSON/CSV 输出六项指标 |
| 10 | PyTorch DQN baseline | 回放池、目标网络、训练、保存、加载、评估 |
| 11 | Streamlit 状态面板与决策时间线 | 本地 Demo 与 API smoke test |

## 统一状态原则

`CaseState` 是事实、证据、法源、争点、风险、评分、对方抗辩、Judge 结果、补偿估算和动作历史的唯一权威来源。LangGraph 只编排节点，不承载散落的业务判断；RL/DQN 只读取归一化向量，不直接读取 Pydantic 大对象或生成自然语言。

## 测试门槛

- 所有核心测试不调用 DeepSeek、Embedding 或外网。
- `pytest` 覆盖任务书列出的八类最低测试，并增加补偿、时效检索、报告和验收 Demo。
- 训练与评估使用固定随机种子，保证结果可复现。
- DQN 训练的目标是流程闭环和接口正确，不把一次短训练结果宣称为法律决策质量证明。

