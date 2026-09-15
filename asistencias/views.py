import calendar
import json
from datetime import date, datetime, timedelta

from django.db import IntegrityError
from django.db.models import Q
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Alumno, Grupo, NotificacionWhatsApp, RegistroAsistencia


GRADOS_CONTROL = [
    {"orden": 1, "nombre": "1ro"},
    {"orden": 2, "nombre": "2do"},
    {"orden": 3, "nombre": "3ro"},
]
GRUPOS_CONTROL = ["A", "B", "C", "D"]
MESES = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]
DIAS_CALENDARIO = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"]


def kiosco_asistencia(request):
    return render(request, "asistencias/kiosco_asistencia.html")


def control_semanal(request):
    grupos = list(
        Grupo.objects.select_related("grado", "ciclo_escolar")
        .filter(activo=True)
        .order_by("grado__orden", "nombre")
    )
    alumnos_por_grupo = _alumnos_por_grupo(grupos)
    tablero = []

    for grado in GRADOS_CONTROL:
        tarjetas = []
        for letra in GRUPOS_CONTROL:
            grupo = _buscar_grupo(grupos, grado["orden"], letra)
            alumnos = alumnos_por_grupo.get(grupo.id, []) if grupo else []
            tarjetas.append(
                {
                    "grado": grado,
                    "letra": letra,
                    "grupo": grupo,
                    "alumnos": alumnos,
                    "total": len(alumnos),
                }
            )
        tablero.append({"grado": grado, "tarjetas": tarjetas})

    contexto = {
        "tablero": tablero,
        "total_alumnos": sum(len(alumnos) for alumnos in alumnos_por_grupo.values()),
        "total_grupos": len(grupos),
        "hoy": timezone.localdate(),
    }
    return render(request, "asistencias/control_semanal.html", contexto)


def perfil_alumno(request, alumno_id):
    alumno = get_object_or_404(
        Alumno.objects.select_related("grupo", "grupo__grado", "grupo__ciclo_escolar"),
        pk=alumno_id,
        activo=True,
    )
    hoy = timezone.localdate()
    mes_inicio = _obtener_inicio_mes(request.GET.get("mes"), hoy)
    mes_fin = _ultimo_dia_mes(mes_inicio)
    calendario = _calendario_alumno(alumno, mes_inicio, mes_fin, hoy)

    registros_mes = RegistroAsistencia.objects.filter(
        alumno=alumno,
        tipo=RegistroAsistencia.TipoRegistro.ENTRADA,
        fecha__range=(mes_inicio, mes_fin),
    )
    resumen = {"presentes": 0, "retardos": 0, "justificados": 0, "ausentes": 0}
    for registro in registros_mes:
        estado = _estado_visual(registro.estado)
        if estado == "presente":
            resumen["presentes"] += 1
        elif estado == "retardo":
            resumen["retardos"] += 1
        elif estado == "justificado":
            resumen["justificados"] += 1
        elif estado == "ausente":
            resumen["ausentes"] += 1

    contexto = {
        "alumno": alumno,
        "calendario": calendario,
        "dias_calendario": DIAS_CALENDARIO,
        "mes_inicio": mes_inicio,
        "mes_nombre": MESES[mes_inicio.month - 1],
        "mes_anterior": _sumar_meses(mes_inicio, -1),
        "mes_siguiente": _sumar_meses(mes_inicio, 1),
        "resumen": resumen,
        "hoy": hoy,
    }
    return render(request, "asistencias/perfil_alumno.html", contexto)


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
            "observaciones": "Registro manual desde perfil de alumno.",
        },
    )

    if creado and estado != RegistroAsistencia.Estado.AUSENTE:
        _crear_notificaciones_whatsapp(registro)

    return HttpResponseRedirect(_destino_post(request, alumno, fecha))


@require_POST
def limpiar_asistencia_manual(request):
    alumno = get_object_or_404(Alumno, pk=request.POST.get("alumno_id"), activo=True)
    fecha = datetime.strptime(request.POST.get("fecha"), "%Y-%m-%d").date()
    RegistroAsistencia.objects.filter(
        alumno=alumno,
        fecha=fecha,
        tipo=RegistroAsistencia.TipoRegistro.ENTRADA,
    ).delete()

    return HttpResponseRedirect(_destino_post(request, alumno, fecha))


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


def _alumnos_por_grupo(grupos):
    resultado = {grupo.id: [] for grupo in grupos}
    alumnos = (
        Alumno.objects.select_related("grupo", "grupo__grado")
        .filter(grupo__in=grupos, activo=True)
        .order_by("apellido_paterno", "apellido_materno", "nombres")
    )
    for alumno in alumnos:
        resultado.setdefault(alumno.grupo_id, []).append(alumno)
    return resultado


def _buscar_grupo(grupos, grado_orden, letra):
    for grupo in grupos:
        if grupo.grado.orden == grado_orden and grupo.nombre.upper() == letra:
            return grupo
    return None


def _obtener_inicio_mes(valor, hoy):
    if valor:
        try:
            fecha = datetime.strptime(valor, "%Y-%m").date()
        except ValueError:
            fecha = hoy
    else:
        fecha = hoy
    return fecha.replace(day=1)


def _ultimo_dia_mes(mes_inicio):
    _, ultimo = calendar.monthrange(mes_inicio.year, mes_inicio.month)
    return mes_inicio.replace(day=ultimo)


def _sumar_meses(mes_inicio, cantidad):
    mes = mes_inicio.month - 1 + cantidad
    year = mes_inicio.year + mes // 12
    month = mes % 12 + 1
    return date(year, month, 1)


def _calendario_alumno(alumno, mes_inicio, mes_fin, hoy):
    registros = RegistroAsistencia.objects.filter(
        alumno=alumno,
        tipo=RegistroAsistencia.TipoRegistro.ENTRADA,
        fecha__range=(mes_inicio, mes_fin),
    )
    registros_por_fecha = {registro.fecha: registro for registro in registros}
    semanas = []

    for semana in calendar.Calendar(firstweekday=0).monthdatescalendar(
        mes_inicio.year, mes_inicio.month
    ):
        dias = []
        for dia in semana:
            fuera_mes = dia.month != mes_inicio.month
            registro = registros_por_fecha.get(dia)
            dias.append(_crear_dia_calendario(alumno, dia, registro, hoy, fuera_mes))
        semanas.append(dias)
    return semanas


def _crear_dia_calendario(alumno, dia, registro, hoy, fuera_mes):
    if fuera_mes:
        return {"fuera_mes": True, "fecha": dia}

    if registro:
        estado = _estado_visual(registro.estado)
        etiqueta = _etiqueta_estado(registro.estado)
        hora = registro.hora.strftime("%H:%M")
    elif dia > hoy:
        estado = "futuro"
        etiqueta = "Pendiente"
        hora = ""
    else:
        estado = "sin_marcar"
        etiqueta = "Sin marcar"
        hora = ""

    return {
        "fuera_mes": False,
        "alumno_id": alumno.id,
        "fecha": dia,
        "dia": dia.day,
        "estado": estado,
        "etiqueta": etiqueta,
        "hora": hora,
        "editable": dia <= hoy,
    }


def _destino_post(request, alumno, fecha):
    siguiente = request.POST.get("next") or ""
    if siguiente.startswith("/") and not siguiente.startswith("//"):
        return siguiente
    return reverse("asistencias:perfil_alumno", args=[alumno.id]) + f"?mes={fecha:%Y-%m}"


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
