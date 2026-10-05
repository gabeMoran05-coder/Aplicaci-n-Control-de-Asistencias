# Aplicacion Control de Asistencias

Sistema web para registrar asistencias escolares por alumno, grado y grupo.

## Funciones base

- Catalogo de ciclos escolares, grados y grupos.
- Registro de alumnos con matricula, grupo, tutores, codigo QR y codigo NFC.
- Registro de entrada y salida por fecha y hora.
- Estado de asistencia: a tiempo, retardo, justificado o manual.
- Pantalla kiosco para pared con lectura automatica NFC / QR.`r`n- Panel semanal de lunes a viernes por grupo, con colores para asistencia, retardo, justificado y ausencia.
- Cola de notificaciones de WhatsApp para avisar a los tutores cuando se registre una asistencia.
- Panel administrativo de Django para gestionar los datos iniciales.

## Instalacion local

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py inicializar_grupos
python manage.py createsuperuser
python manage.py runserver
```

Despues entra a:

```text
http://127.0.0.1:8000/admin/
```

## Panel de control

El panel para directivos o prefectos esta en:

`	ext
http://127.0.0.1:8000/control/
` 

Muestra alumnos por grado y grupo. Al entrar al perfil de un alumno se ve su calendario mensual con colores para presente, retardo, justificado y ausente.

## Prefectura

La pantalla para registrar entradas automaticamente esta en:

```text
http://127.0.0.1:8000/prefectos/
```

Requiere iniciar sesion con una cuenta del grupo `Prefectos`. Permite escanear QR con la camara del telefono o usar lectores NFC/QR configurados como teclado. El calendario del alumno muestra quien registro la entrada y quien la ajusto despues.

En Safari se puede abrir `/prefectos/` y usar Compartir > Agregar a pantalla de inicio. La camara requiere HTTPS o localhost. Solo la primera lectura del dia crea asistencia; los escaneos repetidos no cambian al prefecto responsable.

Los grados se distinguen por color: primero amarillo, segundo rojo y tercero azul.

## Reporte de ausencias

Las cuentas de Prefectura y administracion pueden abrir `/control/ausencias/`, elegir fecha, grado y grupo, e imprimir o guardar el reporte como PDF desde el navegador. El documento muestra cantidades y nombres por salon. Las faltas capturadas se separan de los alumnos sin registro; estos ultimos requieren verificacion y no se cuentan como faltas confirmadas.

## Importar lista escolar

Para cargar la lista oficial de 1ro A del ciclo 2026-2027 desde un PDF local:

```bash
python manage.py importar_lista_asistencia "ruta/al/archivo.pdf" --ciclo 2026-2027 --grado 1 --grupo A
```

El comando valida el encabezado y la numeracion consecutiva del documento. Usa el numero de control como matricula, crea un QR unico por alumno y no sobrescribe registros ya existentes. El PDF original no se guarda en el repositorio.

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


