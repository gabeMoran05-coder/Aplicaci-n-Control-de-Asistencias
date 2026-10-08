import calendar
import json
import mimetypes
import secrets
from uuid import uuid4
from functools import wraps
from io import BytesIO
from datetime import date, datetime, timedelta

from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib import messages
from django.contrib.auth.views import LoginView, redirect_to_login
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.http import FileResponse, Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from .forms import AlumnoAltaForm, AlumnoEditarForm, CicloNuevoForm, EventoEscolarForm, ListaPDFForm, PrefectoCuentaForm
from .cuentas import emitir_acceso
from .ciclos import crear_ciclo_y_promover
from .listas import extraer_lista_pdf
from .models import Alumno, CicloEscolar, CuentaAlumno, DiaEscolar, EventoEscolar, Grupo, Inscripcion, NotificacionWhatsApp, RegistroAsistencia, Tutor


GRADOS_CONTROL = [
    {"orden": 1, "nombre": "1ro"},
    {"orden": 2, "nombre": "2do"},
    {"orden": 3, "nombre": "3ro"},
]
GRUPOS_CONTROL = ["A", "B", "C", "D"]
PREFECTOS_GROUP = "Prefectos"
DIRECCION_GROUP = "Direccion"
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
    return user.is_authenticated and user.is_active and user.groups.filter(name=PREFECTOS_GROUP).exists()


def es_direccion(user):
    return user.is_authenticated and user.is_active and user.groups.filter(name=DIRECCION_GROUP).exists()


def es_operador_escaneo(user):
    return es_prefecto(user) or es_direccion(user)


def direccion_required(view):
    @login_required(login_url="asistencias:direccion_login")
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not es_direccion(request.user):
            raise PermissionDenied("Esta cuenta no tiene acceso a Dirección.")
        return view(request, *args, **kwargs)

    return wrapped


def prefecto_required(view):
    @login_required(login_url="asistencias:prefecto_login")
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not es_prefecto(request.user):
            if request.method == "GET" and es_direccion(request.user):
                return redirect("asistencias:prefecto_login")
            raise PermissionDenied("Esta cuenta no tiene acceso a Prefectura.")
        return view(request, *args, **kwargs)

    return wrapped


def escaneo_required(view):
    @login_required(login_url="asistencias:prefecto_login")
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not es_operador_escaneo(request.user):
            raise PermissionDenied("Esta cuenta no tiene acceso al escaner.")
        return view(request, *args, **kwargs)

    return wrapped


class DireccionLoginView(LoginView):
    template_name = "asistencias/direccion_login.html"
    next_page = "/control/"

    def form_valid(self, form):
        if not es_direccion(form.get_user()):
            form.add_error(None, "Esta cuenta no tiene acceso a Dirección.")
            return self.form_invalid(form)
        return super().form_valid(form)


class PrefectoLoginView(LoginView):
    template_name = "registration/login.html"
    next_page = "/prefectos/"

    def form_valid(self, form):
        if not es_operador_escaneo(form.get_user()):
            form.add_error(None, "Esta cuenta no tiene acceso al escaner.")
            return self.form_invalid(form)
        return super().form_valid(form)


class EstudianteLoginView(LoginView):
    template_name = "asistencias/estudiante_login.html"
    next_page = "/estudiantes/"

    def form_valid(self, form):
        if not CuentaAlumno.objects.filter(usuario=form.get_user(), alumno__activo=True).exists():
            form.add_error(None, "Esta cuenta no tiene acceso al portal de alumnos.")
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


@require_GET
def estudiante_manifest(request):
    return JsonResponse(
        {
            "name": "AsisteEscolar Alumnos",
            "short_name": "Mi asistencia",
            "start_url": reverse("asistencias:portal_alumno"),
            "scope": "/estudiantes/",
            "display": "standalone",
            "background_color": "#f6f8f9",
            "theme_color": "#1177ad",
            "icons": [
                {"src": staticfiles_storage.url("asistencias/prefectura-icon.png"), "sizes": "192x192", "type": "image/png"},
                {"src": staticfiles_storage.url("asistencias/prefectura-icon-512.png"), "sizes": "512x512", "type": "image/png"},
            ],
        },
        content_type="application/manifest+json",
    )


@direccion_required
@never_cache
def agregar_alumno(request):
    form = AlumnoAltaForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            alumno = form.save(commit=False)
            alumno.grupo = form.cleaned_data["grupo_destino"]
            alumno.codigo_qr = uuid4().hex
            alumno.save()
            Inscripcion.objects.create(
                alumno=alumno, ciclo_escolar=alumno.grupo.ciclo_escolar, grupo=alumno.grupo
            )
        acceso = emitir_acceso(alumno.pk)
        return render(request, "asistencias/agregar_alumno.html", {
            "form": AlumnoAltaForm(), "alumno_creado": alumno, "acceso": acceso,
            "active_section": "alumnos",
        })
    return render(request, "asistencias/agregar_alumno.html", {"form": form, "active_section": "alumnos"})


@direccion_required
@never_cache
def importar_lista(request):
    form = ListaPDFForm(request.POST or None, request.FILES or None)
    contexto = {"form": form, "active_section": "importar"}
    if request.method == "POST" and request.POST.get("accion") == "confirmar":
        try:
            datos = signing.loads(request.POST.get("vista_previa", ""), salt="importar-lista", max_age=600)
            if datos["usuario_id"] != request.user.pk or len(datos["filas"]) > 50:
                raise signing.BadSignature("Vista previa invalida")
            grupo = Grupo.objects.select_related("ciclo_escolar", "grado").get(
                pk=datos["grupo_id"], activo=True
            )
            filas = datos["filas"]
            if len({fila["matricula"] for fila in filas}) != len(filas):
                raise signing.BadSignature("Matriculas repetidas")
            existentes = {alumno.matricula: alumno for alumno in Alumno.objects.filter(
                matricula__in=[fila["matricula"] for fila in filas]
            )}
            conflictos = [fila["matricula"] for fila in filas if fila["matricula"] in existentes
                          and (existentes[fila["matricula"]].grupo_id != grupo.id
                               or not existentes[fila["matricula"]].activo)]
            if conflictos:
                raise ValueError("Hay matriculas que pertenecen a otro grupo o estan inactivas: " + ", ".join(conflictos))
            nuevos = []
            with transaction.atomic():
                for fila in filas:
                    alumno, creado = Alumno.objects.get_or_create(
                        matricula=fila["matricula"],
                        defaults={**fila, "grupo": grupo, "codigo_qr": uuid4().hex},
                    )
                    if alumno.grupo_id != grupo.id or not alumno.activo:
                        raise ValueError(f"La matricula {alumno.matricula} cambio de grupo. Revisa la lista.")
                    inscripcion, _ = Inscripcion.objects.get_or_create(
                        alumno=alumno, ciclo_escolar=grupo.ciclo_escolar, defaults={"grupo": grupo}
                    )
                    if inscripcion.grupo_id != grupo.id:
                        raise ValueError(f"La matricula {alumno.matricula} ya tiene otro grupo en este ciclo.")
                    if creado:
                        nuevos.append(alumno)
            accesos = [emitir_acceso(alumno.pk) for alumno in nuevos]
            contexto.update({"form": ListaPDFForm(), "resultado": {
                "grupo": grupo, "creados": len(nuevos), "existentes": len(filas) - len(nuevos),
            }, "accesos": accesos})
        except (signing.BadSignature, KeyError, Grupo.DoesNotExist, ValueError) as error:
            contexto["error"] = str(error) or "La vista previa caduco. Vuelve a subir el PDF."
    elif request.method == "POST" and form.is_valid():
        grupo = form.cleaned_data["grupo_destino"]
        try:
            filas = extraer_lista_pdf(
                form.cleaned_data["archivo"], grupo.ciclo_escolar.nombre,
                grupo.grado.orden, grupo.nombre,
            )
            if len(filas) > 50:
                raise ValueError("La lista contiene mas de 50 alumnos; revisa el archivo.")
            existentes = {alumno.matricula: alumno for alumno in Alumno.objects.filter(
                matricula__in=[fila["matricula"] for fila in filas]
            )}
            vista = []
            for fila in filas:
                actual = existentes.get(fila["matricula"])
                estado = "nuevo" if not actual else (
                    "existente" if actual.grupo_id == grupo.id and actual.activo else "conflicto"
                )
                vista.append({**fila, "estado": estado})
            contexto.update({"vista": vista, "grupo": grupo,
                "conflictos": any(fila["estado"] == "conflicto" for fila in vista),
                "vista_previa": signing.dumps({
                    "usuario_id": request.user.pk, "grupo_id": grupo.pk, "filas": filas,
                }, salt="importar-lista")})
        except ValueError as error:
            contexto["error"] = str(error)
    return render(request, "asistencias/importar_lista.html", contexto)


@direccion_required
@never_cache
def ciclos_escolares(request):
    ciclos = list(CicloEscolar.objects.order_by("-fecha_inicio"))
    origen = ciclos[0] if ciclos else None
    form = CicloNuevoForm(request.POST or None, ciclo_origen=origen)
    if request.method == "POST" and form.is_valid() and origen:
        try:
            ciclo, promovidos, egresados = crear_ciclo_y_promover(
                origen, form.cleaned_data["nombre"], form.cleaned_data["fecha_inicio"],
                form.cleaned_data["fecha_fin"],
            )
            messages.success(request, f"Ciclo {ciclo.nombre} creado: {promovidos} promovidos, {egresados} egresados.")
            return redirect("asistencias:control")
        except ValidationError as error:
            form.add_error(None, error)
    resumen = []
    if origen:
        for orden in (1, 2, 3):
            resumen.append({"grado": orden, "total": Alumno.objects.filter(
                activo=True, grupo__ciclo_escolar=origen, grupo__grado__orden=orden,
            ).count()})
    return render(request, "asistencias/ciclos_escolares.html", {
        "form": form, "ciclos": ciclos, "origen": origen, "resumen": resumen,
        "puede_promover": bool(origen and timezone.localdate() > origen.fecha_fin),
        "active_section": "ciclos",
    })


def _prefectos_gestionables():
    return get_user_model().objects.filter(groups__name=PREFECTOS_GROUP).exclude(
        groups__name=DIRECCION_GROUP
    ).exclude(is_superuser=True).distinct().order_by("-is_active", "first_name", "last_name", "username")


@direccion_required
@never_cache
def gestionar_prefectos(request):
    form = PrefectoCuentaForm(request.POST or None)
    acceso = None
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            grupo = Group.objects.select_for_update().get(name=PREFECTOS_GROUP)
            if get_user_model().objects.filter(groups=grupo, is_active=True).count() >= 3:
                form.add_error(None, "Ya hay tres prefectos activos. Desactiva uno antes de agregar otro.")
            else:
                prefecto = form.save(commit=False)
                contrasena = (secrets.token_urlsafe(18) if form.cleaned_data["metodo_contrasena"] == "generar"
                              else form.cleaned_data["contrasena_manual"])
                prefecto.set_password(contrasena)
                prefecto.save()
                prefecto.groups.add(grupo)
                if form.cleaned_data["metodo_contrasena"] == "generar":
                    acceso = {"usuario": prefecto.username, "contrasena": contrasena}
                messages.success(request, f"Prefecto {prefecto.get_full_name()} agregado.")
                form = PrefectoCuentaForm()
    return render(request, "asistencias/gestionar_prefectos.html", {
        "form": form, "prefectos": _prefectos_gestionables().annotate(
            total_registros=Count("registros_asistencia", distinct=True)
        ), "acceso": acceso,
        "activos": get_user_model().objects.filter(groups__name=PREFECTOS_GROUP, is_active=True).count(),
        "active_section": "prefectos",
    })


@direccion_required
@never_cache
def editar_prefecto(request, prefecto_id):
    prefecto = get_object_or_404(_prefectos_gestionables(), pk=prefecto_id)
    form = PrefectoCuentaForm(request.POST or None, instance=prefecto)
    acceso = None
    if request.method == "POST" and form.is_valid():
        prefecto = form.save(commit=False)
        metodo = form.cleaned_data["metodo_contrasena"]
        if metodo != "conservar":
            contrasena = (secrets.token_urlsafe(18) if metodo == "generar"
                          else form.cleaned_data["contrasena_manual"])
            prefecto.set_password(contrasena)
            if metodo == "generar":
                acceso = {"usuario": prefecto.username, "contrasena": contrasena}
        prefecto.save()
        messages.success(request, f"Cuenta de {prefecto.get_full_name()} actualizada.")
        if not acceso:
            return redirect("asistencias:gestionar_prefectos")
        form = PrefectoCuentaForm(instance=prefecto)
    return render(request, "asistencias/editar_prefecto.html", {
        "form": form, "prefecto": prefecto, "acceso": acceso, "active_section": "prefectos",
    })


@direccion_required
@require_POST
def cambiar_estado_prefecto(request, prefecto_id):
    if request.POST.get("accion") not in {"activar", "desactivar"}:
        return HttpResponse("Accion invalida.", status=400)
    with transaction.atomic():
        grupo = Group.objects.select_for_update().get(name=PREFECTOS_GROUP)
        prefecto = get_object_or_404(
            get_user_model().objects.select_for_update().filter(groups=grupo)
            .exclude(groups__name=DIRECCION_GROUP).exclude(is_superuser=True),
            pk=prefecto_id,
        )
        activar = request.POST.get("accion") == "activar"
        if activar and not prefecto.is_active and get_user_model().objects.filter(
            groups=grupo, is_active=True
        ).count() >= 3:
            messages.error(request, "Ya hay tres prefectos activos. Desactiva uno primero.")
        else:
            prefecto.is_active = activar
            prefecto.save(update_fields=["is_active"])
            messages.success(request, "Acceso activado." if activar else "Acceso desactivado.")
    return redirect("asistencias:gestionar_prefectos")


@escaneo_required
@ensure_csrf_cookie
def profesor_escaner(request):
    return render(
        request,
        "asistencias/kiosco_asistencia.html",
        {
            "prefecto_nombre": request.user.get_full_name() or request.user.username,
            "es_direccion": es_direccion(request.user),
        },
    )


@direccion_required
@never_cache
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
        "can_view_reports": True,
    }
    return render(request, "asistencias/control_semanal.html", contexto)


@direccion_required
@never_cache
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

    cierre = _cierre_fecha(grupos[0].ciclo_escolar, fecha) if grupos else ("Fin de semana" if fecha.weekday() >= 5 else "")

    alumnos_por_grupo = _alumnos_por_grupo(grupos, fecha=fecha)
    registros = RegistroAsistencia.objects.filter(
        Q(alumno__inscripciones__grupo__in=grupos) |
        Q(alumno__inscripciones__isnull=True, alumno__grupo__in=grupos),
        fecha=fecha,
        tipo=RegistroAsistencia.TipoRegistro.ENTRADA,
    ).distinct()
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
            if cierre:
                continue
            registro = registros_por_alumno.get(alumno.id)
            if registro is None:
                if not cierre:
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
        "cierre": cierre,
        "grado_filtro": grado_filtro,
        "grupo_filtro": grupo_filtro,
        "grados": GRADOS_CONTROL,
        "letras_grupo": GRUPOS_CONTROL,
        "secciones": secciones,
        "totales": totales,
        "generado_por": request.user.get_full_name() or request.user.username,
        "generado_en": timezone.localtime(),
    })


@direccion_required
@never_cache
def perfil_alumno(request, alumno_id):
    alumno = get_object_or_404(
        Alumno.objects.select_related("grupo", "grupo__grado", "grupo__ciclo_escolar"),
        pk=alumno_id,
    )
    hoy = timezone.localdate()
    mes_inicio = _obtener_inicio_mes(request.GET.get("mes"), hoy)
    mes_fin = _ultimo_dia_mes(mes_inicio)
    grupo_periodo = _grupo_en_mes(alumno, mes_inicio, mes_fin)
    calendario = _calendario_alumno(alumno, mes_inicio, mes_fin, hoy)
    dias_cerrados = {dia["fecha"] for semana in calendario for dia in semana if dia.get("cierre")}

    registros_mes = RegistroAsistencia.objects.select_related(
        "registrado_por", "modificado_por"
    ).filter(
        alumno=alumno,
        tipo=RegistroAsistencia.TipoRegistro.ENTRADA,
        fecha__range=(mes_inicio, mes_fin),
    ).order_by("fecha")
    resumen = {"presentes": 0, "retardos": 0, "justificados": 0, "ausentes": 0}
    for registro in registros_mes:
        if registro.fecha in dias_cerrados:
            continue
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
        "grupo_periodo": grupo_periodo,
        "can_manage_attendance": es_prefecto(request.user),
        "vista_direccion": True,
        "estados_manual": [("a_tiempo", "✓"), ("retardo", "Retardo"), ("ausente", "Falta")],
        "tutores": alumno.tutores.filter(activo=True).order_by("parentesco", "nombre"),
        "calendario": calendario,
        "dias_calendario": DIAS_CALENDARIO,
        "mes_inicio": mes_inicio,
        "mes_nombre": MESES[mes_inicio.month - 1],
        "mes_anterior": _sumar_meses(mes_inicio, -1),
        "mes_siguiente": _sumar_meses(mes_inicio, 1),
        "resumen": resumen,
        "hoy": hoy,
    }
    return render(request, "asistencias/perfil_alumno_compacto.html", contexto)


@direccion_required
@never_cache
@require_http_methods(["GET", "POST"])
def editar_alumno(request, alumno_id):
    alumno = get_object_or_404(Alumno, pk=alumno_id, activo=True)
    foto_anterior = alumno.foto.name
    form = AlumnoEditarForm(request.POST or None, request.FILES or None, instance=alumno)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            alumno = form.save(commit=False)
            if form.cleaned_data["quitar_foto"] and not request.FILES.get("foto"):
                alumno.foto = ""
            alumno.save()
            Inscripcion.objects.update_or_create(
                alumno=alumno, ciclo_escolar=alumno.grupo.ciclo_escolar,
                defaults={"grupo": alumno.grupo},
            )
            for parentesco in (Tutor.Parentesco.MADRE, Tutor.Parentesco.PADRE):
                nombre = form.cleaned_data[f"{parentesco}_nombre"]
                telefono = form.cleaned_data[f"{parentesco}_telefono"]
                actual = alumno.tutores.filter(parentesco=parentesco, activo=True).first()
                if actual and (actual.nombre != nombre or actual.telefono_whatsapp != telefono):
                    alumno.tutores.remove(actual)
                if nombre and (not actual or actual.nombre != nombre or actual.telefono_whatsapp != telefono):
                    alumno.tutores.add(Tutor.objects.create(nombre=nombre, telefono_whatsapp=telefono, parentesco=parentesco))
            if foto_anterior and foto_anterior != alumno.foto.name:
                storage = alumno.foto.storage
                transaction.on_commit(lambda: storage.delete(foto_anterior))
        return redirect("asistencias:perfil_alumno", alumno_id=alumno.pk)
    return render(request, "asistencias/editar_alumno.html", {"alumno": alumno, "form": form})


@direccion_required
@never_cache
@require_GET
def foto_alumno(request, alumno_id):
    alumno = get_object_or_404(Alumno, pk=alumno_id)
    if not alumno.foto:
        raise Http404("Foto no disponible")
    tipo = mimetypes.guess_type(alumno.foto.name)[0] or "application/octet-stream"
    response = FileResponse(alumno.foto.open("rb"), content_type=tipo)
    response["X-Content-Type-Options"] = "nosniff"
    return response


@direccion_required
@never_cache
@require_http_methods(["GET", "POST"])
def cuentas_alumnos(request):
    accesos = []
    if request.method == "POST":
        accion = request.POST.get("accion")
        if accion == "crear_faltantes":
            for alumno_id in Alumno.objects.filter(activo=True, cuenta__isnull=True).values_list("pk", flat=True):
                acceso = emitir_acceso(alumno_id)
                if acceso:
                    accesos.append(acceso)
        elif accion == "restablecer":
            alumno = get_object_or_404(Alumno, pk=request.POST.get("alumno_id"), activo=True)
            accesos.append(emitir_acceso(alumno.pk, restablecer=True))
        else:
            return HttpResponse("Accion invalida.", status=400)
    alumnos = Alumno.objects.filter(activo=True).select_related(
        "grupo", "grupo__grado", "cuenta", "cuenta__usuario"
    ).order_by("apellido_paterno", "apellido_materno", "nombres")
    filas = [{"alumno": alumno, "usuario": alumno.cuenta.usuario.username if hasattr(alumno, "cuenta") else ""}
             for alumno in alumnos]
    return render(request, "asistencias/cuentas_alumnos.html", {"filas": filas, "accesos": accesos})


@login_required(login_url="asistencias:estudiante_login")
@never_cache
def portal_alumno(request):
    cuenta = CuentaAlumno.objects.select_related(
        "alumno", "alumno__grupo", "alumno__grupo__grado", "alumno__grupo__ciclo_escolar"
    ).filter(usuario=request.user, alumno__activo=True).first()
    if cuenta is None:
        return redirect("asistencias:estudiante_login")
    return render(request, "asistencias/portal_estudiante.html", _contexto_portal_alumno(cuenta.alumno, request.GET.get("mes")))


@direccion_required
@never_cache
@require_GET
def vista_alumno(request, alumno_id):
    alumno = get_object_or_404(
        Alumno.objects.select_related("grupo", "grupo__grado", "grupo__ciclo_escolar"),
        pk=alumno_id, activo=True,
    )
    contexto = _contexto_portal_alumno(alumno, request.GET.get("mes"))
    contexto["vista_previa"] = True
    return render(request, "asistencias/portal_estudiante.html", contexto)


def _contexto_portal_alumno(alumno, mes):
    hoy = timezone.localdate()
    mes_inicio = _obtener_inicio_mes(mes, hoy)
    mes_fin = _ultimo_dia_mes(mes_inicio)
    grupo_periodo = _grupo_en_mes(alumno, mes_inicio, mes_fin)
    registros = RegistroAsistencia.objects.filter(
        alumno=alumno, tipo=RegistroAsistencia.TipoRegistro.ENTRADA,
        fecha__range=(mes_inicio, mes_fin),
    )
    calendario = _calendario_alumno(alumno, mes_inicio, mes_fin, hoy)
    dias_cerrados = {dia["fecha"] for semana in calendario for dia in semana if dia.get("cierre")}
    resumen = {"presentes": 0, "retardos": 0, "justificados": 0, "ausentes": 0}
    for registro in registros:
        if registro.fecha in dias_cerrados:
            continue
        estado = _estado_visual(registro.estado)
        resumen[{"presente": "presentes", "retardo": "retardos",
                 "justificado": "justificados", "ausente": "ausentes"}[estado]] += 1
    return {
        "alumno": alumno,
        "grupo_periodo": grupo_periodo,
        "calendario": calendario,
        "dias_calendario": DIAS_CALENDARIO,
        "mes_inicio": mes_inicio,
        "mes_nombre": MESES[mes_inicio.month - 1],
        "mes_anterior": _sumar_meses(mes_inicio, -1),
        "mes_siguiente": _sumar_meses(mes_inicio, 1),
        "resumen": resumen,
        "hoy": hoy,
    }


@never_cache
def alumno_publico(request, codigo):
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path(), reverse("asistencias:estudiante_login"))
    alumno = get_object_or_404(
        Alumno.objects.select_related("grupo", "grupo__grado", "grupo__ciclo_escolar"),
        codigo_qr=codigo,
        activo=True,
    )
    if es_direccion(request.user):
        destino = reverse("asistencias:vista_alumno", args=[alumno.pk])
        mes = request.GET.get("mes")
        return redirect(destino + f"?mes={mes}" if mes else destino)
    if not CuentaAlumno.objects.filter(alumno=alumno, usuario=request.user).exists():
        raise PermissionDenied("Esta credencial no corresponde a tu cuenta.")
    mes = request.GET.get("mes")
    destino = reverse("asistencias:portal_alumno")
    return redirect(destino + f"?mes={mes}" if mes else destino)


@direccion_required
@never_cache
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


@direccion_required
@never_cache
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
    if _cierre_fecha(alumno.grupo.ciclo_escolar, fecha):
        return HttpResponse("No se puede registrar asistencia en un dia sin clases.", status=409)
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
@escaneo_required
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
    if _cierre_fecha(alumno.grupo.ciclo_escolar, hoy):
        return JsonResponse({"ok": False, "mensaje": "Hoy no hay clases; no se registro asistencia."}, status=409)

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


def _alumnos_por_grupo(grupos, fecha=None):
    resultado = {grupo.id: [] for grupo in grupos}
    if fecha is not None:
        inscripciones = Inscripcion.objects.select_related("alumno").filter(
            grupo__in=grupos,
            ciclo_escolar__fecha_inicio__lte=fecha,
            ciclo_escolar__fecha_fin__gte=fecha,
        ).order_by("alumno__apellido_paterno", "alumno__apellido_materno", "alumno__nombres")
        for inscripcion in inscripciones:
            resultado[inscripcion.grupo_id].append(inscripcion.alumno)
        for alumno in Alumno.objects.filter(inscripciones__isnull=True, grupo__in=grupos, activo=True):
            resultado[alumno.grupo_id].append(alumno)
    else:
        alumnos = Alumno.objects.select_related("grupo", "grupo__grado").filter(
            grupo__in=grupos, activo=True
        ).order_by("apellido_paterno", "apellido_materno", "nombres")
        for alumno in alumnos:
            resultado[alumno.grupo_id].append(alumno)
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
    grupo_periodo = _grupo_en_mes(alumno, mes_inicio, mes_fin)
    ciclo = grupo_periodo.ciclo_escolar
    eventos_por_fecha = _eventos_por_fecha(ciclo, mes_inicio, mes_fin)
    semanas = []

    for semana in calendar.Calendar(firstweekday=0).monthdatescalendar(
        mes_inicio.year, mes_inicio.month
    ):
        dias = []
        for dia in semana:
            fuera_mes = dia.month != mes_inicio.month
            registro = registros_por_fecha.get(dia)
            dias.append(_crear_dia_calendario(alumno, ciclo, dia, registro, hoy, fuera_mes, eventos_por_fecha.get(dia, [])))
        semanas.append(dias)
    return semanas


def _grupo_en_mes(alumno, mes_inicio, mes_fin):
    inscripcion = Inscripcion.objects.select_related("grupo__grado", "grupo__ciclo_escolar").filter(
        alumno=alumno, ciclo_escolar__fecha_inicio__lte=mes_fin,
        ciclo_escolar__fecha_fin__gte=mes_inicio,
    ).order_by("-ciclo_escolar__fecha_inicio").first()
    return inscripcion.grupo if inscripcion else alumno.grupo


def _crear_dia_calendario(alumno, ciclo, dia, registro, hoy, fuera_mes, eventos):
    if fuera_mes:
        return {"fuera_mes": True, "fecha": dia}

    cierre = _motivo_cierre(dia, eventos)
    if cierre:
        estado = "fin_semana" if dia.weekday() >= 5 else "sin_clases"
        etiqueta = cierre
        hora = registro.hora.strftime("%H:%M") if registro else ""
    elif dia < ciclo.fecha_inicio or dia > ciclo.fecha_fin:
        estado, etiqueta, hora = "fuera_ciclo", "Fuera del ciclo", ""
    elif registro:
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
        "es_hoy": dia == hoy,
        "alumno_id": alumno.id,
        "fecha": dia,
        "dia": dia.day,
        "estado": estado,
        "etiqueta": etiqueta,
        "hora": hora,
        "tiene_registro": registro is not None,
        "eventos": eventos,
        "actividades": [evento for evento in eventos if evento.tipo == "evento"],
        "cierre": cierre,
        "estado_registro": registro.get_estado_display() if registro else "",
        "responsable": (
            registro.registrado_por.get_full_name() or registro.registrado_por.username
            if registro and registro.registrado_por else "No consta"
        ),
        "ajustado_por": (
            registro.modificado_por.get_full_name() or registro.modificado_por.username
            if registro and registro.modificado_por else ""
        ),
        "editable": dia <= hoy and not cierre and alumno.activo and ciclo == alumno.grupo.ciclo_escolar and ciclo.fecha_inicio <= dia <= ciclo.fecha_fin,
    }


def _eventos_por_fecha(ciclo, inicio, fin):
    eventos = {}
    for evento in DiaEscolar.objects.filter(ciclo_escolar=ciclo, fecha__range=(inicio, fin)).select_related("registrado_por"):
        eventos.setdefault(evento.fecha, []).append(evento)
    for evento in EventoEscolar.objects.filter(ciclo_escolar=ciclo, fecha__range=(inicio, fin)).select_related("registrado_por"):
        eventos.setdefault(evento.fecha, []).append(evento)
    return eventos


def _motivo_cierre(fecha, eventos):
    cancelacion = next((e for e in eventos if e.tipo == DiaEscolar.Tipo.CANCELACION), None)
    if cancelacion:
        return cancelacion.descripcion
    if fecha.weekday() >= 5:
        return "Fin de semana"
    oficial = next((e for e in eventos if e.sin_clases), None)
    return oficial.descripcion if oficial else ""


def _cierre_fecha(ciclo, fecha):
    if fecha < ciclo.fecha_inicio or fecha > ciclo.fecha_fin:
        return "Fuera del ciclo escolar"
    eventos = list(DiaEscolar.objects.filter(ciclo_escolar=ciclo, fecha=fecha))
    return _motivo_cierre(fecha, eventos)


@direccion_required
@never_cache
@require_GET
def calendario_escolar(request):
    ciclos = CicloEscolar.objects.filter(activo=True)
    ciclo = ciclos.filter(pk=request.GET.get("ciclo")).first() if (request.GET.get("ciclo") or "").isdigit() else None
    if ciclo is None:
        ciclo = ciclos.filter(fecha_inicio__lte=timezone.localdate(), fecha_fin__gte=timezone.localdate()).order_by("-fecha_inicio").first()
    if ciclo is None:
        ciclo = ciclos.order_by("-fecha_inicio").first()
    if ciclo is None:
        return HttpResponse("No hay ciclo escolar activo.", status=404)
    mes = _obtener_inicio_mes(request.GET.get("mes"), timezone.localdate())
    limite_inicio = ciclo.fecha_inicio.replace(day=1)
    limite_fin = ciclo.fecha_fin.replace(day=1)
    if mes < limite_inicio:
        mes = limite_inicio
    if mes > limite_fin:
        mes = limite_fin
    eventos = _eventos_por_fecha(ciclo, mes, _ultimo_dia_mes(mes))
    semanas = []
    for semana in calendar.Calendar(firstweekday=0).monthdatescalendar(mes.year, mes.month):
        semanas.append([{
            "fecha": dia, "fuera_mes": dia.month != mes.month,
            "eventos": eventos.get(dia, []),
            "cierre": _motivo_cierre(dia, eventos.get(dia, [])),
            "cancelado": next((e for e in eventos.get(dia, []) if e.tipo == DiaEscolar.Tipo.CANCELACION), None),
            "actividades": [e for e in eventos.get(dia, []) if e.tipo == "evento"],
            "fin_semana": dia.weekday() >= 5,
            "fuera_ciclo": dia < ciclo.fecha_inicio or dia > ciclo.fecha_fin,
        } for dia in semana])
    return render(request, "asistencias/calendario_direccion.html", {
        "ciclo": ciclo, "mes": mes, "mes_nombre": MESES[mes.month - 1],
        "mes_anterior": _sumar_meses(mes, -1), "mes_siguiente": _sumar_meses(mes, 1),
        "semanas": semanas, "dias_calendario": DIAS_CALENDARIO,
        "cancelaciones_mes": DiaEscolar.objects.filter(ciclo_escolar=ciclo, fecha__range=(mes, _ultimo_dia_mes(mes)), tipo=DiaEscolar.Tipo.CANCELACION),
        "oficiales_mes": DiaEscolar.objects.filter(ciclo_escolar=ciclo, fecha__range=(mes, _ultimo_dia_mes(mes))).exclude(tipo=DiaEscolar.Tipo.CANCELACION),
        "eventos_mes": EventoEscolar.objects.filter(ciclo_escolar=ciclo, fecha__range=(mes, _ultimo_dia_mes(mes))),
    })


@direccion_required
@require_POST
def cancelar_dia(request):
    try:
        fecha = date.fromisoformat(request.POST.get("fecha", ""))
    except ValueError:
        return HttpResponse("Fecha invalida.", status=400)
    ciclo = get_object_or_404(CicloEscolar, pk=request.POST.get("ciclo_id"), fecha_inicio__lte=fecha, fecha_fin__gte=fecha, activo=True)
    motivos = {"huracan": "Huracan", "sismo": "Sismo", "consejo": "Consejo Tecnico", "otro": "Otra causa"}
    motivo = request.POST.get("motivo")
    if motivo not in motivos:
        return HttpResponse("Motivo invalido.", status=400)
    if fecha.weekday() >= 5 or DiaEscolar.objects.filter(ciclo_escolar=ciclo, fecha=fecha).exclude(tipo=DiaEscolar.Tipo.INFORMATIVO).exclude(tipo=DiaEscolar.Tipo.CANCELACION).exists():
        return HttpResponse("Ese dia ya esta marcado sin clases.", status=409)
    nota = (request.POST.get("nota") or "").strip()[:100]
    descripcion = motivos[motivo] + (f": {nota}" if nota else "")
    DiaEscolar.objects.update_or_create(ciclo_escolar=ciclo, fecha=fecha, tipo=DiaEscolar.Tipo.CANCELACION,
                                        defaults={"descripcion": descripcion, "registrado_por": request.user})
    return redirect(reverse("asistencias:calendario_escolar") + f"?ciclo={ciclo.pk}&mes={fecha:%Y-%m}")


@direccion_required
@require_POST
def restaurar_dia(request):
    try:
        fecha = date.fromisoformat(request.POST.get("fecha", ""))
    except ValueError:
        return HttpResponse("Fecha invalida.", status=400)
    ciclo = get_object_or_404(CicloEscolar, pk=request.POST.get("ciclo_id"), activo=True)
    DiaEscolar.objects.filter(fecha=fecha, tipo=DiaEscolar.Tipo.CANCELACION,
                              ciclo_escolar=ciclo).delete()
    return redirect(reverse("asistencias:calendario_escolar") + f"?ciclo={ciclo.pk}&mes={fecha:%Y-%m}")


@direccion_required
@require_POST
def guardar_evento(request):
    form = EventoEscolarForm(request.POST)
    if not form.is_valid():
        return HttpResponse("Revisa la fecha, el titulo y el detalle del evento.", status=400)
    fecha = form.cleaned_data["fecha"]
    ciclo = get_object_or_404(CicloEscolar, pk=request.POST.get("ciclo_id"), activo=True,
                              fecha_inicio__lte=fecha, fecha_fin__gte=fecha)
    evento_id = request.POST.get("evento_id")
    if evento_id:
        evento = get_object_or_404(EventoEscolar, pk=evento_id, ciclo_escolar=ciclo)
    else:
        evento = EventoEscolar(ciclo_escolar=ciclo, registrado_por=request.user)
    evento.fecha = fecha
    evento.titulo = form.cleaned_data["titulo"]
    evento.detalle = form.cleaned_data["detalle"]
    evento.save()
    return redirect(reverse("asistencias:calendario_escolar") + f"?ciclo={ciclo.pk}&mes={fecha:%Y-%m}")


@direccion_required
@require_POST
def eliminar_evento(request):
    ciclo = get_object_or_404(CicloEscolar, pk=request.POST.get("ciclo_id"), activo=True)
    evento = get_object_or_404(EventoEscolar, pk=request.POST.get("evento_id"), ciclo_escolar=ciclo)
    fecha = evento.fecha
    evento.delete()
    return redirect(reverse("asistencias:calendario_escolar") + f"?ciclo={ciclo.pk}&mes={fecha:%Y-%m}")


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
