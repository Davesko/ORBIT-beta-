"""Skill libraries: SKILL.md text is indexed, matched to projects by meaning and domain, adopted as ORBIT methods; nothing runs."""
import tempfile,unittest
from pathlib import Path

import skill_library as L
import assistant_skills
import autopilot_hub
from studio import Studio

SKILL='''---
name: canvas-design
description: Create beautiful visual art posters and designs using design philosophy, color and composition.
---
# Canvas design
## The Process
1. Choose a design philosophy for the poster
   and write it down in one paragraph.
2. Lay out the composition with a clear visual hierarchy.
## Verification
- Check every text is readable at thumbnail size.
```python
print("never run")
```
'''


class Library(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.s=Studio(Path(self.tmp.name));self.addCleanup(self.s.db.close)
        for src in L.SOURCES:
            d=L.folder(self.s,src['repo'])/'skills'/'canvas-design';d.mkdir(parents=True)
            (d.parent.parent/'.git').mkdir()
        (L.folder(self.s,'anthropics/skills')/'skills/canvas-design/SKILL.md').write_text(SKILL)
        (L.folder(self.s,'anthropics/skills')/'skills/canvas-design/run.py').write_text('raise SystemExit("must not run")')
        self.runs=[]
        L.refresh(self.s,run=lambda *a,**k:self.runs.append(a[0]) or type('r',(),{'returncode':0,'stderr':''})())
        pid=self.s.create_project('Poszter bolt','Etsy poszter grafika és design termékek')
        self.pid=pid

    def test_index_reads_text_only(self):
        row=self.s.db.execute("SELECT name,scripts FROM skill_library").fetchone()
        self.assertEqual((row['name'],row['scripts']),('canvas-design',1))
        self.assertTrue(all(cmd[0]=='git' for cmd in self.runs),'only git is called, nothing from the library')

    def test_a_fitting_skill_is_matched_and_adopted_as_a_method(self):
        m=L.matches(self.s)
        self.assertEqual((m[0]['name'],m[0]['project']),('canvas-design',self.pid))
        note=L.scout(self.s)
        self.assertIn('Canvas design',note)
        d=next(x for x in assistant_skills.listing(self.s) if x.get('source')=='library')
        self.assertTrue(d['steps'][0].startswith('Choose a design philosophy for the poster and write it down'),d['steps'])
        self.assertIn('thumbnail',d['verification'][0])
        self.assertNotIn('never run',json_dump(d))
        self.assertEqual(d['library']['repo'],'anthropics/skills')
        self.assertIn('nem volt új',L.scout(self.s),'adopted once')

    def test_an_owner_added_library_only_gives_drafts(self):
        with self.assertRaises(ValueError):L.add_source(self.s,'http://evil.example/x')

    def test_the_autopilot_skill_goal_uses_the_scout(self):
        self.assertEqual(autopilot_hub.kind_of('Dolgozz folyamatosan azon hogy a meglévő projektek alapján, számomra hasznos új skilleket sajátíts el.'),'skills')
        self.assertEqual(autopilot_hub.kind_of('Keress munkamódszereket a projektjeimhez'),'skills')


def json_dump(d):
    import json;return json.dumps(d,ensure_ascii=False)
