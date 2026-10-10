"""Render complete, validated clips into one stable HTML entry, preserving other page content."""
from pathlib import Path
from html import escape
import argparse
import json
import os
import re
import sys
from urllib.parse import quote
from production_common import backup_file, digest, read_json, resolve_file, tracked_files, validate, write_text

START = '<!-- AI_DRAMA_PACKAGE_START -->'
END = '<!-- AI_DRAMA_PACKAGE_END -->'


def local_url(path, output):
    try:
        return quote(os.path.relpath(path, output.parent).replace('\\', '/'), safe='/')
    except ValueError:
        return path.as_uri()


def render(data, project_path, output):
    report = validate(data, project_path, for_render=True)
    if report['status'] != 'passed':
        raise ValueError('内容尚未通过，原HTML保持不变：' + '; '.join(report['errors']))
    assets = {a['id']: a for a in data['assets']}
    characters = {c['id']: c for c in data['characters']}
    sections, navigation = [], []
    for clip in data['clips']:
        cid = clip['id']; target = 'adp-prompt-' + cid
        navigation.append(f'<a href="#adp-{cid}">{escape(cid)}</a>')
        rows = ''.join(f'<tr><td>{s["start"]:g}—{s["end"]:g}秒</td><td>{s["end"]-s["start"]:g}秒</td><td>{escape(s["description"])}</td></tr>' for s in clip['shots'])
        dialogue = ''.join(f'<li><strong>{l["start"]:g}—{l["end"]:g}秒 · {escape(characters[l["characterId"]]["name"])}</strong>：{escape(l["text"])}<br><small>{escape(l.get("tone", ""))}</small></li>' for l in clip['dialogue'])
        gallery = []
        for ref in clip['references']:
            asset = assets[ref['assetId']]; path = resolve_file(project_path, asset['path'])
            url = escape(local_url(path, output), quote=True)
            ratio = asset.get('aspectRatio', '')
            css_ratio = ratio.replace(':', '/') if re.fullmatch(r'[1-9]\d*:[1-9]\d*', ratio) else 'auto'
            label = escape(ref['imageLabel'] + ' · ' + asset.get('label', asset['id']))
            gallery.append(f'<figure><a href="{url}" target="_blank" rel="noopener"><img loading="lazy" style="aspect-ratio:{css_ratio}" src="{url}" alt="{label}"></a><figcaption><strong>{label}</strong><br>第{ref["order"]}张上传<br><small>{escape(ref["purpose"])}</small><br><a href="{url}" download>保存这张图</a></figcaption></figure>')
        prompt_path = resolve_file(project_path, clip['promptPath']); text = prompt_path.read_text(encoding='utf-8-sig')
        prompt_url = escape(local_url(prompt_path, output), quote=True)
        lock = ' · 已锁定' if cid in data['locks'] else ''
        sections.append(f'<section id="adp-{cid}"><h2>{escape(cid)} · {escape(clip["title"])} · {clip["duration"]:g}秒</h2><span class="adp-status">{escape(clip["status"] + lock)}</span><p class="adp-note">衔接：{escape(clip["bridge"])}</p><h3>对白与表演</h3><ul class="adp-dialogue">{dialogue or "<li>本段无指定对白。</li>"}</ul><h3>镜头时间轴</h3><div class="adp-table"><table><thead><tr><th>时间</th><th>时长</th><th>镜头与动作</th></tr></thead><tbody>{rows}</tbody></table></div><p class="adp-end">段末状态：{escape(clip["endState"])}</p><h3>按顺序上传以下{len(clip["references"])}张参考图</h3><div class="adp-gallery">'+''.join(gallery)+f'</div><h3>完整视频提示词</h3><button type="button" data-copy-target="{target}">复制{cid}完整提示词</button> <a href="{prompt_url}" download>保存TXT</a><textarea id="{target}" readonly aria-label="{cid}完整提示词">{escape(text)}</textarea></section>')
    warnings = ''
    if report['warnings']:
        warnings = f'<details><summary>待复核事项（{len(report["warnings"])}项）</summary><ul>'+''.join('<li>'+escape(w)+'</li>' for w in report['warnings'])+'</ul></details>'
    template = (Path(__file__).resolve().parents[1] / 'assets/package-template.html').read_text(encoding='utf-8')
    config = data['config']; meta = f'画幅 {config["frameRatio"]} · {config["style"]} · {len(data["clips"])}段 · 共{sum(c["duration"] for c in data["clips"]):g}秒 · 单镜≤{config["maxShotSeconds"]:g}秒'
    replacements = {'<!--ADP_TITLE-->': escape(data['project']['title']), '<!--ADP_META-->': escape(meta),
                    '<!--ADP_NAV-->': ''.join(navigation), '<!--ADP_BODY-->': ''.join(sections), '<!--ADP_WARNINGS-->': warnings}
    # One pass prevents replacement-like strings in user content from being expanded.
    fresh = re.sub('|'.join(re.escape(k) for k in replacements), lambda m: replacements[m.group()], template)
    module = fresh[fresh.index(START):fresh.index(END)+len(END)]
    html = fresh
    if output.exists():
        old = output.read_text(encoding='utf-8-sig')
        if START in old or END in old:
            if old.count(START) != 1 or old.count(END) != 1 or old.index(START) > old.index(END):
                raise ValueError('原HTML标记异常，未改写；请检查重复或缺失标记')
            html = old[:old.index(START)] + module + old[old.index(END)+len(END):]
        else:
            match = re.search(r'</body\s*>', old, re.I)
            if not match: raise ValueError('已有文件不是可识别HTML入口，未改写')
            html = old[:match.start()] + module + '\n' + old[match.start():]
        if html == old:
            return {'status': 'unchanged', 'html': str(output), 'sha256': digest(output), 'checks': report['checks']}
        backup_file(output)
    write_text(output, html)
    return {'status': 'rendered', 'html': str(output), 'sha256': digest(output), 'checks': report['checks']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path); parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        data = read_json(args.project)
        output = args.output.resolve() if args.output else resolve_file(args.project, data['config']['packagePath'])
        if output == args.project.resolve(): raise ValueError('HTML不能覆盖项目JSON')
        if str(output) in tracked_files(data, args.project): raise ValueError('HTML不能覆盖已有提示词或资产')
        print(json.dumps(render(data, args.project, output), ensure_ascii=False)); return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'status': 'failed', 'error': str(exc)}, ensure_ascii=False)); return 1


if __name__ == '__main__':
    sys.exit(main())
