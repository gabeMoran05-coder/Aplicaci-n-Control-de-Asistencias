import json
import logging
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import NotificacionWhatsApp


logger = logging.getLogger(__name__)


def normalizar_telefono(valor):
    digitos = re.sub(r"\D", "", valor or "")
    if len(digitos) == 10:
        digitos = settings.WHATSAPP_DEFAULT_COUNTRY_CODE + digitos
    return digitos if 11 <= len(digitos) <= 15 else ""


def configuracion_whatsapp():
    if not settings.WHATSAPP_ENABLED:
        return None
    token = settings.WHATSAPP_ACCESS_TOKEN
    numero = settings.WHATSAPP_PHONE_NUMBER_ID
    plantilla = settings.WHATSAPP_TEMPLATE_NAME
    version = settings.WHATSAPP_API_VERSION
    if not (token and numero and plantilla and version):
        return None
    if not re.fullmatch(r"\d+", numero) or not re.fullmatch(r"v\d+\.\d+", version):
        logger.error("Configuracion de WhatsApp invalida")
        return None
    return token, numero, plantilla, version


def despachar_notificaciones(ids):
    configuracion = configuracion_whatsapp()
    if not configuracion:
        return

    token, numero, plantilla, version = configuracion
    url = f"https://graph.facebook.com/{version}/{numero}/messages"
    for notificacion_id in ids:
        with transaction.atomic():
            notificacion = (
                NotificacionWhatsApp.objects.select_for_update()
                .select_related("registro__alumno", "tutor")
                .filter(pk=notificacion_id)
                .first()
            )
            if not notificacion or notificacion.estado == NotificacionWhatsApp.Estado.ENVIADA:
                continue
            if (not notificacion.tutor.activo or not notificacion.tutor.recibe_notificaciones
                    or not notificacion.registro.alumno.tutores.filter(pk=notificacion.tutor_id).exists()):
                notificacion.estado = NotificacionWhatsApp.Estado.FALLIDA
                notificacion.respuesta_proveedor = "Avisos no autorizados para este tutor."
                notificacion.save(update_fields=["estado", "respuesta_proveedor", "actualizado_en"])
                continue

            registro = notificacion.registro
            contenido = {
                "messaging_product": "whatsapp",
                "to": notificacion.telefono_destino,
                "type": "template",
                "template": {
                    "name": plantilla,
                    "language": {"code": settings.WHATSAPP_TEMPLATE_LANGUAGE},
                    "components": [{
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": notificacion.tutor.nombre},
                            {"type": "text", "text": registro.alumno.nombre_completo},
                            {"type": "text", "text": registro.fecha.strftime("%d/%m/%Y")},
                        ],
                    }],
                },
            }
            solicitud = Request(
                url,
                data=json.dumps(contenido).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with urlopen(solicitud, timeout=5) as respuesta:
                    resultado = json.load(respuesta)
                mensaje_id = resultado["messages"][0]["id"]
            except HTTPError as error:
                notificacion.estado = NotificacionWhatsApp.Estado.FALLIDA
                notificacion.respuesta_proveedor = f"Meta respondio HTTP {error.code}."
            except (URLError, TimeoutError, OSError, ValueError, KeyError, IndexError, TypeError):
                notificacion.estado = NotificacionWhatsApp.Estado.FALLIDA
                notificacion.respuesta_proveedor = "No se pudo confirmar el envio con Meta."
            else:
                notificacion.estado = NotificacionWhatsApp.Estado.ENVIADA
                notificacion.enviado_en = timezone.now()
                notificacion.respuesta_proveedor = mensaje_id
            notificacion.save(update_fields=[
                "estado", "enviado_en", "respuesta_proveedor", "actualizado_en",
            ])
