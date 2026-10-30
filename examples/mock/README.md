# 离线Mock记录

决策者是固定 Mock，不是真实模型；工具实际执行。每组保存输入、输出及Trace，run_start标记mock，输出risks说明边界。策略、文案和长稿测试输入均预设，不作为ReAct能力证据。

| 目录 | 实际终态 | 说明 |
| --- | --- | --- |
| normal | completed，23.8秒 | 三镜叙事+产品事实，满足20–30秒 |
| missing_info | needs_input | 中文问句请求目标时长 |
| no_material | insufficient_material | 改写查询后仍无素材 |
| tool_failure | completed，23.8秒 | 一次临时错误后恢复 |
| duration_revision | completed，23.8秒 | 人工构造长文本后按固定策略回到正常草稿 |
| step_limit | step_limit_reached | 工具预算耗尽 |

仓库根目录复现：

```sh
python3 -m src.cli --input examples/mock/normal/input.json --model mock --output-dir runs/mock-normal
python3 -m src.cli --input examples/mock/missing_info/input.json --model mock --output-dir runs/mock-missing
python3 -m src.cli --input examples/mock/no_material/input.json --model mock --output-dir runs/mock-empty
python3 -m src.cli --input examples/mock/tool_failure/input.json --model mock --fail-tool search_materials --output-dir runs/mock-error
python3 -m src.cli --input examples/mock/duration_revision/input.json --model mock --scenario duration_revision --output-dir runs/mock-revision
python3 -m src.cli --input examples/mock/step_limit/input.json --model mock --scenario limit --max-tools 3 --output-dir runs/mock-limit
```

未完成的退出码1是预期行为。旧版1.5秒样例见examples/history/v1/mock，不属于当前时长验收。
