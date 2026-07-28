"""Thin client around the PayPal REST API (Orders v2 + Webhooks).

Docs used to build this:
  - Get started / auth:     https://developer.paypal.com/api/rest/authentication/
  - Create order:           https://developer.paypal.com/docs/api/orders/v2/#orders_create
  - Capture order:          https://developer.paypal.com/docs/api/orders/v2/#orders_capture
  - Get order:              https://developer.paypal.com/docs/api/orders/v2/#orders_get
  - Verify webhook sig:     https://developer.paypal.com/docs/api/webhooks/v1/#verify-webhook-signature
  - Sandbox testing:        https://developer.paypal.com/tools/sandbox/

No official PayPal SDK is required — this project talks to the REST API
directly with `requests`, which is already a project dependency.

This module deliberately contains NO Django view logic, ORM calls, or
request/response handling. It only knows how to talk to PayPal. Keeping it
separate makes it easy to unit test and easy to swap out later.
"""
import logging
import time
import uuid

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# Transient-failure retry policy for outbound PayPal calls. Only network-
# level failures and 5xx responses are retried — a 4xx means PayPal
# rejected the request itself (bad payload, bad auth, etc.) and retrying
# it verbatim would just fail again. Every retried call below already
# carries a PayPal-Request-Id (create_order/capture_order) or is naturally
# idempotent (GET), so retries can't create duplicate orders/captures.
MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 0.5

# PayPal has two completely separate environments. Sandbox is used for all
# testing — sandbox "buyer" test accounts pay with fake money and nothing
# ever touches real funds. Live is only used once PAYPAL_MODE=live and real
# (non-sandbox) client credentials are configured.
PAYPAL_API_BASE = {
    'sandbox': 'https://api-m.sandbox.paypal.com',
    'live': 'https://api-m.paypal.com',
}

REQUEST_TIMEOUT_SECONDS = 15


class PayPalError(Exception):
    """Raised for any problem talking to PayPal — network failure, a
    non-success API response, or an unparsable response body. The message
    is written to be safe to show to an end user."""


def _api_base():
    mode = (getattr(settings, 'PAYPAL_MODE', 'sandbox') or 'sandbox').lower()
    return PAYPAL_API_BASE.get(mode, PAYPAL_API_BASE['sandbox'])


def generate_tx_ref(prefix='moneywise'):
    """A short, unique, URL-safe transaction reference.

    This is OUR OWN reference (PayPal doesn't need it to be unique across
    their system), used as the `reference_id` / `custom_id` on the order
    so a Payment row can always be traced back to what we sent PayPal, even
    before PayPal hands us its own order id.
    """
    return f'{prefix}-{uuid.uuid4().hex[:24]}'


def _request_with_retry(method, url, *, log_context, **kwargs):
    """`requests.request(method, url, **kwargs)` with retries for transient
    failures (connection errors, timeouts, 5xx responses). Raises
    `PayPalError` if every attempt fails; returns the `requests.Response`
    on the first attempt that gets a response back (regardless of status
    code — callers still need to inspect 4xx bodies for PayPal's error
    details, so a 4xx is returned normally, not raised here).

    `log_context` is a short human-readable string (e.g. 'create order
    tx_ref=...') used to make retry/failure log lines traceable back to
    the calling operation.
    """
    last_exc = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.request(method, url, timeout=REQUEST_TIMEOUT_SECONDS, **kwargs)
        except requests.RequestException as exc:
            last_exc = exc
            logger.warning(
                'PayPal request failed (attempt %s/%s) for %s: %s', attempt, MAX_ATTEMPTS, log_context, exc,
            )
        else:
            if response.status_code < 500:
                return response
            logger.warning(
                'PayPal request got %s (attempt %s/%s) for %s',
                response.status_code, attempt, MAX_ATTEMPTS, log_context,
            )
            last_exc = None

        if attempt < MAX_ATTEMPTS:
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)

    if last_exc is not None:
        logger.exception('PayPal request exhausted retries for %s', log_context, exc_info=last_exc)
    else:
        logger.error('PayPal request exhausted retries for %s (repeated 5xx)', log_context)
    raise PayPalError('Could not reach the payment provider. Please try again.')


def _get_access_token():
    """OAuth2 client-credentials token, required on every PayPal REST call.

    Tokens are short-lived (a few hours); for simplicity we fetch a fresh
    one per request rather than caching, which is perfectly fine at this
    project's scale and keeps this module stateless.
    """
    client_id = settings.PAYPAL_CLIENT_ID
    client_secret = settings.PAYPAL_CLIENT_SECRET
    if not client_id or not client_secret:
        logger.error('PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET are not configured.')
        raise PayPalError('Payments are not configured yet. Please try again later.')

    response = _request_with_retry(
        'POST', f'{_api_base()}/v1/oauth2/token',
        log_context='oauth token',
        data={'grant_type': 'client_credentials'},
        auth=(client_id, client_secret),
        headers={'Accept': 'application/json', 'Accept-Language': 'en_US'},
    )

    try:
        data = response.json()
    except ValueError:
        logger.error('PayPal OAuth token returned non-JSON (status=%s): %.500s', response.status_code, response.text)
        raise PayPalError('Received an unexpected response from the payment provider.')

    token = data.get('access_token')
    if response.status_code != 200 or not token:
        logger.error('PayPal OAuth token request rejected (status=%s): %s', response.status_code, data)
        raise PayPalError('Could not authenticate with the payment provider.')

    return token


def create_order(*, amount, currency, tx_ref, return_url, cancel_url, description=''):
    """Call POST /v2/checkout/orders and return the parsed JSON body.

    Raises PayPalError on any failure. On success, the returned dict has
    the shape documented by PayPal, most importantly:
        data['id']                              — the PayPal order id
        [l['href'] for l in data['links'] if l['rel'] == 'approve'][0]
                                                 — where the browser goes next
    """
    token = _get_access_token()
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
        # Ensures a retried request (e.g. a network blip) can't accidentally
        # create two orders for the same checkout attempt.
        'PayPal-Request-Id': tx_ref,
    }
    payload = {
        'intent': 'CAPTURE',
        'purchase_units': [{
            'reference_id': tx_ref,
            'custom_id': tx_ref,
            'description': (description or '')[:127],
            'amount': {
                'currency_code': currency,
                'value': str(amount),
            },
        }],
        'application_context': {
            'brand_name': 'MoneyWise',
            'user_action': 'PAY_NOW',
            'shipping_preference': 'NO_SHIPPING',
            'return_url': return_url,
            'cancel_url': cancel_url,
        },
    }

    response = _request_with_retry(
        'POST', f'{_api_base()}/v2/checkout/orders',
        log_context=f'create order tx_ref={tx_ref}',
        json=payload, headers=headers,
    )

    try:
        data = response.json()
    except ValueError:
        logger.error(
            'PayPal create order returned non-JSON (status=%s) for tx_ref=%s: %.500s',
            response.status_code, tx_ref, response.text,
        )
        raise PayPalError('Received an unexpected response from the payment provider.')

    if response.status_code not in (200, 201) or data.get('status') not in ('CREATED', 'PAYER_ACTION_REQUIRED'):
        logger.warning('PayPal create order rejected tx_ref=%s (status=%s): %s', tx_ref, response.status_code, data)
        message = (data.get('message') or (data.get('details') or [{}])[0].get('description')) if isinstance(data, dict) else None
        raise PayPalError(message or 'Payment could not be started. Please try again.')

    approve_url = next((l.get('href') for l in data.get('links', []) if l.get('rel') == 'approve'), None)
    if not approve_url:
        logger.error('PayPal create order succeeded but had no approve link: %s', data)
        raise PayPalError('Payment provider did not return a checkout link.')

    return data


def capture_order(order_id):
    """Call POST /v2/checkout/orders/{id}/capture and return the parsed JSON.

    This is the call that actually moves the money — PayPal only *reserves*
    the payment when the buyer approves it, our server has to capture it.
    Raises PayPalError on network/parse failure. Does NOT raise just
    because PayPal reports the order as not capturable (e.g. it was already
    captured, or the buyer never approved it) — callers should inspect the
    response body themselves; see `_status_of`.
    """
    token = _get_access_token()
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
        'PayPal-Request-Id': f'capture-{order_id}',
    }

    response = _request_with_retry(
        'POST', f'{_api_base()}/v2/checkout/orders/{order_id}/capture',
        log_context=f'capture order_id={order_id}',
        headers=headers, json={},
    )

    try:
        data = response.json()
    except ValueError:
        logger.error(
            'PayPal capture returned non-JSON (status=%s) for order_id=%s: %.500s',
            response.status_code, order_id, response.text,
        )
        raise PayPalError('Received an unexpected response from the payment provider.')

    return data


def get_order(order_id):
    """Call GET /v2/checkout/orders/{id} and return the parsed JSON.

    Used as the server-to-server "source of truth" check — both the return
    URL flow and the webhook re-fetch the order from PayPal directly rather
    than trusting a redirect querystring or webhook body on their own.
    Raises PayPalError on network/parse failure.
    """
    token = _get_access_token()
    headers = {'Authorization': f'Bearer {token}'}

    response = _request_with_retry(
        'GET', f'{_api_base()}/v2/checkout/orders/{order_id}',
        log_context=f'get order_id={order_id}',
        headers=headers,
    )

    try:
        data = response.json()
    except ValueError:
        logger.error(
            'PayPal get order returned non-JSON (status=%s) for order_id=%s: %.500s',
            response.status_code, order_id, response.text,
        )
        raise PayPalError('Received an unexpected response from the payment provider.')

    return data


def capture_id_from_order(order_data):
    """Dig the capture id out of an order/capture response, if present."""
    try:
        captures = order_data['purchase_units'][0]['payments']['captures']
        return captures[0]['id'] if captures else ''
    except (KeyError, IndexError, TypeError):
        return ''


def verify_webhook_signature(*, webhook_id, headers, raw_body: bytes):
    """Validate an incoming webhook request using PayPal's server-side
    Verify Webhook Signature API, per
    https://developer.paypal.com/docs/api/webhooks/v1/#verify-webhook-signature

    Unlike Chapa (which signs with a shared-secret HMAC we can check
    locally), PayPal signs webhooks with a private key and expects us to
    call back to their API with the transmission headers plus the raw
    event body to confirm the signature. Returns True/False; never raises
    (a network failure is treated as "not verified" — safer to reject a
    real webhook and let PayPal retry it than to risk accepting a forged
    one).
    """
    if not webhook_id:
        return False

    try:
        import json
        event_body = json.loads(raw_body.decode('utf-8') or '{}')
    except (ValueError, UnicodeDecodeError):
        return False

    try:
        token = _get_access_token()
    except PayPalError:
        logger.exception('Could not get an access token to verify a PayPal webhook.')
        return False

    payload = {
        'transmission_id': headers.get('Paypal-Transmission-Id', ''),
        'transmission_time': headers.get('Paypal-Transmission-Time', ''),
        'cert_url': headers.get('Paypal-Cert-Url', ''),
        'auth_algo': headers.get('Paypal-Auth-Algo', ''),
        'transmission_sig': headers.get('Paypal-Transmission-Sig', ''),
        'webhook_id': webhook_id,
        'webhook_event': event_body,
    }
    if not all([payload['transmission_id'], payload['transmission_time'], payload['cert_url'],
                payload['auth_algo'], payload['transmission_sig']]):
        logger.warning('PayPal webhook missing one or more required signature headers.')
        return False

    try:
        response = requests.post(
            f'{_api_base()}/v1/notifications/verify-webhook-signature',
            json=payload,
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        data = response.json()
    except (requests.RequestException, ValueError):
        logger.exception('PayPal verify-webhook-signature call failed.')
        return False

    return data.get('verification_status') == 'SUCCESS'
