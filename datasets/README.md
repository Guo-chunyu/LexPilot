# Synthetic labor cases

`synthetic_cases/` 中的案例由确定性模板生成，用于环境、策略、DQN 和回归测试。所有案例均包含 `human_reviewed: false` 与 `pending_law_student_review` 标记；在法学成员完成审核前，不得把这些案例当作法律真值、训练标注或对外法律意见。

重新生成：

```bash
python scripts/generate_synthetic_cases.py
```

