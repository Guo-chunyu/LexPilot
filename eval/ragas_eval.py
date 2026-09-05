"""
RAGAS evaluation using the official ragas library.
Run: python eval/ragas_eval.py
"""
import json, sys, time, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from openai import OpenAI
from langchain_core.messages import HumanMessage

from ragas import evaluate
from ragas.metrics import Faithfulness, ContextPrecision, ContextRecall
from ragas.llms import llm_factory

from backend.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL

TEST_CASES_FILE = os.path.join(os.path.dirname(__file__), "test_cases.json")


def run_eval(test_file: str = TEST_CASES_FILE):
    if not os.path.exists(test_file):
        print(f"[!] Test file not found: {test_file}")
        return

    with open(test_file, "r", encoding="utf-8") as f:
        cases = json.load(f)

    # Filter to LEGAL only (OOS and CHAT don't have context)
    legal_cases = [c for c in cases if c["type"] == "LEGAL"]
    print(f"RAGAS evaluation - {len(legal_cases)} LEGAL questions\n")

    # Setup RAGAS judge LLM (DeepSeek via OpenAI-compatible API)
    judge_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
    judge_llm = llm_factory(DEEPSEEK_MODEL, client=judge_client, max_tokens=2048)

    # Metrics (LLM-only, no embedding needed)
    metrics = [
        Faithfulness(llm=judge_llm),
        ContextPrecision(llm=judge_llm),
        ContextRecall(llm=judge_llm),
    ]

    # Run agent for each case and collect results
    from backend.graph import app

    eval_data = {"question": [], "answer": [], "contexts": [], "ground_truth": []}

    for i, case in enumerate(legal_cases):
        q = case["question"]
        gt = case.get("ground_truth", "")
        print(f"[{i+1}/{len(legal_cases)}] {q[:60]}...")

        config = {"configurable": {"thread_id": f"eval_{i}_{int(time.time())}"}}
        try:
            state = app.invoke({"messages": [HumanMessage(content=q)]}, config=config)
            answer = state["messages"][-1].content
            ctx_list = state.get("context", [])
        except Exception as e:
            answer = f"[Error: {e}]"
            ctx_list = []

        eval_data["question"].append(q)
        eval_data["answer"].append(answer)
        eval_data["contexts"].append(ctx_list)
        eval_data["ground_truth"].append(gt)

        time.sleep(0.5)

    # Run RAGAS evaluation
    print(f"\nRunning RAGAS metrics...")
    from ragas import EvaluationDataset
    import pandas as pd

    rows = []
    for i in range(len(eval_data["question"])):
        rows.append({
            "user_input": eval_data["question"][i],
            "response": eval_data["answer"][i],
            "retrieved_contexts": eval_data["contexts"][i],
            "reference": eval_data["ground_truth"][i],
        })

    dataset = EvaluationDataset.from_list(rows)
    results = evaluate(dataset=dataset, metrics=metrics)

    # Display results
    df = results.to_pandas()
    print("\n=== RAGAS Results ===\n")
    print(df[["user_input", "faithfulness", "context_precision", "context_recall"]].to_string())

    # Summary
    print("\n=== Averages ===")
    for col in ["faithfulness", "context_precision", "context_recall"]:
        if col in df.columns:
            avg = df[col].mean()
            print(f"  {col}: {avg:.1%}")

    # Save
    out = "LawAgent_Pro_RAGAS_Report.xlsx"
    df.to_excel(out, index=False)
    print(f"\nReport saved: {out}")


if __name__ == "__main__":
    run_eval()
