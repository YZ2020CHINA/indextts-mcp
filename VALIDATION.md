# 验证记录

## 1.2.0 官方GitHub对照优化

2026-11-07实际读取官方README、infer_v2_5.py、webui.py与presets.py，SHA和差异见 evidence/official-review.md。未更换本机原程序和模型。

- 13项单元测试通过，覆盖新增官方参数映射、文本自动情感和互斥校验、WebUI预设发现与同名优先级、注册音色副本、真实阶段进度、模型容量限制及本机采样开关差异检测；skill quick_validate通过。
- 1.2.0已安装且enabled。以安装缓存mcp.json中的真实stdio命令完成初始化、八工具发现和哈基米音色发现；六个关键文件与项目构建产物内容一致。
- 真正加载CUDA/BF16、low_vram=true；容量1815输出token/600文本token。检测到本机源码固定do_sample=true，已安装MCP对false请求准确报错，没有静默忽略。
- 最终后台使用哈基米成功合成“今天也是美好的一天。”：22050Hz单声道、2.032秒、89644字节；运行3.693秒、RTF1.817、warnings为空、possibly_truncated=false。低token上限120只用于这条短测试；插件默认仍1500。
- 较短注音样例 `银<行|HANG2>。` 也实际生成成功：0.708秒WAV、运行1.300秒，无警告且未触及token上限。该结果验证注音输入可通过整条合成链，未做独立听辨评分。
- 一条较长含拼音注音的样例在约6分钟仍处于自回归合成，随后仅停止本次创建的IndexTTS进程；重启将任务正确恢复为failed。本机同时检测到Flux和Stable Audio进程，GPU显存约9.4/10GB，性能与模型输入影响未能分离；没有声称普遍加速。此样例不算成功验收。
- QwenEmotion模式、非中文听感和精确发音辨识未做实机验收；参数按官方接口接入并通过映射测试。分段静音参数传递已验证，测试短句没有多段，未验证实际分段间隔。
- ZIP只包含注册音色与允许发布的源文件，排除运行状态、生成结果和模型；固定ZIP元数据后重复构建hash一致。证据：evidence/official-upgrade-validation.json、evidence/official-smoke.json、.state/backend.log。

## 1.1.0 命名音色更新

已通过 `voice="哈基米"` 实际生成“今天也是美好的一天”：WAV 22050 Hz、单声道、1.869 秒、82476 字节，任务 fbf0839176fd493185cab8dd14a44674，推理约3.07秒。当前 Codex 已安装并启用1.1.0；安装缓存内音频与项目音频逐字节一致，启动已安装MCP声明的命令可发现哈基米且 exists=true。

2026-11-07：用户指定将“哈基米”参考音频加入插件。已复制到 `voices/hajimi.wav`，与源文件 SHA256 一致（19db93137852c5a7514da96a11584fec1e6453fdb9b302dfd1ea4ffd6d06882a）。`voices.json` 注册名称，MCP 支持 `voice="哈基米"` 并保留原 reference_audio 调用。未知名称、双参数冲突和文件丢失均明确报错。8 项单元测试通过，skill 校验通过。此版本 ZIP 明确包含用户要求收录的音色，仍排除其他用户音频、生成结果、令牌、模型与日志。

## 1.0.0 首版验证

验证日期：2026-11-07（北京时间）。

- 本机：IndexTTS2.5 嵌入式 Python 3.11.9，CUDA 可用，RTX 3080，9.9995 GiB 显存；GPT、codec、s2mel、CampPlus、BigVGAN 从已有本地权重加载，后台达到 ready。
- `python -m unittest discover -s tests -v`：7 项通过。覆盖真实 stdio 握手与工具发现、非法参数、队列满、并发任务唯一 ID、重启任务恢复、输出路径限制、端口占用与令牌保持。
- skill-creator `quick_validate.py skills/indextts`：Skill is valid。
- 原生 CLI 独立安装：在项目内 test-install 的独立 CODEX_HOME 注册市场与安装；plugin list 返回 installed=true、enabled=true。
- 当前用户 Codex 安装：CLI 返回 installed=true、enabled=true。读取已安装副本的 mcp.json，启动其声明的 stdio 命令，完成握手、发现七个工具并提交情感配音任务。新聊天才会注入这些 MCP 工具与 skill。
- 实机中文任务一：使用程序自带 voice_01.wav，文本“你好，我是粉红小鸟。欢迎来到你的声音工作室。”，WAV 单声道 22050 Hz，4.063 秒，179244 字节；推理约 6.85 秒。
- 实机情感任务二：通过已安装的 MCP 提交，平静向量 `[0,0,0,0,0,0,0,0.7]`，文本“愿你今天拥有平静而美好的心情。”，WAV 单声道 22050 Hz，3.111 秒，137260 字节；推理约 2.04 秒。
- 两个任务均由后台实际生成，随后由 WAV 读取验证帧数、时长、采样率。此验收证明端到端生成可用，未做主观音色相似度或多语言听辨验收。
- 已验证空闲停止命令返回正确后台 PID，完成后关闭模型进程以释放显存。初次加载发现 Numba 尝试写原程序缓存导致停顿，现将 Numba、Matplotlib、Torch 缓存定向到项目 .state/cache；无需改动原程序。
- Logo：Adobe Firefly 实际生成 1024×1024 PNG，已视觉检查为粉红小鸟张嘴与声波的极简平面图案，256×256 图标已接入插件与 skill。

证据位于源码项目的 evidence/environment.json、evidence/smoke.json、evidence/installed-mcp.json 与 .state/backend.log。分享 ZIP 只包含允许分发的源代码、skill、图标、安装脚本与测试，不包括音频、模型、令牌、日志和 Codex 用户配置。

尚未实机测试的能力：EN/JA/AR/ES、情感参考音频模式、QwenEmotion 文本情感、精确音色相似度。语言与参数支持来自本机源代码，不将这些项目描述为已通过听感测试。时长系数为近似控制，随机种子不保证 GPU 位级复现。
