import json
import socket
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import inference_gate
from execution_queue import DeferredExecution
from inference_stream import chat
from studio import Studio


class SlowModel(BaseHTTPRequestHandler):
    """Reads the prompt for a long time before the first byte, like a 27B model."""
    closed = threading.Event()

    def do_POST(self):
        self.rfile.read(int(self.headers['Content-Length']))
        self.send_response(200)
        self.send_header('Content-Type', 'application/x-ndjson')
        self.end_headers()
        for i in range(60):
            try:
                self.wfile.write(json.dumps(dict(message=dict(content='x'))).encode() + b'\n')
                self.wfile.flush()
            except OSError:
                SlowModel.closed.set()
                return
            time.sleep(.25)
        self.wfile.write(json.dumps(dict(message=dict(content=''), done=True)).encode() + b'\n')

    def log_message(self, *args):
        pass


class Answer(SlowModel):
    def do_POST(self):
        self.rfile.read(int(self.headers['Content-Length']))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps(dict(message=dict(content='kész'), done=True)).encode() + b'\n')


class ChatPriorityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.s = Studio(Path(self.temp.name))
        self.addCleanup(self.s.db.close)
        self.addCleanup(inference_gate.set_background, None)

    def serve(self, handler):
        server = HTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server.server_address[1]

    def waiting_chat(self, age=5, retry_at=None):
        agent = self.s.snapshot('universe')['agents'][0]['id'] if self.s.snapshot('universe')['agents'] else self.s.save_agent(dict(project='universe', name='A', role='A', room='bridge'))
        jid = self.s.enqueue(agent if isinstance(agent, str) else agent['id'], 'Szia', 'command', payload=dict(turn='t', **({'retry_at': retry_at} if retry_at else {})))
        self.s.db.execute('UPDATE jobs SET created=? WHERE id=?', (time.time() - age, jid))
        self.s.db.commit()
        return jid

    def test_waiting_chat_is_recognised_only_when_it_wants_the_model_now(self):
        self.assertFalse(inference_gate.chat_waiting(self.temp.name))
        self.waiting_chat(age=.2)
        self.assertFalse(inference_gate.chat_waiting(self.temp.name))
        self.s.db.execute('DELETE FROM jobs')
        self.s.db.commit()
        self.waiting_chat(retry_at=time.time() + 120)
        self.assertFalse(inference_gate.chat_waiting(self.temp.name))
        self.waiting_chat()
        self.assertTrue(inference_gate.chat_waiting(self.temp.name))

    def test_background_call_hands_the_model_to_a_waiting_chat(self):
        port = self.serve(SlowModel)
        self.waiting_chat()
        inference_gate.set_background('mission_agent')
        started = time.monotonic()
        with self.assertRaises(DeferredExecution):
            chat(port, dict(model='m', messages=[dict(role='user', content='build')]), 60, Path(self.temp.name))
        self.assertLess(time.monotonic() - started, 6)
        self.assertTrue(SlowModel.closed.wait(3))

    def test_chat_itself_and_quiet_times_are_never_interrupted(self):
        port = self.serve(Answer)
        self.waiting_chat()
        inference_gate.set_background('command')
        self.assertEqual(chat(port, dict(model='m', messages=[dict(role='user', content='hi')]), 30, Path(self.temp.name))['message']['content'], 'kész')
        self.s.db.execute('DELETE FROM jobs')
        self.s.db.commit()
        inference_gate.set_background('mission_agent')
        self.assertEqual(chat(port, dict(model='m', messages=[dict(role='user', content='hi')]), 30, Path(self.temp.name))['message']['content'], 'kész')

    def test_refused_connection_still_reads_as_a_connection_error(self):
        import urllib.error
        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
        sock.close()
        with self.assertRaises(urllib.error.URLError):
            chat(port, dict(model='m', messages=[dict(role='user', content='hi')]), 5, Path(self.temp.name))


if __name__ == '__main__':
    unittest.main()


class RunningChatWaitTests(unittest.TestCase):
    def test_a_running_chat_waiting_for_the_lease_raises_the_flag(self):
        import fcntl
        with tempfile.TemporaryDirectory() as root:
            holder = open(Path(root) / 'model-session.lock', 'a')
            fcntl.flock(holder, fcntl.LOCK_EX)
            inference_gate.set_background('command')
            try:
                with self.assertRaises(DeferredExecution):
                    with inference_gate.lease(root, wait=1):
                        pass
            finally:
                inference_gate.set_background(None)
                holder.close()
            self.assertTrue(inference_gate.chat_waiting(root))
