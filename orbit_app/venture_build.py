"""Implementation mode: turn the best business idea into real, usable deliverables.

Each cycle the planner picks one roadmap milestone, the builder writes its files into a
persistent product folder and the tester checks them against acceptance criteria. Anything
with an outside effect (publishing, domains, payments, contacting people, legal sign-off) is
never executed: it becomes an owner action with a ready draft on the Autopilot page.
Milestone state is derived from saved cycle results, so there is no second source of truth.
"""
import json,re,time,uuid
from pathlib import Path,PurePosixPath

PID='orbit-business-lab'
EXTS=('.setting','.lua','.md','.txt','.json','.py','.html','.css','.js','.csv','.svg','.example','.toml','.yml','.yaml','.sh','.sql','.ini','.cfg')
# Deployment files without an extension.
NAMES=('Dockerfile','Procfile','Makefile')
SELF_TEST='Every .py file must pass `python3 file.py --self-test` offline within 60 s (example data, no network, no secrets, standard library; a server binds 127.0.0.1 on a free port, calls itself once and exits). The self-test checks every expected value and prints every mismatch as "field: expected X, got Y" before exiting with code 1, instead of stopping at the first failed assert.'
# A finished product sells; it does not collect a waitlist. The owner gives the checkout link (Stripe Payment Link,
# Gumroad, a marketplace page) and ORBIT points every such button at it when the page is launched.
BUY='The buy or order button is an <a data-orbit-checkout href="#">Megveszem</a> link (ORBIT points it at the owner\'s checkout link when the page is launched). No waitlist, no sign-up for later, no "coming soon" and no conditional promises: the page sells the finished product.'
ROADMAPS=dict(
# The sales page and the 48-hour demand test come right after the API: TermékB built billing,
# self-QA and tests for hours before any visitor said whether anyone wanted it.
saas=[
 ('design','Rendszerterv','End-to-end system design: data ingestion and trigger, processing and AI logic (local Ollama first, paid API only where needed), output and delivery channel, data model, failure modes. File: architecture.md.','Honnan jön az adat, mi dolgozza fel, hogyan jut el a vevőhöz – ember nélkül.'),
 ('engine','Működő mag','The runnable core: standard-library Python that turns real example input into the product output (local model calls only through an injected function with a deterministic fallback). '+SELF_TEST+' Files: engine.py, example-input.json, expected-output.json.','A termék működő magja: valódi bemenetből kész kimenet, lefuttatva.'),
 ('api','API-szolgáltatás','The customer-facing HTTP JSON API around the engine (http.server): API-key authentication from an environment variable, per-key rate limit and usage counter, input validation, /health endpoint, clear error responses. '+SELF_TEST+' It must also run as a server with `python3 server.py --port N` (127.0.0.1, API key from ORBIT_TEST_API_KEY when set). Add smoke.json: {"requests": [{"method": "GET", "path": "/health", "expect": 200}, {"method": "POST", "path": "/your-endpoint", "json_file": "example-input.json", "expect": 200, "expect_keys": ["field"]}]}; ORBIT starts the server and sends these real requests. Files: server.py, smoke.json.','Az ügyfelek által hívható API: kulcs, korlát, hibakezelés – lefuttatva.'),
 ('landing','Értékesítő oldal és árazás','The finished product page with real Hungarian or English copy for the target audience, written in the indicative about what the product does now: benefits, how it works, pricing tiers (unverified), FAQ, terms summary. '+BUY+' Files: index.html (+ styles.css).','Kész termékoldal árazással és Megveszem gombbal – a fizetési linket te adod meg.'),
 ('validation','Forgalmi csomag','Traffic for the launched product page (ORBIT adds cookie-free tracking of visits and buy clicks). Deliver traffic-kit.json: {"channels":[{"source":"short_id_like_fb_ads","name":"channel name","type":"paid|post","budget_eur":0-50,"audience":"who exactly","copy":"ready ad or post text in the audience language"}]} with 3-5 channels (at most one or two paid, total budget <= 50 EUR), plus validation.md: what to measure in the first two weeks (visits, buy clicks, verified revenue) and when to continue or stop. Every channel is started by the owner; never claim it was posted.','Kész hirdetés- és posztszövegek követhető linkekkel a termékoldalhoz.'),
 ('pipeline','Automatizált futtatás','Unattended operation: scheduler/webhook entry point, retries, idempotency, logging and alerting, configuration from environment variables only. '+SELF_TEST+' Files: runner.py, ops.md.','Ütemező, webhook, újrapróbálás és naplózás – magától fut.'),
 ('selfimprove','Önellenőrzés és önjavítás','Automated QA (output validation, hallucination and broken-output checks, API failure handling) and the self-optimization loop: telemetry schema, metrics, how prompts/code are evaluated and improved automatically. '+SELF_TEST+' Files: qa.py, telemetry.md.','Hibakeresés, mérés és automatikus prompt-/kódjavítás.'),
 ('billing','Fizetés és előfizetés','Billing code ready for Stripe but not connected: Checkout session creation and webhook signature verification via the Stripe REST API with keys from environment variables only, plan limits and usage metering tied to the API keys, issuing an API key after payment. '+SELF_TEST+' (the self-test verifies a locally signed sample webhook and the metering without calling Stripe). Files: billing.py, plans.json.','Stripe-fizetés, csomagok, használatmérés és kulcskiadás – a kulcsot te adod meg.'),
 ('tests','Automata tesztek','A unittest suite for the whole product (engine, API, pipeline, QA, billing) using the example data, offline. File: test_product.py.','Automata tesztek az egész rendszerre – minden építés után lefutnak.'),
 ('launch','Üzembe helyezési csomag','Ready-to-run deployment package: Dockerfile (python slim, runs server.py and the scheduler), requirements.txt, .env.example listing every environment variable without values, and deploy.md with hosting choice and monthly cost, monitoring and rollback. Everything is prepared so the owner only creates the accounts, pastes the keys and starts it; each of those is an owner action with exact steps. Files: Dockerfile, requirements.txt, .env.example, deploy.md (up to 4).','Kész telepítőcsomag: Dockerfile, beállításminta, lépések – neked csak a fiókok és kulcsok maradnak.')],
service=[
 ('offer','Ajánlat és árazás','One-page offer: target customer, painful problem, concrete deliverable, 2-3 price tiers (marked unverified), guarantee, why now, required legal/health disclaimers. File: offer.md.','Kinek, mit, mennyiért: egyoldalas ajánlat árszintekkel.'),
 ('landing','Értékesítő weboldal','A complete, self-contained, mobile-friendly sales page in Hungarian with real copy (no lorem ipsum) about the service as it is offered now, pricing and FAQ. '+BUY+' Files: index.html (+ styles.css if needed). Not published.','Kész, mobilbarát értékesítő oldal valódi szöveggel és Megrendelem gombbal.'),
 ('intake','Ügyfélfelvételi űrlap','The customer intake form/questionnaire that collects exactly what delivery needs, with consent text. Files: intake.html and intake-questions.json.','Kérdőív, ami mindent begyűjt, ami a szolgáltatáshoz kell.'),
 ('engine','A szolgáltatás motorja','The working core of the product: a runnable prototype (Python standard library only, no network) or a precise step-by-step delivery template that turns intake answers into the customer deliverable. Include an example input. Files: engine.py or delivery-playbook.md, example-input.json.','A szolgáltatás működő magja: program vagy lépésről lépésre sablon.'),
 ('samples','Minta-eredmények','Three realistic sample deliverables for three different example customers, produced with the engine/playbook, clearly labelled as samples. File: samples.md.','Három kidolgozott minta-eredmény különböző ügyfeleknek.'),
 ('sales','Értékesítési csomag','First-customer acquisition kit: channel plan with exact places to post, 5 contact/post drafts, follow-up messages, objection handling. Drafts only, nothing is sent. File: sales-kit.md.','Hol és mit írj az első ügyfelekért: kész üzenetvázlatok.'),
 ('launch','Indítási csomag','Launch checklist: legal/GDPR and disclaimer texts, payment setup options, pricing test plan, success metrics for the first 2 weeks and every step that needs the owner. File: launch.md.','Jogi szövegek, fizetés, mérés és minden, amit neked kell elintézni.')],
dropshipping=[
 ('product','Termékkutatás','Evidence that the product sells now: trend/search/marketplace signals with actual URLs, target buyer, price points seen at competitors, seasonality, risks (fragile, regulated, IP). File: product-research.md.','Bizonyíték, hogy a termék most fogy: trendek, versenytárs-árak, kockázatok.'),
 ('suppliers','Beszállítók','Compare at least 3 real supplier listings found via web search (URL, unit price, shipping cost and time to Hungary/EU, MOQ, rating). Mark unknowns. File: suppliers.md.','Legalább 3 valódi beszállító összevetése árral, szállítással, értékeléssel.'),
 ('economics','Egységgazdaságtan','Write economics.json with numeric fields price, product_cost, shipping_cost, payment_fee_pct, ad_cost_per_sale, return_rate_pct, currency (best evidence-based estimates). ORBIT computes margin and break-even ad cost itself. Explain the assumptions in economics.md.','Ár, beszerzés, szállítás, hirdetés: marad-e haszon egy rendelésen? (ORBIT számolja)'),
 ('store','Bolt és termékoldal','Ready store content in Hungarian: product page HTML (title, benefits, specs, FAQ, shipping/returns), product description variants, legal pages (ÁSZF, elállás, adatkezelés) drafts. Files: product-page.html, policies.md. Not published.','Kész termékoldal, leírások és jogi oldalak – közzététel nélkül.'),
 ('ads','Hirdetési csomag','Ad test plan: 3 audiences, 5 ad copies, creative briefs (image/video shot lists), a small capped test budget proposal for the owner to approve, kill/scale rules. Files: ads.md and traffic-kit.json in the same format as the validation milestone (channels with source, name, type, budget_eur, audience, copy).','Hirdetésszövegek, kreatív tervek és egy kis, plafonos tesztkeret javaslat.'),
 ('launch','Indítási csomag','Step-by-step launch for the owner: store platform setup, payment, supplier order flow, ad account, budget approval, tracking and the first 14-day metrics. Every money step is an owner action. File: launch.md.','Bolt, fizetés, beszállítói rendelés, hirdetési fiók: lépésről lépésre neked.')],
# Products ORBIT makes itself and an intermediary sells: it draws the designs with its local image model
# (design_studio), the marketplace prints, takes the payment and delivers.
digital=[
 ('niche','Piac és témák','Evidence of what sells now on the target marketplaces (print-on-demand: Redbubble, Spreadshirt, Printful or Printify with Etsy; printables: Etsy digital downloads, Amazon KDP): best-selling themes in the niche with actual URLs, buyers, price points and royalties, file requirements (size, format, transparency) and the marketplace rules on trademarks and characters. File: niche.md.','Mi fogy most a piactereken: témák, árak, jutalékok, fájlkövetelmények – forrásokkal.'),
 ('designs','Grafikák','Write designs.json: {"designs":[{"id":"kebab-case-id","title":"product title","kind":"apparel|coloring|art","prompt":"English visual description for the image model: one subject, style, composition; no text, no brand, character or celebrity names"}]} with 12 designs that follow niche.md (apparel: t-shirt and hoodie graphics; coloring: children\'s colouring pages; art: wall art or stickers). ORBIT renders every design itself with its local image model: apparel as a transparent print-ready PNG up to 4096 px, coloring as black line art on an A4 page at 300 dpi, all colouring pages bound into one printable PDF. Explain the collection and its style in designs.md.','12 grafika leírása – az ORBIT maga rajzolja meg nyomdakész fájlokká.'),
 ('listings','Termékadatlapok','listings.json: {"listings":[{"id":"design id from designs.json","marketplace":"Redbubble|Spreadshirt|Etsy|Amazon KDP|…","title":"<=140 characters","description":"…","tags":["13 search tags"],"price":"unverified price with currency","products":["t-shirt","hoodie","sticker" or "PDF download","paperback"]}]} for every design and target marketplace, written in the buyers\' language. listings.md: shop name and description, upload order.','Kész termékcímek, leírások, címkék és árak minden grafikához.'),
 ('pricing','Árazás és haszon','pricing.md: royalty or margin per product and marketplace from the marketplaces\' published fee tables (actual URLs), price ladder, bundles (for example all colouring pages as one PDF), break-even for any paid promotion. Never claim sales.','Jutalék és haszon termékenként és piacteren – forrásokkal.'),
 ('promo','Forgalmi csomag','traffic-kit.json in the same format as the other products (3-5 channels such as Pinterest pins, marketplace search, niche communities; at most one paid, total budget <= 50 EUR) with ready post texts that point to the marketplace shop. The owner posts them.','Kész posztszövegek (Pinterest, közösségek) a bolt felé.'),
 ('launch','Feltöltési csomag','launch.md: exact upload steps per marketplace (account, tax and payout details, shop setup, uploading every design file from the designs folder with its listing from listings.json, product mockups) and what to check after the first week. Every account, tax and publishing step is an owner action.','Lépésről lépésre feltöltés a piacterekre – a fiók és a közzététel a tiéd.')],
trading=[
 ('thesis','Tézis és piac','Trading thesis: market/coin, why an edge may exist, what would disprove it, liquidity and risks, with actual URLs for any news or data. File: thesis.md.','Melyik piac, miért lehet előny, mi cáfolná – forrásokkal.'),
 ('strategy','Szabályok gépi formában','Write strategy.json exactly in this schema: {"coin":"SOL","interval":"1h|4h|1d","rules":{"type":"sma_cross","fast":10,"slow":30} or {"type":"rsi_reversion","period":14,"buy":30,"sell":70} or {"type":"breakout","lookback":20},"side":"long|long_short","stop_loss_pct":5,"take_profit_pct":15,"fee_pct":0.05,"position_pct":100,"days":365}. Use a coin traded on Hyperliquid perpetuals. ORBIT runs the backtest itself. Explain the rules in strategy.md.','A stratégia pontos szabályai – az ORBIT ebből maga futtat backtestet.'),
 ('backtest','Backtest értékelése','Read backtest.json that ORBIT computed (full period, in-sample, out-of-sample, buy-and-hold, drawdown, trades). Write an honest evaluation; if weak, improve strategy.json once (it is re-tested) or recommend dropping it. File: backtest-review.md (+ strategy.json if revised).','Az ORBIT méri a múltbeli adatokon; őszinte értékelés, szükség esetén javítás.'),
 ('paper','Virtuális pénzes teszt','ORBIT runs the strategy on new candles with 1000 virtual USD (paper.json). Review the forward results versus the backtest and decide continue, revise or drop. File: paper-review.md.','Valódi pénz nélküli élő teszt az új árfolyamokon.'),
 ('risk','Kockázati szabályok','Risk rules: maximum loss per trade/day/month, kill switch conditions, position limits, what to do on exchange outage. File: risk.md.','Veszteséglimitek és vészfék, mielőtt bármi élesedne.'),
 ('live','Élesítési csomag','Owner-only live plan: exchange account and API steps, which numbers must be confirmed by the owner, monitoring routine. Never recommend an amount to invest; state the measured results and risks only. File: live-plan.md.','Ha te úgy döntesz: lépések az élesítéshez – az ORBIT nem kereskedik valódi pénzzel.')])
ROADMAPS['toolkit']=[
 ('host_scope','Kompatibilitás','Identify the exact host, supported version, install folder, native formats, limits and smallest useful workflow. Verify against first-party documentation; save compatibility.md.','Ellenőrzött gazdaalkalmazás, formátum és cél.'),
 ('native_asset','Használható fájlok','Build the host-native presets, scripts or extension files. Provide actual assets and a minimal usage example; use the documented host API and file formats. Do not add a web API unless required.','Natív presetek vagy bővítményfájlok.'),
 ('host_qa','Ellenőrzés','Add a reproducible installation and smoke checklist with known inputs and expected output. Report separately what actually ran locally and what needs the host application. Save qa.md and any offline validators.','Tesztpéldák és kompatibilitási korlátok.'),
 ('install_kit','Telepítés és átadás','Write README.md with the exact installation, sample usage and uninstall steps for the target host. Package distributable assets, license and a product page only when relevant.','Telepítési útmutató és átadható csomag.')]
ROADMAP=ROADMAPS['service']
TITLES={k:t for r in ROADMAPS.values() for k,t,_,_ in r}
MAX_REVISIONS=3
MAX_CODE_REVISIONS=5
TYPES={'toolkit':'Bővítmény vagy sabloncsomag','saas':'Automatizált szoftver','service':'Szolgáltatás','dropshipping':'Dropshipping','trading':'Kereskedési stratégia','digital':'Digitális termék (POD, nyomtatható)'}

DIGITAL_WORDS=('print-on-demand','print on demand','redbubble','spreadshirt','printful','printify','teespring','merch by amazon','kdp','színező','coloring','colouring','póló','t-shirt','tshirt','hoodie','nyomtatható','printable','matrica','sticker','falikép','wall art','poszter','poster')

def classify(plan):
 label=' '.join(str((plan or {}).get(k) or '') for k in ('name','offer','category')).casefold()
 if ('davinci resolve' in label or 'fusion' in label) and any(w in label for w in ('preset','plugin','macro','sablon','bővítmény')):
  return 'toolkit'
 if (plan or {}).get('business_type') in ROADMAPS:return plan['business_type']
 text=' '.join(str(v) for v in (plan or {}).values()).casefold()
 # Before the automation level: a colouring-book or t-shirt idea rated 95% automated is still a digital product.
 if any(w in text for w in DIGITAL_WORDS):return 'digital'
 if (plan or {}).get('automation_level') is not None:return 'saas'
 if any(w in text for w in ('dropship','webshop','e-commerce','ecommerce','termékeladás','aliexpress','shopify','termék eladás')):return 'dropshipping'
 if any(w in text for w in ('altcoin','crypto','kripto','trading','tőzsde','részvény','backtest','kereskedési stratégia','stock')):return 'trading'
 return 'service'

def roadmap(f):return ROADMAPS.get(f.get('type'),ROADMAPS['saas'])

PLAN='''You are the delivery planner of ORBIT Business Lab. The operator wants the chosen business idea IMPLEMENTED, not researched further. The roadmap fits the idea type (service, dropshipping or trading strategy). The saved operator_direction takes priority within this product. For host-specific plugins or presets, produce the host's native files, installation steps and verifiable tests; skip irrelevant HTTP and billing scaffolding. You may mark a milestone that truly does not apply to this idea as skip with a one-line reason. Read the focus, roadmap and tester feedback below and the current product files (use read_file on the listed paths). The milestone is fixed by ORBIT: work only on next_milestone and return it as milestone_id; do not pick another one (ORBIT chose it: broken code first); fix exactly what the tester reported and every file listed in its code_errors, with the error shown, otherwise the first pending one. Never stop or wait for the owner: everything except creating accounts, paying, publishing and pasting keys is built by ORBIT. Use web_search/read_web only for concrete facts this milestone needs (competitor prices, legal requirements, where customers gather); cite actual returned URLs. Call tools through the tool interface, never by printing JSON. Return a short Hungarian brief: milestone_id, exact deliverable specification, acceptance criteria (checkable), facts with URLs, and what must stay a draft for the owner.'''
BUILD='''You are the builder of ORBIT Business Lab. Implement exactly ONE roadmap milestone from the planner brief for the chosen business. Produce finished, usable work in Hungarian: real copy, real HTML/CSS/JS, real questions, runnable standard-library Python. No placeholders or lorem ipsum. Customer-facing pages describe the finished product as available now, in the indicative: no waitlist, no sign-up for later, no 'coming soon' or 'would/could' promises; buy and order buttons are <a data-orbit-checkout href="#"> links that ORBIT points at the owner's checkout link. Revise existing product files instead of starting over: read_file only files listed under product_folder or the current milestone in the roadmap, at most two reads, requested together in ONE turn (two read_file calls at once), then write. Do not read focus.json, cycle-modes.json, other ventures or other products; everything else you need is already in this task. Reading too much fills the context and your answer is lost. Return JSON only, keys in exactly this order (the answer may be cut at its length limit, so the essentials come first): {"milestone_id":"one roadmap id","edits":[{"name":"existing product file","find":"exact text copied verbatim from the current file, unique in it","replace":"new text"}],"files":[{"name":"file name","content":"complete file content"}],"summary":"Hungarian, at most 600 characters: what was built and how to use it","acceptance":["criteria you checked"],"status":"done|partial|skipped (only if the milestone truly does not apply; then explain in summary and files may be empty)","owner_actions":[{"title":"step only the owner may do (account, payment, publishing, contacting people, legal sign-off); never running tests, servers or code, ORBIT does that itself","kind":"money|publish|account|contact|legal","why":"reason","draft":"ready text or exact steps"}],"next":"what should follow"}. 1-4 files, each <=4500 characters, total <=8000 (keep HTML lean: inline minimal CSS, no long comments); allowed .setting .lua .md .txt .json .py .html .css .js .csv .svg .toml .yml .sh .sql, .env.example, Dockerfile, requirements.txt; plain file names. '''+SELF_TEST+''' ORBIT runs every product .py file sandboxed after the build; a failing run sends the milestone back with its error output. milestone_id must be next_milestone from the task context (ORBIT fixed it), even if the brief names another. When the selected milestone lists fix_first, change exactly those files (edits); do not work on other files until they pass. If the task already contains the current content of the broken files, use it and do not read them again. When the roadmap lists code_errors, fix those files first so they pass their self-test. recurring_code_errors lists mistakes that already came back in several builds: follow their advice. Bytes literals must be ASCII: never write accented text inside b'...'; use '...'.encode('utf-8'). Files marked ORBIT-PROTECTED are the owner's acceptance tests on real data: never edit them; make the product pass them. The sandbox has no internet and sets ORBIT_OFFLINE=1: self-tests and smoke.json must work from recorded or example data, never the network. API products: the product folder has orbit_server_base.py from ORBIT (read-only, restored after every build); build server.py on it: subclass JSONHandler with get_<path>()/post_<path>(data) methods returning (status, dict) and end with main(Handler, checks); it already handles JSON, accents, API keys, --self-test and --port. Files fully replace the product file of that name. To change an EXISTING file prefer edits: short find/replace blocks copied verbatim from the file you read (each find must occur exactly once; include enough surrounding lines); they are much faster than rewriting the file. Use files for new files or full rewrites, never both for one file. Never claim anything was published, sent, sold, bought, traded or paid. Never fabricate customers, revenue, testimonials or backtest numbers (ORBIT computes backtests and unit economics itself). Never recommend an amount of money to invest.'''
TEST='''You are the independent tester of ORBIT Business Lab. Review the files this build changed: their current content is in the task when it fits; read_file only those that are missing. Check them against the acceptance criteria and the roadmap goal: completeness, correctness, usability by a real customer, Hungarian quality, broken HTML/code, invented claims, missing legal/consent text; for trading, overfitting, too few trades, ignoring fees or drawdown, and any implied promise of profit; for dropshipping, unrealistic costs, missing shipping times or legal pages. ORBIT has actually run the product code; its result is the "ORBIT futtatás" line of the build summary. A failed file written in THIS milestone means revise; failures in other product files belong to other milestones and do not count here. First line exactly "VERDICT: accept" or "VERDICT: revise". Then at most 120 words in Hungarian: what works, the concrete defects, and the exact fixes needed (only the first part reaches the builder).'''
PROMPTS=dict(research=PLAN,build=BUILD,review=TEST)
MAINTAIN_PLAN='''You are the product owner of a FINISHED ORBIT product (all roadmap milestones are built). Keep it improving while other products are built in parallel. Read the roadmap with the tester notes and the current product files (read_file). Choose ONE improvement with the highest value: fix the most serious defect the tester reported, harden automation (error handling, telemetry, self-optimization), sharpen the offer or landing page, or improve the validation test. Name the milestone_id it belongs to. Prioritize the saved operator_direction when choosing the improvement. Use web_search/read_web only for facts the improvement needs and cite actual URLs. Call tools through the tool interface. Return a short Hungarian brief: milestone_id, the exact change, acceptance criteria.'''
MAINTAIN_PROMPTS=dict(research=MAINTAIN_PLAN,build=BUILD,review=TEST)

def _path(s,name):return s.safe_path(PID,'workspace/ventures/'+name)
def read(s):
 try:return json.loads(_path(s,'focus.json').read_text())
 except (OSError,ValueError):return None
def write(s,value):
 p=_path(s,'focus.json');p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,ensure_ascii=False,indent=1))

MIN_SCORE=15
# The critic may not rate demand above 2 without evidence, and before launch there is none, so
# demand is judged by the launch test (measured_demand) instead of blocking the build. When no
# idea reaches MIN_SCORE, the best of at least COMPARE rated automated ideas is built above FLOOR.
FLOOR=10
COMPARE=3

def buildable(sc):
 # solved>=4: the critic found a free, official or already-used solution; building it again is wasted work.
 return bool(sc and sc['total']>=FLOOR and sc['automation']>=3 and sc.get('measured')!='failed' and sc.get('solved',1)<4)

def qualified(s,idea_id):
 from venture import idea_scores
 mid=mission_id(s);return buildable((idea_scores(s,mid) if mid else {}).get(idea_id))

def best_idea(s,exclude=(),since=0):
 """The highest-rated fully automated idea (critic score), not the most repeated one; with since, only ideas
 first found after that time."""
 from venture import known_ideas,idea_scores
 mid=mission_id(s);scores=idea_scores(s,mid) if mid else {}
 # Only fully automated designs are implemented automatically (no human in delivery).
 ideas=[i for i in known_ideas(s,PID) if len(str(i['name']).strip())>3 and str(i['name']).strip().casefold()!='new' and i.get('automated') and (i.get('first') or 0)>=since]
 rated=[i for i in ideas if scores.get(i['idea_id'])]
 good=[i for i in rated if i['idea_id'] not in exclude and buildable(scores[i['idea_id']])]
 if not good or (len(rated)<COMPARE and max(scores[i['idea_id']]['total'] for i in good)<MIN_SCORE):return None
 return max(good,key=lambda i:(scores[i['idea_id']]['total'],scores[i['idea_id']]['automation'],-ideas.index(i)))

def mission_id(s):
 row=s.db.execute("SELECT id FROM orbit_missions WHERE origin='orbit:business-lab'").fetchone()
 return row[0] if row else None

def start_focus(s,idea,auto,old=None):
 old=old or {}
 f=dict(mode='build',idea_id=idea['idea_id'],name=idea['name'],started=time.time(),auto=auto,finished=old.get('finished',[]),queue=[q for q in old.get('queue',[]) if q!=idea['idea_id']])
 f['directions']=dict(old.get('directions') or {})
 if auto and old.get('next_direction'):
  f['directions'][f['idea_id']]=old['next_direction']
 f['type']=classify(plan_text(s,f));write(s,f);return f

def active(s):
 """Implementation is the default once an idea exists. A finished roadmap moves on by itself to
 the next queued or most developed idea; the operator can switch or go back to exploring."""
 f=read(s)
 if f is None:
  idea=best_idea(s)
  if not idea:return None
  return start_focus(s,idea,True)
 if f.get('mode')!='build':
  # Scouting started by the system (not by the operator) resumes building once a fully
  # automated design exists.
  if f.get('auto_explore'):
   # After a new search the owner asked for, only ideas found since then: at 21:52 on 1 Nov the search for
   # t-shirt graphics and colouring pages started building an old, already scored idea (SpecForge) at once.
   idea=best_idea(s,f.get('finished',[])+f.get('skip',[]),f.get('scout_since') or 0)
   if idea:return start_focus(s,idea,True,f)
  return None
 if f.get('auto',True) and not (compliant(s,f) and (qualified(s,f['idea_id']) or progress_count(s,f)>=3)):
  idea=best_idea(s,f.get('finished',[])+[f['idea_id']])
  if idea:return start_focus(s,idea,True,f)
  write(s,dict(f,mode='explore',auto_explore=True,reason='A megvalósított ötlethez emberi munka kellene; új, teljesen automatizált ötletet keres.'));return None
 if 'type' not in f:f['type']=classify(plan_text(s,f));write(s,f)
 mid=mission_id(s)
 if mid:
  ms,_=progress(s,mid,f)
  if ms and all(m['state'] in ('done','skipped') for m in ms):
   finished=list(dict.fromkeys(f.get('finished',[])+[f['idea_id']]))
   from venture import known_ideas
   known={i['idea_id']:i for i in known_ideas(s,PID)}
   if not f.get('auto') and (f.get('directions') or {}).get(f['idea_id']):
    if finished!=f.get('finished'):write(s,dict(f,finished=finished))
    return f
   ok=best_idea(s,finished)
   # Queued ideas still need a passing critic score; otherwise the best scored idea wins.
   nxt=next((known[q] for q in f.get('queue',[]) if q in known and q not in finished and qualified(s,q)),None) or ok
   if nxt:return start_focus(s,nxt,True,dict(f,finished=finished))
   write(s,dict(f,finished=finished))
 return f

# Products ORBIT can make itself and an intermediary sells (print-on-demand, printables) come every other scouting
# cycle: the owner asked for ideas like t-shirt graphics and colouring pages (1 Nov).
SECTORS=[('Ruhagrafika (print-on-demand)', 'print-on-demand apparel graphics (t-shirts, hoodies) for a narrow, passionate niche, sold through marketplaces such as Redbubble, Spreadshirt or Printful/Printify with Etsy that print, take the payment and ship; ORBIT draws the designs with its local image model'), ('AI mikro-SaaS', 'an AI micro-SaaS for a narrow professional niche'), ('Gyerek színezők és nyomtathatók', "children's colouring pages and printable activity sheets on a narrow theme, sold as PDF downloads (Etsy) or as a low-content colouring book (Amazon KDP prints and ships); ORBIT draws the pages with its local image model"), ('Automatizált tartalom-pipeline', 'an automated content pipeline (articles, newsletters, social posts) monetized by subscription or ads'), ('Matricák, falikép, poszter', 'stickers, wall art and posters for a niche, sold through print-on-demand marketplaces that print and ship; ORBIT draws them with its local image model'), ('Adat-pipeline és adattermék', 'an automated data collection and cleaning pipeline sold as a dataset, feed or API'), ('Digitális sablonok és letölthetők', 'digital templates and printables (planners, worksheets, party printables, educational sheets) sold as downloads on Etsy or Gumroad, generated by ORBIT'), ('Programmatikus SEO', 'a programmatic SEO site network monetized by ads or affiliate'), ('API-first mikroszolgáltatás', 'an API-first micro-service with pay-per-use pricing'), ('Fejlesztői eszköz', 'a developer tool (CLI, GitHub app, editor extension) with a subscription'), ('Automatizált videó és média', 'an automated media or video generation product'), ('Algoritmikus arbitrázs', 'algorithmic arbitrage or a rule-based trading strategy (tested only with the ORBIT backtest and virtual money)'), ('Böngésző-bővítmény', 'a browser extension with freemium monetization'), ('Automatizált monitorozás és riport', 'an automated monitoring, alerting or reporting service (prices, SEO, compliance, uptime)'), ('Beágyazható AI-ügynök', 'a fully self-serve embeddable AI agent or chatbot for websites'), ('Dokumentum-feldolgozás', 'automated document processing (invoices, contracts, CVs) through an API')]
SCOUT_EVERY=3

def progress_count(s,f):
 """Built milestones of a focus; a well advanced build is not dropped for a missing score."""
 mid=mission_id(s)
 return sum(m['state'] in ('done','skipped') for m in progress(s,mid,f)[0]) if mid else 0

def compliant(s,f):
 from venture import known_ideas
 idea=next((i for i in known_ideas(s,PID) if i['idea_id']==f['idea_id']),None)
 return bool(idea and idea.get('automated'))

def portfolio(s):
 """Finished, fully built products: each keeps improving in its own cycles."""
 return [i for i in (read(s) or {}).get('finished',[]) if i]

def focus_for(s,idea_id):
 """A focus-like record for any built idea, so a cycle can work on it."""
 from venture import known_ideas
 idea=next((i for i in known_ideas(s,PID) if i['idea_id']==idea_id),None)
 if not idea:return None
 f=dict(mode='build',idea_id=idea_id,name=idea['name'],started=0,auto=True)
 f['type']=classify(plan_text(s,f));return f

def plan_cycle(s,cycle):
 """Interleave the work so several products advance in parallel: every third cycle scouts,
 one in three improves a finished product (round robin), the rest build the current idea."""
 f=active(s)
 saved=read(s) or {}
 if not f and saved.get('next_direction'):return 'explore'
 done=portfolio(s)
 if f and (f.get('directions') or {}).get(f['idea_id']) and not f.get('auto'):
  return ('maintain:' if f['idea_id'] in done else 'build:')+f['idea_id']
 # Scouting while ideas already wait in the queue only delays the product being built.
 if explore_cycle(cycle) and len((read(s) or {}).get('queue') or [])<2:return 'explore'
 if done and cycle%SCOUT_EVERY==2:return 'maintain:'+done[(cycle//SCOUT_EVERY)%len(done)]
 if f:return 'build:'+f['idea_id']
 return 'maintain:'+done[cycle%len(done)] if done else 'explore'

def explore_cycle(cycle):
 """Every third cycle scouts a different sector while the current idea is being built."""
 return bool(cycle) and cycle%SCOUT_EVERY==0

def sector(cycle,direction=''):
 """Rotate sectors so scouting covers many kinds of opportunity, not one favourite. An operator direction that
 asks for print-on-demand graphics or colouring pages keeps scouting in those sectors (the owner, 1 Nov)."""
 creative=[x for x in SECTORS if any(w in x[1].casefold() for w in DIGITAL_WORDS)]
 pool=creative if creative and any(w in str(direction).casefold() for w in DIGITAL_WORDS) else SECTORS
 return pool[(cycle//SCOUT_EVERY)%len(pool)]

def note_idea(s,plan):
 """An explorer plan marked ready for validation joins the queue of ideas to implement next."""
 f=read(s)
 if f and plan.get('decision')=='ready_for_validation' and plan.get('idea_id') not in [f.get('idea_id')]+f.get('queue',[])+f.get('finished',[]):
  write(s,dict(f,queue=f.get('queue',[])+[plan['idea_id']]))

def choose(s,idea_id):
 from venture import known_ideas
 if idea_id=='scout':
  # Fresh search requested: stop the current build, scout new ideas, then build the best
  # qualified one automatically.
  f=read(s) or {};write(s,dict(f,mode='explore',auto_explore=True,auto=True,next_direction='',scout_since=time.time(),skip=list(dict.fromkeys(f.get('skip',[])+([f['idea_id']] if f.get('idea_id') else []))),reason='Új keresés: csak az ezután talált, teljesen ember nélkül működő ötletek közül építi a legjobbat.'));return
 if idea_id in (None,'explore'):
  f=read(s) or {};write(s,dict(f,mode='explore',auto_explore=False));return
 idea=next((i for i in known_ideas(s,PID) if i['idea_id']==idea_id),None)
 if not idea:raise ValueError('Ismeretlen ötlet.')
 old=read(s) or {}
 if old.get('idea_id')==idea_id:write(s,dict(old,mode='build',auto=False));return
 start_focus(s,idea,False,old)

def folder(f):return 'workspace/product-'+re.sub(r'[^a-z0-9]','',str(f['idea_id']).lower())[:16]

# Milestones the owner finished outside the Autopilot, kept in the product folder (builders cannot write
# it). TermékA's tested engine came from the owner; the Autopilot, seeing "engine" open, wrote a
# second, failing engine.py beside it and replaced the README.
OWNER_FILE='orbit-milestones.json'

def owner_done(s,f):
 try:return json.loads(s.safe_path(PID,folder(f)+'/'+OWNER_FILE).read_text())
 except (OSError,ValueError):return {}

def mark_done(s,f,mid,done=True,files=(),note=''):
 """Mark (or unmark) a roadmap step as finished by the owner, with the files that deliver it."""
 if mid not in {k for k,_,_,_ in roadmap(f)}:raise ValueError('Ismeretlen lépés.')
 path=s.safe_path(PID,folder(f)+'/'+OWNER_FILE);path.parent.mkdir(parents=True,exist_ok=True)
 marks=owner_done(s,f)
 if done:marks[mid]=dict(files=[PurePosixPath(str(x)).name for x in files][:12],note=str(note or '')[:600],at=time.time())
 else:marks.pop(mid,None)
 path.write_text(json.dumps(marks,ensure_ascii=False,indent=1));return marks

def plan_text(s,f):
 """The saved business plan of the focus idea, so the team builds what was researched."""
 for p in sorted(_path(s,'').glob('*/result.json'),key=lambda p:p.stat().st_mtime,reverse=True):
  try:v=json.loads(p.read_text())
  except (OSError,ValueError):continue
  if v.get('mode')!='build' and (v.get('idea_id')==f['idea_id'] or v.get('name')==f['name']):
   return {k:v.get(k) for k in ('business_type','category','automation_level','name','problem','buyer','offer','revenue_model','architecture','autonomy','tech_stack','costs','revenue_potential','hypothesis','validation','next_action')}
 return {'name':f['name']}

# The builder sometimes lists work ORBIT does itself (run the tests, start the server, add a
# feature) as an owner step; those flooded the "Rád vár" list and are dropped.
NOT_OWNER=re.compile(r'futtas|futtat|self-?test|smoke|szerver|server|pipeline|roadmap|sandbox|homokoz|\.py\b|beilleszt|implementál|teszteld|próbáld ki',re.I)
MAX_OWNER_ACTIONS=10

OWNER_ORDER=('money','legal','account','publish','contact','other')
OWNER_FILLER={'és','a','az','the','and','beállítása','létrehozása','elkészítése','megadása'}

def owner_words(title):return {w for w in re.findall(r'[^\W_]+',str(title).casefold()) if len(w)>1 and w not in OWNER_FILLER}

def similar_words(x,y):
 common=len(x&y)
 return common*3>=len(x|y) or common>=2 and common>=.6*min(len(x),len(y))

def rank_owner_actions(actions):
 """The owner's to-dos, most important kind first (money, legal, account, publishing, contact),
 with near-duplicates of the same kind merged into the newest wording: the builder kept adding
 variants such as three different 'webhook endpoint' steps."""
 groups=[]
 for a in sorted(actions,key=lambda x:-(x.get('cycle') or 0)):
  words=owner_words(a['title'])
  for g in groups:
   # Early builds (product df9ec276) saved owner steps without a kind.
   if g.get('kind')==a.get('kind') and any(similar_words(words,w) for w in g['words']):
    g['words'].append(words);g['count']+=1;g['variants'].append(a['title']);break
  else:groups.append(dict(a,words=[words],count=1,variants=[]))
 order={k:i for i,k in enumerate(OWNER_ORDER)}
 groups.sort(key=lambda g:(order.get(g.get('kind'),len(order)),-(g.get('cycle') or 0)))
 return [{k:v for k,v in g.items() if k!='words'} for g in groups[:MAX_OWNER_ACTIONS]]

LEGAL=re.compile(r'§|törvény|rendelet|jogszabály|\bEkertv|\bGDPR\b|irányelv',re.I)
DISPUTE=re.compile(r'nem egyezik|nem stimmel|helytelen|téves|rossz hivatkoz|hibás hivatkoz|nem megfelel|helyes hivatkozás|megfelelő hivatkozás|helyett a|właściw',re.I)

def legal_caution(review):
 """A tester that disputes a legal citation without a source gets no say over it: in cycle 191 the model
 called the correct Ekertv. 4. § wrong (in a sentence with a Polish word in it)."""
 if LEGAL.search(review) and DISPUTE.search(review) and not re.search(r'https?://',review):
  return '\n[ORBIT: a tesztelő forrás nélkül vitat egy jogszabályi hivatkozást. Jogszabályi hivatkozást csak forrással (a jogszabályhely címe vagy URL-je) együtt szabad módosítani; addig a meglévő hivatkozás marad.]'
 return ''

def owner_step(a):
 return isinstance(a,dict) and isinstance(a.get('title'),str) and a['title'].strip() and not NOT_OWNER.search(a['title'])

def progress(s,mid,f):
 """Milestone states from this focus's saved cycles: build sets done/partial/skipped, tester can reopen.
 A failing file counts against the milestone that last wrote it, judged by the newest code run:
 one old broken file used to send every later milestone back for revision."""
 states={k:dict(id=k,title=t,goal=g,desc=d,state='pending',cycles=[],summary='',files=[],review='',code_errors={}) for k,t,g,d in roadmap(f)}
 actions={};writer={};latest=None;seen_errors={};history=[]
 # A milestone belongs to this focus by its idea_id, even if its cycle began before the switch.
 for run in s.rows("""SELECT r.id,r.cycle FROM orbit_mission_runs r
   JOIN orbit_mission_steps b ON b.run=r.id AND b.node='build' AND b.state='done'
   WHERE r.mission=? AND CASE WHEN json_valid(b.result) THEN json_extract(b.result,'$.content.idea_id') END=? ORDER BY r.cycle""",(mid,f['idea_id'])):
  steps={st['node']:st for st in s.rows('SELECT node,state,result FROM orbit_mission_steps WHERE run=?',(run['id'],))}
  b=steps.get('build')
  if not b or b['state']!='done':continue
  c=json.loads(b['result'] or '{}').get('content')
  if not isinstance(c,dict) or c.get('mode')!='build' or c.get('idea_id')!=f['idea_id'] or c.get('milestone_id') not in states:continue
  # The planner's milestone wins over the builder's label: in cycles 149-151 the builder filed
  # API fixes as 'billing' and 'engine', which marked an unbuilt step done.
  r0=steps.get('research');planned=None
  # Since save-time enforcement (15:40), ORBIT's own choice is stored and wins; the 9B planner later
  # named 'billing' for an engine fix (cycle 158). Its word only repairs builds from before that.
  by=c.get('milestone_by') or ('orbit' if (c.get('created') or 0)>=ENFORCED_SINCE else 'builder')
  if r0 and r0['state']=='done' and by!='orbit':
   brief=json.loads(r0['result'] or '{}').get('content')
   hit=re.search(r'milestone(?:_id)?\W{0,8}([a-z_]+)',brief[:300],re.I) if isinstance(brief,str) else None
   planned=hit.group(1).lower() if hit and hit.group(1).lower() in states else None
  m=states[planned or c['milestone_id']];m['cycles'].append(run['cycle']);m['summary']=c.get('summary','');m['files']=c.get('files',[]) or m['files'];m['state']=c.get('status','done')
  for x in c.get('files') or []:writer[PurePosixPath(x).name]=m['id']
  if (c.get('checks') or {}).get('ok') is not None:
   # Older results kept the error lines only in the summary text.
   latest=dict(c['checks']);latest.setdefault('errors',dict(re.findall(r'([\w.-]+\.py) → ([^;]+?)(?:;|\s+Élő próba|$)',c.get('summary',''))))
   for fn in latest.get('failed') or []:seen_errors[(fn,general_error((latest.get('errors') or {}).get(fn,'')))]=seen_errors.get((fn,general_error((latest.get('errors') or {}).get(fn,''))),0)+1
   history.append((run['cycle'],dict(latest.get('errors') or {}),c.get('summary','')))
  if m['state']=='partial':m['state']='revise'
  for a in c.get('owner_actions',[]):
   if owner_step(a):actions.setdefault(a['title'].casefold(),dict(a,milestone=c['milestone_id'],cycle=run['cycle']))
  r=steps.get('review')
  m['review_revise']=False
  if r and r['state']=='done' and m['state']!='skipped':
   text=json.loads(r['result'] or '{}').get('content')
   if isinstance(text,str):
    m['review']=text[:2500]+legal_caution(text)
    if re.search(r'VERDICT:\s*revise',text,re.I):m['state']='revise';m['review_revise']=True
 for k,info in owner_done(s,f).items():
  if k in states:
   states[k].update(state='done',by_owner=True,summary=('A tulajdonos elkészítette. '+str(info.get('note') or '')).strip(),files=info.get('files') or states[k]['files'])
   for x in info.get('files') or []:writer.setdefault(x,k)
 errors=(latest or {}).get('errors') or {}
 product=s.safe_path(PID,folder(f))
 for name in (latest or {}).get('failed') or []:
  # A failing file that is no longer in the product (set aside by the owner) has nothing left to fix.
  if name!='smoke.json' and not (product/name).exists():continue
  if writer.get(name) in states:states[writer[name]]['code_errors'][name]=str(errors.get(name) or 'a futtatás hibával állt le')[:300]
 for m in states.values():
  m['code_failed']=bool(m['code_errors'])
  if m['code_failed'] and m['state']!='skipped':m['state']='revise'
  # A strict tester must not hold the whole roadmap on one step; code that does not run gets
  # more attempts than a matter of taste.
  if m['state']=='revise' and len(m['cycles'])>=(MAX_CODE_REVISIONS if m['code_failed'] else MAX_REVISIONS):m['state']='done';m['note']=('Öt javítási kör után sem futott hibátlanul ('+', '.join(m['code_errors'])+'); a karbantartó körök tovább javítják.' if m['code_failed'] else 'Három javítási kör után továbbléptünk; a tesztelő megjegyzései megmaradtak.')
  m.pop('review_revise',None)
  # A closed step whose every error came back unchanged in STUCK_BUILDS builds is stuck: it no longer
  # blocks new steps (no endless fix loop), and the owner gets a to-do with the errors.
  counts=[seen_errors.get((fn,general_error(err)),0) for fn,err in m['code_errors'].items()]
  m['stuck']=m['state']=='done' and bool(counts) and min(counts)>=STUCK_BUILDS
  if m['stuck']:
   actions.setdefault('stuck:'+m['id'],dict(title='Makacs hiba: '+', '.join('élő próba' if n=='smoke.json' else n for n in sorted(m['code_errors'])),kind='other',cycle=(m['cycles'] or [0])[-1],milestone=m['id'],
    why='Az Autopilóta legalább '+str(STUCK_BUILDS)+' építés óta ugyanezekkel a hibákkal nem boldogul a(z) „'+m['title']+'” lépésben, ezért továbblépett az új lépésekre.',
    draft='\n'.join(n+': '+str(e) for n,e in sorted(m['code_errors'].items()))+'\n\nMit tehetsz: nézd meg a fájlokat (📁 gomb az Autopilóta oldalon), és írd meg a fő chatben, hogyan javítsa, vagy hogy hagyja ki ezt a részt.'))
 for name,said,err,cycle in contradictions(history):
  actions.setdefault('contradiction:'+name,dict(title='Ellentmondás: az építő javítottnak mondja, a mérés szerint hibás ('+('élő próba' if name=='smoke.json' else name)+')',kind='other',cycle=cycle,
   why='Két egymást követő építésben ugyanez a mért hiba maradt, miközben az építő azt írta, hogy kijavította. Vagy az ORBIT ellenőrzése téved, vagy az építő félreérti a hibát.',
   draft='A mérés szerint: '+str(err)[:400]+'\n\nAz építő szerint: „'+said+'”\n\nMit tehetsz: nézd meg a fájlt (📁 gomb az Autopilóta oldalon); ha az ellenőrzés téved, írd meg a fő chatben.'))
 return list(states.values()),rank_owner_actions(list(actions.values()))

# One sentence: a dot inside a file name (engine.py) does not end it.
FIX_CLAIM=re.compile(r'(?:[^.\n]|\.(?=\S))*(?:kijavítottam|javítottam|eltávolítottam|töröltem|megoldottam|rendbe tettem|kivettem|\bfixed\b|\bremoved\b)(?:[^.\n]|\.(?=\S))*',re.I)
COMMON=re.compile(r'^(?:ígéret|ellenőrzés|oldal|ígéri|kódban|nincs|nyoma|expected|SELF|TEST|hiba|FAIL)$',re.I)

def contradictions(history):
 """Files whose measured error stayed the same in the last two builds while the newest build says it fixed
 it. TermékA's builder 'removed the Stripe promise' twice while ORBIT's check (wrongly) kept failing the
 page: three cycles went by before anyone looked."""
 if len(history)<2:return []
 (_,before,_),(cycle,now,summary)=history[-2],history[-1]
 out=[]
 for name,err in now.items():
  if name not in before or general_error(before[name])!=general_error(err):continue
  words={w.casefold() for w in re.findall(r'[A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű]{5,}',str(err)) if not COMMON.match(w)}
  said=next((x.strip() for x in FIX_CLAIM.findall(summary or '') if name in x or any(w in x.casefold() for w in words)),None)
  if said:out.append((name,said[:300],err,cycle))
 return out

def recent_builds(s,mid,since):
 """Milestones built since a time, for the morning report: what exists now and whether it ran."""
 out=[]
 for row in s.rows("SELECT st.result FROM orbit_mission_steps st JOIN orbit_mission_runs r ON r.id=st.run WHERE r.mission=? AND st.node='build' AND st.state='done' AND st.updated>=? ORDER BY st.updated",(mid,since)):
  c=json.loads(row['result'] or '{}').get('content')
  if not isinstance(c,dict) or c.get('mode')!='build':continue
  checks=c.get('checks') or {};own={PurePosixPath(x).name for x in c.get('files') or []}
  # Whether THIS build's own files ran: other, older broken files are not its failure.
  ok=None if checks.get('ok') is None else not (own & set(checks.get('failed') or []))
  f=focus_for(s,c.get('idea_id')) or {};titles={k:t for k,t,_,_ in roadmap(f)}
  out.append(dict(title=titles.get(c.get('milestone_id'),c.get('milestone_id')),files=len(c.get('files') or []),ran=ok,partial=c.get('status')=='partial'))
 return out

def measurements(s,f):
 """ORBIT's own computed numbers for this idea (backtest, virtual test, unit economics)."""
 out={}
 for name in ('backtest.json','paper.json','economics-result.json'):
  try:out[name.split('.')[0]]=json.loads(s.safe_path(PID,folder(f)+'/'+name).read_text())
  except (OSError,ValueError):pass
 return out

def paper_started(s,f):
 """When this product's virtual-money test began (kept in its own folder, not the focus)."""
 try:return json.loads(s.safe_path(PID,folder(f)+'/paper-start.json').read_text())['started']
 except (OSError,ValueError,KeyError):return f.get('paper_started')

def refresh_paper(s,f):
 """Advance the virtual-money test with the newest public candles (trading ideas only)."""
 started=paper_started(s,f)
 if f.get('type')!='trading' or not started:return
 from strategy_lab import forward
 try:
  spec=json.loads(s.safe_path(PID,folder(f)+'/strategy.json').read_text())
  s.safe_path(PID,folder(f)+'/paper.json').write_text(json.dumps(forward(spec,started),ensure_ascii=False,indent=1))
 except (OSError,ValueError) as exc:
  s.safe_path(PID,folder(f)+'/paper.json').write_text(json.dumps(dict(status='error',error=str(exc)[:300],started=started),ensure_ascii=False))

def compact_roadmap(f,milestones,detailed=2,focus=None):
 """Full detail (goal, tester notes, code errors) only for the milestone to work on now; the rest
 as one line each. The whole roadmap with goals and tester notes outgrew the job prompt limit, and
 with two detailed milestones the 27B builder kept working on the other one."""
 out=[];left=1 if focus else detailed
 for m in milestones:
  row=dict(id=m['id'],title=m['title'],state=m['state'],files=[folder(f)+'/'+PurePosixPath(x).name for x in m['files']])
  chosen=m['id']==focus if focus else m['state'] not in ('done','skipped')
  if chosen and left:
   # The tester now writes at most ~120 words, so the builder gets the whole note.
   row.update(goal=m['goal'],tester=m['review'][:1500]);left-=1
   if m['code_errors']:
    # The broken files themselves, not the files last written under this milestone: the builder
    # kept re-editing selfimprove.py (filed under the milestone) while ocr.py and pipeline.py stayed broken.
    row['code_errors']=m['code_errors'];row['fix_first']=[folder(f)+'/'+n for n in fix_targets_of(m['code_errors'])]
    row['files']=row['fix_first']+[x for x in row['files'] if x not in row['fix_first']]
  elif m['code_errors']:row['broken_files']=sorted(m['code_errors'])
  out.append(row)
 return out

def short_plan(plan,limit=350):
 return {k:(v[:limit]+'…' if isinstance(v,str) and len(v)>limit else v) for k,v in plan.items()}

CODE_PITFALLS=(
 ('bytes can only contain ASCII',"Bytes literals must be ASCII: write ('…').encode('utf-8') for accented text."),
 ('cannot import name',"An import names something the other file no longer defines: read that file and keep shared class and function names consistent across files."),
 ('No module named',"Use only the standard library and the product's own files."),
 ('offline',"The sandbox has no internet (ORBIT_OFFLINE=1): the request needs data that is not recorded. Call the product with inputs the recorded data covers (the error lists them) and answer unknown inputs with a clear result, not a server error."),
 ('urlopen error',"The sandbox has no internet and sets ORBIT_OFFLINE=1: code that fetches web pages must use recorded data there (for example a realdata/ replay), and smoke.json must call it with inputs that recorded data covers."),
 ('Időtúllépés',"A --self-test must finish quickly: bind port 0, call yourself once, shut down; never serve forever in self-test mode."),
 ('Élő próba',"The live API test failed: started with --port, server.py must answer every request in smoke.json with the expected status and keys."),
 ('Ígéret-ellenőrzés',"The sales page promises something the product code does not do: rewrite or remove that promise in the .html page, or build it in the code; never promise unbuilt features."),
 ('expected ',"A self-test value differs from its expectation: check the code and the test's own arithmetic (what the test does before that check); fix whichever is wrong, never delete the check."),
 ('AssertionError',"A self-test assertion fails: make the code and the expected value agree; never delete or weaken the test. Make the self-test collect every mismatch and print them all before exiting 1, so one run shows each failing value (a first-assert stop hid brutto behind afa for a whole cycle)."),
)

def general_error(err):
 """An error message without paths and quoted names, so the same failure is recognized again."""
 return re.sub(r"'[^']*'",'…',re.sub(r'\s*\(/[^)]*\)','',str(err))).strip()[:140]

def recurring_code_errors(s,mid,f,builds=12):
 """Code-run errors that came back in at least two of the recent builds of this product, in a
 general form and with advice where the fix is known, so the builder stops repeating them."""
 seen={}
 for row in s.rows("SELECT st.result FROM orbit_mission_steps st JOIN orbit_mission_runs r ON r.id=st.run WHERE r.mission=? AND st.node='build' AND st.state='done' ORDER BY r.cycle DESC LIMIT ?",(mid,builds*3)):
  c=json.loads(row['result'] or '{}').get('content')
  if not isinstance(c,dict) or c.get('idea_id')!=f['idea_id']:continue
  errors=(c.get('checks') or {}).get('errors') or dict(re.findall(r'([\w.-]+\.py) → ([^;]+?)(?:;|\s+Élő próba|$)',c.get('summary','')))
  kinds=set()
  for file,err in errors.items():
   general=general_error(err)
   kinds.add((file,general))
  for k in kinds:seen[k]=seen.get(k,0)+1
  builds-=1
  if builds<=0:break
 out=[]
 for (file,err),n in sorted(seen.items(),key=lambda x:-x[1]):
  if n<2:continue
  advice=next((a for key,a in CODE_PITFALLS if key in err),'Find the root cause instead of patching around it.')
  out.append(dict(file=file,error=err,builds=n,advice=advice))
 return out[:4]

BLOCKING=('SyntaxError','IndentationError','ImportError','ModuleNotFoundError')
STUCK_BUILDS=6

import datetime as _dt
ENFORCED_SINCE=_dt.datetime(2026,10,31,15,40).timestamp()

def next_milestone(milestones):
 """Broken code first, then other revisions, then the first pending step, then a step closed
 with code still failing. The 9B planner kept picking 'tests' while server.py did not start."""
 # A file that cannot even load (syntax or import error) blocks the server and the live test, so
 # its milestone comes first, even one already closed.
 blocking=lambda m:m['state']!='skipped' and any(any(b in e for b in BLOCKING) for e in m['code_errors'].values())
 # A closed step whose code still fails comes before new steps: features are not built on broken code.
 order=[blocking,lambda m:m['state']=='revise' and m['code_errors'],lambda m:m['state']=='revise',lambda m:m['code_errors'] and m['state']!='skipped' and not m.get('stuck'),lambda m:m['state']=='pending']
 for rule in order:
  m=next((m for m in milestones if rule(m)),None)
  if m:return m['id']
 return None

def context(s,mission,f):
 refresh_paper(s,f)
 milestones,actions=progress(s,mission['id'],f);nxt=next_milestone(milestones)
 return dict(mode='implementation',operator_direction=__import__('venture').direction_for(s,f['idea_id']),idea_type=TYPES.get(f.get('type'),'Szolgáltatás'),focus=dict(idea_id=f['idea_id'],name=f['name'],plan=short_plan(plan_text(s,f))),product_folder=folder(f),
  roadmap=compact_roadmap(f,milestones,focus=nxt),next_milestone=nxt,recurring_code_errors=recurring_code_errors(s,mission['id'],f),
  measurements=measurements(s,f),avoid_recent_failures=__import__('venture').pitfalls(s,mission['id']),owner_actions=[a['title'] for a in actions],instruction='Implement; do not research new ideas. Everything outward-facing or involving real money stays a draft for the owner.')

def _computed(s,f,product,picked):
 """Run ORBIT's own calculators on the files the builder just wrote; return extra files and notes."""
 extra={};notes=[]
 if 'strategy.json' in picked:
  from strategy_lab import backtest
  try:
   r=backtest(json.loads(picked['strategy.json']))
   extra['backtest.json']=json.dumps(r,ensure_ascii=False,indent=1)
   o=r['out_of_sample'];a=r['full']
   notes.append(f"ORBIT backtest ({r['spec']['coin']} {r['spec']['interval']}, {r['bars']} gyertya): teljes {a['return_pct']}% (tartás: {a['buy_hold_pct']}%), mintán kívül {o['return_pct']}%, max. visszaesés {a['max_drawdown_pct']}%, {a['trades']} kötés → {'ígéretes' if r['verdict']=='promising' else 'gyenge'}.")
  except (ValueError,OSError) as exc:raise ValueError('A stratégia nem tesztelhető: '+str(exc)[:200])
 if 'economics.json' in picked:
  from strategy_lab import economics
  r=economics(json.loads(picked['economics.json']));extra['economics-result.json']=json.dumps(r,ensure_ascii=False,indent=1)
  notes.append(f"ORBIT számítás: rendelésenkénti haszon {r['profit_per_order']} {r['currency']} ({r['margin_pct']}%), max. hirdetési költség/eladás {r['breakeven_ad_cost']} → {r['verdict']}.")
 return extra,notes

def fix_bytes_literals(source):
 """b'Érvénytelen JSON' is a SyntaxError (bytes literals are ASCII only), and the 27B writes it
 again and again in Hungarian products: it kept server.py and pipeline.py from even starting.
 Such literals become '...'.encode('utf-8'); nothing else changes. None if no repair applies."""
 import ast,io,tokenize
 try:ast.parse(source);return None
 except SyntaxError as e:
  if 'bytes can only contain ASCII' not in str(e):return None
 try:tokens=list(tokenize.generate_tokens(io.StringIO(source).readline))
 except (tokenize.TokenError,SyntaxError,IndentationError):return None
 starts=[0]
 for line in source.splitlines(keepends=True):starts.append(starts[-1]+len(line))
 edits=[]
 for tok in tokens:
  if tok.type!=tokenize.STRING:continue
  prefix=re.match(r'[A-Za-z]*',tok.string).group(0)
  if 'b' not in prefix.lower() or tok.string.isascii():continue
  body=prefix.replace('b','').replace('B','')+tok.string[len(prefix):]
  edits.append((starts[tok.start[0]-1]+tok.start[1],starts[tok.end[0]-1]+tok.end[1],'('+body+").encode('utf-8')"))
 for a,b,new in reversed(edits):source=source[:a]+new+source[b:]
 try:ast.parse(source)
 except SyntaxError:return None
 return source

def restore_working(s,mid,f,product,skip=()):
 """A product .py file that does not even parse goes back to its newest version that ran cleanly
 in an earlier build (cycle 148 left server.py with an invalid line before the syntax guard).
 Files the builder wrote in this very build are kept, so their error goes back to the builder."""
 import ast
 broken=[]
 for path in sorted(Path(product).glob('*.py')):
  if path.name in skip:continue
  try:ast.parse(path.read_text())
  except SyntaxError:broken.append(path.name)
  except (OSError,UnicodeDecodeError):continue
 if not broken:return []
 rows=s.rows("SELECT r.id AS run,st.result FROM orbit_mission_steps st JOIN orbit_mission_runs r ON r.id=st.run WHERE r.mission=? AND st.node='build' AND st.state='done' ORDER BY r.cycle DESC LIMIT 80",(mid,))
 restored=[]
 for name in broken:
  for row in rows:
   c=json.loads(row['result'] or '{}').get('content')
   if not isinstance(c,dict) or c.get('idea_id')!=f['idea_id'] or (c.get('checks') or {}).get('ok') is None:continue
   if name not in {PurePosixPath(x).name for x in c.get('files') or []} or name in (c['checks'].get('failed') or []) or name in (c.get('regressions') or []):continue
   try:old=_path(s,row['run']).joinpath(name).read_text();ast.parse(old)
   except (OSError,ValueError,SyntaxError):continue
   (Path(product)/name).write_text(old);restored.append(name);break
 return restored

SERVER_BASE='orbit_server_base.py'

def ensure_server_base(product,f):
 """API products get ORBIT's tested server base; it is restored after every build so the
 builder cannot break it (servers kept failing on bytes literals, exits and imports)."""
 if 'api' not in {k for k,_,_,_ in roadmap(f)} or not (Path(product)/'server.py').is_file():return False
 src=Path(__file__).with_name(SERVER_BASE);dst=Path(product)/SERVER_BASE
 if not src.is_file():return False
 text=src.read_text()
 if not dst.is_file() or dst.read_text()!=text:dst.write_text(text);return True
 return False

def repair_product(product):
 """Apply the deterministic repairs to every product .py file; returns the repaired names."""
 fixed=[]
 for path in sorted(Path(product).glob('*.py')):
  try:new=fix_bytes_literals(path.read_text())
  except (OSError,UnicodeDecodeError):continue
  if new is not None:path.write_text(new);fixed.append(path.name)
 return fixed

MAX_EDITS=12
# Existing files above this size change only with edits: 10 of 53 builds hit the 4500-token reply limit
# (about 170 minutes of generation) mostly by writing 12-13 thousand characters of whole files again.
EDIT_ONLY=2500

def file_sizes(s,f):
 """The product's files and their size in characters, for the build task."""
 product=s.safe_path(PID,folder(f))
 if not product.is_dir():return {}
 return {p.name:len(p.read_text(errors='replace')) for p in sorted(product.iterdir()) if p.is_file() and (p.suffix in EXTS or p.name in NAMES) and p.name not in (SERVER_BASE,OWNER_FILE)}
PROTECTED='ORBIT-PROTECTED'
NAME_KEYS=('name','path','file','filename')

def named(entries):
 """The builder often calls the file key "path" or "file" instead of "name"; in cycle 163 that
 alone threw away a correct 26-minute build. Each entry gets "name" from the first alias present."""
 out=[]
 for x in entries:
  if isinstance(x,dict) and not isinstance(x.get('name'),str):
   alias=next((x[k] for k in NAME_KEYS[1:] if isinstance(x.get(k),str)),None)
   if alias is not None:x=dict(x,name=alias)
  out.append(x)
 return out

def apply_edits(product,edits,skip=()):
 """Patch existing product files with exact find/replace blocks instead of rewriting them: the
 27B spends most of a build writing whole files out again. Every block must match the current
 file exactly once; if any block of a file does not, none of that file's blocks is applied."""
 out={};bad={}
 for i,e in enumerate(named(edits[:MAX_EDITS])):
  # An incomplete block is skipped and reported; only a path outside the product folder rejects the answer.
  if not isinstance(e,dict) or not all(isinstance(e.get(k),str) for k in ('name','find','replace')):bad[str(i+1)+'. csere-blokk']='hiányzik a name, find vagy replace mező';continue
  if '..' in e['name'] or e['name'].startswith('/'):raise ValueError('Érvénytelen csere-blokk.')
  name=PurePosixPath(e['name']).name
  if name in skip or name in bad:continue
  if name not in out:
   path=product/name
   if not path.is_file():bad[name]='nincs ilyen fájl';continue
   out[name]=path.read_text()
  hits=out[name].count(e['find']) if e['find'] else 0
  if hits!=1:bad[name]='a keresett szöveg '+('nem található' if not hits else 'több helyen szerepel ('+str(hits)+' találat)');out.pop(name,None);continue
  out[name]=out[name].replace(e['find'],e['replace'],1)
 # Edited Python must still parse: one block once produced 'self.state = "HALF_OPEN" = "HALF_OPEN"'.
 # A full file with a syntax error is kept so the code run reports it; a broken patch is not.
 import ast
 for name in [n for n in out if n.endswith('.py')]:
  code=fix_bytes_literals(out[name]) or out[name]
  try:ast.parse(code);out[name]=code
  except SyntaxError as exc:bad[name]='a csere után szintaxishiba lenne, '+str(exc.lineno)+'. sor: '+str(exc.msg)[:80];out.pop(name)
 return out,[n+' ('+why+')' for n,why in bad.items()]

def checks_record(check):
 """What a build stores about its code run. A failed live API test is recorded as an error of
 smoke.json, so it reopens the milestone that wrote the test requests, reaches the builder with
 the exact failing request, and counts in the recurring errors and the product status line."""
 failed=[r['file'] for r in check.get('results',[]) if not r['ok']]
 import product_check
 errors={r['file']:product_check.problem(r)[:300] for r in check.get('results',[]) if not r['ok']}
 live=check.get('smoke')
 if live and not live.get('ok'):
  bad=[x for x in live.get('results',[]) if not x['ok']]
  errors['smoke.json']=('Élő próba: '+(live.get('note') or '; '.join(x['request']+' → '+str(x['status'])+' '+str(x.get('error') or '')[:80] for x in bad[:3])))[:300]
  failed.append('smoke.json')
 # An unkept promise is an error of the page that makes it: the builder removes it or builds it.
 for page,bad in ((check.get('promises') or {}).get('pages') or {}).items():
  errors[page]=('Ígéret-ellenőrzés: '+'; '.join(bad))[:300];failed.append(page)
 return dict(ok=check.get('ok'),failed=failed,errors=errors)

def save(s,run,value,f=None,enforce=False):
 """Validate one milestone and write it into the product folder plus a per-cycle copy.
 With enforce (the Autopilot's own builds), the work is filed under the milestone ORBIT selected:
 the 27B builder labelled it differently in 3 of 3 measured cycles, which marked an unbuilt billing
 step done while the API stayed broken."""
 if not isinstance(value,dict):raise ValueError('Strukturált fejlesztési eredmény szükséges.')
 f=f or active(s)
 if not f:raise ValueError('Nincs kijelölt megvalósítandó ötlet.')
 ids={k for k,_,_,_ in roadmap(f)};mid=value.get('milestone_id');relabelled=None;fix_targets=set()
 if enforce:
  row=s.db.execute('SELECT mission,cycle FROM orbit_mission_runs WHERE id=?',(run,)).fetchone()
  ms=progress(s,row[0],f)[0] if row else []
  chosen=remembered_milestone(s,row[1],f) if row else None
  expected=chosen if chosen in {m['id'] for m in ms if m['state'] not in ('done','skipped')} else next_milestone(ms) if row else None
  if expected and mid!=expected:relabelled=mid;value=dict(value,milestone_id=expected);mid=expected
  fix_targets=set(fix_targets_of(next((m['code_errors'] for m in progress(s,row[0],f)[0] if m['id']==expected),{}))) if row and expected else set()
 if mid not in ids:
  # A wrong id (often the idea id) would discard the whole build; the work belongs to the next
  # open milestone, which is what the planner asked for.
  row=s.db.execute('SELECT mission FROM orbit_mission_runs WHERE id=?',(run,)).fetchone()
  open_ms=[m['id'] for m in progress(s,row[0],f)[0] if m['state'] not in ('done','skipped')] if row else []
  if not open_ms:raise ValueError('Ismeretlen mérföldkő ennél az ötlettípusnál: '+str(mid))
  value=dict(value,milestone_id=open_ms[0]);mid=open_ms[0]
 summary=str(value.get('summary') or '').strip()
 if len(summary)<10:raise ValueError('Hiányzik az elkészült munka leírása.')
 status=value.get('status') if value.get('status') in ('partial','skipped') else 'done'
 files=value.get('files') or [];edits=value.get('edits') or []
 if not isinstance(files,list) or not isinstance(edits,list) or (not files and not edits and status!='skipped'):raise ValueError('Legalább egy elkészült fájl szükséges.')
 picked={}
 for x in named(files):
  if not isinstance(x,dict) or not isinstance(x.get('name'),str) or '..' in x['name'] or x['name'].startswith('/'):raise ValueError('Érvénytelen fájl.')
  picked[PurePosixPath(x['name']).name]=x.get('content')
 patched,unmatched=apply_edits(s.safe_path(PID,folder(f)),edits,skip=picked)
 if edits and not patched and not picked:raise ValueError('Egyik csere-blokk sem illeszkedett a meglévő fájlokra: '+'; '.join(unmatched)[:300])
 picked.update(patched)
 # Rejecting extra files would lose the whole cycle; the rest is built in the next milestone pass.
 picked=dict(list(picked.items())[:4])
 total=0
 for name,content in picked.items():
  if (PurePosixPath(name).suffix not in EXTS and name not in NAMES) or name in ('backtest.json','paper.json','economics-result.json','paper-start.json',OWNER_FILE,'launch-form.json'):raise ValueError('Nem engedélyezett fájl: '+name)
  if not isinstance(content,str) or not 20<=len(content)<=16000:raise ValueError('Üres vagy túl nagy fájl: '+name)
  if name.endswith('.py'):
   repaired=fix_bytes_literals(content)
   if repaired is not None:picked[name]=content=repaired
   # With the sandbox, a syntax error is reported back by the code run (the file is kept and
   # revised); without it, broken code is rejected outright.
   try:__import__('ast').parse(content)
   except SyntaxError:
    import product_check
    if not __import__('os').path.exists(product_check.SANDBOX):raise
  if name.endswith('.json'):json.loads(content)
  total+=len(content)
 if total>30000:raise ValueError('Túl nagy munkacsomag.')
 product=s.safe_path(PID,folder(f));product.mkdir(parents=True,exist_ok=True)
 extra,notes=_computed(s,f,product,picked)
 # Files the owner marked ORBIT-PROTECTED (an acceptance test on real data) are read-only for the
 # builder: rewriting its labels to match a regression would empty the measure.
 guarded=[n for n in list(picked) if (product/n).is_file() and PROTECTED in (product/n).read_text(errors='replace')[:800]]
 for n in guarded:picked.pop(n)
 if guarded:notes.append('Védett fájl, az ORBIT nem engedte módosítani (a tulajdonos mércéje): '+', '.join(guarded)+'.')
 rewrites={n:(len((product/n).read_text(errors='replace')),len(picked[n])) for n in picked if n not in patched and (product/n).is_file() and len((product/n).read_text(errors='replace'))>EDIT_ONLY}
 if rewrites:notes.append('Teljes újraírás csere-blokk helyett: '+', '.join(n+' ('+str(a)+' → '+str(b)+' karakter)' for n,(a,b) in rewrites.items())+'.')
 if fix_targets and not (set(picked)|{PurePosixPath(e.get('name','')).name for e in edits if isinstance(e,dict)})&fix_targets:
  notes.append('Az Építő nem a hibás fájlokat javította ('+', '.join(sorted(fix_targets))+'), hanem: '+(', '.join(picked) or 'semmit')+'.')
 if relabelled:notes.append('Az Építő „'+str(TITLES.get(relabelled,relabelled))+'” lépésnek jelölte a munkát, de az ORBIT a kijelölt „'+TITLES[mid]+'” lépéshez rendelte.')
 if patched:notes.append('Csere-blokkokkal javítva: '+', '.join(patched)+'.')
 if unmatched:notes.append('Nem illeszkedő csere-blokk, a fájl változatlan maradt: '+'; '.join(unmatched)+'. Ezeket teljes tartalommal kell megadni.')
 if mid=='paper' and f.get('type')=='trading' and not paper_started(s,f):
  (product/'paper-start.json').write_text(json.dumps(dict(started=time.time())));notes.append('A virtuális pénzes teszt elindult 1000 virtuális USD-vel; minden következő kör frissíti.')
 # Regression guard: a .py file that ran cleanly in the last code run must not be replaced by a
 # broken one (a later build once broke a working server.py and the product went backwards).
 owner=s.db.execute('SELECT mission FROM orbit_mission_runs WHERE id=?',(run,)).fetchone()
 last=product_health(s,owner[0],f) if owner else None
 working={n:(product/n).read_text() for n in picked if n.endswith('.py') and (product/n).is_file() and last and n not in last['failed']}
 copy=_path(s,run);copy.mkdir(parents=True,exist_ok=True)
 saved=[]
 for name,content in list(picked.items())+list(extra.items()):
  for target in (product/name,copy/name):target.write_text(content)
  if not s.db.execute('SELECT 1 FROM artifacts WHERE project=? AND path=?',(PID,str(product/name))).fetchone():
   s.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)',(uuid.uuid4().hex,PID,name,str(product/name),'text',time.time(),None))
  saved.append(str(product/name))
 ensure_server_base(product,f)
 fixed=repair_product(product)
 if fixed:notes.append('Az ORBIT automatikusan javította (ékezetes szöveg bájtliterálban): '+', '.join(fixed)+'.')
 back=restore_working(s,owner[0],f,product,skip=picked) if owner else []
 if back:notes.append('Az ORBIT visszaállította az utolsó hibátlanul futó változatot (a fájl nem volt értelmezhető): '+', '.join(back)+'.')
 import product_check
 # The checks run every product file and take minutes: the rows above must not hold the write lock.
 if s.db.in_transaction:s.db.commit()
 check=product_check.run(product)
 broken={r['file']:product_check.problem(r)[:200] for r in check.get('results',[]) if not r['ok'] and r['file'] in working}
 # A file this build did not touch that ran cleanly before and fails now was broken by the files the
 # build changed (radar.py breaking realcheck.py): those go back, not the untouched file.
 knock={r['file']:product_check.problem(r)[:150] for r in check.get('results',[]) if not r['ok'] and r['file'] not in picked and last and last.get('files') and r['file'] not in last['failed']}
 if knock and working and not broken:
  for name,text in working.items():(product/name).write_text(text)
  check=product_check.run(product)
 if knock and working and not broken and any(not r['ok'] and r['file'] in knock for r in check.get('results',[])):
  # Still failing without this build's changes: something else broke it, so the build's work stays.
  for name in working:(product/name).write_text(picked[name])
  check=product_check.run(product)
 elif knock and working and not broken:
  notes.append('Regresszió megakadályozva: '+', '.join(knock)+' korábban hibátlanul futott, ehhez a kör nem nyúlt, de a(z) '+', '.join(working)+' módosítása után elbukott ('+'; '.join(knock.values())+'). Az ORBIT visszaállította: '+', '.join(working)+'; a hibás új változat a kör mappájában maradt.')
  broken={n:'miatta elbukott: '+', '.join(knock) for n in working}
 elif broken:
  for name in broken:(product/name).write_text(working[name])
  check=product_check.run(product)
  notes.append('Regresszió megakadályozva: '+'; '.join(n+' korábban hibátlanul futott, az új változat hibás volt ('+e+')' for n,e in broken.items())+'. Az ORBIT visszaállította a működő változatot; a hibás új változat a kör mappájában maradt, a javítást arra kell építeni.')
 kept=product_check.promises(product)
 if kept and check.get('ok') is not None:check=dict(check,promises=kept,ok=check['ok'] and kept['ok'])
 if check.get('results') or check.get('note'):notes.append(product_check.summary(check))
 actions=[]
 # The builder re-adds the same to-dos in new words every cycle; a variant of an open one is dropped.
 known=[owner_words(x['title']) for x in progress(s,owner[0],f)[1]] if owner else []
 for a in value.get('owner_actions') or []:
  if owner_step(a) and not any(similar_words(owner_words(a['title']),w) for w in known):
   kind=a.get('kind') if a.get('kind') in ('money','publish','account','contact','legal') else 'other'
   actions.append(dict(title=a['title'].strip()[:200],kind=kind,why=str(a.get('why') or '')[:600],draft=str(a.get('draft') or '')[:3000]))
 result=dict(mode='build',idea_id=f['idea_id'],idea=f['name'],idea_type=f.get('type','service'),milestone_id=mid,title=TITLES[mid],summary=(summary[:2000]+('\n\n'+'\n'.join(notes) if notes else '')),files=saved,
  acceptance=[str(x)[:300] for x in (value.get('acceptance') or [])[:10]],status=status,
  owner_actions=actions[:6],checks=checks_record(check),regressions=sorted(broken),rewrites=sorted(rewrites),milestone_by='orbit' if enforce else 'builder',next=str(value.get('next') or '')[:600],revenue_status='unverified',created=time.time())
 (copy/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));s.db.commit()
 if owner and result['checks'].get('ok') and (not (product/'server.py').is_file() or check.get('smoke')):
  announce_ready(s,f,dict(ok=True,**run_counts(product_check.summary(check)),failed=[]))
 return result

def run_counts(summary):
 """Files that ran cleanly, live requests that passed and real-data checks that matched, from a build summary."""
 out={}
 for key,label in (('files','ORBIT futtatás'),('live','Élő próba'),('real','Valós minta')):
  m=re.search(label+r': (\d+)/(\d+)',summary or '')
  out[key+'_ok'],out[key]=(int(m.group(1)),int(m.group(2))) if m else (None,None)
 return out

def real_note(h):
 """How the product was measured, for the owner: its own tests only, or also real data."""
 if h and h.get('real'):return 'a valós mintán '+str(h['real_ok'])+'/'+str(h['real'])+' kézzel ellenőrzött tétel egyezik'
 return 'valódi adaton még nincs mérve'

def product_health(s,mid,f):
 """The newest ORBIT code run of this product: files that ran cleanly and the live API test."""
 for row in s.rows("SELECT st.result FROM orbit_mission_steps st JOIN orbit_mission_runs r ON r.id=st.run WHERE r.mission=? AND st.node='build' AND st.state='done' ORDER BY r.cycle DESC LIMIT 60",(mid,)):
  c=json.loads(row['result'] or '{}').get('content')
  if not isinstance(c,dict) or c.get('idea_id')!=f['idea_id'] or (c.get('checks') or {}).get('ok') is None:continue
  return dict(ok=c['checks']['ok'],**run_counts(c.get('summary')),failed=c['checks'].get('failed',[]),at=c.get('created'))
 return None

def timeline(s,mid,f,limit=14):
 """One entry per recent build of this product, oldest first: how long it took, how many files ran
 cleanly and whether the live API test passed, so going in circles is visible at a glance."""
 titles={k:t for k,t,_,_ in roadmap(f)};out=[]
 for row in s.rows("""SELECT r.id AS run,r.cycle,st.result,(SELECT finished-started FROM jobs j WHERE j.kind='mission_agent' AND +j.status='done'
   AND json_extract(j.payload,'$.mission_run')=r.id AND json_extract(j.payload,'$.mission_node')='build' ORDER BY j.finished DESC LIMIT 1) AS seconds
   FROM orbit_mission_steps st JOIN orbit_mission_runs r ON r.id=st.run WHERE r.mission=? AND st.node='build' AND st.state='done' ORDER BY r.cycle DESC LIMIT ?""",(mid,limit*3)):
  c=json.loads(row['result'] or '{}').get('content')
  if not isinstance(c,dict) or c.get('idea_id')!=f['idea_id'] or (c.get('checks') or {}).get('ok') is None:continue
  out.append(dict(cycle=row['cycle'],at=c.get('created'),minutes=round(row['seconds']/60,1) if row['seconds'] else None,milestone=titles.get(c.get('milestone_id'),c.get('milestone_id')),
   **run_counts(c.get('summary')),ok=bool(c['checks']['ok']),failed=c['checks'].get('failed',[]),errors=c['checks'].get('errors') or {},regressions=c.get('regressions') or []))
  if len(out)>=limit:break
 return out[::-1]

# Whole files preloaded into a build or review task: ocr.py (7.6k) and pipeline.py (5.4k) together.
FILE_BUDGET=14000

def fix_targets_of(errors):
 """Files the builder has to change for these errors. A failed live test is fixed in server.py:
 smoke.json is the specification, and the builder kept editing the expectations instead."""
 names=[n for n in errors if n.endswith(('.py','.html')) or n=='traffic-kit.json']
 if 'smoke.json' in errors and 'server.py' not in names:names.append('server.py')
 # Most valuable first, since only some fit the task: the server behind a failed live test, files that
 # cannot load, other real errors, and last a file failing only because it runs the others' tests.
 others=[x for x in names if x!='server.py']
 def rank(n):
  err=str(errors.get(n,''))
  if n=='server.py' and 'smoke.json' in errors:return 0
  if any(b in err for b in BLOCKING):return 1
  if '"self_test"' in err or any(o!=n and o in err for o in others):return 3
  return 2
 return sorted(names,key=lambda n:(rank(n),names.index(n)))

def broken_files(s,mid,cycle,budget=7000):
 """Whole contents of the selected milestone's broken .py files, largest error first, within a
 character budget. Partial files are left out: an edit or rewrite from half a file breaks it."""
 import venture
 f=venture.cycle_focus(s,cycle) or active(s)
 if not f or budget<=0:return {}
 milestones=progress(s,mid,f)[0];sel=next_milestone(milestones)
 m=next((x for x in milestones if x['id']==sel),None)
 out={};left=min(budget,FILE_BUDGET)
 for name in fix_targets_of(m['code_errors'] if m else {}):
  try:text=s.safe_path(PID,folder(f)+'/'+name).read_text()
  except (OSError,ValueError):continue
  if len(text)<=left:out[name]=text;left-=len(text)
 return out

def changed_files(s,run,budget=7000):
 """Whole current contents of the files the build of this run wrote, within a character budget."""
 row=s.db.execute("SELECT result FROM orbit_mission_steps WHERE run=? AND node='build' AND state='done'",(run,)).fetchone()
 c=json.loads(row['result'] or '{}').get('content') if row else None
 if not isinstance(c,dict) or c.get('mode')!='build' or budget<=0:return {}
 out={};left=min(budget,FILE_BUDGET)
 for path in c.get('files') or []:
  try:text=Path(path).read_text()
  except (OSError,ValueError):continue
  if PurePosixPath(path).name.endswith(('.py','.json','.md','.html')) and len(text)<=left:out[PurePosixPath(path).name]=text;left-=len(text)
 return out

def product_text(s):
 """The /termek Telegram answer: the product in progress, its code health, live test, next step and
 the last builds, in a few plain lines."""
 import venture
 row=s.db.execute('SELECT id FROM orbit_missions WHERE origin=?',(venture.ORIGIN,)).fetchone();f=active(s)
 if not row or not f:return 'Az Autopilóta most nem épít terméket.'
 mid=row[0];ms=progress(s,mid,f)[0];h=product_health(s,mid,f);nxt=next_step(ms);recent=timeline(s,mid,f,limit=5)
 label=lambda names:', '.join('élő próba' if x=='smoke.json' else x for x in names)
 lines=['🧪 '+f['name'],'Lépések: '+str(sum(m['state'] in ('done','skipped') for m in ms))+'/'+str(len(ms))+' kész']
 if h and h.get('files') is not None:lines.append(('✅ ' if h['ok'] else '⚠️ ')+str(h['files_ok'])+'/'+str(h['files'])+' fájl fut hibátlanul'+(' · élő próba '+str(h['live_ok'])+'/'+str(h['live']) if h.get('live') is not None else '')+(' · valós minta '+str(h['real_ok'])+'/'+str(h['real']) if h.get('real') else '')+(' · hibás: '+label(h['failed']) if h['failed'] else ''))
 if nxt:lines.append('Következő: '+nxt['title']+(' · javítandó: '+label(nxt['fix']) if nxt['fix'] else ''))
 est=eta(s,mid,f)
 if est.get('text'):lines.append('⏱ '+est['text'])
 if recent:lines.append('Utolsó építések: '+' · '.join(str(e['cycle'])+'. kör '+(str(e['files_ok'])+'/'+str(e['files']) if e['files'] is not None else '?')+(' ('+str(round(e['minutes']))+' perc)' if e['minutes'] else '') for e in recent))
 return '\n'.join(lines)

STEP_LABELS=dict(research='tervezés',build='építés',review='ellenőrzés')

def mins(seconds):return max(1,round(seconds/60))

def eta(s,mid,f,now=None):
 """Measured times for the owner and the assistant, which once told the owner that a 20-minute cycle
 takes "1-2 minutes": the running step against its usual length, when this cycle should end, the
 usual cycle, and whether the failing checks of the product are going down."""
 import math,statistics
 now=now or time.time();out={}
 runs={r[0]:dict(cycle=r[1],status=r[2]) for r in s.db.execute('SELECT id,cycle,status FROM orbit_mission_runs WHERE mission=? ORDER BY cycle DESC LIMIT 12',(mid,))}
 jobs=[]
 for jid,status,created,started,finished,payload in s.db.execute("SELECT id,status,created,started,finished,payload FROM jobs WHERE status IN ('done','running','queued') AND kind='mission_agent' AND created>?",(now-2*86400,)):
  try:p=json.loads(payload or '{}')
  except ValueError:continue
  if p.get('mission_run') in runs:jobs.append(dict(status=status,created=created,started=started,finished=finished,node=p.get('mission_node'),fixed=bool(p.get('fixed_result')),run=p['mission_run']))
 # Usual length of a model step; steps ORBIT writes from measurements take seconds and are left out.
 typical={}
 for node in STEP_LABELS:
  done=sorted((j for j in jobs if j['node']==node and j['status']=='done' and not j['fixed'] and j['started'] and j['finished']),key=lambda j:-j['finished'])[:8]
  typical[node]=statistics.median([j['finished']-j['started'] for j in done]) if done else None
 spans=[]
 for rid,r in sorted(runs.items(),key=lambda x:-x[1]['cycle']):
  js=[j for j in jobs if j['run']==rid and j['finished']]
  if r['status']=='done' and js:spans.append(max(j['finished'] for j in js)-min(j['created'] for j in js))
 if spans:out['cycle_minutes']=mins(statistics.median(spans[:6]))
 rid,run=max(runs.items(),key=lambda x:x[1]['cycle']) if runs else (None,{})
 if run.get('status')=='running':
  steps={r[0]:dict(state=r[1],result=r[2]) for r in s.db.execute('SELECT node,state,result FROM orbit_mission_steps WHERE run=?',(rid,))}
  research=json.loads((steps.get('research') or {}).get('result') or '{}').get('content')
  fixing=isinstance(research,str) and 'ORBIT fix brief' in research
  usual_of=lambda n:0 if fixing and n=='review' else typical.get(n)
  current=next((n for n in STEP_LABELS if n in steps and steps[n]['state'] not in ('done','skipped')),None)
  if current:
   job=next((j for j in sorted(jobs,key=lambda j:-j['created']) if j['run']==rid and j['node']==current),None)
   usual=usual_of(current);step=dict(node=current,label=STEP_LABELS[current],cycle=run['cycle'],usual_minutes=mins(usual) if usual else None,measured=fixing and current=='review')
   if job and job['status']=='running' and job['started']:step.update(state='fut',minutes=mins(now-job['started']));left=max(0,(usual or 0)-(now-job['started']))
   else:step.update(state='sorban áll' if job else 'indul');left=usual or 0
   for n in list(STEP_LABELS)[list(STEP_LABELS).index(current)+1:]:
    if n in steps and steps[n]['state'] not in ('done','skipped'):left+=usual_of(n) or 0
   out.update(step=step,cycle_left_minutes=mins(left) if left else 0)
 # The product: failing checks (files plus the live test) over the recent builds.
 recent=[e for e in timeline(s,mid,f,limit=6) if e['files'] is not None]
 if recent:
  fails=lambda e:(e['files']-e['files_ok'])+(1 if e.get('live') and (e.get('live_ok') or 0)<e['live'] else 0)+sum(not n.endswith('.py') and n!='smoke.json' for n in e.get('failed') or [])
  # Progress is judged against the previous build, counting the failing values inside a file too: TermékA's
  # server.py went from 5 failed checks to 2 and the estimate still said "a new failure appeared".
  weight=lambda e:sum(int(m.group(1)) if (m:=re.search(r'FAIL \((\d+) hiba\)',str((e.get('errors') or {}).get(n,'')))) else 1 for n in e.get('failed') or []) or fails(e)
  last=recent[-1];prev=recent[-2] if len(recent)>1 else None
  new=[n for n in last.get('failed') or [] if prev and n not in (prev.get('failed') or [])]
  out.update(failing=fails(last),weight=weight(last),new=new,
   trend='nő' if new else 'csökken' if prev and weight(last)<weight(prev) else 'változatlan',
   error_changed=bool(prev) and last.get('errors')!=prev.get('errors'),previous_weight=weight(prev) if prev else None)
  if out['failing'] and out['trend']=='csökken' and out.get('cycle_minutes'):
   out['cycles_left']=math.ceil(out['weight']/(out['previous_weight']-out['weight']));out['ready_minutes']=out['cycles_left']*out['cycle_minutes']
 parts=[];st=out.get('step')
 if st:
  usual=' (az ORBIT a mérésből ítél, pár másodperc)' if st.get('measured') else ' (szokásosan kb. '+str(st['usual_minutes'])+' perc)' if st.get('usual_minutes') else ''
  if st['state']=='fut':parts.append(str(st['cycle'])+'. kör: '+st['label']+' fut '+str(st['minutes'])+' perce'+usual+(', a szokásosnál tovább tart' if st.get('usual_minutes') and st['minutes']>st['usual_minutes']*1.3 else ''))
  else:parts.append(str(st['cycle'])+'. kör: '+st['label']+' '+st['state']+usual)
  if out.get('cycle_left_minutes'):parts.append('a kör várhatóan kb. '+str(out['cycle_left_minutes'])+' perc múlva ér véget')
 if out.get('cycle_minutes'):parts.append('egy kör átlagosan kb. '+str(out['cycle_minutes'])+' perc')
 if 'failing' in out:
  if not out['failing']:parts.append('a termék átment a saját öntesztjein és az élő API-próbán, '+real_note(last))
  elif out['trend']=='nő':parts.append('még '+str(out['failing'])+' hibás ellenőrzés: új hiba jelent meg ('+', '.join('élő próba' if n=='smoke.json' else n for n in out['new'])+'), a következő javító kör ezzel kezd')
  elif out['trend']=='csökken':parts.append('még '+str(out['failing'])+' hibás ellenőrzés, a hibák száma csökken ('+str(out['previous_weight'])+' → '+str(out['weight'])+')'+(': kb. '+str(out['cycles_left'])+' kör (≈ '+str(out['ready_minutes'])+' perc) múlva lehet kész' if out.get('cycles_left') else ''))
  elif out['error_changed']:parts.append('még '+str(out['failing'])+' hibás ellenőrzés; a számuk nem csökkent, de a hiba körről körre változik (haladás), ezért a kész időpontja nem becsülhető')
  else:parts.append('még '+str(out['failing'])+' hibás ellenőrzés, és ugyanaz a hiba ismétlődik: elakadás gyanúja')
 out['text']=' · '.join(parts)
 return out

def autopilot_now(s):
 """The Autopilot's measured times for the assistant's live snapshot; None when nothing is built."""
 import venture
 row=s.db.execute('SELECT id FROM orbit_missions WHERE origin=?',(venture.ORIGIN,)).fetchone();f=active(s)
 if not row or not f:return None
 return dict(product=f['name'],**eta(s,row[0],f),note='Measured by ORBIT from job times; quote these, never guess durations.')

def remember_milestone(s,mid,cycle):
 """Fix the milestone a cycle works on when it starts (research dispatch). Filing the build under the milestone
 that is next only when the build is saved mislabels it if the roadmap changes in between (a deploy)."""
 import venture
 f=venture.cycle_focus(s,cycle) or active(s)
 if not f:return None
 sel=next_milestone(progress(s,mid,f)[0])
 path=s.safe_path(PID,'workspace/ventures/cycle-milestones.json')
 try:marks=json.loads(path.read_text())
 except (OSError,ValueError):marks={}
 marks[str(cycle)]=dict(idea_id=f['idea_id'],milestone=sel)
 keep=sorted(marks,key=lambda k:int(k) if k.isdigit() else 0)[-40:]
 path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps({k:marks[k] for k in keep}));return sel

def remembered_milestone(s,cycle,f):
 try:mark=json.loads(s.safe_path(PID,'workspace/ventures/cycle-milestones.json').read_text()).get(str(cycle))
 except (OSError,ValueError):mark=None
 return mark['milestone'] if isinstance(mark,dict) and mark.get('idea_id')==f['idea_id'] else None

def fix_brief(s,mid,cycle):
 """The planner's brief, written by ORBIT, when the selected milestone has broken code: exactly the
 failing files with their measured errors and the acceptance test. None outside fix mode."""
 import venture
 f=venture.cycle_focus(s,cycle) or active(s)
 if not f:return None
 milestones=progress(s,mid,f)[0];sel=next_milestone(milestones)
 m=next((x for x in milestones if x['id']==sel),None)
 if not m or not m['code_errors']:return None
 lines=['milestone_id: '+sel,'','ORBIT fix brief (written from the measured code run, not by a planner): milestone "'+m['title']+'" has broken files. Fix exactly these and nothing else:']
 for name,err in sorted(m['code_errors'].items()):lines.append('- '+('server.py (live test against smoke.json)' if name=='smoke.json' else name)+': '+str(err)[:300])
 if 'smoke.json' in m['code_errors']:lines.append('smoke.json is the specification: change server.py until it answers every smoke.json request as expected; do not weaken the expectations.')
 if any(n.endswith('.html') or n=='traffic-kit.json' for n in m['code_errors']):lines.append('A listed page or traffic kit promises what the launched product does not do: rewrite or remove exactly those promises (or build them in the code); promise nothing the launched page cannot do.')
 # Cycles 162-164 fixed one field per 20-minute cycle: afa first, then brutto, hidden behind it.
 # The same check failing build after build while the code changes: the test's own arithmetic may be the
 # bug (TermékA's rate-limit test made 11 calls before expecting the 10th to pass, two cycles in a row).
 again={(r['file'],r['error']):r['builds'] for r in recurring_code_errors(s,mid,f)}
 for name,err in sorted(m['code_errors'].items()):
  n=again.get((name,general_error(err)))
  if n and n>=2 and name.endswith('.py'):lines.append('The same check in '+name+' has failed in '+str(n)+' builds although the code changed: re-derive its expected value by counting what the test itself does before that check (calls, inputs, time). A wrong expected value or test arithmetic may be corrected; a check must not be deleted or weakened.')
 asserting=[n for n,err in sorted(m['code_errors'].items()) if 'AssertionError' in str(err) and n.endswith('.py')]
 if asserting:lines.append('The self-test of '+', '.join(asserting)+' stops at its first failed assert, so later wrong values stay hidden: fix the reported value, check the other expected values of the same example too, and make the self-test print every mismatch before exiting 1.')
 lines+=['','Acceptance: every listed .py file passes `python3 file.py --self-test`; when smoke.json is listed, server.py started with --port answers every smoke.json request as expected. Use edits on the current file contents in the task. Do not add features, new files or owner actions in this cycle.']
 return '\n'.join(lines)

def measured_review(s,run_id):
 """The tester's verdict, written by ORBIT from the code run, for a build that followed an ORBIT fix
 brief; None otherwise (new work still gets the 27B tester). In fix mode the tester took 8-9 minutes
 of a 20-minute cycle (162-164) to restate what the code run and the live test had measured."""
 row=lambda node:s.db.execute("SELECT result FROM orbit_mission_steps WHERE run=? AND node=? AND state='done'",(run_id,node)).fetchone()
 research,build=row('research'),row('build')
 brief=json.loads(research[0] or '{}').get('content') if research else None
 c=json.loads(build[0] or '{}').get('content') if build else None
 if not isinstance(brief,str) or 'ORBIT fix brief' not in brief or not isinstance(c,dict) or (c.get('checks') or {}).get('ok') is None:return None
 targets={('smoke.json' if m.group(2) else m.group(1)) for m in re.finditer(r'^- (\S+?)( \(live test against smoke\.json\))?: ',brief,re.M)}
 targets|={PurePosixPath(x).name for x in c.get('files') or []}
 errors=c['checks'].get('errors') or {}
 failing=[n for n in c['checks'].get('failed') or [] if n in targets]
 measured=next((l.strip() for l in c.get('summary','').splitlines() if l.startswith('ORBIT futtatás')),'')
 head='ORBIT mérés (javító kör, a kritikus modell helyett az ORBIT kódfuttatása ítél): '
 if not failing:return 'VERDICT: accept\n'+head+'a javítandó fájlok most hibátlanul futnak. '+measured
 return 'VERDICT: revise\n'+head+'még hibás: '+'; '.join(('élő próba' if n=='smoke.json' else n)+' → '+str(errors.get(n,'a futtatás hibával állt le'))[:200] for n in failing)+'. Javítsd ezeket, más fájlhoz ne nyúlj.'

def ready(health):
 """Every product file ran cleanly and the live API test (if any) passed in the newest code run."""
 return bool(health and health.get('ok') and health.get('files') and health['files_ok']==health['files'] and (health.get('live') is None or health.get('live_ok')==health.get('live'))
  and (not health.get('real') or health.get('real_ok')==health.get('real')))

def announce_ready(s,f,health):
 """The first time a product passes everything, tell the owner once on Telegram (if notifications are on)."""
 if not ready(health):return False
 path=_path(s,'ready.json')
 try:seen=json.loads(path.read_text())
 except (OSError,ValueError):seen={}
 if f['idea_id'] in seen:return False
 seen[f['idea_id']]=time.time();path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(seen))
 try:
  import connections
  cfg=connections.settings()['providers'].get('telegram',{})
  if cfg.get('notifications') and cfg.get('chat_id') and connections.allowed('telegram'):
   connections.http('telegram','sendMessage',dict(chat_id=cfg['chat_id'],text='✅ „'+f['name']+'” átment a saját ellenőrzésein: '+str(health['files'])+' fájl hibátlan'+(', élő próba '+str(health['live_ok'])+'/'+str(health['live']) if health.get('live') is not None else '')+'.\n'+('A '+real_note(health).removeprefix('a ')+'.' if health.get('real') else 'Ez a termék saját tesztjeit méri, valódi adaton (például valódi ügyféladaton) még nincs mérve.')+' Az ORBIT Autopilóta oldalán a ▶︎ Kipróbálás gombbal kipróbálhatod; az élesítés a te döntésed.'),timeout=10,priority=True)
 except Exception:pass
 return True

def next_step(milestones):
 """What the Autopilot works on next, and which broken files it has to fix there."""
 mid=next_milestone(milestones);m=next((x for x in milestones if x['id']==mid),None)
 return dict(id=mid,title=m['title'],fix=sorted(m['code_errors'])) if m else None

def view(s,mid,f):
 """Implementation state for the Autopilot page, with file previews."""
 milestones,actions=progress(s,mid,f)
 for m in milestones:
  previews=[]
  for p in m['files']:
   name=PurePosixPath(p).name
   try:text=s.safe_path(PID,folder(f)+'/'+name).read_text()[:4000]
   except (OSError,ValueError):text=''
   previews.append(dict(name=name,preview=text))
  m['files']=previews
 done=sum(m['state'] in ('done','skipped') for m in milestones)
 from venture import known_ideas
 names={i['idea_id']:i['name'] for i in known_ideas(s,PID)}
 import launch
 live=launch.read_state(s,folder(f))
 out=dict(operator_direction=__import__('venture').direction_for(s,f['idea_id']),traffic=launch.traffic_kit(s,folder(f),(live or {}).get('url') if (live or {}).get('status')=='live' else None),launch=live,previews=web_previews(s,f),idea_id=f['idea_id'],name=f['name'],type=f.get('type','service'),type_label=TYPES.get(f.get('type'),'Szolgáltatás'),started=f.get('started'),auto=f.get('auto',False),folder=folder(f),
  health=(health:=product_health(s,mid,f)),ready=ready(health),eta=eta(s,mid,f),timeline=timeline(s,mid,f),next=next_step(milestones),  milestones=milestones,owner_actions=actions,done=done,total=len(milestones),measurements=measurements(s,f),
  queue=[names.get(q,q) for q in f.get('queue',[])],finished=[names.get(q,q) for q in f.get('finished',[])],live_update=(update:=launch.staleness(s,folder(f),live)))
 import concierge,design_studio
 product=s.safe_path(PID,folder(f));designs=design_studio.summary(s,product)
 if f.get('type')=='digital':
  # A digital product is ready when every design is rendered and every one has its listing: the marketplace sells it.
  out['ready']=bool(designs and designs['total'] and designs['done']==designs['total'] and (product/'listings.json').is_file())
 import product_check
 out.update(designs=designs,checkout=launch.checkout(launch.form_config(product)),api_examples=product_check.api_examples(product),has_api=(product/'server.py').is_file())
 if out['has_api'] and (not out['api_examples'] or not (out['health'] or {}).get('live')):
  out['ready']=False
 return dict(out,owner_actions=publish_step(out,update)+concierge.actions(s,f)+actions,requests=concierge.requests(s,f))

def publish_step(v,update):
 """The owner's next step once the product is ready, first in their list: publish it, or bring the
 live site up to the version the Autopilot has built since. ORBIT never publishes by itself."""
 if v.get('type')=='digital':
  d=v.get('designs') or {}
  if not v.get('ready'):return []
  # With the owner's Etsy shop connected, the Etsy part is no longer the owner's job.
  import etsy
  shop=etsy.connected()
  return [dict(title=('Feltöltés a többi piactérre: ' if shop else 'Feltöltés a piacterekre: ')+str(d.get('done'))+' kész grafika',kind='publish',count=1,variants=[],
   why='Minden grafika elkészült, és mindhez van termékadatlap. '+('Az Etsyre az ORBIT maga tölti fel őket piszkozatként; a többi piactér fiókja és feltöltése a tiéd.' if shop else 'A piactér nyomtat, fizettet és szállít; a fiók, az adóadatok és a feltöltés a tiéd. Az Etsyre az ORBIT is fel tudja tölteni őket: Etsy-feltöltés → Etsy csatlakoztatása.'),
   draft='1. 📁 Elkészült fájlok megnyitása → designs mappa: a nyomdakész PNG-k'+(' és a coloring-book.pdf színezőfüzet' if d.get('book') else '')+'.\n2. Minden grafikához a listings.json címe, leírása, címkéi és ára.\n3. A launch.md lépései piacterenként (fiók, kifizetési adatok, feltöltés).')]
 if not v['previews']:return []
 when=time.strftime('%m.%d. %H:%M',time.localtime(update['since'])) if update and update.get('since') else ''
 if update and update['stale']:
  return [dict(title='Élő oldal frissítése az új változatra',kind='publish',relaunch='update',count=1,variants=[],
   why='Az élő oldal a '+when+' állapotot mutatja; azóta az Autopilóta továbbfejlesztette'+(' ('+', '.join(update['changed'])+')' if update['changed'] else '')+'. A frissítés ugyanazon a címen történik, a mérések és a várólista megmaradnak.',
   draft='1. Nézd meg az új oldalt: Autopilóta → ▶︎ Kipróbálás.\n2. Ha rendben van: Élő blokk → 🔄 Új változat élesítése → Igen.\n3. Az ORBIT csak a te megerősítéseddel cseréli le az élő oldalt.')]
 if v['ready'] and not (v['launch'] or {}).get('status')=='live':
  return [dict(title='Bemutató közzététele: a termék átment a helyi ellenőrzésein',kind='publish',relaunch='first',count=1,variants=[],
   why='A saját öntesztek és az élő API-próba hibátlanok; '+real_note(v.get('health'))+', ezért élesítés előtt nézd át, hogy az oldal csak azt ígéri-e, amit a kód tud. A weboldal a Cloudflare-fiókodba tehető (ingyenes csomag) a várólistás méréssel.',
   draft='1. Nézd meg az oldalt: ▶︎ Kipróbálás.\n2. 🚀 Élesítés → Igen, élesítem.\n3. A forgalmat (posztok, hirdetés) te indítod; ehhez a Forgalom indítása blokk ad kész szövegeket.')]
 return []

def salvage(text):
 """Keep the complete files of a milestone answer that was cut off mid-JSON (model length limit)."""
 text=str(text or '')
 mid=re.search(r'"milestone_id"\s*:\s*"([a-z_]+)"',text)
 # The id often comes last and is cut off with the rest; ORBIT files the work under the selected
 # milestone anyway, so its absence no longer loses the complete files.
 mid=mid.group(1) if mid and mid.group(1) in TITLES else ''
 lit=lambda m:json.loads('"'+m+'"')
 summary=re.search(r'"summary"\s*:\s*"((?:[^"\\]|\\.)*)"',text)
 files=[]
 for m in re.finditer(r'\{\s*"(?:name|path|file|filename)"\s*:\s*"((?:[^"\\]|\\.)*)"\s*,\s*"content"\s*:\s*"((?:[^"\\]|\\.)*)"',text,re.S):
  try:files.append(dict(name=lit(m.group(1)),content=lit(m.group(2))))
  except ValueError:continue
 edits=[]
 for m in re.finditer(r'\{\s*"(?:name|path|file|filename)"\s*:\s*"((?:[^"\\]|\\.)*)"\s*,\s*"find"\s*:\s*"((?:[^"\\]|\\.)*)"\s*,\s*"replace"\s*:\s*"((?:[^"\\]|\\.)*)"\s*\}',text,re.S):
  try:edits.append(dict(name=lit(m.group(1)),find=lit(m.group(2)),replace=lit(m.group(3))))
  except ValueError:continue
 if not files and not edits:return None
 return dict(edits=edits,milestone_id=mid,summary=(lit(summary.group(1)) if summary else 'Részben elkészült.')+' (A válasz megszakadt; a teljes fájlok mentve, a többit a következő kör pótolja.)',files=files,status='partial',owner_actions=[])

def web_previews(s,f):
 """Self-contained previews of the product's web pages (local CSS inlined) plus the artifact id
 to open the real file in the browser. The page shows them sandboxed without scripts."""
 product=s.safe_path(PID,folder(f))
 if not product.is_dir():return []
 out=[]
 for page in sorted(product.glob('*.html'),key=lambda p:(p.name!='index.html',p.name)):
  try:html=page.read_text()[:80000]
  except OSError:continue
  def inline(m):
   css=product/PurePosixPath(m.group(1)).name
   return '<style>'+css.read_text()[:100000]+'</style>' if css.is_file() and css.suffix=='.css' else ''
  html=re.sub(r'<link[^>]+href=["\']([^"\']+\.css)["\'][^>]*>',inline,html,flags=re.I)
  row=s.db.execute('SELECT id FROM artifacts WHERE project=? AND path=?',(PID,str(page))).fetchone()
  out.append(dict(name=page.name,html=html,artifact=row[0] if row else None))
 return out[:6]
