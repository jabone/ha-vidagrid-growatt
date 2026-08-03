"""Constants for the VidaGrid (Growatt white-label) integration.

This integration talks to the REST API behind the VidaGrid portal used by
Base Power's Growatt-branded batteries (growatt-us.vidagrid.com, "Shiner"
consumer app backend). It is NOT the official Growatt OpenAPI and NOT the
same backend the official `growatt_server` HA integration talks to -- this
portal is a separate white-label deployment (Delta Networks (Xiamen) LTD)
that Base Power / Sunrun license on top of Growatt hardware.

The portal's login page requires solving a CAPTCHA, so this integration
cannot log in on its own. Worse, the copied Bearer token turned out to be
short-lived in practice (observed expiring in as little as ~15-25 minutes),
even though the browser's own session keeps itself alive indefinitely via a
silent refresh that never needs the captcha again.

Because of that, the pasted token is now just used for initial setup
validation and as an infrequent best-effort fallback poll. The real,
sustainable data path is a webhook: a small userscript (Tampermonkey) running
in the user's already-authenticated browser tab periodically fetches fresh
telemetry using whatever token the page currently holds (read locally by the
user's own script, never sent to or seen by anything else) and POSTs the
resulting data -- not the token -- to this integration's webhook endpoint.
See README.md for the userscript and setup steps.
"""

from __future__ import annotations

DOMAIN = "vidagrid_growatt"

CONF_BEARER_TOKEN = "bearer_token"
CONF_BASE_URL = "base_url"
CONF_SITE_ID = "site_id"
CONF_INVERTER_SNS = "inverter_sns"
CONF_WEBHOOK_ID = "webhook_id"

DEFAULT_BASE_URL = "https://growatt-us.vidagrid.com"
# The pasted-token poll is now just a fallback safety net; the webhook push
# (see webhook.py) is the primary, frequent data path.
DEFAULT_SCAN_INTERVAL_SECONDS = 1200

# Endpoints observed via browser network inspection on 2026-08-02.
# These are undocumented/unofficial and may change without notice.
EP_INVERTER_BATTERY = "/web/v1/inverter/{sn}/battery"
EP_INVERTER_DIAGRAM = "/web/v1/inverter/{sn}/diagram"
EP_INVERTER_PRODUCTION = "/web/v1/inverters/production"
EP_INVERTER_POWER_CURVE = "/web/v1/inverter/{sn}/flows/curve/power"
