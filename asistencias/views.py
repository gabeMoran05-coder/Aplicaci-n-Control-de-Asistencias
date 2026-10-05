import calendar
import json
from functools import wraps
from io import BytesIO
from datetime import date, datetime, timedelta

from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError
from django.db.models import Q
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .models import Alumno, Grupo, NotificacionWhatsApp, RegistroAsistencia


GRADOS_CONTROL = [
    {"orden": 1, "nombre": "1ro"},
    {"orden": 2, "nombre": "2do"},
    {"orden": 3, "nombre": "3ro"},
]
GRUPOS_CONTROL = ["A", "B", "C", "D"]
PREFECTOS_GROUP = "Prefectos"
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


def es_prefecto(user):
    return user.is_authenticated and user.groups.filter(name=PREFECTOS_GROUP).exists()


def prefecto_required(view):
    @login_required(login_url="asistencias:prefecto_login")
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not es_prefecto(request.user):
            raise PermissionDenied("Esta cuenta no tiene acceso a Prefectura.")
        return view(request, *args, **kwargs)

    return wrapped


def reporte_required(view):
    @login_required(login_url="asistencias:prefecto_login")
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not (request.user.is_staff or es_prefecto(request.user)):
            raise PermissionDenied("Esta cuenta no tiene acceso a reportes escolares.")
        return view(request, *args, **kwargs)

    return wrapped


class PrefectoLoginView(LoginView):
    template_name = "registration/login.html"
    next_page = "/prefectos/"

    def form_valid(self, form):
        if not es_prefecto(form.get_user()):
            form.add_error(None, "Esta cuenta no tiene acceso a Prefectura.")
            return self.form_invalid(form)
        return super().form_valid(form)


@require_GET
def prefecto_manifest(request):
    return JsonResponse(
        {
            "name": "AsisteEscolar Prefectura",
            "short_name": "Prefectura",
            "start_url": reverse("asistencias:prefectos"),
            "scope": "/prefectos/",
            "display": "standalone",
            "background_color": "#f7f9fc",
            "theme_color": "#1177ad",
            "icons": [
                {
                    "src": staticfiles_storage.url("asistencias/prefectura-icon.png"),
                    "sizes": "192x192",
                    "type": "image/png",
                    "purpose": "any maskable",
                },
                {
                    "src": staticfiles_storage.url("asistencias/prefectura-icon-512.png"),
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "any maskable",
                },
            ],
        },
        content_type="application/manifest+json",
    )


@prefecto_required
@ensure_csrf_cookie
def profesor_escaner(request):
    return render(
        request,
        "asistencias/kiosco_asistencia.html",
        {"prefecto_nombre": request.user.get_full_name() or request.user.username},
    )


def control_semanal(request):
    ordenes_grado = [grado["orden"] for grado in GRADOS_CONTROL]
    hoy = timezone.localdate()
    grupos = list(
        Grupo.objects.select_related("grado", "ciclo_escolar")
        .filter(
            activo=True, grado__orden__in=ordenes_grado, nombre__in=GRUPOS_CONTROL,
            ciclo_escolar__fecha_inicio__lte=hoy, ciclo_escolar__fecha_fin__gte=hoy,
        )
        .order_by("grado__orden", "nombre")
    )
    filtro_grado = request.GET.get("grado") or ""
    filtro_grupo = request.GET.get("grupo") or ""
    filtro_edad = request.GET.get("edad") or ""
    busqueda = (request.GET.get("q") or "").strip()

    alumnos = (
        Alumno.objects.select_related("grupo", "grupo__grado", "grupo__ciclo_escolar")
        .filter(
            activo=True,
            grupo__grado__orden__in=ordenes_grado,
            grupo__nombre__in=GRUPOS_CONTROL,
            grupo__ciclo_escolar__fecha_inicio__lte=hoy,
            grupo__ciclo_escolar__fecha_fin__gte=hoy,
        )
        .order_by("apellido_paterno", "apellido_materno", "nombres")
    )
    if filtro_grado:
        alumnos = alumnos.filter(grupo__grado_id=filtro_grado)
    if filtro_grupo:
        alumnos = alumnos.filter(grupo__nombre=filtro_grupo)
    if busqueda:
        alumnos = alumnos.filter(
            Q(nombres__icontains=busqueda)
            | Q(apellido_paterno__icontains=busqueda)
            | Q(apellido_materno__icontains=busqueda)
            | Q(matricula__icontains=busqueda)
        )

    alumnos_tabla = list(alumnos)
    if filtro_edad:
        try:
            edad = int(filtro_edad)
        except ValueError:
            edad = None
        if edad is not None:
            alumnos_tabla = [alumno for alumno in alumnos_tabla if alumno.edad == edad]

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
        "total_grupos": len({(grupo.grado.orden, grupo.nombre) for grupo in grupos}),
        "asistencias_hoy": RegistroAsistencia.objects.filter(
            fecha=timezone.localdate(),
            tipo=RegistroAsistencia.TipoRegistro.ENTRADA,
            alumno__grupo__grado__orden__in=ordenes_grado,
            alumno__grupo__nombre__in=GRUPOS_CONTROL,
            alumno__grupo__ciclo_escolar__fecha_inicio__lte=hoy,
            alumno__grupo__ciclo_escolar__fecha_fin__gte=hoy,
        ).count(),
        "notificaciones_pendientes": NotificacionWhatsApp.objects.filter(
            estado=NotificacionWhatsApp.Estado.PENDIENTE,
        ).count(),
        "hoy": timezone.localdate(),
        "alumnos_tabla": alumnos_tabla,
        "grupos": grupos,
        "letras_grupo": GRUPOS_CONTROL,
        "grados": sorted({grupo.grado for grupo in grupos}, key=lambda grado: grado.orden),
        "filtros": {
            "grado": filtro_grado,
            "grupo": filtro_grupo,
            "edad": filtro_edad,
            "q": busqueda,
        },
        "can_view_reports": request.user.is_authenticated
        and (request.user.is_staff or es_prefecto(request.user)),
    }
    return render(request, "asistencias/control_semanal.html", contexto)


@reporte_required
@require_GET
def reporte_ausencias(request):
    fecha_texto = request.GET.get("fecha") or timezone.localdate().isoformat()
    try:
        fecha = date.fromisoformat(fecha_texto)
    except ValueError:
        return HttpResponse("Fecha inválida. Usa el formato AAAA-MM-DD.", status=400)
    if fecha > timezone.localdate():
        return HttpResponse("No se pueden consultar fechas futuras.", status=400)

    grupos = list(
        Grupo.objects.select_related("grado", "ciclo_escolar")
        .filter(
            activo=True,
            grado__orden__in=[1, 2, 3],
            nombre__in=GRUPOS_CONTROL,
            ciclo_escolar__fecha_inicio__lte=fecha,
            ciclo_escolar__fecha_fin__gte=fecha,
        )
        .order_by("grado__orden", "nombre")
    )
    grado_filtro = request.GET.get("grado") or ""
    grupo_filtro = request.GET.get("grupo") or ""
    if grado_filtro in {"1", "2", "3"}:
        grupos = [grupo for grupo in grupos if grupo.grado.orden == int(grado_filtro)]
    if grupo_filtro in GRUPOS_CONTROL:
        grupos = [grupo for grupo in grupos if grupo.nombre == grupo_filtro]

    alumnos_por_grupo = _alumnos_por_grupo(grupos)
    registros = RegistroAsistencia.objects.filter(
        alumno__grupo__in=grupos,
        alumno__activo=True,
        fecha=fecha,
        tipo=RegistroAsistencia.TipoRegistro.ENTRADA,
    )
    registros_por_alumno = {registro.alumno_id: registro for registro in registros}
    totales = {"alumnos": 0, "presentes": 0, "retardos": 0, "justificados": 0,
               "faltas": 0, "sin_registro": 0}
    secciones = []
    for grupo in grupos:
        alumnos = alumnos_por_grupo.get(grupo.id, [])
        seccion = {"grupo": grupo, "total": len(alumnos), "presentes": 0,
                   "retardos": 0, "justificados": 0, "faltas": [], "sin_registro": []}
        totales["alumnos"] += len(alumnos)
        for alumno in alumnos:
            registro = registros_por_alumno.get(alumno.id)
            if registro is None:
                seccion["sin_registro"].append(alumno)
                totales["sin_registro"] += 1
            elif registro.estado == RegistroAsistencia.Estado.AUSENTE:
                seccion["faltas"].append(alumno)
                totales["faltas"] += 1
            elif registro.estado == RegistroAsistencia.Estado.RETARDO:
                seccion["retardos"] += 1
                totales["retardos"] += 1
            elif registro.estado == RegistroAsistencia.Estado.JUSTIFICADO:
                seccion["justificados"] += 1
                totales["justificados"] += 1
            else:
                seccion["presentes"] += 1
                totales["presentes"] += 1
        secciones.append(seccion)

    return render(request, "asistencias/reporte_ausencias.html", {
        "fecha": fecha,
        "hoy": timezone.localdate(),
        "es_fin_semana": fecha.weekday() >= 5,
        "grado_filtro": grado_filtro,
        "grupo_filtro": grupo_filtro,
        "grados": GRADOS_CONTROL,
        "letras_grupo": GRUPOS_CONTROL,
        "secciones": secciones,
        "totales": totales,
        "generado_por": request.user.get_full_name() or request.user.username,
        "generado_en": timezone.localtime(),
    })


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

    registros_mes = RegistroAsistencia.objects.select_related(
        "registrado_por", "modificado_por"
    ).filter(
        alumno=alumno,
        tipo=RegistroAsistencia.TipoRegistro.ENTRADA,
        fecha__range=(mes_inicio, mes_fin),
    ).order_by("fecha")
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
        "can_manage_attendance": es_prefecto(request.user),
        "tutores": alumno.tutores.filter(activo=True).order_by("parentesco", "nombre"),
        "calendario": calendario,
        "dias_calendario": DIAS_CALENDARIO,
        "mes_inicio": mes_inicio,
        "mes_nombre": MESES[mes_inicio.month - 1],
        "mes_anterior": _sumar_meses(mes_inicio, -1),
        "mes_siguiente": _sumar_meses(mes_inicio, 1),
        "resumen": resumen,
        "detalles_mes": registros_mes,
        "hoy": hoy,
    }
    return render(request, "asistencias/perfil_alumno.html", contexto)


def alumno_publico(request, codigo):
    alumno = get_object_or_404(
        Alumno.objects.select_related("grupo", "grupo__grado", "grupo__ciclo_escolar"),
        codigo_qr=codigo,
        activo=True,
    )
    return perfil_alumno(request, alumno.id)


def credencial_alumno(request, alumno_id):
    alumno = get_object_or_404(
        Alumno.objects.select_related("grupo", "grupo__grado", "grupo__ciclo_escolar"),
        pk=alumno_id,
        activo=True,
    )
    tutores = alumno.tutores.filter(activo=True).order_by("parentesco", "nombre")
    return render(
        request,
        "asistencias/credencial_alumno.html",
        {"alumno": alumno, "tutores": tutores, "hoy": timezone.localdate()},
    )


def qr_alumno(request, alumno_id):
    alumno = get_object_or_404(Alumno, pk=alumno_id, activo=True)
    contenido = request.build_absolute_uri(
        reverse("asistencias:alumno_publico", args=[alumno.codigo_qr])
    )

    try:
        import qrcode
        from qrcode.image.svg import SvgPathImage
    except ImportError:
        return HttpResponse(
            "Instala la dependencia qrcode para generar imagenes QR.",
            status=503,
            content_type="text/plain",
        )

    imagen = qrcode.make(contenido, image_factory=SvgPathImage, box_size=12)
    salida = BytesIO()
    imagen.save(salida)
    return HttpResponse(salida.getvalue(), content_type="image/svg+xml")


@require_POST
@prefecto_required
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

    registro, creado = RegistroAsistencia.objects.get_or_create(
        alumno=alumno,
        fecha=fecha,
        tipo=RegistroAsistencia.TipoRegistro.ENTRADA,
        defaults={
            "hora": timezone.localtime(),
            "estado": estado,
            "registrado_por": request.user,
            "observaciones": "Registro manual desde perfil de alumno.",
        },
    )
    if not creado:
        registro.estado = estado
        registro.modificado_por = request.user
        registro.observaciones = "Asistencia ajustada manualmente."
        registro.save(update_fields=["estado", "modificado_por", "observaciones", "actualizado_en"])

    if creado and estado != RegistroAsistencia.Estado.AUSENTE:
        _crear_notificaciones_whatsapp(registro)

    return HttpResponseRedirect(_destino_post(request, alumno, fecha))


@require_POST
@prefecto_required
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
@prefecto_required
def registrar_asistencia_prefecto(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "mensaje": "Lectura invalida."}, status=400)

    codigo = _normalizar_codigo(payload.get("codigo") or "")
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
                "registrado_por": request.user,
                "observaciones": "Escaneo de credencial por prefectura.",
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
            "alumno_id": alumno.id,
            "hora": registro.hora.strftime("%H:%M"),
            "fecha": registro.fecha.strftime("%d/%m/%Y"),
            "grado_orden": alumno.grupo.grado.orden,
            "prefecto": (
                registro.registrado_por.get_full_name() or registro.registrado_por.username
                if registro.registrado_por else "No consta"
            ),
        }
    )


def _normalizar_codigo(valor):
    codigo = valor.strip()
    if not codigo:
        return ""
    partes = codigo.rstrip("/").split("/")
    if "q" in partes:
        indice = partes.index("q")
        if indice + 1 < len(partes):
            return partes[indice + 1]
    return codigo


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
    registros = RegistroAsistencia.objects.select_related(
        "registrado_por", "modificado_por"
    ).filter(
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
        "tiene_registro": registro is not None,
        "responsable": (
            registro.registrado_por.get_full_name() or registro.registrado_por.username
            if registro and registro.registrado_por else "No consta"
        ),
        "ajustado_por": (
            registro.modificado_por.get_full_name() or registro.modificado_por.username
            if registro and registro.modificado_por else ""
        ),
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
