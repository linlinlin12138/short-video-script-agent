# 短视频脚本 Agent

帮助短视频创作者生成有事实依据、符合时长、可以编辑和拍摄的脚本。输入主题、受众、平台、目标时长和风格；输出标题、分镜、旁白/字幕、各镜和总时长、素材来源、风险与任务状态。

## 最终验证结果

| 验证项目 | 最终结果 | 证据 |
| --- | --- | --- |
| 正常生成，目标30秒 | completed，24.1秒、4镜，真实语义审核通过 | [输出](examples/live/normal/output.json)、[Trace](examples/live/normal/trace.jsonl) |
| 超时后修正，目标30秒 | 36.2秒 → 模型压缩为20.1秒，重新检查通过，无门禁拒绝 | [输出](examples/live/duration_revision/output.json)、[Trace](examples/live/duration_revision/trace.jsonl) |
| 临时工具失败 | 检索失败 → 模型重试成功 → completed，22.8秒，真实语义审核通过 | [输出](examples/live/tool_failure/output.json)、[Trace](examples/live/tool_failure/trace.jsonl) |
| 固定36句真实语义评估 | 语义/最终层35/36符合预期；留出集20/20；无调用错误 | [逐句结果](examples/checker/claim-eval-live.json)、[完整Trace](examples/checker/claim-eval-live.trace.jsonl) |
| 自动化与离线核对 | 53项测试通过；真实场景审计、36句结果及代码版本核对通过 | [评估报告](docs/03-evaluation.md) |

三条成稿来自独立执行，最终检查均与真实模型返回对应。超时场景共采样4次，完整记录全部保留，不将选中的修正路径当作稳定成功率。缺信息、无素材路径保留语义层加入前的历史记录。语义审核仍漏检“做出爆款视频”，同次误拦标题；35/36是小样本单次结果，不代表通用准确率。

仓库：[linlinlin12138/short-video-script-agent](https://github.com/linlinlin12138/short-video-script-agent)。本次检查确认当前账号可读写，仓库为**私有**，匿名访问返回404；尚未核对指定评审账号权限。提交版本以GitHub提交链接及`git rev-parse HEAD`输出为准，不能把评估时补录清单里的旧HEAD当作最终提交。

## 运行

Python 3.10+，应用、测试和离线复核均只用标准库；Mock 不需要密钥。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m src.cli --input examples/inputs/normal.json --model mock --output-dir runs/normal
```

也可以直接用系统 python3 执行同样的模块命令。

真实模型配置见 .env.example；在本地创建 .env 填写变量，不提交密钥。已有进程环境变量优先，环境文件只作为文本读取。

```sh
python3 -m src.cli --input examples/inputs/normal.json --model live --env-file .env --api responses --reasoning-effort medium --timeout 60 --output-dir runs/live-normal
```

默认 Responses；兼容服务可选择 --api chat。推理参数是可选项，仅用于支持它的模型。本次 gpt-5.4-mini-2026-03-17 的 Chat 接口实际拒绝“函数工具+low推理”组合，因此真实改进用例采用 Responses。当前保存的采样包含不同推理配置，详见 Trace，不做跨配置成功率比较。

每次写出 input.json、output.json、trace.jsonl。退出码0为完成、1为明确未完成、2为配置/输入错误。默认10次工具调用、12轮模型决策、单次请求45秒；--timeout 可设至60秒，--max-tools/--max-rounds 可下调。--data-dir 指定资料，--fail-tool 注入一次临时工具错误；--scenario 只适用于Mock。

## 评审入口

- [需求与验收条件](docs/01-requirements.md)
- [方案与代码职责](docs/02-solution.md)
- [实际结果、失败及限制](docs/03-evaluation.md)
- [AI使用与个人贡献](docs/04-ai-usage.md)
- [复盘](docs/05-retrospective.md)
- [提交说明](docs/06-submission.md)
- [真实输入、输出和Trace](examples/live/README.md)
- [离线Mock说明](examples/mock/README.md)
- [输出Schema](schemas/output.schema.json)

已有结果可以离线复核，不消耗模型额度：

```sh
python3 -m examples.live.verify_results
python3 -m examples.live.verify_semantic_runs
python3 -m examples.checker.verify_claim_eval
python3 -m examples.tools.run_examples
python3 -m examples.checker.run_regression
python3 -m examples.checker.run_claim_eval
```

用真实判定模型评估产品声明检测（每句一次模型调用，共36次）：

```sh
python3 -m examples.checker.run_claim_eval --judge live --env-file .env --api responses --reasoning-effort medium --timeout 60
```

固定36句真实评估已执行：语义层及最终层 **35/36** 符合预期，留出集 **20/20**；“做出爆款视频”仍漏检，并在同次误拦标题。详见 [评估报告](docs/03-evaluation.md) 和 [逐句结果](examples/checker/claim-eval-live.json)。本次单轮小样本结果不代表通用准确率。

新评估Trace已绑定[代码版本清单](examples/checker/claim-eval-live.runtime-manifest.json)与完整源码快照，内容版本为`8a11784b006e`（完整SHA-256见清单，运行后补录）。执行`python3 -m examples.checker.verify_claim_eval`可离线核对代码、输入、输出和Trace的一致性；这不产生新的模型判定。

时长为目标的三分之二至目标区间，30秒即20–30秒。产品声明逐字核验，非产品事实叙事允许创作；每句文案还交给判定模型做产品声明语义复核（live 用 OPENAI_JUDGE_MODEL，默认同 OPENAI_MODEL；Mock 用离线固定标注），程序校验判定结果，判定失败不算通过。词法风险信号在有判定模型时只作提示。两层都可能误判，不是事实证明；实际配音和成片仍未验证。

## 打包

```sh
python3 scripts/package_submission.py
```

生成 dist/submission.zip 和哈希清单，排除.env、Git元数据、缓存和runs。历史1.5秒样例在 examples/history/v1/，只说明旧版缺陷，不作为当前验收成果。个人贡献已记录；提交前仍须补充实际用时，并确认指定评审账号可读取私有仓库。压缩包只在明确要求时更新，本次最终文档与版本提交不重新生成压缩包。
