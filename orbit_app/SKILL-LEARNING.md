# Self-learned API skills (2026-11-09)

ORBIT can learn a new skill that calls a public web API, on request ("tanuld meg az időjárás API-t") or by itself
when a request needs live data none of its tools cover.

- `skill_api.learn(goal)`: picks candidate APIs from the community index github.com/public-apis (cached a week),
  reads each API's home page and up to two of its own documentation pages, has the planner's model write a spec
  (base URL, auth, GET endpoints, test call), runs the test call live, repairs the spec once from the error.
  A spec that answered its test is stored as a published skill (source `learned`); one that needs a key is stored
  as a draft until the owner pastes the key on Memória → Skillek, which re-runs the test and publishes it.
- `skill_api.call(skill, endpoint, params)`: GET only, https public hosts only, only declared parameters, the key
  only to the skill's own host, no cross-host redirect, 600 kB / 20 s, 60 calls per hour per skill, key redacted.
- Planner reads: `{"skill_call":{...}}` and `{"learn_skill":"goal"}` (contract in `skill_api.CONTRACT`); matching
  skills are offered with their endpoints in TASK CONTEXT AND METHODS.
- Keys live in `connections/skill_secrets.json` (0600) and never enter a prompt, reply or the skill data.
- Public search engines answered with junk or a CAPTCHA, so discovery uses the index; a configured Tavily key adds
  web search as a fallback.
