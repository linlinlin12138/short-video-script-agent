# 离线 Mock 运行记录

这里的 input.json、output.json、trace.jsonl 来自实际 CLI 执行，但决策者是固定 Mock 模拟器，不是真实模型。每份 Trace 的 run_start 都标记 mode=mock，输出 risks 也说明限制。不得用这些记录声称已满足题目的真实模型 ReAct 验收。

| 目录 | 实际终态 | 工具调用数 | 说明 |
| --- | --- | --- | --- |
| normal | completed | 3 | 检索、估时、规则检查后结束 |
| missing_info | needs_input | 0 | 请求补充目标时长 |
| no_material | insufficient_material | 2 | 首次检索与改写查询均无命中 |
| tool_failure | completed | 4 | 观察一次注入的临时检索错误，重试后恢复 |
| duration_revision | completed | 4 | 首稿估时 40.5 秒；压缩为第二版后 1.5 秒，再检查规则 |
| step_limit | step_limit_reached | 3 | 消耗工具预算后停止，不执行第四次工具调用 |

在仓库根目录复现（未完成任务退出码为 1，这是预期行为）：

```sh
python3 -m src.cli --input examples/mock/normal/input.json --model mock --output-dir runs/normal
python3 -m src.cli --input examples/mock/missing_info/input.json --model mock --output-dir runs/missing_info
python3 -m src.cli --input examples/mock/no_material/input.json --model mock --output-dir runs/no_material
python3 -m src.cli --input examples/mock/tool_failure/input.json --model mock --fail-tool search_materials --output-dir runs/tool_failure
python3 -m src.cli --input examples/mock/duration_revision/input.json --model mock --scenario duration_revision --output-dir runs/duration_revision
python3 -m src.cli --input examples/mock/step_limit/input.json --model mock --scenario limit --max-tools 3 --output-dir runs/step_limit
```

Trace 中每个 decision 记录 step、action、arguments、reason 和 observation；有后续模型动作时，前一步另带 next_action、next_action_reason。task_end 记录最终状态。原始工具结果完整保留，便于核对分镜和检查版本。reason 只是简短公开说明，不是内部思维过程。

当前 normal 的 1.5 秒脚本是最小流程样例，未体现接近 30 秒的内容质量。duration_revision 的重复长文本专门用于触发超时，不是模型生成的真实文案。
