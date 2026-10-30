# 短视频脚本 Agent

给短视频创作者写产品介绍脚本。输入主题、受众、平台、目标时长和风格，Agent 先检索产品素材，再起草脚本，用工具估算时长、检查事实和品牌规则，根据检查结果修改，直到通过或说明为什么做不到。

输出包括标题、分镜（画面 / 旁白 / 字幕 / 预计时长）、总时长、素材来源 ID、检查结果、风险和任务状态。

## 结果一览

| 场景 | 结果 | 记录 |
| --- | --- | --- |
| 正常生成（目标 30 秒） | 24.1 秒，4 个分镜，引用 P01，检查全部通过 | [输出](examples/live/normal/output.json) · [Trace](examples/live/normal/trace.jsonl) |
| 超时后修正 | 首稿 36.2 秒超时，模型压缩到 20.1 秒后重新检查通过 | [输出](examples/live/duration_revision/output.json) · [Trace](examples/live/duration_revision/trace.jsonl) |
| 工具失败 | 检索报临时错误，模型重试成功，最终 22.8 秒 | [输出](examples/live/tool_failure/output.json) · [Trace](examples/live/tool_failure/trace.jsonl) |
| 缺关键信息 | 用中文问句请求补充目标时长 | [记录](examples/live/missing_info/) |
| 无素材 | 换一种说法再检索仍无结果，请求补充资料 | [记录](examples/live/no_material/) |
| 产品声明检测（36 句） | 语义复核 35/36 符合预期，留出集 20/20 | [逐句结果](examples/checker/claim-eval-live.json) |

以上都是真实模型（gpt-5.4-mini-2026-03-17）的运行结果。限制和失败案例见 [评估报告](docs/03-evaluation.md)。

## 运行

需要 Python 3.10+，只用标准库，离线模式不需要密钥：

```sh
python3 -m unittest discover -s tests -v
python3 -m src.cli --input examples/inputs/normal.json --model mock --output-dir runs/normal
```

Mock 模式用固定策略代替模型，只用来检查流程能不能跑通，不能说明模型的决策能力。

用真实模型时，参照 `.env.example` 在本地建一个 `.env`：

```sh
python3 -m src.cli --input examples/inputs/normal.json --model live --env-file .env \
  --api responses --reasoning-effort medium --timeout 60 --output-dir runs/live-normal
```

每次运行会在输出目录写入 `input.json`、`output.json`、`trace.jsonl`。退出码：0 表示完成，1 表示任务未完成（如缺信息、无素材），2 表示配置或输入有误。

常用参数：

- `--api`：默认 `responses`，兼容服务可用 `chat`。
- `--max-tools` / `--max-rounds`：工具调用和模型轮数上限，默认 10 和 12，只能调低。
- `--fail-tool`：让指定工具第一次调用失败，用于测试错误处理。
- `--scenario`：只对 Mock 有效。

## 检查已保存的结果

下面的命令不联网、不调用模型，用来核对仓库里的运行记录：

```sh
python3 -m examples.live.verify_results        # 五个场景的输出、时长、引用
python3 -m examples.live.verify_semantic_runs  # 三条新记录的语义复核是否来自真实返回
python3 -m examples.checker.verify_claim_eval  # 36 句评估的输入、输出和代码版本
python3 -m examples.checker.run_claim_eval     # 词法层在评估集上的结果
```

重新跑 36 句真实评估（会产生 36 次模型调用）：

```sh
python3 -m examples.checker.run_claim_eval --judge live --env-file .env \
  --api responses --reasoning-effort medium --timeout 60
```

## 文档

- [需求与验收标准](docs/01-requirements.md)
- [方案设计](docs/02-solution.md)
- [评估结果与限制](docs/03-evaluation.md)
- [AI 使用与个人贡献](docs/04-ai-usage.md)
- [复盘](docs/05-retrospective.md)
- [提交说明](docs/06-submission.md)
- [真实运行记录](examples/live/README.md) · [Mock 记录](examples/mock/README.md)

## 打包

```sh
python3 scripts/package_submission.py
```

生成 `dist/submission.zip` 和文件哈希清单，不包含 `.env`、`.git`、缓存和 `runs/`。
