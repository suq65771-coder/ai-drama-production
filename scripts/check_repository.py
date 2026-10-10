"""Dependency-free repository checks for the distributable Codex skill."""
from pathlib import Path
import ast
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills/ai-drama-production'
EXCLUDED = {'.git', '.test-work', '__pycache__', '.venv', 'venv', 'dist', 'my-drama', 'local-projects'}


def distributable_files():
    return sorted(p for p in ROOT.rglob('*') if p.is_file()
                  and not set(p.relative_to(ROOT).parts) & EXCLUDED and p.suffix != '.pyc')


def main():
    errors = []
    required = ['README.md', '.gitignore', '.gitattributes', '.github/workflows/validate.yml',
                'tests/test_skill.py', 'skills/ai-drama-production/SKILL.md',
                'skills/ai-drama-production/agents/openai.yaml',
                'skills/ai-drama-production/assets/package-template.html']
    for name in required:
        if not (ROOT/name).is_file(): errors.append('缺少必需文件：'+name)
    if errors:
        print(json.dumps({'status':'failed','errors':errors},ensure_ascii=False));return 1
    text = (SKILL/'SKILL.md').read_text(encoding='utf-8')
    match = re.match(r'^---\n(.*?)\n---\n', text, re.S)
    if not match: errors.append('SKILL.md缺少YAML frontmatter')
    else:
        name = re.search(r'^name:\s*(.+)$',match.group(1),re.M)
        description = re.search(r'^description:\s*(.+)$',match.group(1),re.M)
        if not name or name.group(1).strip() != 'ai-drama-production': errors.append('Skill名称与目录不一致')
        if not description or not description.group(1).strip(): errors.append('缺少Skill触发描述')
    if re.search(r'TODO|FIXME|\[INSERT', text): errors.append('SKILL.md有未完成脚手架')
    files = distributable_files()
    # Split Unix prefixes so the scanner does not flag its own pattern definition.
    private_path = re.compile(r'[A-Za-z]:[\\/](?:Users|Codex|codex_Workspace)[\\/]' + '|'
                              + re.escape('/'+'Users'+'/') + r'[^/\s]+/' + '|'
                              + re.escape('/'+'home'+'/') + r'[^/\s]+/')
    token = re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{24,}|sk-[A-Za-z0-9]{24,})')
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        if path.suffix.lower() not in ('.py','.md','.yaml','.yml','.html') and path.name not in ('.gitignore','.gitattributes'):
            errors.append('出现未约定的发布文件：'+rel);continue
        content = path.read_text(encoding='utf-8')
        if private_path.search(content): errors.append('包含本机绝对路径：'+rel)
        if token.search(content): errors.append('疑似凭据内容，请检查文件：'+rel)
        if path.suffix == '.py':
            try: ast.parse(content,filename=rel,feature_version=(3,10))
            except SyntaxError as exc: errors.append(f'Python3.10语法检查失败：{rel}:{exc.lineno}')
        if path.suffix == '.md':
            for link in re.findall(r'\[[^\]]+\]\(([^)]+)\)',content):
                if '://' in link or link.startswith('#'):continue
                target = path.parent/link.split('#',1)[0]
                if not target.is_file():errors.append('Markdown链接失效：'+rel+' -> '+link)
    print(json.dumps({'status':'failed' if errors else 'passed','fileCount':len(files),
                      'skillName':'ai-drama-production','checks':['required files','frontmatter','links','Python3.10 syntax','portable paths','credential patterns'],
                      'errors':errors},ensure_ascii=False))
    return 1 if errors else 0


if __name__=='__main__':
    sys.exit(main())
