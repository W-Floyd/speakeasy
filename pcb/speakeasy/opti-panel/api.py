#!/usr/bin/env python3
"""JLCPCB Online Quote API — auth signing and live PCB pricing."""

import base64
import hashlib
import hmac
import json
import random
import string
import time
import urllib.error
import urllib.request

API_BASE  = "https://open.jlcpcb.com"
QUOTE_URI = "/overseas/openapi/pcb/calculate"

# PCB parameter defaults for a standard 2-layer green HASL board
_DEFAULT_LAYERS         = 2
_DEFAULT_THICKNESS      = 1.6
_DEFAULT_COLOR          = 1      # green
_DEFAULT_SURFACE_FINISH = 1      # HASL
_DEFAULT_COPPER_WEIGHT  = 1.0    # oz


def _nonce(length: int = 32) -> str:
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


def _sign(s: str, secret_key: str) -> str:
    mac = hmac.new(secret_key.encode(), s.encode(), hashlib.sha256)
    return base64.b64encode(mac.digest()).decode()


def auth_header(method: str, path: str, body: str,
                app_id: str, access_key: str, secret_key: str) -> str:
    nonce = _nonce()
    ts    = int(time.time())
    sig   = _sign(f"{method}\n{path}\n{ts}\n{nonce}\n{body}\n", secret_key)
    return (f'JOP appid="{app_id}",accesskey="{access_key}",'
            f'nonce="{nonce}",timestamp="{ts}",signature="{sig}"')


def get_quote_live(cols: int, rows: int, qty: int, pcb_w: float, pcb_l: float,
                   app_id: str, access_key: str, secret_key: str,
                   country: str | None = None,
                   postcode: str | None = None,
                   city: str | None = None,
                   ) -> tuple[float | None, list[dict]]:
    """
    Fetch a live JLCPCB fab quote for a panel variant.

    Returns (fab_price, ship_options).  ship_options is non-empty only when
    country/postcode are supplied.  Each entry:
      {"method": str, "display": str, "cost": float | None, "days": str}
    """
    panel_flag = 0 if (cols == 1 and rows == 1) else 1
    pcb_param: dict = {
        "layer": _DEFAULT_LAYERS, "width": pcb_w, "length": pcb_l,
        "qty": qty, "thickness": _DEFAULT_THICKNESS,
        "pcbColor": _DEFAULT_COLOR, "surfaceFinish": _DEFAULT_SURFACE_FINISH,
        "copperWeight": _DEFAULT_COPPER_WEIGHT, "panelFlag": panel_flag,
    }
    if panel_flag == 1:
        pcb_param["panelByJLCPCB_X"] = cols
        pcb_param["panelByJLCPCB_Y"] = rows
    payload: dict = {"orderType": 1, "pcbParam": pcb_param}
    if country:
        payload["country"] = country
    if postcode:
        payload["postCode"] = postcode
    if city:
        payload["city"] = city
    body = json.dumps(payload, separators=(",", ":"))
    auth = auth_header("POST", QUOTE_URI, body, app_id, access_key, secret_key)
    req  = urllib.request.Request(
        f"{API_BASE}{QUOTE_URI}", data=body.encode(),
        headers={"Content-Type": "application/json", "Authorization": auth},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"    HTTP {e.code}: {e.read().decode()[:200]}")
        return None, []
    except Exception as e:
        print(f"    Request failed: {e}")
        return None, []
    if result.get("code") != 0:
        print(f"    API error {result.get('code')}: {result.get('message')}")
        return None, []
    data      = result.get("data") or {}
    price_str = data.get("priceWithoutFreight")
    fab_price = float(price_str) if price_str is not None else None
    ship_opts = [
        {
            "method":  s.get("options", ""),
            "display": s.get("showOptions", s.get("options", "")),
            "cost":    float(s["cost"]) if s.get("cost") not in (None, "") else None,
            "days":    s.get("day", ""),
        }
        for s in (data.get("shipList") or [])
    ]
    return fab_price, ship_opts
