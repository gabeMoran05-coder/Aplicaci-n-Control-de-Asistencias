# Aplicacion Control de Asistencias

Sistema web para registrar asistencias escolares por alumno, grado y grupo.

## Funciones base

- Catalogo de ciclos escolares, grados y grupos.
- Registro de alumnos con matricula, grupo, tutores, codigo QR y codigo NFC.
- Registro de entrada y salida por fecha y hora.
- Estado de asistencia: a tiempo, retardo, justificado o manual.
- Pantalla kiosco para pared con lectura automatica NFC / QR.
- Cola de notificaciones de WhatsApp para avisar a los tutores cuando se registre una asistencia.
- Panel administrativo de Django para gestionar los datos iniciales.

## Instalacion local

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Despues entra a:

```text
http://127.0.0.1:8000/admin/
```

## Pantalla kiosco

La pantalla para registrar entradas automaticamente esta en:

```text
http://127.0.0.1:8000/kiosco/
```

Funciona con lectores NFC o QR configurados en modo teclado. El lector debe enviar el codigo de la credencial y terminar con Enter.

Para usarla desde otra computadora o telefono de la misma red, ejecuta Django escuchando en toda la red:

```bash
python manage.py runserver 0.0.0.0:8000
```

Y configura `DJANGO_ALLOWED_HOSTS` con la IP local de la computadora que corre el sistema.

## Siguiente etapa

- Generar QR por alumno automaticamente.
- Crear pantalla para emitir/asociar credenciales NFC.
- Crear dashboard diario por grado y grupo.
- Integrar WhatsApp Business Cloud API.
