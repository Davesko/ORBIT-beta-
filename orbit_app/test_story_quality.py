import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import story_quality as q
from studio import Studio

PROFILE = dict(art=dict(lead='Pip: orange round head, red cap.', support='Dot: pale grey round head, tiny purple hair tuft.', world='A sparse purple-grey cartoon stage.'))
WEAK = {"premise": "Pip frantically tries to inflate a massive beach ball while Dot calmly holds the nozzle steady.",
        "hook": "Pip's face turns purple with strain as he blows into a giant yellow beach ball.",
        "escalation": "The ball expands rapidly, pushing Pip backward across the stage.",
        "payoff": "The ball pops instantly, releasing a cloud of air that lifts a hair tuft into the sky.",
        "hook_caption": "He blew it all out!", "payoff_caption": "Now she floats!"}
GOOD = dict(WEAK, hook="Pip, cheeks puffed and red, blows into a giant yellow beach ball three times his size.",
            reaction="Pip gives Dot a proud thumbs-up, out of breath.", twist="Dot simply lets go of the valve and the ball rockets around the stage with Pip clinging to it.",
            payoff="Dot lets go of the valve; the ball rockets around the stage with Pip clinging to it.", loop="The empty ball drops at Dot's feet and she hands the valve back to Pip.",
            hook_caption="One more breath…", payoff_caption="She just let go of the ball.")


class ChecksTests(unittest.TestCase):
    def test_the_weak_story_problems_are_found_without_a_model(self):
        found = ' | '.join(q.checks(WEAK, PROFILE))
        for part in ('gives away the outcome', 'payoff caption', 'Dot', 'purple face', 'reaction', 'loop'):
            self.assertIn(part, found)

    def test_a_good_story_passes_the_checks(self):
        self.assertEqual(q.checks(GOOD, PROFILE), [])


class LoopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.s = Studio(Path(self.temp.name))
        self.addCleanup(self.s.db.close)
        self.job = dict(id=None, project='universe')

    def test_weak_idea_is_rewritten_and_the_better_one_kept(self):
        scores = iter([dict(scores={k: 5 for k in q.RUBRIC}, problems=['flat twist'], fix='make Dot cause it'), dict(scores={k: 9 for k in q.RUBRIC}, problems=[], fix='')])
        with patch('autonomous.ask_json', side_effect=lambda *a: next(scores)):
            best, report = q.improve(self.s, self.job, lambda extra: dict(GOOD), WEAK, PROFILE)
        self.assertEqual(best['payoff_caption'], GOOD['payoff_caption'])
        self.assertGreaterEqual(report['total'], q.PASS)
        self.assertEqual(len(report['history']), 2)

    def test_feedback_becomes_lessons_used_next_time(self):
        reply = dict(message=dict(content=json.dumps(dict(lessons=['The hook caption must create curiosity, never reveal the outcome.', 'x']))))
        with patch('studio.local_api', return_value=reply):
            self.assertEqual(len(q.learn(self.s, 'universe', 'a hook felirata lelőtte a poént')), 1)
            self.assertEqual(q.learn(self.s, 'universe', 'ugyanez megint'), [])
        self.assertIn('curiosity', q.lessons(self.s, 'universe')[0])

    def test_chat_feedback_action_teaches_the_writer(self):
        import commander
        with patch('story_quality.learn', return_value=['Rule']) as learn:
            commander.prepare(self.s, 'universe', [dict(type='story_feedback', project='universe', feedback='túl gyenge a csattanó')], global_mode=True)
            self.assertIn('story_feedback', __import__('assistant_tools').ACTION_CONTRACTS)
        learn.assert_not_called()


if __name__ == '__main__':
    unittest.main()


class StricterChecksTests(unittest.TestCase):
    VAC = {'premise': 'Pip tries to suck up a tiny speck of dust with a giant vacuum, while Dot calmly watches from the side.',
           'hook': 'Pip wrestles a huge vacuum nozzle.', 'escalation': 'Pip turns it to MAX POWER.', 'reaction': 'Pip eyes bulge.',
           'payoff': 'The vacuum sucks up the speck and the whole floor, leaving Pip and Dot floating.', 'twist': 'The vacuum swallows the floor.',
           'loop': 'They stare at the speck which is now stuck to the outside of the nozzle.', 'hook_caption': 'This dust fights back!', 'payoff_caption': 'The floor is gone.'}

    def test_a_watching_support_character_and_a_contradicting_loop_are_caught(self):
        found = ' | '.join(q.checks(self.VAC, PROFILE))
        self.assertIn('Dot only watches', found)
        self.assertIn('loop contradicts', found)

    def test_dot_acting_and_a_consistent_loop_pass(self):
        fixed = dict(self.VAC, twist='Dot calmly pinches the speck with two fingers and blows it away.', loop="The speck lands on Pip's nose and he grabs the vacuum again.")
        self.assertEqual(q.checks(fixed, PROFILE), [])


class AnimatableTests(unittest.TestCase):
    def test_a_shape_changing_body_is_flagged(self):
        idea = dict(hook='Pip stares at a bubble.', escalation='Dot pokes it.', twist="Pip's body instantly flattens into a pancake.", reaction='Pip screams.', loop='Pip stares at a bubble.')
        self.assertTrue(any('changes shape' in p for p in q.checks(idea, None)))


class LoopBeatTests(unittest.TestCase):
    def test_the_loop_may_restart_from_the_opening_image(self):
        import story_episode
        shot = lambda beat, i: dict(beat=beat, opening_image='Pip holds the red balloon %d' % i, visual_action='Pip squeezes the balloon %d' % i, visible_result='The balloon bends shape %d' % i)
        clean = [shot(b, i) for i, b in enumerate(story_episode.MEME_BEATS)]
        clean[-1]['opening_image'] = clean[0]['opening_image']
        story_episode.distinct(clean)
        self.assertEqual(clean[-1]['opening_image'], clean[0]['opening_image'])


class AutomationPriorityTests(unittest.TestCase):
    def test_a_number_in_the_task_is_not_a_repeat_order(self):
        import automation_intent as ai
        self.assertFalse(ai.wants('Olvasd be a hibát, ami egy hét alatt 11-szer állította meg a feladatokat, és javítsd'))
        self.assertFalse(ai.wants('Valósítsd meg most ezt a fejlesztést: a hiba 11-szer megállt'))
        self.assertEqual(ai.schedule('a hiba 11-szer állította meg')['daily_goal'], 1)
        self.assertEqual(ai.schedule('fusson le egymás után 3 szor')['daily_goal'], 3)

    def test_an_automation_run_is_background_work(self):
        import inference_gate as g
        g.set_background('command', automated=True)
        self.assertTrue(g.is_background())
        g.set_background('command')
        self.assertFalse(g.is_background())
        g.set_background(None)
