# 提交说明

| 项目 | 内容 |
| --- | --- |
| 题目 | 短视频脚本 Agent |
| 仓库 | [linlinlin12138/short-video-script-agent](https://github.com/linlinlin12138/short-video-script-agent) |
| 运行方式 | Python CLI，支持真实模型和离线 Mock |
| 依赖 | Python 3.10+，只用标准库 |
| 投入时间 | 约 3 小时（估计，未连续计时） |
| AI 辅助 | Codex、Claude，分工见 [AI 使用与个人贡献](04-ai-usage.md) |

评审版本以提交时填写的 commit SHA 为准。

## 建议的查看顺序

1. [README](../README.md)：先跑一下离线测试和 Mock。
2. [真实运行记录](../examples/live/README.md)：正常生成、超时修正、工具失败三条的输入、输出和 Trace。
3. [评估报告](03-evaluation.md)：各验收点的结果、36 句声明检测、失败案例和限制。
4. [方案设计](02-solution.md)、[AI 使用](04-ai-usage.md)、[复盘](05-retrospective.md)。

## 快速运行

```sh
python3 -m unittest discover -s tests -v
python3 -m src.cli --input examples/inputs/normal.json --model mock --output-dir runs/normal
```

不调用模型、核对已保存的真实记录：

```sh
python3 -m examples.live.verify_results
python3 -m examples.live.verify_semantic_runs
python3 -m examples.checker.verify_claim_eval
```

## 完成情况

已完成：素材检索、脚本生成、时长估算、事实和品牌检查、模型语义复核、根据检查结果修改并重新检查、明确的结束状态，以及工具调用和模型轮数上限。五个验收场景都有真实运行记录。

没有做：界面、线上部署、生产级运行环境。

主要限制：样本少，没有统计成功率；语义复核在 36 句评估中漏了 1 句；时长是按字数估算的。详见 [评估报告](03-evaluation.md#限制)。

`submission.zip` 是方便下载的副本，内容以 GitHub 上的提交为准。
