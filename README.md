# 粉红小鸟 · IndexTTS 本地语音插件

为 Codex 连接已有 `D:\IndexTTS2.5`：八个 MCP 工具、中文 `indextts` skill、粉红说话小鸟图标、原生本地插件市场和安装脚本。桥接仅使用 Python 标准库，不往原程序安装依赖。模型和原程序不随插件分发，也不修改原程序源代码。

## 安装

保留解压后的 `indextts-mcp` 目录作为稳定运行目录，编辑 `config.json` 中的 `tts_root` 为你的 IndexTTS2.5 路径，然后在 PowerShell 中运行：

```powershell
.\install-plugin.ps1
```

脚本使用 Codex 自带 CLI 注册 `pink-bird-local` 市场并安装 `pink-bird-indextts`，安装前重建绝对路径。移动项目后重新运行安装脚本。不要直接从 ZIP 内运行，也不要删除该项目目录；插件缓存中的 MCP 指向此目录保存状态与产出。需要已安装 Codex CLI 和 IndexTTS 原有依赖、模型。安装完成后开新聊天以加载工具。

## 使用

可以直接对 Codex 说：

- “用粉红小鸟把‘你好，欢迎来到我的工作室。’转成中文语音，先用自带示例音色。”
- “用 `D:\声音\参考.wav` 给这段文字配音，语气平静一点。”
- “查一下刚才的语音任务，给我试听。”
- “结束配音，释放 IndexTTS 占用的显存。”

也可显式使用 `$indextts`。必须有参考音频；插件能列出程序自带示例，也能接收任意已存在的绝对本地音频路径。输出为 `outputs/<job_id>.wav`，任务状态为 `.state/jobs/<job_id>.json`，后台日志为 `.state/backend.log`。

### 命名音色（1.1.0）

已按用户要求收录 **哈基米**，参考音频从 `D:\IndexTTS2.5\outputs\presets\哈基米\prompt.wav` 复制到 `voices/hajimi.wav`，在 `voices.json` 中注册。插件包包含这份明确指定加入的音色，移动原预设也不影响使用。下次直接说“用粉红小鸟的哈基米音色说：今天也是美好的一天”。

MCP 调用：`indextts_generate(text="今天也是美好的一天", voice="哈基米", language="ZH")`。`voice` 与 `reference_audio` 二选一；`indextts_references` 的 `voices` 返回命名音色与可用状态。新增音色时复制参考音频到 `voices/` 并在 `voices.json` 注册，再重新构建安装；不要通过改名把其他声音冒充目标音色。

## 八个工具

| 工具 | 用途 |
| --- | --- |
| indextts_environment | 安装、模型、能力与路径检查 |
| indextts_status | 后台加载阶段、错误、队列与当前任务 |
| indextts_start | 隐藏启动独立后台，模型按需加载 |
| indextts_references | 列出示例参考音频 |
| indextts_register_voice | 把用户指定音频复制并注册为可复用命名音色 |
| indextts_generate | 提交异步语音任务 |
| indextts_job | 查询任务并验证产出的 WAV |
| indextts_stop | 空闲时关闭本插件后台，释放显存 |

语言：ZH、EN、JA、AR、ES。情感支持参考音频、八维向量，以及可选 QwenEmotion 文本模式。默认启用支持时的 BF16、关闭额外文本情感模型和 CUDA 编译扩展，适合当前 RTX 3080 约 10GB 显存。修改配置后重启后台。WebUI 和插件后台会各加载一份模型，显存不足时关闭不用的实例。

`duration_factor` 是 0.5–2 的近似时长乘数，不保证精确秒数。任务单队列串行处理、最多排队四个任务；失败不自动重复执行。运行时使用本地模型并设置 Hugging Face 离线模式，不自动下载缺失模型。参考音频、生成音频和文本都不发送给云端。

## 1.2.0 官方接口对齐

依据 [官方 README](https://github.com/index-tts/index-tts/blob/main/README.md)、[推理实现](https://github.com/index-tts/index-tts/blob/main/indextts/infer_v2_5.py)、[WebUI](https://github.com/index-tts/index-tts/blob/main/webui.py) 和 [预设实现](https://github.com/index-tts/index-tts/blob/main/indextts/utils/presets.py) 优化；完整来源与读取时SHA见 `evidence/official-review.md`。

- 自动发现 `outputs/presets/<name>/preset.json` 中的参考音色；同名优先用插件已注册音色。这里只选择其声音，不自动套用预设情感或高级参数。新增WebUI预设可立即发现，无需重新安装。
- 用 `indextts_register_voice` 保存音色副本，普通后续调用用 `voice=<名称>`；拒绝覆盖已有插件音色。新注册音色即时可用，重新构建ZIP后才进入分享包。
- `use_emotion_text=true` 可从朗读文本推断情感；显式 `emotion_text` 可单独描述情感。均要求启用 QwenEmotion、重新加载后台；保持本机默认关闭。官方建议文本情感权重约0.6或更低；随机情感可能降低音色相似度。
- 支持 `do_sample`、`length_penalty`、`repetition_penalty`、`max_mel_tokens`、`interval_silence_ms`、`text_normalization`。提交时对照已加载模型配置检查token上限。当前本机上限为1815输出token、600文本token；默认仍1500/120。
- 原文可带拼音、CMU音素和日语假名注解，如 `银<行|HANG2>`、`<minute|M IH1 . N AH0 T>`、`<上手|じょうず>`。参考音频按官方代码只使用前15秒。
- 任务增加 `stage`、`progress`、`elapsed_seconds` 和成功后的 `rtf`。阶段值由模型回调提供，长稿会分段重置，不能当作整个任务的线性百分比或剩余时间；RTF为运行耗时除以音频长度。
- 状态增加实际设备、BF16/FP32、低显存模式与token容量。`version_matches=false` 时应空闲停止并重新启动后台，以免旧进程忽略新能力。
- 对照发现本机整合包将 `do_sample` 写死true，而当前官方代码传递此参数。插件检测后会明确拒绝不生效的 `do_sample=false`，不会改写原程序。结果新增 `warnings` 与 `possibly_truncated`，暴露模型达到输出token上限的警告。
- 构建只打包注册音色；ZIP采用固定文件元数据，相同内容重复构建的SHA256一致。

示例：`indextts_generate(text="今天去银<行|HANG2>办事。", voice="哈基米", interval_silence_ms=350, duration_factor=1.1)`。保留已有0.65情感权重及120分段默认值，避免悄然改变旧调用。

## 本地诊断与开发

```powershell
& 'D:\IndexTTS2.5\python_embeded\python.exe' .\server.py --call indextts_environment
& 'D:\IndexTTS2.5\python_embeded\python.exe' -m unittest discover -s tests -v
```

MCP 通过 stdio JSON-RPC 工作；后台监听 `127.0.0.1:17865` 并要求 `.state/token` 中的随机令牌。端口冲突可修改 config。日志和令牌不要打包分享。需要协议工具未加载时，可用 `--call` 诊断，当前聊天是否已加载工具仍以实际工具列表为准。

Logo 使用 Adobe Firefly 生成，提示词保存在 `assets/logo-prompt.txt`；原图 1024×1024，插件图标 256×256。IndexTTS 程序、模型及自带样例音频权利归各自权利方，本包只包含集成代码、skill 与生成的 Logo，不附带它们。

构建格式依据：[OpenAI 官方插件打包文档](https://developers.openai.com/plugins/build/plugins)。验证结果见 `VALIDATION.md`；项目流程见本目录 `project-blocks`。

## GitHub 源码与许可

源码仓库：https://github.com/YZ2020CHINA/indextts-mcp

自有代码使用 [MIT License](LICENSE)，第三方组件、软件、模型与素材保留各自许可。开发、分支和发布流程见 [CONTRIBUTING.md](CONTRIBUTING.md)。

首次从源码安装时，先复制 `config.example.json` 为 `config.json` 并按本机安装位置修改；本机配置不会提交到 Git。

私人参考音频与本地音色登记表不公开。复制 `voices.example.json` 为 `voices.json`；可先使用空对象，再通过绝对路径传入你有权使用的 `reference_audio`，或自行登记本地音色。仓库不附带哈基米音频。
