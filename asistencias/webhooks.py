import hashlib
import hmac
import json

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods


@csrf_exempt
@require_http_methods(["GET", "POST"])
def whatsapp_webhook(request):
    if request.method == "GET":
        token = settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN
        if not token:
            return HttpResponse(status=503)
        supplied = request.GET.get("hub.verify_token", "")
        challenge = request.GET.get("hub.challenge", "")
        if (request.GET.get("hub.mode") != "subscribe" or not challenge
                or not hmac.compare_digest(token, supplied)):
            return HttpResponse(status=403)
        return HttpResponse(challenge, content_type="text/plain")

    secret = settings.WHATSAPP_APP_SECRET
    if not secret:
        return HttpResponse(status=503)
    signature = request.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"), request.body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return HttpResponse(status=403)
    try:
        payload = json.loads(request.body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return HttpResponse(status=400)
    if not isinstance(payload, dict) or payload.get("object") != "whatsapp_business_account":
        return HttpResponse(status=400)
    return HttpResponse(status=200)
