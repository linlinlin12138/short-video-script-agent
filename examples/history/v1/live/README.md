# 真实模型验收记录

模型：gpt-5.4-mini-2026-03-17；服务：用户配置的官方 API；日期：2026-10-30。主目录五组均由真实模型决定动作，工具在本地实际执行。每组保存 input.json、output.json、trace.jsonl。

| 目录 | 最终结果 | 工具调用数 |
| --- | --- | --- |
| normal | completed，1.5 秒 | 3 |
| missing_info | needs_input，询问目标时长 | 0 |
| no_material | insufficient_material | 1 |
| tool_failure | tool_error，明确未完成 | 1 |
| duration_revision | completed，4.5 秒 → 1.5 秒，版本 1 → 2 | 5 |

超时 Trace：检索 → 超时估算 → 第一版规则检查 → 尝试结束被门禁拒绝 → 模型提交第二版并估时 → 第二版规则检查 → 完成。没有预填修正版，也没有伪造估时。工具失败是测试注入；模型选择结束，并非成功恢复。

复现需要自行配置 .env（不入库），在仓库根目录执行：

```sh
python3 -m src.cli --input examples/live/normal/input.json --model live --env-file .env --output-dir runs/live-normal
python3 -m src.cli --input examples/live/missing_info/input.json --model live --env-file .env --output-dir runs/live-missing
python3 -m src.cli --input examples/live/no_material/input.json --model live --env-file .env --output-dir runs/live-no-material
python3 -m src.cli --input examples/live/tool_failure/input.json --model live --env-file .env --fail-tool search_materials --output-dir runs/live-tool-failure
python3 -m src.cli --input examples/live/duration_revision/input.json --model live --env-file .env --output-dir runs/live-revision
```

模型非确定性，新运行动作与结果可能不同。未完成任务返回退出码 1，不是 CLI 崩溃。无网络复核已有结果：`python3 -m examples.live.verify_results`。

## 保留的失败尝试

- attempts/normal_initial：误判一条事实无法生成脚本。
- attempts/*_before_strict：工具说明与参数约束收紧前的记录；包含错误索要资料、清单外表达，以及超时路径协议失败。
- attempts/duration_first_strict：参数收紧后仍过早宣布无法满足。
- attempts/duration_before_finish_guard：提示要求修正后，模型仍直接结束；随后增加程序结束门禁，最终主记录实际改稿成功。

历史尝试对应不同开发阶段，不保证用当前代码复现相同结果。当前评估不把历史失败删除后声称一次通过，也不将用例数量当作统计成功率。
