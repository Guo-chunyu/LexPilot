# Development Changelog

## 2026-09-02 - LexPilot 第一阶段

### Phase 0 - 仓库审计

- 完成 `REPO_AUDIT.md` 和 `IMPLEMENTATION_PLAN.md`。
- 确认原项目为公司法固定工作流，保留 RAG、GraphRAG、FastAPI、Streamlit、Judge 和工具注册资产。

### Phase 1-3 - 状态、领域模型与策略

- 建立唯一权威 `CaseState`，包含事实、证据、法源、争点、风险、评分、Judge、补偿和时间线。
- 建立六类劳动争议最小要素模型及证据规则。
- 新增四态 Evidence Gap、Active Inquiry、10 个离散 `LegalAction` 和完整节点映射。
- 实现 Rule-Based、Random 和可加载 DQN 的 `LegalPolicy`。

### Phase 4-5 - 动态工作流与 Agents

- 将 `backend/graph.py` 从固定公司法流水线改造成 Policy Router 条件路由。
- 新增 AskFact、Opponent、结构化 Judge 和 Final Report。
- 保留旧公司法 Agents/RAG 文件作为可复用资产，不再让其旧 `AgentState` 控制 LexPilot。

### Phase 6-10 - RL 环境、数据、评估与 DQN

- 新增 Gymnasium `LegalDecisionEnv`、8 维 observation、独立 reward breakdown。
- 生成 60 个简单/中等/复杂合成案例，并全部标记待法学审核。
- 新增 Random / Rule-Based / DQN 六项指标评估，输出 JSON/CSV。
- 实现 PyTorch DQN、Replay Buffer、Target Network、epsilon-greedy、训练、保存和加载。
- 增加安全动作掩码，仅过滤不可能或明显无效动作，不替策略对剩余动作排序。

### Phase 11 - API 与前端

- FastAPI 返回当前动作、理由、完整案件状态、时间线和 Final Report。
- Streamlit 增加案件健康度、Evidence Gap、当前动作和 Agent Decision Timeline。
- 增加可离线运行的验收脚本 `scripts/demo_acceptance.py`。

### 法律检索与工具

- 新增官方法源 URL、条文、摘要、`effective_from/effective_to` 元数据和时效检索接口。
- 现有向量库构建脚本可将劳动法源元数据并入原 Vector/BM25/RRF 管道。
- 新增确定性的 N、N+1、2N、未签合同双倍工资计算工具及依据回溯。

### 质量保障

- 新增 pytest，覆盖任务书最低测试项、时效检索、补偿、数据集、DQN 与验收 Demo。
- 训练模型与评估结果均基于未人工审核的合成环境，仅证明软件闭环，不代表法律效果。

### 2026-09-02 - 多轮交互与 DQN 开关修复

- Active Inquiry 能根据上一轮待回答问题理解“签了”“有的”“三年”等省略式回答，并支持常用中文数字。
- Streamlit 增加可用的 DQN 开关、checkpoint 校验和训练元数据显示。
- 用户输入与处理异常会保留在会话历史中，错误不再因立即 rerun 而消失。
- API 增加可选 `policy_type`，DQN checkpoint 在同一版本内缓存加载。
- 增加 Streamlit `AppTest` 多轮聊天和 DQN 控件回归测试。

### 2026-09-02 - 案件材料上传

- Streamlit 聊天输入支持 PDF、DOC/DOCX、PNG/JPG/WebP、TXT/MD、CSV、XLS/XLSX 多文件附件。
- 新增文件大小、扩展名、文件签名和 Office 解压体积校验，并使用 SHA-256 去重。
- PDF、DOCX、TXT/MD、CSV、XLSX 可本地抽取文字；图片和本机无法解析的旧 Office 文件明确标记解析状态。
- 上传材料自动匹配当前索证项，写入 `CaseState.uploaded_files` 与 Evidence Gap，并支持图片预览和原件下载。
- FastAPI 新增 multipart 证据上传接口；原件默认仅写入被 Git 忽略的本地材料目录。

### 2026-09-02 - 规则化产品路径与 Web 重构

- Web、FastAPI 与 LangGraph 生产路径固定为确定性规则决策，移除 DQN 开关、策略请求参数和 checkpoint 加载。
- Streamlit 改为双栏法律工作台：左侧多轮咨询，右侧案件概览、材料和阶段报告。
- 新增首屏常见情形入口、中文处理状态、证据解析状态、材料摘要与阶段报告下载。
- 新增暖白与深墨主题，统一字体、圆角、边框和语义色，不再依赖内部 CSS 选择器。
- 早期强化学习实验文件只作为历史研究记录保留，不参与 Web、API 或默认配置运行。

### 2026-09-02 - 多轮回答语义增强

- 案件状态直接保存待回答的事实 ID，不再依赖完整问题文字反查字段。
- 新增上下文布尔语义识别，可理解“告知并留存了”“明确说过并签字了”“从未说明过”等自然表达。
- 兼容旧会话中的历史问题措辞；明确表示“不清楚”时仍保留待确认状态。
- 将“是否告知录用条件”和“是否有留存证据”拆回事实与证据两个阶段，减少复合问题歧义。
- 文件去重同时比较原始哈希和提取文本指纹，避免 Office 容器时间戳变化造成重复登记。
