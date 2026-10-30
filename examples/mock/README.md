# Mock 运行记录

这里的“模型”是写死的模拟器，文案和修改策略都是预设的，工具是真实执行的。这些记录只用来检查流程，比如缺信息、工具出错、达到上限时程序会不会正确结束，不能说明模型的决策能力。

| 目录 | 结果 | 说明 |
| --- | --- | --- |
| normal | completed，23.8 秒 | 3 个分镜 |
| missing_info | needs_input | 用中文问目标时长 |
| no_material | insufficient_material | 换查询后仍无素材 |
| tool_failure | completed，23.8 秒 | 第一次检索出错后重试成功 |
| duration_revision | completed，23.8 秒 | 先给一份故意写长的稿子，超时后换回正常稿 |
| step_limit | step_limit_reached | 工具次数用完 |

在仓库根目录复现：

```sh
python3 -m src.cli --input examples/mock/normal/input.json --model mock --output-dir runs/mock-normal
python3 -m src.cli --input examples/mock/missing_info/input.json --model mock --output-dir runs/mock-missing
python3 -m src.cli --input examples/mock/no_material/input.json --model mock --output-dir runs/mock-empty
python3 -m src.cli --input examples/mock/tool_failure/input.json --model mock --fail-tool search_materials --output-dir runs/mock-error
python3 -m src.cli --input examples/mock/duration_revision/input.json --model mock --scenario duration_revision --output-dir runs/mock-revision
python3 -m src.cli --input examples/mock/step_limit/input.json --model mock --scenario limit --max-tools 3 --output-dir runs/mock-limit
```

未完成的任务返回退出码 1，这是正常的。
