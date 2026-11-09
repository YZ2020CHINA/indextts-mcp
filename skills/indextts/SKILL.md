---
name: indextts
description: 使用本机 IndexTTS2.5 进行参考音色文字转语音、情感配音、时长系数调整与 WAV 导出。用户指定 IndexTTS、本地文字转语音或本插件时使用；不用于音乐生成或现有音频剪辑。
---

# 粉红小鸟 · 本地配音

使用 `indextts_*` MCP 工具操作本机程序。模型与用户音频留在本地；首次生成前需加载模型。不要把安装成功、任务排队或模型加载成功描述为语音生成成功。

## 操作流程

1. 调用 `indextts_environment` 查看安装、模型缺失、语言和当前状态。默认安装为 `D:\IndexTTS2.5`，以工具返回为准。文件缺失时报告具体路径，不自动下载或替换模型。
2. 离线时调用 `indextts_start` 一次，再通过 `indextts_status` 查询。`phase=loading` 时等待并隔一段时间查询，不重复启动。`phase=failed` 时读取返回的 backend.log 找出原因；不要循环重启。
3. 先用 `indextts_references` 发现插件命名音色、WebUI预设（返回 `voices`）与自带示例。已收录用户指定的“哈基米”，直接用 `voice="哈基米"`。同名时插件音色优先；WebUI预设只提供音色参考，不自动套用其情感或采样设置。只有指定音色不在列表且没有参考时，才询问音频位置。支持 WAV、MP3、FLAC、M4A、OGG；建议清晰单人、无伴奏片段。官方模型只使用参考音频前15秒。
4. 调用 `indextts_generate`，传 `text`，并在 `voice`（命名音色）和 `reference_audio`（绝对路径）中选一个。中文默认 `language=ZH`。例如 `{"text":"今天也是美好的一天","voice":"哈基米","language":"ZH"}`。其他界面语言代码为 `EN/JA/AR/ES`。不要自动翻译原文。
5. 保存返回的 `job_id`，用 `indextts_job` 查询 queued/running/succeeded/failed，`stage` 为真实模型阶段、`progress` 为阶段值，长文本分段时可能重置，不代表整体完成百分比或ETA。`elapsed_seconds` 为运行耗时，成功后 `rtf` 为耗时/音频时长。失败时根据具体错误修复，最多进行一次有明确依据的重试；不盲目重复生成。
6. 成功后用返回的绝对 WAV 路径交付可播放音频，并说明所用音色、语言和时长。Codex 支持 `![试听](/absolute/path.wav)`。成功依据是工具验证后的实际非空 WAV。

## 情感与节奏

- `emotion_audio`、`emotion_vector`、`emotion_text` 三选一；缺省沿用音色参考的情感。
- 八维向量顺序：喜、怒、哀、惧、厌恶、低落、惊喜、平静。每项 0–1；后台会按原程序方法应用偏置并把总强度归一到不超过 0.8。
- `emotion_weight` 为 0–1，默认 0.65；语气过重时降低它。
- `emotion_text` 需要 `config.json` 中启用 `use_qwen_emo` 并重启后台，消耗额外显存。本机约 10GB 显存，默认关闭；可用向量或情感参考音频实现情感控制。
- 传 `use_emotion_text=true` 且省略 `emotion_text`，可按官方API从朗读文本自动推断情感，同样要求QwenEmotion。显式 `emotion_text` 会自动启用该模式；文本模式不能再与向量/情感音频混用。官方建议文本情感权重约0.6或更低；`random_emotion=true` 会降低音色克隆保真度，保持默认false，除非用户想要随机变化。
- `duration_factor` 为 0.5–2，越大通常越慢；只近似控制时长。需要精确秒数时先生成并检查实际长度，再决定是否调整，不承诺精确时长。
- 默认分段为 120 tokens，长文本由模型分段。低显存或内存错误时减少文本长度、分段 token 或 beams，先确认同一显卡上是否有其他模型占用。
- `seed` 帮助复现，GPU 不保证逐字节一致。

## 发音和高级参数

保留用户提供的 `<文字|发音>`，不要自行删改注解。官方支持中文拼音（如 `银<行|HANG2>`）、英文CMU音素（如 `<minute|M IH1 . N AH0 T>`）、日语假名（如 `<上手|じょうず>`）。仅在用户指定发音或确有多音字问题时添加，遵循所选语言。

`interval_silence_ms` 控制模型分段之间的静音（默认200ms），不能凭它给每个标点设置精确停顿。`text_normalization` 默认true，朗读数字、日期时通常保留。`do_sample` 默认true；高级选项包括 `length_penalty`、`repetition_penalty`、`max_mel_tokens`。后两者和分段token会在提交时检查实际模型容量。不要只提高输出token来解决超长稿；先看文本分段和是否有截断证据。加速选项保持本机已验证设置，不默认开启DeepSpeed或编译扩展。

本机整合包与官方版本有差异：官方传递 `do_sample` 开关，本机代码却写死true。后台会检测 `runtime.sampling_switch_supported`，不支持时拒绝 `do_sample=false`，不会伪称已关闭随机采样。生成结果的 `possibly_truncated=true` 或 `warnings` 提到max_mel_tokens时，要告知用户可能截断，不能只因WAV非空就声称完整朗读。

用户说“添加/记住这个音色”时，用 `indextts_register_voice(name,reference_audio,description)` 保存一份到插件 `voices/`，随后按名字使用；已存在名称会拒绝覆盖。注册即时生效，分享包需要重新构建才包含新参考。只在用户要求添加时注册，普通一次配音直接引用路径。

## 路径与生命周期

运行目录由 `INDEXTTS_MCP_HOME` 指向的项目决定。命名音色在 `voices.json` 注册，对应音频存放 `voices/`；哈基米已复制到 `voices/hajimi.wav`，不依赖原预设目录。音频在 `outputs/`，任务在 `.state/jobs/`，日志在 `.state/backend.log`。插件缓存不保存运行状态和产出。配置修改后需后台重启才生效，已加载的 MCP 配置也可能需要新聊天。

用户请求释放显存或结束语音工作时调用 `indextts_stop`。它仅关闭本插件带认证的后台，并拒绝在加载或任务执行中停止。不要结束其他 Python 或 IndexTTS WebUI 进程。该后台与 WebUI 分别加载模型；显存不足时先说明占用并让用户关闭其不用的实例。

`indextts_status.version_matches=false` 表示后台仍是旧版本；空闲时停止再启动后使用新功能，忙碌时先等待已有任务。`runtime` 包含实际设备、精度、低显存模式和模型token上限。

若 MCP 工具尚未加载，安装插件后开新聊天。排查安装方法见插件根目录 README.md；可用项目 `server.py --call indextts_status` 验证桥接本身，但不要声称当前聊天已获得未注入的工具。
