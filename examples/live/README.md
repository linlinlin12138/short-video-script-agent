# 真实运行记录

生成模型和语义判定模型都是 gpt-5.4-mini-2026-03-17（Responses API，推理强度 medium）。

| 目录 | 结果 | 语义复核 | 工具调用 |
| --- | --- | --- | --- |
| [normal](normal/) | completed，24.1 秒，4 个分镜 | 通过 | 3 |
| [duration_revision](duration_revision/) | 36.2 秒超时 → 第 2 版 20.1 秒，completed | 通过 | 5 |
| [tool_failure](tool_failure/) | 检索临时出错 → 重试 → completed，22.8 秒 | 通过 | 4 |
| [missing_info](missing_info/) | needs_input，询问目标时长 | 未执行到检查 | 1 |
| [no_material](no_material/) | 换查询后仍无素材，请求补充资料 | 未执行到检查 | 2 |

前三条是加入语义复核后分别独立运行的，输入都是普通的 30 秒请求，没有提示怎么写或怎么改。原始运行目录和所有尝试在 [semantic-rerun](semantic-rerun/)，超时场景跑了 4 次，只有 1 次出现超时。

后两条是加入语义复核之前的记录，之后没有重跑。

每个目录包含：

- `input.json`、`output.json`、`trace.jsonl`：输入、结果，以及每一步的动作、参数、返回和下一步。
- `api-audit.json`（前三条）：语义判定的实际请求和返回，不含密钥和模型内部推理。
- `runtime-manifest.json`（前三条）：运行时源码和数据文件的哈希。

## 复核

不联网、不调用模型：

```sh
python3 -m examples.live.verify_semantic_runs   # 最终语义复核是否和 API 实际返回一致
python3 -m examples.live.verify_results         # 五个场景的时长、引用、版本和哈希
```

## 重新运行

先在本地配置 `.env`，输出目录要用新目录：

```sh
python3 -m scripts.run_live_acceptance --input examples/inputs/normal.json --model live --env-file .env \
  --api responses --reasoning-effort medium --timeout 60 --output-dir runs/new-normal
python3 -m scripts.run_live_acceptance --input examples/inputs/normal.json --model live --env-file .env \
  --api responses --reasoning-effort medium --timeout 60 --fail-tool search_materials --output-dir runs/new-tool-failure
python3 -m src.cli --input examples/live/missing_info/input.json --model live --env-file .env --output-dir runs/new-missing
python3 -m src.cli --input examples/live/no_material/input.json --model live --env-file .env --output-dir runs/new-no-material
```

模型输出不确定，重新运行的结果可能和这里不同。未完成的任务返回退出码 1，这是正常的。
