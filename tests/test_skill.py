"""Integration checks for actual project initialization, scoped revisions and HTML delivery."""
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import unquote
import json
import subprocess
import sys
import tempfile
import struct
import zlib
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills/ai-drama-production'
sys.path.insert(0, str(SKILL / 'scripts'))
from production_common import clip_fingerprint, digest, make_snapshot, next_action, read_json, validate, write_json
from project import blank_project
from render_package import render


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids, self.images, self.buttons, self.areas = [], [], [], {}
        self.current = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if 'id' in values: self.ids.append(values['id'])
        if tag == 'img': self.images.append(values['src'])
        if tag == 'button': self.buttons.append(values.get('data-copy-target'))
        if tag == 'textarea':
            self.current = values.get('id')
            if self.current: self.areas[self.current] = ''

    def handle_data(self, text):
        if self.current: self.areas[self.current] += text

    def handle_endtag(self, tag):
        if tag == 'textarea': self.current = None


class SkillIntegration(unittest.TestCase):
    def setUp(self):
        run_root = ROOT / '.test-work'
        run_root.mkdir(exist_ok=True)
        self.directory = Path(tempfile.mkdtemp(prefix='case_', dir=run_root))
        self.path = self.directory / 'drama-project.json'
        self.image_path = self.directory / 'fixture_16x9.png'
        # A tiny solid-color PNG tests file mechanics; it is not a production reference.
        def chunk(kind, payload):
            return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload) & 0xffffffff)
        raw = b''.join(b'\x00' + bytes((70, 100, 140)) * 16 for _ in range(9))
        image = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 16, 9, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')
        self.image_path.write_bytes(image)
        self.data = blank_project('横屏测试 <script>alert(1)</script>', '16:9')
        self.data['workflow']['stages'] = {s: 'ready' if s != 'review' else 'pending' for s in self.data['workflow']['stages']}
        self.data['characters'] = [{'id': 'C01', 'name': '测试人物', 'appearance': '测试服装说明。', 'voice': {'description': '平稳自然中音。', 'referenceAudio': None}}]
        self.data['assets'] = [dict(id='A'+str(i), kind=kind, label='测试参考'+str(i), path=str(self.image_path),
                                    sha256=digest(self.image_path), aspectRatio='16:9', visualReview='pending',
                                    **({'characterId': 'C01'} if kind == 'character' else {}))
                               for i, kind in enumerate(('firstFrame', 'character', 'scene'), 1)]
        for cid in ('B01', 'B09'):
            prompt = self.directory / (cid+'.txt')
            prompt.write_text('16:9。图一首帧。图二人物。图三场景。测试服装说明。平稳自然中音。台词：你好。\n收尾。', encoding='utf-8')
            self.data['clips'].append({'id': cid, 'title': '测试段', 'duration': 10, 'status': 'prompt_ready', 'videoStatus': 'not_verified',
                'promptPath': prompt.name, 'promptSha256': digest(prompt), 'requiredCharacters': ['C01'],
                'shots': [{'start': a, 'end': b, 'description': '真实切镜与连续动作。'} for a,b in [(0,2.5),(2.5,5),(5,7.5),(7.5,10)]],
                'dialogue': [{'characterId': 'C01', 'text': '你好。', 'start': .1, 'end': 1.5, 'tone': '日常问候'}],
                'references': [{'order': i, 'imageLabel': label, 'assetId': 'A'+str(i), 'purpose': '机械测试素材，不代表目视验收。'} for i,label in enumerate(('图一','图二','图三'),1)],
                'startState': '初态', 'endState': '终态', 'bridge': '时间与动作连续。'})
        self.data['locks']['B01'] = {'fingerprint': clip_fingerprint(self.data, self.data['clips'][0], self.path), 'reason': '测试锁定'}
        write_json(self.path, self.data)

    def cli(self, *args):
        return subprocess.run([sys.executable, '-X', 'utf8', str(SKILL/'scripts/project.py'), *map(str,args)], capture_output=True, text=True, encoding='utf-8')

    def update_prompt(self, clip):
        path = self.directory / clip['promptPath']
        path.write_text(path.read_text(encoding='utf-8')+'\n补充自然表演。', encoding='utf-8')
        clip['promptSha256'] = digest(path)

    def test_fresh_projects_offer_every_ratio(self):
        for index, ratio in enumerate(('9:16','16:9','1:1','4:5','21:9','3:2')):
            with self.subTest(ratio=ratio):
                target = self.directory/str(index)
                result = self.cli('init',target,'--title','新故事','--ratio',ratio)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                data = read_json(target/'drama-project.json')
                self.assertEqual(data['config']['frameRatio'],ratio)
                self.assertEqual(next_action(data)['stage'],'story')
                self.assertEqual(data['assets'],[]); self.assertEqual(data['clips'],[])

    def test_ratio_is_required_and_invalid_ratios_rejected(self):
        self.assertNotEqual(self.cli('init',self.directory/'unset','--title','新故事').returncode,0)
        self.assertNotEqual(self.cli('init',self.directory/'bad','--title','新故事','--ratio','0:16').returncode,0)

    def test_existing_project_not_overwritten(self):
        before = self.path.read_bytes()
        result = self.cli('init',self.directory,'--title','另一个故事','--ratio','1:1')
        self.assertNotEqual(result.returncode,0); self.assertEqual(before,self.path.read_bytes())

    def test_resume_goes_to_review(self):
        result = self.cli('status',self.path)
        self.assertEqual(result.returncode,0,result.stdout)
        self.assertEqual(json.loads(result.stdout)['nextAction']['stage'],'review')

    def test_targeted_revision_passes(self):
        baseline = make_snapshot(self.data,self.path)
        self.update_prompt(self.data['clips'][1])
        self.data['clips'][1]['shots'][0]['description'] = '修改目标片段表演。'
        self.assertEqual(validate(self.data,self.path,baseline,['B09'])['status'],'passed')

    def test_non_target_revision_fails_even_with_updated_hash(self):
        self.data['locks'] = {}
        baseline = make_snapshot(self.data,self.path)
        self.update_prompt(self.data['clips'][0])
        report = validate(self.data,self.path,baseline,['B09'])
        self.assertEqual(report['status'],'failed'); self.assertTrue(any('不在本轮' in e for e in report['errors']))

    def test_locked_content_cannot_be_changed(self):
        self.update_prompt(self.data['clips'][0])
        report = validate(self.data,self.path)
        self.assertEqual(report['status'],'failed'); self.assertTrue(any('已锁定' in e for e in report['errors']))

    def test_shared_voice_change_is_rejected(self):
        baseline = make_snapshot(self.data,self.path)
        self.data['characters'][0]['voice']['description'] += '改成另一种音色。'
        self.assertEqual(validate(self.data,self.path,baseline,['B09'])['status'],'failed')

    def test_missing_images_do_not_replace_existing_html(self):
        output = self.directory/'index.html'; output.write_text('<html><body>保留的原文</body></html>',encoding='utf-8')
        before = output.read_bytes(); self.data['assets'][0]['path'] = '不存在的图.png'
        with self.assertRaises(ValueError): render(self.data,self.path,output)
        self.assertEqual(before,output.read_bytes())

    def test_long_shots_are_rejected(self):
        self.data['clips'][1]['shots'] = [{'start':0,'end':10,'description':'错误的10秒单镜'}]
        self.assertEqual(validate(self.data,self.path)['status'],'failed')

    def test_wrong_reference_order_is_rejected(self):
        self.data['clips'][1]['references'][1]['imageLabel'] = '图八'
        self.assertEqual(validate(self.data,self.path)['status'],'failed')

    def test_wrong_first_frame_ratio_is_rejected(self):
        self.data['config']['frameRatio'] = '1:1'
        self.assertEqual(validate(self.data,self.path)['status'],'failed')

    def test_draft_projects_cannot_render_placeholder_pages(self):
        output = self.directory/'empty.html'
        with self.assertRaises(ValueError): render(blank_project('新故事','1:1'),self.path,output)
        self.assertFalse(output.exists())

    def test_html_matches_prompts_images_and_copy_buttons(self):
        output = self.directory/'delivery/index.html'
        self.assertEqual(render(self.data,self.path,output)['status'],'rendered')
        before = output.read_bytes()
        self.assertEqual(render(self.data,self.path,output)['status'],'unchanged')
        self.assertEqual(before,output.read_bytes())
        html = output.read_text(encoding='utf-8'); parser=Page();parser.feed(html)
        self.assertNotIn('<script>alert(1)</script>',html)
        self.assertIn('画幅 16:9',html)
        self.assertEqual(len(parser.ids),len(set(parser.ids)))
        self.assertEqual(len(parser.images),6)
        self.assertEqual(set(parser.buttons),set(parser.areas))
        for url in parser.images: self.assertTrue((output.parent/unquote(url)).is_file())
        for clip in self.data['clips']:
            self.assertEqual(parser.areas['adp-prompt-'+clip['id']],(self.directory/clip['promptPath']).read_text(encoding='utf-8'))

    def test_existing_html_keeps_other_content_and_updates_only_module(self):
        output=self.directory/'existing.html';output.write_text('<html><body><p id="keep">原页面内容</p></body></html>',encoding='utf-8')
        render(self.data,self.path,output)
        self.update_prompt(self.data['clips'][1]);render(self.data,self.path,output)
        html=output.read_text(encoding='utf-8')
        self.assertIn('<p id="keep">原页面内容</p>',html)
        self.assertEqual(html.count('<!-- AI_DRAMA_PACKAGE_START -->'),1)
        self.assertTrue(list((self.directory/'backups').glob('*.html')))

    def test_legacy_import_is_standalone_and_read_only(self):
        tasks=[]
        for clip in self.data['clips']:
            tasks.append({'id':clip['id'],'name':clip['title'],'seconds':10,
                'prompt':str(self.directory/clip['promptPath']),'promptSha256':clip['promptSha256'],
                'references':[{'uploadOrder':r['order'],'imageLabel':r['imageLabel'],
                    'label':'测试人物人物表' if self.data['assets'][i]['kind']=='character' else '测试图片',
                    'kind':self.data['assets'][i]['kind'],'file':str(self.image_path),
                    'sha256':digest(self.image_path),'purpose':r['purpose']}
                    for i,r in enumerate(clip['references'])],
                'ranges':[[s['start'],s['end']] for s in clip['shots']],
                'beats':[s['description'] for s in clip['shots']],
                'lines':[dict(role='测试人物',text=l['text'],start=l['start'],end=l['end']) for l in clip['dialogue']],
                'bridge':clip['bridge'],'end':clip['endState']})
        manifest=self.directory/'tasks.json';voices=self.directory/'voices.json'
        write_json(manifest,{'film':'虚构测试','b01VideoRetained':True,'tasks':tasks})
        write_json(voices,{'roles':[{'id':'V_01','role':'测试人物','description':'平稳自然中音。'}]})
        original={str(p):digest(p) for p in [manifest,voices,self.image_path,self.directory/'B01.txt',self.directory/'B09.txt']}
        output=self.directory/'imported/drama-project.json'
        result=self.cli('import-pack',manifest,'--voices',voices,'--output',output,'--ratio','16:9')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        data=read_json(output)
        self.assertEqual(len(data['clips']),2);self.assertEqual(len(data['assets']),6)
        self.assertIn('B01',data['locks'])
        self.assertEqual(validate(data,output)['status'],'passed')
        self.assertEqual(original,{path:digest(path) for path in original})

    def test_snapshot_and_lock_commands(self):
        snapshot=self.directory/'snapshot.json'
        self.assertEqual(self.cli('snapshot',self.path,'--output',snapshot).returncode,0)
        saved=read_json(snapshot)
        self.assertIn('B09',saved['clipFingerprints'])
        self.assertEqual(self.cli('lock',self.path,'--clip','B09','--reason','测试确认').returncode,0)
        self.assertIn('B09',read_json(self.path)['locks'])


if __name__=='__main__':
    unittest.main(verbosity=2)
