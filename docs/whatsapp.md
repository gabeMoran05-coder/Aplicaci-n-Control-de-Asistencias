# Avisos de asistencia por WhatsApp

La asistencia se guarda aunque Meta no responda. Los avisos se crean solo para
madres y padres activos que tengan marcada la autorizacion en el perfil del
alumno. Un segundo escaneo del mismo dia no crea otro aviso.

## Preparacion en Meta

1. Configura WhatsApp Cloud API con un numero registrado y un token con permiso
   `whatsapp_business_messaging`.
2. La plantilla aprobada `asistencia_fmp` usa `es_MX` y **tres variables de
   texto en el cuerpo**, en este orden: nombre del tutor, nombre del alumno y
   fecha. La vista previa muestra un aviso de entrada a la escuela sin hora.

   Confirma en el editor de Meta que los marcadores `{{1}}`, `{{2}}`, `{{3}}`
   corresponden a ese orden antes de habilitar el envio.

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
| `WHATSAPP_TEMPLATE_NAME` | `asistencia_fmp` |
| `WHATSAPP_TEMPLATE_LANGUAGE` | `es_MX`, o el idioma exacto de la plantilla |
| `WHATSAPP_API_VERSION` | Version vigente de Graph API, por ejemplo `v26.0` |
| `WHATSAPP_DEFAULT_COUNTRY_CODE` | `52` para telefonos mexicanos de 10 digitos |

No pongas estos valores en GitHub. Sin `WHATSAPP_ENABLED=True` y las cuatro variables obligatorias
(`ACCESS_TOKEN`, `PHONE_NUMBER_ID`, `TEMPLATE_NAME`, `API_VERSION`), no se crean
avisos ni se intenta llamar a Meta. Tras configurarlas, los avisos nuevos se
envian al registrar la entrada. Los anteriores no se envian automaticamente
para evitar avisos tardios.

## Webhook de Meta (opcional para enviar avisos)

La URL de devolucion de llamada es
`https://fmp-control.onrender.com/webhooks/whatsapp/`. En **Render > FMP Control >
Environment**, crea `WHATSAPP_WEBHOOK_VERIFY_TOKEN` con un valor aleatorio largo y
`WHATSAPP_APP_SECRET` con la clave secreta de la app de Meta. No publiques ninguno
en GitHub, capturas ni mensajes. En **Meta > Configurar webhooks**, pega la URL y
el mismo valor de `WHATSAPP_WEBHOOK_VERIFY_TOKEN` en **Token de verificacion**;
despues pulsa **Verificar y guardar**. La app de Django debe haber terminado de
desplegarse y las variables deben estar guardadas antes de verificar.

El webhook comprueba la firma de los eventos entrantes y los confirma, pero
todavia no procesa respuestas ni estados de entrega. No es necesario configurarlo
para el envio saliente de la plantilla de asistencia.
