from django.urls import path

from . import views

app_name = "asistencias"

urlpatterns = [
    path("kiosco/", views.kiosco_asistencia, name="kiosco"),
    path("kiosco/registrar/", views.registrar_asistencia_kiosco, name="registrar_kiosco"),
]
