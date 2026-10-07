# Aplicacion Control de Asistencias

Sistema web para registrar asistencias escolares por alumno, grado y grupo.

## Funciones base

- Catalogo de ciclos escolares, grados y grupos.
- Registro de alumnos con matricula, grupo, tutores, codigo QR y codigo NFC.
- Registro de entrada y salida por fecha y hora.
- Estado de asistencia: a tiempo, retardo, justificado o manual.
- Escaner de prefectura para registrar asistencia por QR o lector NFC.
- Calendario por alumno con colores para asistencia, retardo, justificado y ausencia.
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

El directorio y los reportes son privados para la cuenta del grupo `Direccion`:

```text
http://127.0.0.1:8000/control/
```

Muestra alumnos por grado y grupo. Al entrar al perfil de un alumno se ve su calendario mensual con colores para presente, retardo, justificado y ausente.
La sesion se cierra con el boton `Salir`. Los prefectos usan una cuenta distinta en `/prefectos/`; no pueden abrir el directorio. La consulta individual por QR solo muestra asistencia, sin datos medicos ni telefonos.

## Prefectura

La pantalla para registrar entradas automaticamente esta en:

```text
http://127.0.0.1:8000/prefectos/
```

Requiere iniciar sesion con una cuenta del grupo `Prefectos`. Permite escanear QR con la camara del telefono o usar lectores NFC/QR configurados como teclado. El calendario del alumno muestra quien registro la entrada y quien la ajusto despues.

En Safari se puede abrir `/prefectos/` y usar Compartir > Agregar a pantalla de inicio. La camara requiere HTTPS o localhost. Solo la primera lectura del dia crea asistencia; los escaneos repetidos no cambian al prefecto responsable.

Los grados se distinguen por color: primero amarillo, segundo rojo y tercero azul.

## Reporte de ausencias

La cuenta de Direccion puede abrir `/control/ausencias/`, elegir fecha, grado y grupo, e imprimir o guardar el reporte como PDF desde el navegador. El documento muestra cantidades y nombres por salon. Las faltas capturadas se separan de los alumnos sin registro; estos ultimos requieren verificacion y no se cuentan como faltas confirmadas.

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

- Crear pantalla para emitir/asociar credenciales NFC.
- Integrar WhatsApp Business Cloud API.

## Despliegue en Render

Usa un **Web Service** de Python 3 conectado a la rama `main`. Deja vacio Root Directory.

| Campo | Valor |
| --- | --- |
| Build Command | `bash render-build.sh` |
| Start Command | `bash render-start.sh` |
| Health Check Path | `/control/ingresar/` |

Crea antes una base **Render Postgres** en la misma region y configura estas variables
en el Web Service (nunca en GitHub):

| Variable | Valor |
| --- | --- |
| `DATABASE_URL` | URL interna de la base Postgres |
| `DJANGO_SECRET_KEY` | Clave aleatoria larga, generada en Render |
| `DJANGO_BOOTSTRAP_USERNAME` | Usuario inicial de Direccion |
| `DJANGO_BOOTSTRAP_PASSWORD` | Contrasena inicial de al menos 12 caracteres |

El comando de arranque aplica migraciones, crea los 12 grupos y la primera cuenta
de Direccion. Solo crea esa cuenta una vez; no restablece su contrasena en despliegues
posteriores. Despues del primer acceso se pueden retirar las dos variables
`DJANGO_BOOTSTRAP_*`.

La base SQLite, las listas de alumnos, las fotos y los CSV de credenciales locales
**no se suben a GitHub**. La base nueva en Render estara vacia hasta importar los
alumnos de forma privada. No subas la base de datos ni PDFs con datos de menores al
repositorio. Render Free pierde las fotos guardadas en el disco local al reiniciar
o redesplegar; para usarlas con datos reales configura almacenamiento persistente
(por ejemplo, un disco de pago montado en `/var/data` con
`DJANGO_MEDIA_ROOT=/var/data/media`) o almacenamiento privado externo. La base
Postgres gratuita de Render tiene caducidad; revisa el plan antes de usarla en la
escuela.

Si Auto-Deploy esta activado en Render, cada `git push` a `main` construye y
despliega la nueva version. Antes de publicar cambios de modelos, crea y prueba
las migraciones localmente.


