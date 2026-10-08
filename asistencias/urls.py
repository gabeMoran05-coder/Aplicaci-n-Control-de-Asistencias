from django.urls import path

from django.contrib.auth.views import LogoutView
from django.views.generic import RedirectView

from . import views

app_name = "asistencias"

urlpatterns = [
    path("", views.control_semanal, name="inicio"),
    path("control/", views.control_semanal, name="control"),
    path("control/alumnos/agregar/", views.agregar_alumno, name="agregar_alumno"),
    path("control/alumnos/importar/", views.importar_lista, name="importar_lista"),
    path("control/ciclos/", views.ciclos_escolares, name="ciclos_escolares"),
    path("control/ausencias/", views.reporte_ausencias, name="reporte_ausencias"),
    path("control/calendario/", views.calendario_escolar, name="calendario_escolar"),
    path("control/calendario/cancelar/", views.cancelar_dia, name="cancelar_dia"),
    path("control/calendario/restaurar/", views.restaurar_dia, name="restaurar_dia"),
    path("control/calendario/eventos/guardar/", views.guardar_evento, name="guardar_evento"),
    path("control/calendario/eventos/eliminar/", views.eliminar_evento, name="eliminar_evento"),
    path("control/cuentas/", views.cuentas_alumnos, name="cuentas_alumnos"),
    path("control/ingresar/", views.DireccionLoginView.as_view(), name="direccion_login"),
    path("control/salir/", LogoutView.as_view(next_page="asistencias:direccion_login"), name="direccion_logout"),
    path("alumnos/<int:alumno_id>/", views.perfil_alumno, name="perfil_alumno"),
    path("alumnos/<int:alumno_id>/vista/", views.vista_alumno, name="vista_alumno"),
    path("alumnos/<int:alumno_id>/editar/", views.editar_alumno, name="editar_alumno"),
    path("alumnos/<int:alumno_id>/foto/", views.foto_alumno, name="foto_alumno"),
    path("alumnos/<int:alumno_id>/credencial/", views.credencial_alumno, name="credencial_alumno"),
    path("alumnos/<int:alumno_id>/qr.svg", views.qr_alumno, name="qr_alumno"),
    path("q/<str:codigo>/", views.alumno_publico, name="alumno_publico"),
    path("estudiantes/", views.portal_alumno, name="portal_alumno"),
    path("estudiantes/ingresar/", views.EstudianteLoginView.as_view(), name="estudiante_login"),
    path("estudiantes/salir/", LogoutView.as_view(next_page="asistencias:estudiante_login"), name="estudiante_logout"),
    path("estudiantes/manifest.webmanifest", views.estudiante_manifest, name="estudiante_manifest"),
    path("control/marcar/", views.marcar_asistencia_manual, name="marcar_manual"),
    path("control/limpiar/", views.limpiar_asistencia_manual, name="limpiar_manual"),
    path("prefectos/", views.profesor_escaner, name="prefectos"),
    path("prefectos/ingresar/", views.PrefectoLoginView.as_view(), name="prefecto_login"),
    path("prefectos/salir/", LogoutView.as_view(next_page="asistencias:prefecto_login"), name="prefecto_logout"),
    path("prefectos/registrar/", views.registrar_asistencia_prefecto, name="registrar_prefecto"),
    path("prefectos/manifest.webmanifest", views.prefecto_manifest, name="prefecto_manifest"),
    path("profesor/", RedirectView.as_view(pattern_name="asistencias:prefectos", permanent=False), name="profesor"),
]
