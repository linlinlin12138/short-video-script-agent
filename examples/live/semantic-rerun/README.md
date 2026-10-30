# 最新版三个独立真实场景

本轮运行语义复核版本的原始CLI，Agent、工具、提示词和判定器业务代码未改动。生成及判定均使用gpt-5.4-mini-2026-03-17、Responses、medium。input均为普通30秒、简洁实用的字幕主题；工具失败仅额外注入一次本地检索临时错误。

| 场景与选中目录 | 总时长 | 最终版本 | 最终语义句段数 | 最终checks.semantic |
| --- | --- | --- | --- | --- |
| [normal/attempt-01](normal/attempt-01/) | 24.1秒 | 1 | 15 | passed，live |
| [duration_revision/attempt-03](duration_revision/attempt-03/) | 36.2 → 20.1秒 | 2 | 13 | passed，live |
| [tool_failure/attempt-01](tool_failure/attempt-01/) | 22.8秒，错误后重试成功 | 1 | 13 | passed，live |

三条是独立执行、不同的最终判定响应ID，不共享一条Trace；三条均无GUARD_REJECTED。已复制到examples/live同名正式入口，原始执行路径仍保留在这里。

## 真实语义通过的证据

每次目录保存：

- input.json、output.json、trace.jsonl：CLI实际输入、结果、工具反馈及下一动作。
- api-audit.json：实际HTTP调用的模型、响应ID、哈希、语义请求中的全部句段和真实结构化判定；不保存认证头、密钥或内部推理，不替换API返回。
- runtime-manifest.json：执行时src、data、schemas文件哈希，用于确认是最新语义版本。

离线审计将最终check_rules草稿与对应真实judge_input精确匹配；确认输出semantic=passed、Trace中judge_mode=live、句段覆盖完整、产品声明被标为supported且引用P01-F1；使用保存的原始判定重放程序校验，再核对版本、哈希、逐镜时长及输出。重放标记为replay，不是新的live调用。

```sh
python3 -m examples.live.verify_semantic_runs
```

结果见[verification.json](verification.json)，选择映射见[selection.json](selection.json)。这证明该批实际记录的对应关系和通过状态，不证明判定模型不会误判。

## 全部尝试与采样边界

共6次新执行，全部保留：正常1次、工具失败1次、时长4次。时长attempt-01为18.8→29.9秒，attempt-02为25.6秒，attempt-03为36.2→20.1秒，attempt-04为28.2秒。只有attempt-03覆盖超时压缩；其他没有被描述为超时修正。此为有限开发采样，不是稳定成功率。

## 重跑

先在本地配置.env，输出目录必须是全新目录，审计脚本拒绝覆盖旧证据：

```sh
python3 -m scripts.run_live_acceptance --input examples/inputs/normal.json --model live --env-file .env --api responses --reasoning-effort medium --timeout 60 --output-dir runs/new-normal
python3 -m scripts.run_live_acceptance --input examples/inputs/normal.json --model live --env-file .env --api responses --reasoning-effort medium --timeout 60 --output-dir runs/new-duration
python3 -m scripts.run_live_acceptance --input examples/inputs/normal.json --model live --env-file .env --api responses --reasoning-effort medium --timeout 60 --fail-tool search_materials --output-dir runs/new-tool-failure
```

模型非确定性，普通输入不保证每次超时；不得手改工具结果、补写旧Trace或将未触发超时的运行说成超时修正。36句真实语义评估不在本轮任务范围，尚未额外执行。
