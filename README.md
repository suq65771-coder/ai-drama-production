# AI漫剧制作总控 · AI Drama Production

一个面向 **Codex** 的制作流程 Skill，把故事、统一人物资产、导演分镜、独立视频提示词、HTML图文交付和局部修订接成同一个项目。

支持真人AI短片、二维动漫和3D等视觉媒介。**画幅由你选择**：9:16、16:9、1:1、4:5、21:9或自定义比例；已有项目沿用既定配置。

## 它能做什么

| 阶段 | 产物 |
| --- | --- |
| 故事与剧本 | 情节因果、正式剧本、自然对白、必要时核实真实来源 |
| 统一设定 | 画风、人物外形与服装、音色、场景空间、道具状态 |
| 资产制作 | 图片提示词、实际参考图、素材清单 |
| 导演分镜 | 生成段、段内切镜、动作表演、首尾状态与衔接 |
| 视频生产包 | 每段完整独立提示词、图号绑定、TXT、HTML图文包 |
| 修订与收尾 | 指定片段返修、实片检查、封面、片尾与发布素材 |

支持“继续下一步”和“只改B09”。已确认片段可以锁定；工具能检查图片缺失、图号错位、镜头超时及未授权的范围变化。

**Skill提供制作方法，Python工具负责确定性的检查与排版。** 视频生成仍需要用户所选平台或当前可用的工具。本仓库不内置生成服务、API密钥或自动发布流程。

## 安装到Codex

### 从GitHub安装

在Codex对话中输入下面的请求：

```text
使用 $skill-installer 安装 https://github.com/suq65771-coder/ai-drama-production/tree/main/skills/ai-drama-production
```

标准Skill目录是：`skills/ai-drama-production`。仓库名、账号或默认分支改变时，链接也要对应更新。

### 手动安装

下载并解压仓库，将完整的`skills/ai-drama-production`文件夹复制到Codex用户技能目录：

- 设置了`CODEX_HOME`时：其下的`skills/`目录。
- 未设置时：用户主目录下的`.codex/skills/`。

最终应能找到`skills/ai-drama-production/SKILL.md`，不要只复制这个文件而漏掉scripts、references和assets。已有同名Skill时先保留旧版，再决定如何更新。安装完成后在下一轮对话调用。

## 使用

### 从故事开始

```text
使用 $ai-drama-production，把下面的故事做成AI漫剧。
先让我选择画幅，再按当前范围推进。
故事：……
```

### 明确指定风格和规格

```text
使用 $ai-drama-production，做一部16:9横屏、二维动漫风格的60秒短片。
每段10秒，单镜不超过3秒。我手动复制提示词到视频平台。
```

### 继续已有项目

```text
使用 $ai-drama-production，读取当前项目文件和进度，继续下一步。
保留已经确认的剧本、人物、音色和视频片段。
```

### 局部修订

```text
使用 $ai-drama-production，只改B09。
先读B08结尾和B09开头，把情绪衔接补自然。
其他片段保留，改好后更新原HTML入口。
```

一个可复用的虚构故事输入见[示例](examples/story-brief.md)。

## 可调整的配置

| 配置 | 行为 |
| --- | --- |
| 画幅 | 新项目未指定时先询问，不默认固定竖屏 |
| 视觉风格 | 真人、二维、3D或明确指定的其他媒介 |
| 每生成段时长 | 初始值10秒，可按平台与项目修改 |
| 单镜上限 | 初始值3秒，可修改 |
| 生成方式 | 手动复制，或在明确授权且工具可用时提交 |
| 声音 | 固定文字音色，可登记参考音频；实片声纹另行核验 |

角色参考表比例可以不同于正片，例如横向人物表配合竖屏影片。更改已有项目画幅时，需要一起检查首帧和构图；工具不会自动裁图或重新生成媒体。

## 命令行工具

需要Python **3.10或更高版本**。制作脚本与测试仅使用Python标准库，无需安装生成API或第三方依赖。以下命令从仓库根目录运行，Windows可在PowerShell中执行。

```shell
# 建立横屏项目；--ratio必填，也支持1:1、21:9等比例
python -X utf8 skills/ai-drama-production/scripts/project.py init my-drama --title "新故事" --ratio 16:9

# 读取下一步，不重复初始化
python -X utf8 skills/ai-drama-production/scripts/project.py status my-drama/drama-project.json

# 检查已填写的项目资料
python -X utf8 skills/ai-drama-production/scripts/validate_project.py my-drama/drama-project.json

# 修改前保存快照
python -X utf8 skills/ai-drama-production/scripts/project.py snapshot my-drama/drama-project.json --output my-drama/snapshots/before-B09.json

# 修改后只允许B09变化
python -X utf8 skills/ai-drama-production/scripts/validate_project.py my-drama/drama-project.json --baseline my-drama/snapshots/before-B09.json --only B09

# 完整提示词与参考图准备好后生成/更新固定HTML入口
python -X utf8 skills/ai-drama-production/scripts/render_package.py my-drama/drama-project.json
```

初始化只建立状态和计划，不生成假故事、假图或空白视频包。JSON字段、旧制作包导入和锁定方法见[项目数据约定](skills/ai-drama-production/references/project-schema.md)。

## 项目结构

```text
.
├─ README.md
├─ .github/workflows/validate.yml
├─ examples/story-brief.md
├─ scripts/check_repository.py
├─ tests/test_skill.py
└─ skills/ai-drama-production/
   ├─ SKILL.md
   ├─ agents/openai.yaml
   ├─ references/
   ├─ scripts/
   └─ assets/package-template.html
```

其他剧本、人物、分镜或生图Skill是可选增强。本Skill会按需寻找真实已安装技能，缺失时不会假称已调用，不需要同时安装一整套技能才能读取或使用本流程。

## 验证与维护

```shell
python -X utf8 scripts/check_repository.py
python -X utf8 -m unittest discover -s tests -v
```

测试自行在仓库`.test-work/`下创建少量文件及色块PNG，只验证文件、比例、时间轴和交付机制；不依赖任何真实人物图或私有项目。`.test-work/`、用户项目、缓存和本地环境文件不纳入Git。

GitHub Actions在提交和Pull Request时执行相同检查，覆盖Windows/Linux与Python版本矩阵。配置采用官方[checkout](https://github.com/actions/checkout)和[setup-python](https://github.com/actions/setup-python)用法；云端是否通过以上传后的实际运行结果为准。

机械检查不证明剧情自然、道具画对、口型合适或声纹一致。这些需要查看资产/实片，详见[检查范围](skills/ai-drama-production/references/quality-checks.md)。

## 上传GitHub

1. 创建名为`ai-drama-production`的GitHub仓库，按需要选择公开或私有。
2. 上传本仓库根目录里的文件和目录，包含`.github/`；让README.md和skills/直接位于仓库顶层。
3. 仓库创建后，把上面的安装链接换成真实账号与仓库地址。
4. 查看Actions的检查结果，再分享安装链接。

ZIP是交付容器：先解压再上传其中的源码。只上传一个ZIP文件不会形成上述标准的Skill安装路径。

## 许可证

当前未指定开源许可证。仓库作者选择授权方式后再添加LICENSE；本交付不代替作者授予开放复制、修改或分发权限。
