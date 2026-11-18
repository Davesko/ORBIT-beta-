"""Exercise the boundary missed by browser mocks: native command admission."""
import re,unittest
from pathlib import Path
class NativeConnectionsContractTests(unittest.TestCase):
 def test_every_connections_action_is_admitted_by_native_shell(self):
  base=Path(__file__).parent;swift=(base/'OrbitApp.swift').read_text();js=(base/'web/connections_ui.js').read_text()
  actions=set(re.findall(r'"([a-z_]+)"',swift.split('private let actions: Set<String> = [',1)[1].split(']',1)[0]))
  actions.update(re.findall(r'if action == "([a-z_]+)"',swift))
  used=set(re.findall(r"call\('([a-z_]+)'",js))
  self.assertEqual(used-actions,set(),'The native shell must admit every settings action')
 def test_automation_actions_are_admitted_by_native_shell(self):
  base=Path(__file__).parent;swift=(base/'OrbitApp.swift').read_text();js=(base/'web/automations_ui.js').read_text()
  actions=set(re.findall(r'"([a-z_]+)"',swift.split('private let actions: Set<String> = [',1)[1].split(']',1)[0]));used=set(re.findall(r"(?:call|taskCall)\('([a-z_]+)'",js));self.assertEqual(used-actions,set())
 def test_workbench_controls_are_admitted_by_native_shell(self):
  base=Path(__file__).parent;swift=(base/'OrbitApp.swift').read_text();actions=set(re.findall(r'"([a-z_]+)"',swift.split('private let actions: Set<String> = [',1)[1].split(']',1)[0]));actions.update(re.findall(r'if action == "([a-z_]+)"',swift))
  used=set()
  for name in ('editing_ui.js','workbench_ui.js'):used.update(re.findall(r"call\('([a-z_]+)'",(base/'web'/name).read_text()))
  self.assertEqual(used-actions,set())
