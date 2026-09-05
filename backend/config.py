"""
统一配置中心 [X] 所有模块从这里读取配置，不散落魔法值。
"""
import os
try:
    from dotenv import load_dotenv
except ImportError:  # Core policy/environment can run without optional app dependencies.
    def load_dotenv() -> bool:
        return False

load_dotenv()

# LexPilot local evidence storage
LEXPILOT_UPLOAD_DIR = os.getenv("LEXPILOT_UPLOAD_DIR", "./.local_data/uploads")

# LLM 
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-your-key-here")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
LLM_TEMPERATURE = 0
LLM_MAX_TOKENS = 4096

# Optional semantic enrichment. Credentials stay in the ignored local .env file
# and are never serialized into CaseState or sent to the Streamlit frontend.
QWEN_API_KEY = (
    os.getenv("DASHSCOPE_API_KEY", "").strip()
    or os.getenv("QWEN_API_KEY", "").strip()
)
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen3.8-flash")
QWEN_API_BASE = os.getenv(
    "QWEN_API_BASE",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
)
QWEN_ENABLE_THINKING = os.getenv("QWEN_ENABLE_THINKING", "true").lower() in {
    "1", "true", "yes", "on",
}
LLM_REQUEST_TIMEOUT_SECONDS = float(os.getenv("LLM_REQUEST_TIMEOUT_SECONDS", "8"))
LEXPILOT_ENABLE_SEMANTIC_AI = os.getenv("LEXPILOT_ENABLE_SEMANTIC_AI", "true").lower() in {
    "1", "true", "yes", "on",
}

# Embedding & Reranker 
EMBED_MODEL_NAME = "BAAI/bge-large-zh-v1.5"
RERANK_MODEL_NAME = "BAAI/bge-reranker-base" # 轻量级，CPU 友好
EMBED_DEVICE = "cpu"
HF_ENDPOINT = os.getenv("HF_ENDPOINT", "https://hf-mirror.com")
HF_HOME = os.getenv("HF_HOME", "./models_cache")
os.environ["HF_ENDPOINT"] = HF_ENDPOINT
os.environ["HF_HOME"] = HF_HOME

# 向量库 
CHROMA_DIR = "./law_chroma_db"
MEMORY_DB = "law_agent_memory.db"

# 检索参数 
VECTOR_K = 5 # 向量检索 Top K（瘦身到5）
BM25_K = 5 # BM25 检索 Top K
RERANK_CANDIDATE_K = 5 # 关键词粗筛后的候选数（原来的20[X]5）
RERANK_FINAL_K = 3 # 最终返回给 LLM 的文档数
JACCARD_THRESHOLD = 0.1 # 关键词粗筛阈值

# Multi-Query 
MULTI_QUERY_VARIANTS = 3
MULTI_QUERY_MIN_SCORE = 0.3 # Top-3 RRF分低于此值[X]触发扩展

# 数据文件 
LAW_MAIN_FILE = "./data/law_main.txt"
LAW_INTERPRET_FILE = "./data/law_interpret.txt"
KG_FILE = "./data/legal_kg.json"
LABOR_LAW_SOURCES_FILE = "./backend/legal_domain/labor/law_sources.yaml"

# Judge Agent 
JUDGE_MAX_RETRIES = 1 # 最多退回重试次数
JUDGE_PASS_THRESHOLD = 60 # 通过分数

# 法律摘要 (SAC) 
LAW_MAIN_SUMMARY = (
 "【本文为《中华人民共和国公司法》(2023修订版)，共15章266条，"
 "涵盖：公司设立与登记、股东权利与义务、"
 "组织机构(股东会/董事会/监事会/经理)、"
 "股权转让与回购、董监高资格与义务、"
 "财务与会计、合并分立增减资、解散清算、法律责任】"
)

LAW_INTERPRET_SUMMARY = (
 "【本文为《公司法》最高人民法院司法解释，涵盖：公司设立纠纷、"
 "股东资格确认、股权转让效力、公司决议效力、"
 "股东知情权与利润分配请求权、公司解散与清算等问题的司法适用规则】"
)
