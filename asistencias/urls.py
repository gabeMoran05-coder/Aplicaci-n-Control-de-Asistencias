from django.urls import path

from . import views

app_name = "asistencias"

urlpatterns = [
    path("", views.control_semanal, name="inicio"),
    path("control/", views.control_semanal, name="control"),
    path("alumnos/<int:alumno_id>/", views.perfil_alumno, name="perfil_alumno"),
    path("alumnos/<int:alumno_id>/credencial/", views.credencial_alumno, name="credencial_alumno"),
    path("alumnos/<int:alumno_id>/qr.svg", views.qr_alumno, name="qr_alumno"),
    path("q/<str:codigo>/", views.alumno_publico, name="alumno_publico"),
    path("control/marcar/", views.marcar_asistencia_manual, name="marcar_manual"),
    path("control/limpiar/", views.limpiar_asistencia_manual, name="limpiar_manual"),
    path("kiosco/", views.kiosco_asistencia, name="kiosco"),
    path("profesor/", views.profesor_escaner, name="profesor"),
    path("kiosco/registrar/", views.registrar_asistencia_kiosco, name="registrar_kiosco"),
]
