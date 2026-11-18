# ORBIT Mobile

Private companion: mobile_server.py binds only 127.0.0.1:47832. It exposes project/job summaries and the existing global assistant chat; never the unrestricted native bridge. Authenticated API calls require a random bearer key stored with mode 0600 in Orbit/integrations/mobile/access.key. The browser keeps it in sessionStorage; logout discards it. No private response caching or external fonts/scripts. API text is rendered as text, never HTML.

Start with the installed media runtime: python mobile_server.py. For phone access, install/sign in to Tailscale on the Mac and iPhone, enable HTTPS for your private network, restrict access to your device/account, then use `tailscale serve --bg http://127.0.0.1:47832`. Do not use Funnel: this service is intended for private access. Open the private HTTPS address in iPhone Safari, enter the access key locally, and use Share → Add to Home Screen. No App Store submission. The Mac must stay awake. Disconnected phone views show a connection error rather than claiming current data.

Rotate access by stopping the service, replacing access.key with a new random value, and restarting; old sessions lose access. This first version shows text chat and project activity, not artifact video playback or push notifications. Approval-required actions remain in the desktop approval flow. Generated responses and commands use the existing model routing and user policies.

Palette references: https://catppuccin.com/palette/ and https://www.nordtheme.com/docs/colors-and-palettes/ . Six base colors per theme; UI text/background combinations are checked at >=4.5:1. Status colors and artwork may remain semantic/source-specific. Reduced-motion settings disable the animated atmosphere.
