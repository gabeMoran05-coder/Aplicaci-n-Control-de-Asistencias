from django.urls import path

from . import views

app_name = "asistencias"

urlpatterns = [
    path("", views.control_semanal, name="inicio"),
    path("control/", views.control_semanal, name="control"),
    path("control/marcar/", views.marcar_asistencia_manual, name="marcar_manual"),
    path("control/limpiar/", views.limpiar_asistencia_manual, name="limpiar_manual"),
    path("kiosco/", views.kiosco_asistencia, name="kiosco"),
    path("kiosco/registrar/", views.registrar_asistencia_kiosco, name="registrar_kiosco"),
]
