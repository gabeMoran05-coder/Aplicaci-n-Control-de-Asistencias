from django.urls import path

from django.contrib.auth.views import LogoutView
from django.views.generic import RedirectView

from . import views

app_name = "asistencias"

urlpatterns = [
    path("", views.control_semanal, name="inicio"),
    path("control/", views.control_semanal, name="control"),
    path("control/ausencias/", views.reporte_ausencias, name="reporte_ausencias"),
    path("alumnos/<int:alumno_id>/", views.perfil_alumno, name="perfil_alumno"),
    path("alumnos/<int:alumno_id>/credencial/", views.credencial_alumno, name="credencial_alumno"),
    path("alumnos/<int:alumno_id>/qr.svg", views.qr_alumno, name="qr_alumno"),
    path("q/<str:codigo>/", views.alumno_publico, name="alumno_publico"),
    path("control/marcar/", views.marcar_asistencia_manual, name="marcar_manual"),
    path("control/limpiar/", views.limpiar_asistencia_manual, name="limpiar_manual"),
    path("prefectos/", views.profesor_escaner, name="prefectos"),
    path("prefectos/ingresar/", views.PrefectoLoginView.as_view(), name="prefecto_login"),
    path("prefectos/salir/", LogoutView.as_view(next_page="asistencias:prefecto_login"), name="prefecto_logout"),
    path("prefectos/registrar/", views.registrar_asistencia_prefecto, name="registrar_prefecto"),
    path("prefectos/manifest.webmanifest", views.prefecto_manifest, name="prefecto_manifest"),
    path("profesor/", RedirectView.as_view(pattern_name="asistencias:prefectos", permanent=False), name="profesor"),
]
