# Avisos de asistencia por WhatsApp

La asistencia se guarda aunque Meta no responda. Los avisos se crean solo para
madres y padres activos que tengan marcada la autorizacion en el perfil del
alumno. Un segundo escaneo del mismo dia no crea otro aviso.

## Preparacion en Meta

1. Configura WhatsApp Cloud API con un numero registrado y un token con permiso
   `whatsapp_business_messaging`.
2. Crea y espera la aprobacion de una plantilla de utilidad en `es_MX` con
   **tres variables de texto en el cuerpo**, en este orden: nombre del alumno,
   fecha y hora. Ejemplo:

   `AsisteEscolar: {{1}} llego a la escuela el {{2}} a las {{3}}.`

3. Obten la autorizacion de cada padre o tutor antes de activar su casilla
   `Autoriza avisos por WhatsApp` en Editar alumno. No incluyas datos medicos.
   Revisa especialmente los tutores capturados antes de esta version: la casilla
   antigua podia quedar activada por defecto. La migracion cambia el valor para
   nuevos tutores, pero conserva los valores existentes.

## Variables privadas en Render

Configura estas variables en el servicio web, en **Environment**:

| Variable | Valor |
| --- | --- |
| `WHATSAPP_ENABLED` | `True` solo despues de revisar autorizaciones y plantilla |
| `WHATSAPP_ACCESS_TOKEN` | Token de acceso permanente de Meta |
| `WHATSAPP_PHONE_NUMBER_ID` | ID del numero de telefono de WhatsApp |
| `WHATSAPP_TEMPLATE_NAME` | Nombre exacto de la plantilla aprobada |
| `WHATSAPP_TEMPLATE_LANGUAGE` | `es_MX`, o el idioma exacto de la plantilla |
| `WHATSAPP_API_VERSION` | Version vigente de Graph API, por ejemplo `v26.0` |
| `WHATSAPP_DEFAULT_COUNTRY_CODE` | `52` para telefonos mexicanos de 10 digitos |

No pongas estos valores en GitHub. Sin `WHATSAPP_ENABLED=True` y las cuatro variables obligatorias
(`ACCESS_TOKEN`, `PHONE_NUMBER_ID`, `TEMPLATE_NAME`, `API_VERSION`), no se crean
avisos ni se intenta llamar a Meta. Tras configurarlas, los avisos nuevos se
envian al registrar la entrada. Los anteriores no se envian automaticamente
para evitar avisos tardios.
