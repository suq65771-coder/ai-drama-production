"""Shared project data, file integrity and revision-scope checks (standard library)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import hashlib
import json
import math
import re
import struct

STAGES = ('story', 'design', 'assets', 'storyboard', 'prompts', 'review')
STAGE_NAMES = dict(zip(STAGES, ('故事与剧本', '统一设定', '资产制作', '导演分镜', '视频生产包', '实片检查与收尾')))
KINDS = ('firstFrame', 'character', 'scene', 'prop', 'insertFrame')
NUMERALS = ('一','二','三','四','五','六','七','八','九','十','十一','十二','十三','十四','十五','十六','十七','十八','十九','二十')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json(path, data):
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.writing')
    temporary.write_text(text, encoding='utf-8')
    temporary.replace(path)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def object_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def resolve_file(project_path, value):
    path = Path(value)
    return path.resolve() if path.is_absolute() else (Path(project_path).resolve().parent / path).resolve()


def image_label(order):
    return '图' + (NUMERALS[order-1] if 0 < order <= len(NUMERALS) else str(order))


def backup_file(path):
    path = Path(path)
    if path.exists():
        target = path.parent / 'backups' / (datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '_' + path.name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
        return str(target)
    return None


def tracked_files(data, project_path):
    paths = [a.get('path') for a in data.get('assets', [])]
    paths += [c.get('promptPath') for c in data.get('clips', []) if c.get('promptPath')]
    paths += [c.get('voice', {}).get('referenceAudio') for c in data.get('characters', [])]
    return {str(resolve_file(project_path, p)): digest(resolve_file(project_path, p))
            if resolve_file(project_path, p).is_file() else None for p in paths if p}


def clip_fingerprint(data, clip, project_path):
    """Freeze content and its dependencies while allowing production-status updates."""
    assets = {a['id']: a for a in data['assets']}
    characters = {c['id']: c for c in data['characters']}
    body = {k: v for k, v in clip.items() if k not in ('status', 'videoStatus', 'videoOutputs', 'review')}
    used_characters = set(clip.get('requiredCharacters', [])) | {d['characterId'] for d in clip.get('dialogue', [])}
    dependencies = []
    for ref in clip.get('references', []):
        a = assets[ref['assetId']]
        dependencies.append({k: a.get(k) for k in ('id', 'path', 'sha256', 'kind', 'characterId', 'aspectRatio')})
        if a.get('characterId'):
            used_characters.add(a['characterId'])
    actual = {}
    for path in [clip.get('promptPath')] + [assets[r['assetId']]['path'] for r in clip.get('references', [])]:
        if path:
            actual[str(path)] = digest(resolve_file(project_path, path)) if resolve_file(project_path, path).is_file() else None
    for cid in used_characters:
        path = characters[cid].get('voice', {}).get('referenceAudio')
        if path:
            actual['audio:' + path] = digest(resolve_file(project_path, path)) if resolve_file(project_path, path).is_file() else None
    return object_hash({'clip': body, 'assets': dependencies, 'characters': {cid: characters[cid] for cid in sorted(used_characters)}, 'actual': actual})


def make_snapshot(data, project_path):
    return {'snapshotVersion': 1, 'projectPath': str(Path(project_path).resolve()), 'project': data,
            'files': tracked_files(data, project_path),
            'clipFingerprints': {c['id']: clip_fingerprint(data, c, project_path) for c in data['clips']}}


def next_action(data):
    for stage in STAGES:
        if data.get('workflow', {}).get('stages', {}).get(stage) not in ('ready', 'approved'):
            return {'stage': stage, 'title': STAGE_NAMES[stage], 'reason': '该阶段尚未完成，结合最新用户指令继续。'}
    return {'stage': 'complete', 'title': '本轮制作已完成', 'reason': '按用户要求交付或进行指定局部修订；不自动发布。'}


def validate(data, project_path, baseline=None, only=None, for_render=False):
    errors, warnings = [], []
    def error(message): errors.append(message)
    def warning(message): warnings.append(message)
    if not isinstance(data, dict) or data.get('schemaVersion') != 1:
        return {'status': 'failed', 'errors': ['需要schemaVersion=1的项目对象'], 'warnings': [], 'checks': {}}
    for key, expected in [('config', dict), ('workflow', dict), ('characters', list), ('assets', list), ('clips', list), ('project', dict), ('locks', dict)]:
        if not isinstance(data.get(key), expected): error(f'{key}字段缺失或类型错误')
    if errors:
        return {'status': 'failed', 'errors': errors, 'warnings': warnings, 'checks': {}}
    config = data['config']
    def number(value): return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    for field in ('clipSeconds', 'maxShotSeconds', 'maxHanPerSecond'):
        if not number(config.get(field)) or config[field] <= 0: error(f'config.{field}须为正数')
    if not re.fullmatch(r'[1-9]\d*:[1-9]\d*', str(config.get('frameRatio', ''))): error('config.frameRatio须为正整数比例，例如16:9、1:1或自定义比例')
    for key in STAGES:
        if data['workflow'].get('stages', {}).get(key) not in ('pending', 'in_progress', 'ready', 'approved'):
            error(f'workflow.stages.{key}状态无效')
    for collection in ('characters', 'assets', 'clips'):
        seen = set()
        for item in data[collection]:
            if not isinstance(item, dict) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*', str(item.get('id', ''))):
                error(f'{collection}含无效ID'); continue
            if item['id'] in seen: error(f'{collection}重复ID：{item["id"]}')
            seen.add(item['id'])
    if errors:
        return {'status': 'failed', 'errors': errors, 'warnings': warnings, 'checks': {}}
    characters = {c['id']: c for c in data['characters']}
    assets = {a['id']: a for a in data['assets']}
    clips = {c['id']: c for c in data['clips']}
    for cid, character in characters.items():
        if not character.get('name'): error(f'{cid}缺少人物名称')
        if character.get('voice', {}).get('referenceAudio'):
            if not resolve_file(project_path, character['voice']['referenceAudio']).is_file(): error(f'{cid}参考音频不存在')
    for aid, asset in assets.items():
        if asset.get('kind') not in KINDS: error(f'{aid}资产类型无效')
        if not isinstance(asset.get('path'), str) or not asset['path']:
            error(f'{aid}资产路径缺失'); continue
        path = resolve_file(project_path, asset['path'])
        if not path.is_file() or path.stat().st_size == 0:
            error(f'{aid}图片不存在或为空：{path}'); continue
        if not asset.get('sha256') or digest(path) != asset['sha256']: error(f'{aid}图片哈希不匹配')
        head = path.read_bytes()[:32]
        png = head.startswith(b'\x89PNG\r\n\x1a\n') and head[12:16] == b'IHDR'
        other = head.startswith(b'\xff\xd8\xff') or (head[:4] == b'RIFF' and head[8:12] == b'WEBP')
        if not png and not other: error(f'{aid}不支持或无效的图片文件头（支持PNG/JPEG/WebP）')
        if png and len(head) >= 24 and asset.get('aspectRatio'):
            try:
                width, height = struct.unpack('>II', head[16:24]); rw, rh = map(float, asset['aspectRatio'].split(':'))
                if not width or not height or rw <= 0 or rh <= 0 or abs(width / height - rw / rh) > .015: error(f'{aid}PNG画幅与声明不一致')
            except (ValueError, ZeroDivisionError): error(f'{aid}画幅格式无效')
        if asset.get('kind') == 'character' and asset.get('characterId') not in characters: error(f'{aid}人物资产未绑定角色')
        if asset.get('kind') == 'firstFrame' and asset.get('aspectRatio') != config['frameRatio']:
            error(f'{aid}首帧比例与项目画幅不一致，不能只改项目比例而沿用错误构图')
        if asset.get('visualReview') != 'passed': warning(f'{aid}图片内容未在本清单登记目视通过')
    for cid, clip in clips.items():
        duration = clip.get('duration')
        if not number(duration) or duration <= 0:
            error(f'{cid}时长无效'); continue
        if abs(duration - config['clipSeconds']) > 1e-6: error(f'{cid}不符合项目每段时长')
        if clip.get('status') not in ('draft', 'prompt_ready', 'video_reported', 'video_verified'): error(f'{cid}制作状态无效')
        ready = clip.get('status') != 'draft' or for_render
        prompt = ''
        if clip.get('promptPath'):
            path = resolve_file(project_path, clip['promptPath'])
            if not path.is_file() or not path.read_text(encoding='utf-8-sig').strip(): error(f'{cid}提示词不存在或为空')
            else:
                prompt = path.read_text(encoding='utf-8-sig')
                if digest(path) != clip.get('promptSha256'): error(f'{cid}提示词哈希不匹配')
        elif ready: error(f'{cid}尚未准备提示词，不能排占位段')
        shots, lines, refs = clip.get('shots', []), clip.get('dialogue', []), clip.get('references', [])
        if ready and not shots: error(f'{cid}缺少镜头')
        previous = 0
        for shot in shots:
            a, b = shot.get('start'), shot.get('end')
            if not number(a) or not number(b) or a < 0 or b <= a or b > duration or abs(a-previous) > 1e-6:
                error(f'{cid}镜头时间轴有空隙、重叠或越界'); continue
            if b-a > config['maxShotSeconds'] + 1e-6: error(f'{cid}单镜{b-a:.1f}秒超过上限')
            if not shot.get('description'): error(f'{cid}镜头缺少描述')
            previous = b
        if shots and abs(previous-duration) > 1e-6: error(f'{cid}镜头没有覆盖全段')
        previous = 0
        for line in lines:
            a, b = line.get('start'), line.get('end'); who = characters.get(line.get('characterId'))
            if not number(a) or not number(b) or a < 0 or b <= a or b > duration:
                error(f'{cid}对白时间无效'); continue
            if not config.get('allowDialogueOverlap', False) and a < previous-1e-6: error(f'{cid}对白重叠或未按时间排列')
            previous = max(previous, b)
            if not who:
                error(f'{cid}对白角色不存在'); continue
            voice = who.get('voice', {}).get('description', '')
            if not voice: error(f'{cid}说话人{who["name"]}未登记文字音色')
            if ready and (not line.get('text') or line['text'] not in prompt): error(f'{cid}提示词缺少指定台词')
            if ready and voice and voice not in prompt: error(f'{cid}提示词缺少{who["name"]}固定音色')
            if len(re.findall(r'[\u4e00-\u9fff]', line.get('text', ''))) / (b-a) > config['maxHanPerSecond']: warning(f'{cid}台词可能过快：{line.get("text", "")}')
        used = set()
        for index, ref in enumerate(refs, 1):
            if ref.get('order') != index or ref.get('imageLabel') != image_label(index): error(f'{cid}图号或上传顺序不连续')
            asset = assets.get(ref.get('assetId'))
            if not asset:
                error(f'{cid}引用资产不存在：{ref.get("assetId")}'); continue
            if asset.get('characterId'): used.add(asset['characterId'])
            if not ref.get('purpose'): error(f'{cid}参考图缺少职责')
            if ready and ref.get('imageLabel', '') not in prompt: error(f'{cid}提示词未绑定{ref.get("imageLabel")}')
        if ready:
            if not refs or assets.get(refs[0].get('assetId'), {}).get('kind') != 'firstFrame': error(f'{cid}第一张必须是已存在的首帧')
            if not any(assets.get(r.get('assetId'), {}).get('kind') == 'scene' for r in refs): error(f'{cid}缺少场景图')
            for char_id in clip.get('requiredCharacters', []):
                if char_id not in characters: error(f'{cid}所需角色不存在：{char_id}')
                elif char_id not in used: error(f'{cid}缺少{characters[char_id]["name"]}人物图')
                elif characters[char_id].get('appearance') and characters[char_id]['appearance'] not in prompt: warning(f'{cid}外形说明与角色表文字不完全一致，需核对语义和图片')
            if not clip.get('endState') or not clip.get('bridge'): error(f'{cid}缺少终态或段间衔接说明')
    if for_render and not clips: error('尚无完整片段，不能生成占位图文包')
    if not errors:
        for cid, record in data['locks'].items():
            if cid not in clips or clip_fingerprint(data, clips[cid], project_path) != record.get('fingerprint'): error(f'{cid}已锁定内容或依赖发生变化')
    if baseline:
        if not only: error('提供baseline时必须指定only修改范围')
        elif not isinstance(baseline.get('project'), dict) or not isinstance(baseline.get('clipFingerprints'), dict): error('快照格式无效')
        else:
            allowed = set(only)
            if allowed - set(clips): error('only包含不存在的片段')
            old = baseline['project']; old_clips = {c['id']: c for c in old['clips']}
            if set(old_clips) != set(clips): error('局部修订不能静默增删其他片段')
            for key in ('project', 'config', 'sources'):
                if old.get(key) != data.get(key): error(f'局部修订改变了共享{key}字段')
            if not errors:
                for cid in set(old_clips) - allowed:
                    if clip_fingerprint(data, clips[cid], project_path) != baseline['clipFingerprints'].get(cid): error(f'{cid}不在本轮修改范围内')
                for cid, lock in old.get('locks', {}).items():
                    if cid not in allowed and data['locks'].get(cid) != lock: error(f'{cid}锁定记录被改变')
    return {'status': 'failed' if errors else 'passed', 'errors': errors, 'warnings': warnings,
            'checks': {'clipCount': len(clips), 'referenceCount': sum(len(c.get('references', [])) for c in clips.values()),
                       'lockedClips': list(data['locks']), 'nextAction': next_action(data),
                       'visualStoryAndVideoVerified': False}}
