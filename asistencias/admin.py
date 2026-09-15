from django.contrib import admin
from .models import (
    Alumno,
    CicloEscolar,
    Grado,
    Grupo,
    NotificacionWhatsApp,
    RegistroAsistencia,
    Tutor,
)


@admin.register(CicloEscolar)
class CicloEscolarAdmin(admin.ModelAdmin):
    list_display = ("nombre", "fecha_inicio", "fecha_fin", "activo")
    list_filter = ("activo",)
    search_fields = ("nombre",)


@admin.register(Grado)
class GradoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "orden")
    ordering = ("orden",)


@admin.register(Grupo)
class GrupoAdmin(admin.ModelAdmin):
    list_display = ("grado", "nombre", "ciclo_escolar", "activo")
    list_filter = ("ciclo_escolar", "grado", "activo")
    search_fields = ("nombre",)


@admin.register(Tutor)
class TutorAdmin(admin.ModelAdmin):
    list_display = (
        "nombre",
        "parentesco",
        "telefono_whatsapp",
        "recibe_notificaciones",
        "activo",
    )
    list_filter = ("parentesco", "recibe_notificaciones", "activo")
    search_fields = ("nombre", "telefono_whatsapp", "email")


@admin.register(Alumno)
class AlumnoAdmin(admin.ModelAdmin):
    list_display = ("matricula", "nombre_completo", "grupo", "activo")
    list_filter = ("grupo__ciclo_escolar", "grupo__grado", "grupo", "activo")
    search_fields = (
        "matricula",
        "nombres",
        "apellido_paterno",
        "apellido_materno",
        "codigo_qr",
        "codigo_nfc",
    )
    filter_horizontal = ("tutores",)


@admin.register(RegistroAsistencia)
class RegistroAsistenciaAdmin(admin.ModelAdmin):
    list_display = ("alumno", "tipo", "fecha", "hora", "estado", "registrado_por")
    list_filter = ("tipo", "estado", "fecha", "alumno__grupo")
    search_fields = (
        "alumno__matricula",
        "alumno__nombres",
        "alumno__apellido_paterno",
        "alumno__apellido_materno",
    )
    date_hierarchy = "fecha"


@admin.register(NotificacionWhatsApp)
class NotificacionWhatsAppAdmin(admin.ModelAdmin):
    list_display = ("tutor", "telefono_destino", "registro", "estado", "enviado_en")
    list_filter = ("estado", "creado_en")
    search_fields = ("tutor__nombre", "telefono_destino", "mensaje")
    readonly_fields = ("creado_en", "actualizado_en")
