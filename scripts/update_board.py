"""Expand the existing canvas while preserving node IDs and user layout."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / 'project-blocks/data/project.json'
project = json.loads(path.read_text(encoding='utf-8'))
items = [
 ('requirements','01 · 需求与交付范围','prologue',60,80,'连接 D:/IndexTTS2.5，交付可复用 MCP、中文 skill、粉红小鸟 Logo 和可安装插件。','README.md',['明确本地推理、参考音色、情感控制、异步任务和音频交付范围']),
 ('inspect','02 · 调查本机程序与模型','common',500,80,'检查启动脚本、Python 环境、模型文件、infer 签名、语言及情感参数。','evidence/environment.json',['记录真实 Python 路径和模型完整性','对照 infer_v2_5.py 确认参数，不猜测接口']),
 ('design','03 · 连接方案与运行目录','branch',940,80,'独立本地后台进程复用原程序 Python 和模型；MCP 使用 stdio；模型与用户音频不进入插件包。','config.json; server.py; backend.py',['插件启动不加载模型','后台仅监听回环地址，带认证令牌','运行状态和音频保存在稳定项目目录']),
 ('implementation','04 · MCP 协议与工具','common',1380,80,'实现 initialize、tools/list、tools/call；提供健康检查、后台启动、参考音频发现、生成、任务查询及关闭。','server.py',['JSON-RPC 标准输入输出可由客户端初始化','错误以工具错误返回，日志不污染 stdout']),
 ('backend','05 · 本地模型后台与生命周期','common',1820,80,'后台隐藏启动、模型只加载一次、任务串行运行、记录日志与失败原因；停止只针对本插件进程。','backend.py',['真实 CUDA 环境能加载 IndexTTS2.5','重复启动复用服务','忙碌时拒绝停止']),
 ('speech','06 · 文本、音色与情感参数','common',2260,80,'支持参考音频、语言、时长系数、情感参考音频、八维情感与可选情感文本。','server.py; backend.py',['拒绝空文本、无效音频、越界和互斥情感参数','情感向量按官方方法归一化','时长系数注明是近似控制']),
 ('jobs','07 · 异步任务与音频交付','common',2700,80,'快速返回 job_id；后台串行合成；查询排队/运行/成功/失败；返回 WAV 路径和音频信息。','backend.py; outputs/',['长推理不阻塞 MCP 调用','输出使用唯一文件名且不覆盖已有文件','只在实际 WAV 可读时报告完成']),
 ('skill','08 · 编写中文语音 skill','route',1380,500,'指导后续 Codex 发现环境、选择真实参考音频、提交并轮询、返回可播放结果；说明低显存和情感文本限制。','skills/indextts/SKILL.md; skills/indextts/agents/openai.yaml',['触发范围准确，中文操作说明清晰','不虚构参考音色或成功结果','skill validator 通过']),
 ('logo','09 · 生成粉红说话小鸟 Logo','character',500,920,'生成粉红小鸟张嘴说话与声波，极简平面风格；保存原图与小尺寸插件图标。','assets/logo.png; assets/icon.png',['图片真实生成并检查外观','缩小后主体与声波仍清晰','插件与 skill 引用正确图标']),
 ('package','10 · 插件结构与安装入口','route',1820,920,'创建 plugin.json、mcp.json、本地 marketplace；构建时重定位路径；提供 PowerShell 安装脚本。','plugin.json; scripts/build_plugin.py; install-plugin.ps1',['插件清单符合当前格式','安装不覆盖其他插件或配置','压缩包排除模型、用户音频、令牌和日志']),
 ('protocol-test','11 · 协议与失败路径测试','ending',2260,500,'启动真实 stdio 子进程，验证初始化、工具发现、参数错误；测试队列和输出边界。','tests/test_bridge.py; evidence/validation.json',['协议测试通过','无效参数和路径可诊断','标准输出没有调试日志']),
 ('real-test','12 · 实机短句语音验收','ending',3140,80,'用程序自带示例音频合成一句中文；检查 WAV 帧、时长、采样率并提供试听。','outputs/; evidence/smoke.json',['真实模型合成完成','WAV 非空且可以播放','记录参考来源、参数与任务结果']),
 ('verification','13 · 打包交付与使用说明','ending',3140,920,'校验 ZIP 与 SHA256；以独立 Codex 配置目录验证安装和插件启用状态；交付使用例句与限制。','dist/; README.md; VALIDATION.md',['干净安装流程通过或明确列出实际阻碍','交付 ZIP、Logo、源码与验证记录','区分协议通过和真实生成结果'])
]
edges = [('requirements','inspect'),('inspect','design'),('design','implementation'),('implementation','backend'),('backend','speech'),('speech','jobs'),('design','skill'),('requirements','logo'),('implementation','package'),('logo','package'),('skill','package'),('jobs','protocol-test'),('jobs','real-test'),('package','verification'),('protocol-test','verification'),('real-test','verification')]
existing = {n['id']:n for n in project['nodes']}
for ident,title,kind,x,y,summary,files,acceptance in items:
    n = existing.get(ident)
    if n is None:
        n = {'id':ident,'x':x,'y':y,'choices':[],'workflow':{'status':'todo','priority':'P1','blockReason':'','evidence':[]}}
        project['nodes'].append(n)
    n.update(title=title, routeType=kind, color='#ed83ad' if ident=='logo' else '#88bccc', characters='Codex',summary=summary,script=summary,location=files,bgm=files)
    n['workflow'].update(files=files.split('; '),acceptance=acceptance)
    existing[ident]=n
for source,target in edges:
    n=existing[source]
    if not any(c.get('target')==target for c in n['choices']):
        n['choices'].append({'id':f'rel_{source}_{target}','target':target,'text':'前置依赖','tag':'前置依赖'})
# Remove only initial scaffolding shortcuts, now represented by concrete stages.
for source,target in [('requirements','implementation'),('implementation','verification')]:
    existing[source]['choices']=[c for c in existing[source]['choices'] if c.get('target')!=target]
temporary=path.with_suffix('.tmp')
temporary.write_text(json.dumps(project,ensure_ascii=False,indent=2),encoding='utf-8')
os.replace(temporary,path)
print(json.dumps({'cards':len(project['nodes']),'edges':len(edges)},ensure_ascii=False))
