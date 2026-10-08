from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Alumno, CicloEscolar, Grado, Grupo, Inscripcion


@transaction.atomic
def crear_ciclo_y_promover(origen, nombre, fecha_inicio, fecha_fin):
    origen = CicloEscolar.objects.select_for_update().get(pk=origen.pk)
    if CicloEscolar.objects.exclude(pk=origen.pk).filter(fecha_inicio__gt=origen.fecha_inicio).exists():
        raise ValidationError("Ya existe un ciclo posterior. Revisa los ciclos antes de promover.")
    if CicloEscolar.objects.filter(nombre=nombre).exists() or fecha_inicio <= origen.fecha_fin:
        raise ValidationError("El ciclo nuevo ya existe o se superpone con el anterior.")
    if timezone.localdate() <= origen.fecha_fin:
        raise ValidationError("La promocion se habilita al terminar el ciclo actual.")
    if fecha_inicio > timezone.localdate():
        raise ValidationError("La promocion se realiza cuando inicia el nuevo ciclo.")

    ciclo = CicloEscolar.objects.create(
        nombre=nombre, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin, activo=True
    )
    grupos = {}
    for grado in Grado.objects.filter(orden__in=[1, 2, 3]):
        for letra in "ABCD":
            grupos[(grado.orden, letra)] = Grupo.objects.create(
                grado=grado, nombre=letra, ciclo_escolar=ciclo, activo=True
            )

    promovidos = egresados = 0
    alumnos = Alumno.objects.select_for_update().select_related("grupo__grado").filter(
        activo=True, grupo__ciclo_escolar=origen
    )
    for alumno in alumnos:
        Inscripcion.objects.get_or_create(
            alumno=alumno, ciclo_escolar=origen, defaults={"grupo": alumno.grupo}
        )
        orden = alumno.grupo.grado.orden
        if orden == 3:
            alumno.activo = False
            alumno.save(update_fields=["activo", "actualizado_en"])
            egresados += 1
        elif orden in (1, 2):
            destino = grupos[(orden + 1, alumno.grupo.nombre)]
            Inscripcion.objects.create(alumno=alumno, ciclo_escolar=ciclo, grupo=destino)
            alumno.grupo = destino
            alumno.save(update_fields=["grupo", "actualizado_en"])
            promovidos += 1
    return ciclo, promovidos, egresados
