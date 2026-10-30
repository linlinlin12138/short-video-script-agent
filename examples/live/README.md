# 真实模型验收入口

normal、duration_revision、tool_failure已用最新语义复核版本独立重跑；旧的对应记录移至examples/history/pre-semantic-rerun。missing_info和no_material仍是此前历史记录，不宣称它们已接受本轮新版语义判定。

| 目录 | 最新实际结果 | 最终checks.semantic | 工具调用数 |
| --- | --- | --- | --- |
| normal | completed，24.1秒、4镜 | passed，真实判定 | 3 |
| duration_revision | 36.2秒 → 模型压缩第二版为20.1秒、4镜 | passed，真实判定 | 5 |
| tool_failure | 临时检索错误 → 重试 → completed，22.8秒、4镜 | passed，真实判定 | 4 |
| missing_info | 历史：询问目标时长 | 未重跑，不补写passed | 1 |
| no_material | 历史：两次查询无素材后请求补充 | 未重跑，不补写passed | 2 |

三条新记录的生成模型和判定模型均为gpt-5.4-mini-2026-03-17，Responses、medium。它们是独立执行，不复用同一次正常/超时记录；全程无GUARD_REJECTED。超时用例输入仍为普通30秒、简洁实用，无指定首稿分镜或修正动作。首稿和最终稿的真实语义判定均通过，模型根据时长反馈自行压缩。

每组包含input.json、output.json、trace.jsonl、api-audit.json、runtime-manifest.json。审计核对实际HTTP语义返回、最终句段覆盖、声明与来源、版本/哈希、最终估时及输出，见[详细重跑说明](semantic-rerun/README.md)。所有新尝试都保留在semantic-rerun，时长4次尝试中只有attempt-03出现超时，不将其余尝试冒充超时修正。

离线复核，不调用模型：

```sh
python3 -m examples.live.verify_semantic_runs
python3 -m examples.live.verify_results
```

第一条严格审计三个新场景及全部新尝试，第二条核对正式入口与对应证据副本，并保留两个历史场景的有限验证。真实语义passed不等于模型不会误判；36句真实判定评估尚未额外执行，不能把端到端三例当作留出集准确率。
