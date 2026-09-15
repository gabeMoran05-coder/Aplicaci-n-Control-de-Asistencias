# Aplicacion Control de Asistencias

Sistema web para registrar asistencias escolares por alumno, grado y grupo.

## Funciones base

- Catalogo de ciclos escolares, grados y grupos.
- Registro de alumnos con matricula, grupo, tutores y codigo QR.
- Registro de entrada y salida por fecha y hora.
- Estado de asistencia: a tiempo, retardo, justificado o manual.
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

## Siguiente etapa

- Crear pantalla de escaneo QR.
- Crear dashboard diario por grado y grupo.
- Generar QR por alumno automaticamente.
- Integrar WhatsApp Business Cloud API.
