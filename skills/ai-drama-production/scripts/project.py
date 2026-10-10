"""Initialize, import, resume and protect AI drama projects without generating media."""
from pathlib import Path
import argparse
import json
import os
import re
import sys
from production_common import (STAGES, backup_file, clip_fingerprint, digest, image_label,
                               make_snapshot, next_action, read_json, validate, write_json, write_text)


def ratio(value):
    if not re.fullmatch(r'[1-9]\d*:[1-9]\d*', value):
        raise argparse.ArgumentTypeError('请明确选择正整数画幅，例如9:16、16:9、1:1、4:5、21:9或自定义比例')
    return value


def blank_project(title, frame_ratio, seconds=10, max_shot=3, style='真人电影', mode='manual'):
    return {'schemaVersion': 1, 'project': {'id': 'drama-project', 'title': title},
            'config': {'frameRatio': frame_ratio, 'style': style, 'clipSeconds': seconds,
                       'maxShotSeconds': max_shot, 'maxHanPerSecond': 5.5, 'allowDialogueOverlap': False,
                       'generationMode': mode, 'packagePath': 'delivery/index.html', 'noBgm': True, 'noGeneratedSubtitles': True},
            'workflow': {'stages': {s: 'pending' for s in STAGES}, 'lastAction': '初始化项目'},
            'characters': [], 'assets': [], 'clips': [], 'locks': {}, 'sources': []}


def portable_path(path, destination):
    try:
        return Path(os.path.relpath(path.resolve(), destination.resolve().parent)).as_posix()
    except ValueError:
        return str(path.resolve())


def import_pack(args):
    source = read_json(args.manifest)
    voices = read_json(args.voices)
    data = blank_project(source.get('film', args.manifest.stem), args.ratio, args.clip_seconds, args.max_shot, args.style)
    by_name = {}
    for voice in voices['roles']:
        cid = voice['id']
        by_name[voice['role']] = cid
        data['characters'].append({'id': cid, 'name': voice['role'], 'appearance': '',
                                   'voice': {'description': voice['description'], 'referenceAudio': None}})
    for index, name in enumerate(voices.get('silentRoles', []), 1):
        if name in by_name: continue
        cid = f'SILENT_{index}'
        by_name[name] = cid
        data['characters'].append({'id': cid, 'name': name, 'appearance': '', 'voice': {'description': '', 'referenceAudio': None}})
    characters = {c['id']: c for c in data['characters']}
    texts = []
    for task in source['tasks']:
        if len(task['ranges']) != len(task['beats']): raise ValueError(f'{task["id"]}镜头时间与描述数量不一致')
        prompt_path = args.manifest.parent / task['prompt']
        text = prompt_path.read_text(encoding='utf-8-sig'); texts.append(text)
        if task.get('promptSha256') and digest(prompt_path) != task['promptSha256']:
            raise ValueError(f'{task["id"]}源提示词哈希错误')
        refs, required = [], []
        for index, item in enumerate(task['references'], 1):
            path = args.manifest.parent / item['file']
            if not path.is_file() or digest(path) != item['sha256']: raise ValueError(f'{task["id"]}源图片缺失或哈希错误')
            aid = f'{task["id"]}_A{index:02}'
            asset = {'id': aid, 'kind': item['kind'], 'label': item['label'],
                     'path': portable_path(path, args.output), 'sha256': digest(path),
                     'aspectRatio': '16:9' if item['kind'] == 'character' else args.ratio,
                     'visualReview': 'pending', 'reviewNote': '从旧包继承，不在导入过程中声称重新目视检查。'}
            if item['kind'] == 'character':
                alias = item['label'].removesuffix('人物表')
                names = sorted((name for name in by_name if alias == name or alias.endswith(name)), key=len, reverse=True)
                if not names: raise ValueError(f'人物参考{alias}无法绑定音色表，需先补齐角色或silentRoles')
                char_id = by_name[names[0]]; asset['characterId'] = char_id; required.append(char_id)
                match = re.search(r'^' + re.escape(alias) + r'：([^\n]+)$', text, re.M)
                if match and not match.group(1).startswith(('“', '"', '‘')) and not characters[char_id]['appearance']:
                    characters[char_id]['appearance'] = match.group(1)
            data['assets'].append(asset)
            refs.append({'order': item['uploadOrder'], 'imageLabel': item['imageLabel'], 'assetId': aid, 'purpose': item['purpose']})
        lines = []
        for line in task['lines']:
            if line['role'] not in by_name: raise ValueError(f'对白角色{line["role"]}不在音色表中')
            lines.append({'characterId': by_name[line['role']], 'text': line['text'], 'start': line['start'],
                          'end': line['end'], 'tone': line.get('tone', '沿用本段完整提示词中的表演说明。')})
        data['clips'].append({'id': task['id'], 'title': task['name'], 'duration': task['seconds'],
                              'status': 'prompt_ready', 'videoStatus': 'not_verified',
                              'promptPath': portable_path(prompt_path, args.output), 'promptSha256': digest(prompt_path),
                              'shots': [{'start': bounds[0], 'end': bounds[1], 'description': beat}
                                        for bounds, beat in zip(task['ranges'], task['beats'])],
                              'dialogue': lines, 'requiredCharacters': list(dict.fromkeys(required)), 'references': refs,
                              'startState': '以已确认首帧和完整提示词中的初态为准。',
                              'endState': task['end'], 'bridge': task['bridge']})
    data['workflow']['stages'] = {s: 'ready' if s != 'review' else 'in_progress' for s in STAGES}
    data['workflow']['lastAction'] = '只读导入已有制作包；视频尚未核验，资产目视状态待复核。'
    data['sources'] = [{'type': 'legacy-pack', 'path': str(args.manifest.resolve()), 'sha256': digest(args.manifest)}]
    if source.get('b01VideoRetained') and any(c['id'] == 'B01' for c in data['clips']):
        first = next(c for c in data['clips'] if c['id'] == 'B01')
        data['locks']['B01'] = {'fingerprint': clip_fingerprint(data, first, args.output),
                                'reason': '源包记录用户保留B01；不代表已经读取实片。'}
    report = validate(data, args.output)
    if report['status'] != 'passed': raise ValueError('; '.join(report['errors']))
    write_json(args.output, data)
    return {'status': 'imported', 'project': str(args.output.resolve()), 'clipCount': len(data['clips']),
            'referenceCount': sum(len(c['references']) for c in data['clips']), 'nextAction': next_action(data)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init')
    init.add_argument('directory', type=Path); init.add_argument('--title', required=True)
    init.add_argument('--ratio', type=ratio, required=True)
    init.add_argument('--clip-seconds', type=float, default=10); init.add_argument('--max-shot', type=float, default=3)
    init.add_argument('--style', default='真人电影'); init.add_argument('--mode', choices=('manual', 'tool'), default='manual')
    imp = commands.add_parser('import-pack')
    imp.add_argument('manifest', type=Path); imp.add_argument('--voices', type=Path, required=True)
    imp.add_argument('--output', type=Path, required=True); imp.add_argument('--ratio', type=ratio, required=True)
    imp.add_argument('--clip-seconds', type=float, default=10); imp.add_argument('--max-shot', type=float, default=3)
    imp.add_argument('--style', default='真人电影')
    status = commands.add_parser('status'); status.add_argument('project', type=Path)
    snapshot = commands.add_parser('snapshot'); snapshot.add_argument('project', type=Path); snapshot.add_argument('--output', type=Path, required=True)
    lock = commands.add_parser('lock'); lock.add_argument('project', type=Path); lock.add_argument('--clip', required=True); lock.add_argument('--reason', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'init':
            path = args.directory / 'drama-project.json'
            if path.exists(): raise ValueError('项目已存在，请读取状态继续，不覆盖初始化')
            plan = args.directory / 'production-plan.md'
            if plan.exists(): raise ValueError('目录已有计划，请检查既有项目后继续')
            data = blank_project(args.title, args.ratio, args.clip_seconds, args.max_shot, args.style, args.mode)
            report = validate(data, path)
            if report['status'] != 'passed': raise ValueError('; '.join(report['errors']))
            write_json(path, data)
            write_text(plan, f'# {args.title} 制作计划\n\n画幅：{args.ratio}；风格：{args.style}；每段{args.clip_seconds:g}秒；单镜≤{args.max_shot:g}秒。\n\n目标：依次完成正式剧本、统一设定、实际资产、导演分镜、独立提示词与HTML交付、实片检查及收尾。按用户当前范围推进，不生成假占位素材。\n\n验收：文件/时序/引用/锁定机械检查，以及剧情、图片和实片内容检查分别记录。已有结果保留，指定片段修订先快照。\n')
            result = {'status': 'initialized', 'project': str(path.resolve()), 'nextAction': next_action(data)}
        elif args.command == 'import-pack':
            if args.output.exists(): raise ValueError('导入目标已存在，拒绝覆盖')
            result = import_pack(args)
        else:
            data = read_json(args.project)
            report = validate(data, args.project)
            if report['status'] != 'passed': raise ValueError('; '.join(report['errors']))
            if args.command == 'status':
                result = {'status': 'read', 'nextAction': next_action(data), 'lockedClips': list(data['locks']),
                          'clips': [{'id': c['id'], 'status': c['status'], 'videoStatus': c.get('videoStatus', 'not_verified')} for c in data['clips']]}
            elif args.command == 'snapshot':
                if args.output.exists(): raise ValueError('快照已存在，使用新文件名保存')
                write_json(args.output, make_snapshot(data, args.project))
                result = {'status': 'snapshot_saved', 'path': str(args.output.resolve())}
            else:
                clip = next((c for c in data['clips'] if c['id'] == args.clip), None)
                if not clip: raise ValueError('片段不存在')
                if clip['status'] == 'draft': raise ValueError('草稿片段不能登记为已确认锁定')
                backup_file(args.project)
                data['locks'][args.clip] = {'fingerprint': clip_fingerprint(data, clip, args.project), 'reason': args.reason}
                write_json(args.project, data)
                result = {'status': 'locked', 'clip': args.clip}
        print(json.dumps(result, ensure_ascii=False)); return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'status': 'failed', 'error': str(exc)}, ensure_ascii=False)); return 1


if __name__ == '__main__':
    sys.exit(main())
