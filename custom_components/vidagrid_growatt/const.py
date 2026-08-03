"""Constants for the VidaGrid (Growatt white-label) integration.

This integration talks to the REST API behind the VidaGrid portal used by
Base Power's Growatt-branded batteries (growatt-us.vidagrid.com, "Shiner"
consumer app backend). It is NOT the official Growatt OpenAPI and NOT the
same backend the official `growatt_server` HA integration talks to -- this
portal is a separate white-label deployment (Delta Networks (Xiamen) LTD)
that Base Power / Sunrun license on top of Growatt hardware.

The portal's login page requires solving a CAPTCHA, so this integration
cannot log in on its own. Instead, you sign in through your normal browser,
copy the Bearer token your browser already holds (see the integration's
setup instructions), and paste it in here. The token is good for roughly
30 days ("remember me"); when it expires, Home Assistant will prompt you
to paste a fresh one via its normal re-authentication flow.
"""

from __future__ import annotations

DOMAIN = "vidagrid_growatt"

CONF_BEARER_TOKEN = "bearer_token"
CONF_BASE_URL = "base_url"
CONF_SITE_ID = "site_id"
CONF_INVERTER_SNS = "inverter_sns"

DEFAULT_BASE_URL = "https://growatt-us.vidagrid.com"
DEFAULT_SCAN_INTERVAL_SECONDS = 60

# Endpoints observed via browser network inspection on 2026-08-02.
# These are undocumented/unofficial and may change without notice.
EP_INVERTER_BATTERY = "/web/v1/inverter/{sn}/battery"
EP_INVERTER_DIAGRAM = "/web/v1/inverter/{sn}/diagram"
EP_INVERTER_PRODUCTION = "/web/v1/inverters/production"
EP_INVERTER_POWER_CURVE = "/web/v1/inverter/{sn}/flows/curve/power"
