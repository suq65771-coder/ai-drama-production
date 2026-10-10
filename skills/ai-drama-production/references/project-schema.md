# 项目JSON、状态及工具用法

所有命令中的 `<skill>` 是本技能绝对目录，`<project>` 是目标项目目录。命令参数用本机shell正确引用，路径可含中文和空格。Python脚本不依赖第三方包。

## 初始化与画幅选择

先让用户选择9:16、16:9、1:1、4:5、21:9或自定义画幅；用户已经说过就直接使用。命令故意不提供画幅默认值，避免无声地强制竖屏。

```powershell
python -X utf8 "<skill>/scripts/project.py" init "<project>" --title "新故事" --ratio 16:9
python -X utf8 "<skill>/scripts/project.py" status "<project>/drama-project.json"
```

可加 `--clip-seconds 10 --max-shot 3 --style "二维动漫" --mode manual`。设置只改变配置，不能自动改变旧参考图的构图；改变既有项目画幅时需重新检查首帧、构图与交付，不仅修改数字。

## 结构约定

```json
{
  "schemaVersion": 1,
  "project": {"id": "drama-project", "title": "故事名称"},
  "config": {
    "frameRatio": "16:9", "style": "真人电影", "clipSeconds": 10,
    "maxShotSeconds": 3, "maxHanPerSecond": 5.5,
    "allowDialogueOverlap": false, "generationMode": "manual",
    "packagePath": "delivery/index.html", "noBgm": true, "noGeneratedSubtitles": true
  },
  "workflow": {
    "stages": {"story": "pending", "design": "pending", "assets": "pending", "storyboard": "pending", "prompts": "pending", "review": "pending"},
    "lastAction": "初始化项目"
  },
  "characters": [], "assets": [], "clips": [], "locks": {}, "sources": []
}
```

`ready`表示该阶段产物已准备；`approved`表示有用户确认依据。`review`只有实际检查完成才登记ready。`status`工具返回最早未完成阶段；最新用户指令可指定阶段或片段，不机械服从建议。

角色：`id`、`name`、`appearance`、`voice.description`、`voice.referenceAudio`（可为null）。沉默角色可无音色，指定说话人必须有描述。角色定义是共享资料，不在每段另造一个“同名新角色”。

资产：`id`、`kind`（firstFrame/character/scene/prop/insertFrame）、`label`、`path`、`sha256`、`aspectRatio`、`visualReview`（pending/passed）；人物资产另有`characterId`。`aspectRatio`是该图片自身比例，可与正片不同，例如横向人物表用于竖屏影片。路径相对项目JSON所在目录解析，也支持已授权绝对路径。

片段字段：

```json
{
  "id": "B02", "title": "片段名称", "duration": 10,
  "status": "prompt_ready", "videoStatus": "not_verified",
  "promptPath": "prompts/B02.txt", "promptSha256": "实际文件的sha256",
  "requiredCharacters": ["C01"],
  "shots": [{"start": 0, "end": 2.5, "description": "本镜动作与摄影说明"}],
  "dialogue": [{"characterId": "C01", "text": "指定台词", "start": 0.1, "end": 1.5, "tone": "日常低声"}],
  "references": [{"order": 1, "imageLabel": "图一", "assetId": "B02_A01", "purpose": "锁首帧机位和初态"}],
  "startState": "首帧初始状态", "endState": "段末状态", "bridge": "如何承接上一段"
}
```

这里的shots/references只示意一项，实际必须覆盖全段并包含所需人物和场景。初稿可`status=draft`且尚无提示词；HTML拒绝草稿占位。状态区分：prompt_ready已准备，video_reported用户称已生成，video_verified已实际核验。`videoStatus`及可选`videoOutputs`记录实片证据，不能由文本校验自动升级。

ID只用字母、数字、连字符和下划线，以字母开头。文件修改后同步更新相应sha256；若内容已锁定，先核对用户是否授权修改并记录理由，不能仅改哈希绕过锁。

## 导入已有tasks制作包

支持任务含`id/name/seconds/prompt/promptSha256/references/ranges/beats/lines/bridge/end`的旧包。参考含`uploadOrder/imageLabel/label/kind/file/sha256/purpose`；对白含`role/text/start/end`；音色表含`roles`及可选`silentRoles`。不支持的结构先做明确适配，不推测声纹或角色。

```powershell
python -X utf8 "<skill>/scripts/project.py" import-pack "<旧包>/tasks.json" --voices "<旧包>/voices.json" --output "<project>/drama-project.json" --ratio 9:16
```

只读引用旧包，不改写或搬动旧图和提示词。新项目JSON保留源包哈希。源包已记录B01保留时继承锁定，但不据此宣称看过实际视频。导入后的图片视觉状态为pending，需按原检查依据或本次目视补充；文本外形表述不同只提醒核对，不自动重写旧提示词。

## 校验、快照与排版

```powershell
python -X utf8 "<skill>/scripts/validate_project.py" "<project>/drama-project.json" --report "<project>/validation.json"
python -X utf8 "<skill>/scripts/project.py" snapshot "<project>/drama-project.json" --output "<project>/snapshots/before-B09.json"
python -X utf8 "<skill>/scripts/validate_project.py" "<project>/drama-project.json" --baseline "<project>/snapshots/before-B09.json" --only B09
python -X utf8 "<skill>/scripts/render_package.py" "<project>/drama-project.json"
```

先写完整TXT与JSON，再校验并排版。新项目输出到`config.packagePath`；已有入口先将该字段指向原HTML，不额外创建竞争入口。排版标记为`AI_DRAMA_PACKAGE_START/END`，只替换该区域；首次接入旧HTML时加到body末尾，原区块由维护者根据项目情况明确整理，不自动删除用户内容。成功更新有备份；无变化不重写；内容错误不改原页。

锁定：用户已确认保留后运行 `project.py lock <项目JSON> --clip B01 --reason "用户要求保留已生成开场"`。再次锁定前现有锁仍须通过校验；要改锁定内容时先依据用户明确授权处理锁定记录、保存快照和理由，再更新，不能因脚本阻拦而静默解除。

快照与局部校验同时比较实际文件哈希及片段依赖。禁止未点名的片段、角色定义或共享资产偷偷变化；允许目标片段增加只供自身使用的资产。工具返回非零退出码表示失败，不能继续排版。
