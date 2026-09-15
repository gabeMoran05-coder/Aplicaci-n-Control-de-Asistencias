import json
from datetime import datetime, timedelta

from django.db import IntegrityError
from django.db.models import Q
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Alumno, Grupo, NotificacionWhatsApp, RegistroAsistencia


DIAS_SEMANA = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes"]


def kiosco_asistencia(request):
    return render(request, "asistencias/kiosco_asistencia.html")


def control_semanal(request):
    hoy = timezone.localdate()
    semana_inicio = _obtener_inicio_semana(request.GET.get("semana"), hoy)
    semana_fin = semana_inicio + timedelta(days=4)
    dias = [semana_inicio + timedelta(days=i) for i in range(5)]

    grupos = Grupo.objects.select_related("grado", "ciclo_escolar").filter(activo=True)
    grupo_id = request.GET.get("grupo")
    grupo = None
    if grupo_id:
        grupo = get_object_or_404(grupos, pk=grupo_id)
    else:
        grupo = grupos.first()

    alumnos = Alumno.objects.none()
    filas = []
    resumen = {"presentes": 0, "retardos": 0, "justificados": 0, "ausentes": 0}

    if grupo:
        alumnos = grupo.alumnos.filter(activo=True).order_by(
            "apellido_paterno", "apellido_materno", "nombres"
        )
        registros = RegistroAsistencia.objects.filter(
            alumno__in=alumnos,
            tipo=RegistroAsistencia.TipoRegistro.ENTRADA,
            fecha__range=(semana_inicio, semana_fin),
        )
        registros_por_alumno_fecha = {
            (registro.alumno_id, registro.fecha): registro for registro in registros
        }

        for alumno in alumnos:
            celdas = []
            for dia in dias:
                registro = registros_por_alumno_fecha.get((alumno.id, dia))
                celda = _crear_celda_control(alumno, dia, registro, hoy)
                if celda["estado"] == "presente":
                    resumen["presentes"] += 1
                elif celda["estado"] == "retardo":
                    resumen["retardos"] += 1
                elif celda["estado"] == "justificado":
                    resumen["justificados"] += 1
                elif celda["estado"] == "ausente":
                    resumen["ausentes"] += 1
                celdas.append(celda)
            filas.append({"alumno": alumno, "celdas": celdas})

    contexto = {
        "grupos": grupos,
        "grupo": grupo,
        "dias": zip(DIAS_SEMANA, dias),
        "filas": filas,
        "semana_inicio": semana_inicio,
        "semana_fin": semana_fin,
        "semana_anterior": semana_inicio - timedelta(days=7),
        "semana_siguiente": semana_inicio + timedelta(days=7),
        "hoy": hoy,
        "resumen": resumen,
    }
    return render(request, "asistencias/control_semanal.html", contexto)


@require_POST
def marcar_asistencia_manual(request):
    alumno = get_object_or_404(Alumno, pk=request.POST.get("alumno_id"), activo=True)
    fecha = datetime.strptime(request.POST.get("fecha"), "%Y-%m-%d").date()
    estado = request.POST.get("estado")

    estados_permitidos = {
        RegistroAsistencia.Estado.A_TIEMPO,
        RegistroAsistencia.Estado.RETARDO,
        RegistroAsistencia.Estado.JUSTIFICADO,
        RegistroAsistencia.Estado.AUSENTE,
    }
    if estado not in estados_permitidos:
        estado = RegistroAsistencia.Estado.A_TIEMPO

    registro, creado = RegistroAsistencia.objects.update_or_create(
        alumno=alumno,
        fecha=fecha,
        tipo=RegistroAsistencia.TipoRegistro.ENTRADA,
        defaults={
            "hora": timezone.localtime(),
            "estado": estado,
            "registrado_por": request.user if request.user.is_authenticated else None,
            "observaciones": "Registro manual desde control semanal.",
        },
    )

    if creado and estado != RegistroAsistencia.Estado.AUSENTE:
        _crear_notificaciones_whatsapp(registro)

    url = reverse("asistencias:control")
    query = f"?grupo={alumno.grupo_id}&semana={_inicio_semana(fecha).isoformat()}"
    return HttpResponseRedirect(url + query)


@require_POST
def limpiar_asistencia_manual(request):
    alumno = get_object_or_404(Alumno, pk=request.POST.get("alumno_id"), activo=True)
    fecha = datetime.strptime(request.POST.get("fecha"), "%Y-%m-%d").date()
    RegistroAsistencia.objects.filter(
        alumno=alumno,
        fecha=fecha,
        tipo=RegistroAsistencia.TipoRegistro.ENTRADA,
    ).delete()

    url = reverse("asistencias:control")
    query = f"?grupo={alumno.grupo_id}&semana={_inicio_semana(fecha).isoformat()}"
    return HttpResponseRedirect(url + query)


@require_POST
def registrar_asistencia_kiosco(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "mensaje": "Lectura invalida."}, status=400)

    codigo = (payload.get("codigo") or "").strip()
    if not codigo:
        return JsonResponse({"ok": False, "mensaje": "Codigo vacio."}, status=400)

    alumno = (
        Alumno.objects.select_related("grupo", "grupo__grado")
        .filter(Q(codigo_qr=codigo) | Q(codigo_nfc=codigo), activo=True)
        .first()
    )
    if alumno is None:
        return JsonResponse(
            {
                "ok": False,
                "tipo": "desconocido",
                "mensaje": "Credencial no registrada",
                "codigo": codigo,
            },
            status=404,
        )

    hoy = timezone.localdate()
    ahora = timezone.localtime()

    try:
        registro, creado = RegistroAsistencia.objects.get_or_create(
            alumno=alumno,
            fecha=hoy,
            tipo=RegistroAsistencia.TipoRegistro.ENTRADA,
            defaults={
                "hora": ahora,
                "estado": RegistroAsistencia.Estado.A_TIEMPO,
                "observaciones": "Registro automatico desde kiosco.",
            },
        )
    except IntegrityError:
        registro = RegistroAsistencia.objects.get(
            alumno=alumno,
            fecha=hoy,
            tipo=RegistroAsistencia.TipoRegistro.ENTRADA,
        )
        creado = False

    if creado:
        _crear_notificaciones_whatsapp(registro)

    return JsonResponse(
        {
            "ok": True,
            "tipo": "registrado" if creado else "repetido",
            "mensaje": "Entrada registrada" if creado else "Entrada ya registrada hoy",
            "alumno": alumno.nombre_completo,
            "grupo": str(alumno.grupo),
            "hora": registro.hora.strftime("%H:%M"),
            "fecha": registro.fecha.strftime("%d/%m/%Y"),
        }
    )


def _obtener_inicio_semana(valor, hoy):
    if valor:
        try:
            fecha = datetime.strptime(valor, "%Y-%m-%d").date()
        except ValueError:
            fecha = hoy
    else:
        fecha = hoy
    return _inicio_semana(fecha)


def _inicio_semana(fecha):
    return fecha - timedelta(days=fecha.weekday())


def _crear_celda_control(alumno, dia, registro, hoy):
    if registro:
        estado = _estado_visual(registro.estado)
        return {
            "alumno_id": alumno.id,
            "fecha": dia,
            "estado": estado,
            "etiqueta": _etiqueta_estado(registro.estado),
            "hora": registro.hora.strftime("%H:%M"),
            "editable": dia <= hoy,
        }

    if dia > hoy:
        estado = "futuro"
        etiqueta = "Pendiente"
    else:
        estado = "sin_marcar"
        etiqueta = "Sin marcar"

    return {
        "alumno_id": alumno.id,
        "fecha": dia,
        "estado": estado,
        "etiqueta": etiqueta,
        "hora": "",
        "editable": dia <= hoy,
    }


def _estado_visual(estado):
    if estado == RegistroAsistencia.Estado.RETARDO:
        return "retardo"
    if estado == RegistroAsistencia.Estado.JUSTIFICADO:
        return "justificado"
    if estado == RegistroAsistencia.Estado.AUSENTE:
        return "ausente"
    return "presente"


def _etiqueta_estado(estado):
    etiquetas = {
        RegistroAsistencia.Estado.A_TIEMPO: "Asistio",
        RegistroAsistencia.Estado.RETARDO: "Retardo",
        RegistroAsistencia.Estado.JUSTIFICADO: "Justificado",
        RegistroAsistencia.Estado.AUSENTE: "Ausente",
        RegistroAsistencia.Estado.MANUAL: "Manual",
    }
    return etiquetas.get(estado, "Asistio")


def _crear_notificaciones_whatsapp(registro):
    alumno = registro.alumno
    mensaje = (
        f"Hola, le informamos que {alumno.nombre_completo} llego a la escuela "
        f"el {registro.fecha.strftime('%d/%m/%Y')} a las {registro.hora.strftime('%H:%M')}."
    )

    notificaciones = []
    for tutor in alumno.tutores.filter(activo=True, recibe_notificaciones=True):
        notificaciones.append(
            NotificacionWhatsApp(
                registro=registro,
                tutor=tutor,
                telefono_destino=tutor.telefono_whatsapp,
                mensaje=mensaje,
            )
        )

    if notificaciones:
        NotificacionWhatsApp.objects.bulk_create(notificaciones)
