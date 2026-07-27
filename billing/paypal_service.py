import requests
from django.conf import settings
import base64
import requests
from django.conf import settings


class PayPalService:

    @staticmethod
    def get_access_token():

        client_id = settings.PAYPAL_CLIENT_ID
        secret = settings.PAYPAL_CLIENT_SECRET

        auth = base64.b64encode(
            f"{client_id}:{secret}".encode()
        ).decode()

        headers = {
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        data = {
            "grant_type": "client_credentials"
        }

        url = "https://api-m.sandbox.paypal.com/v1/oauth2/token"

        response = requests.post(
            url,
            headers=headers,
            data=data,
        )

        return response.json()["access_token"]


    @staticmethod
    def create_order(amount):

        token = PayPalService.get_access_token()

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        body = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "amount": {
                        "currency_code": "USD",
                        "value": str(amount),
                    }
                }
            ]
        }

        response = requests.post(
            "https://api-m.sandbox.paypal.com/v2/checkout/orders",
            headers=headers,
            json=body,
        )

        return response.json()

    @staticmethod
    def capture_order(order_id):

        token = PayPalService.get_access_token()

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        response = requests.post(
            f"https://api-m.sandbox.paypal.com/v2/checkout/orders/{order_id}/capture",
            headers=headers,
        )

        return response.json()