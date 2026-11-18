import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import news_sources
from continuous_data import NewsStore, parse_feed, parse_telegram, quick_sentiment, tag_assets

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


def telegram(channel='WatcherGuru', text='JUST IN: 🇺🇸 Binance hacked, withdrawals halted.', at='2026-11-02T11:58:00+00:00', post=101):
    return ('<html><div class="tgme_widget_message_wrap js-widget_message_wrap"><div class="tgme_widget_message" data-post="' + channel + '/' + str(post) +
            '"><div class="tgme_widget_message_text js-message_text" dir="auto">' + text + '<br/>@WatcherGuru</div>'
            '<a class="tgme_widget_message_date"><time datetime="' + at + '" class="time">11:58</time></a></div></div></html>').encode()


class NewsSourceTests(unittest.TestCase):
    def test_x_accounts_are_read_from_their_telegram_channels(self):
        (row,) = parse_telegram(telegram(), 'Watcher Guru', 'WatcherGuru', NOW)
        self.assertEqual((row['group'], row['url'], row['title']), ('x', 'https://t.me/WatcherGuru/101', 'JUST IN: 🇺🇸 Binance hacked, withdrawals halted.'))
        self.assertIn('MACRO', row['assets']); self.assertEqual(row['quick']['impact'], 'negative')
        self.assertFalse(parse_telegram(telegram(channel='Someone'), 'Watcher Guru', 'WatcherGuru', NOW), 'a forwarded post from another channel is not this source')
        alert = parse_telegram(telegram(text='🚨 🚨 🚨 3,000 $BTC transferred from #Binance'), 'Whale Alert', 'WatcherGuru', NOW, universe=['BTC'], analyze=False)[0]
        self.assertTrue(alert['title'].startswith('3,000 $BTC')); self.assertFalse(alert['eligible'], 'transfers are never queued for the AI')

    def test_coins_are_found_by_name_and_cashtag(self):
        self.assertEqual(tag_assets('Solana and $ZEC rally', universe=['ZEC', 'SOL']), ['SOL', 'ZEC'])
        self.assertEqual(tag_assets('$PEPE pumps', universe=['kPEPE']), ['kPEPE'])
        self.assertEqual(tag_assets('Fed signals a rate cut in December'), ['MACRO'])
        self.assertEqual(tag_assets('Bitcoin market update'), ['BTC'])

    def test_instant_reading_of_a_headline(self):
        self.assertEqual(quick_sentiment('SEC approves spot Solana ETF')['impact'], 'positive')
        self.assertEqual(quick_sentiment('Exchange hacked, $300M drained')['impact'], 'negative')
        self.assertEqual(quick_sentiment('Weekly market wrap')['impact'], 'uncertain')

    def test_atom_feeds_and_other_sites_work(self):
        atom = ('<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Ethereum upgrade goes live</title><link href="https://example-news.com/a"/>'
                '<updated>2026-11-02T11:00:00Z</updated><summary>Mainnet upgrade.</summary></entry></feed>').encode()
        (row,) = parse_feed(atom, 'Example', NOW, expected='example-news.com', group='custom')
        self.assertEqual((row['assets'], row['quick']['impact'], row['group']), (['ETH'], 'positive', 'custom'))
        self.assertFalse(parse_feed(atom, 'Example', NOW, expected='other.com'))

    def test_owner_can_switch_sources_and_add_safe_ones_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertTrue(all(s['enabled'] for s in news_sources.load(root)))
            sources = news_sources.save(root, {'disabled': ['x-whalealert', 'unknown'], 'custom': [
                {'kind': 'telegram', 'channel': 'https://t.me/s/BWEnews', 'name': 'BWEnews'}, {'kind': 'rss', 'url': 'https://example-news.com/feed'}]})
            by_id = {s['id']: s for s in sources}
            self.assertFalse(by_id['x-whalealert']['enabled'])
            custom = [s for s in sources if s['group'] == 'custom']
            self.assertEqual([c.get('channel') or c.get('url') for c in custom], ['BWEnews', 'https://example-news.com/feed'])
            for bad in ({'kind': 'rss', 'url': 'http://example.com/feed'}, {'kind': 'rss', 'url': 'https://127.0.0.1/feed'},
                        {'kind': 'rss', 'url': 'https://user:pw@example.com/feed'}, {'kind': 'telegram', 'channel': 'a b'}, {'kind': 'ftp', 'url': 'x'}):
                with self.assertRaises(ValueError): news_sources.save(root, {'custom': [bad]})

    def test_collector_reads_due_sources_and_reports_each(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); store = NewsStore(root / 'news.sqlite'); memory = {}; calls = []
            def reader(source, universe, now):
                calls.append(source['id'])
                if source['id'] == 'decrypt': raise ValueError('HTTP 503')
                return parse_telegram(telegram(post=len(calls)), source['name'], 'WatcherGuru', now) if source['kind'] == 'telegram' else []
            report = news_sources.collect(root, store, memory, now=NOW, reader=reader)
            self.assertEqual(len(calls), len(news_sources.SOURCES))
            failed = next(s for s in report['sources'] if s['id'] == 'decrypt')
            self.assertEqual((failed['ok'], failed['error']), (False, 'HTTP 503'))
            calls.clear(); news_sources.collect(root, store, memory, now=NOW.replace(second=40), reader=reader)
            self.assertTrue(calls and all(c.startswith('x-') for c in calls), 'after 40 s only the X accounts are due again')
            recent = store.recent(30, NOW); store.close()
            self.assertTrue(recent and recent[0]['reading']['by'] == 'quick')


if __name__ == '__main__':
    unittest.main()
