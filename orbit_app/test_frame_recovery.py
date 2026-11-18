import contextlib
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import stickman_studio as st
from story_contract import digest


def plan():
    value = dict(title='Delivery', mission='Deliver the cake.', resolution='You arrive.',
                 support=dict(needed=False), places=[],
                 shots=[dict(say='You walk step %d.' % i, kind='medium', place='street',
                             actors=[], hud='', sound='none') for i in range(5)])
    value['engineering'] = dict(status='verified', version=st.fingerprint(value))
    return value


class FrameRecovery(unittest.TestCase):
    def test_second_round_corrections_are_applied_and_verified(self):
        p = plan()
        s = SimpleNamespace(root=Path('/tmp'), job_stage=lambda *a: None)
        replies = [dict(fixes=[dict(index=i, say='You take step %d.' % i)]) for i in range(3)]
        replies.append(dict(fixes=[], problems=[]))
        with patch('inference_gate.lease', return_value=contextlib.nullcontext()), patch.object(st, 'ask', side_effect=replies):
            st.require_script_review(s, dict(id='j'), p['shots'], p)
        self.assertEqual(p['review']['status'], 'verified')
        self.assertEqual(p['review']['version'], digest(p, p['shots']))
        self.assertEqual(p['shots'][2]['say'], 'You take step 2.')

    def test_unresolved_review_stops_instead_of_marking_script_done(self):
        p = plan()
        s = SimpleNamespace(root=Path('/tmp'), job_stage=lambda *a: None)
        with patch('inference_gate.lease', return_value=contextlib.nullcontext()), patch.object(st, 'ask', return_value=dict(fixes=[], problems=['Missing solution'])):
            with self.assertRaisesRegex(ValueError, 'Missing solution'):
                st.require_script_review(s, dict(id='j'), p['shots'], p)

    def test_frame_reuses_approved_repair_after_audio_failure(self):
        original = plan()
        original['review'] = dict(status='needs_revision')
        with tempfile.TemporaryDirectory() as tmp:
            s = SimpleNamespace(root=Path(tmp), safe_path=lambda pid, path: Path(tmp)/pid/path,
                                job_stage=lambda *a: None)
            calls = []
            def accept(s, job, shots, value):
                calls.append(1)
                shots[0]['say'] = 'You take the cake.'
                value['review'] = dict(status='verified', version=digest(value, shots))
            with patch.object(st, 'review_logic', side_effect=accept), patch.object(st, 'plausible'), patch.object(st, 'fx_from_words'), patch.object(st, 'find_tools'), patch.object(st, 'paint_inserts', return_value={}), patch.object(st, 'paint_tools', return_value={}), patch.object(st, 'prepare_audio', side_effect=[ValueError('audio interrupted'), None]) as audio:
                with self.assertRaisesRegex(ValueError, 'audio interrupted'):
                    st.recover_frame_review(s, dict(id='j', project='p'), 'run', copy.deepcopy(original), dict(support=dict(name='Dot')))
                resumed = copy.deepcopy(original)
                st.recover_frame_review(s, dict(id='j', project='p'), 'run', resumed, dict(support=dict(name='Dot')))
            self.assertEqual(len(calls), 1)
            self.assertEqual(audio.call_count, 2)
            self.assertEqual(resumed['shots'][0]['say'], 'You take the cake.')
            self.assertEqual(resumed['frame_recovery']['changed_lines'], 1)

    def test_no_audio_regeneration_when_saved_text_is_accepted_unchanged(self):
        p = plan()
        with tempfile.TemporaryDirectory() as tmp:
            s = SimpleNamespace(root=Path(tmp), safe_path=lambda pid, path: Path(tmp)/path)
            def accept(s, job, shots, value):
                value['review'] = dict(status='verified', version=digest(value, shots))
            with patch.object(st, 'review_logic', side_effect=accept), patch.object(st, 'prepare_audio') as audio:
                st.recover_frame_review(s, dict(id='j', project='p'), 'run', p, {})
            audio.assert_not_called()

    def test_engineering_rejection_cannot_be_overridden_by_frame_repair(self):
        p = plan()
        p['mission'] = 'Different mission'
        with patch.object(st, 'require_script_review') as review:
            st.recover_frame_review(None, {}, 'run', p, {})
        review.assert_not_called()


if __name__ == '__main__':
    unittest.main()
