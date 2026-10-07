from datetime import date, timedelta

from django.db import migrations


def cargar_calendario(apps, schema_editor):
    Ciclo = apps.get_model("asistencias", "CicloEscolar")
    Dia = apps.get_model("asistencias", "DiaEscolar")
    db = schema_editor.connection.alias
    ciclo, _ = Ciclo.objects.using(db).get_or_create(
        nombre="2026-2027",
        defaults={"fecha_inicio": date(2026, 8, 31), "fecha_fin": date(2027, 7, 9), "activo": True},
    )
    Ciclo.objects.using(db).filter(pk=ciclo.pk).update(
        fecha_inicio=date(2026, 8, 31), fecha_fin=date(2027, 7, 9)
    )

    def agregar(fecha, tipo, descripcion):
        Dia.objects.using(db).get_or_create(
            ciclo_escolar_id=ciclo.pk, fecha=date.fromisoformat(fecha), tipo=tipo,
            defaults={"descripcion": descripcion},
        )

    def rango(inicio, fin, tipo, descripcion):
        actual, ultimo = date.fromisoformat(inicio), date.fromisoformat(fin)
        while actual <= ultimo:
            agregar(actual.isoformat(), tipo, descripcion)
            actual += timedelta(days=1)

    rango("2026-08-01", "2026-08-23", "receso", "Receso escolar")
    rango("2026-08-24", "2026-08-28", "consejo", "Consejo Tecnico Escolar intensivo")
    rango("2026-08-29", "2026-08-30", "receso", "Receso escolar")
    for fecha in ("2026-09-25", "2026-10-30", "2026-11-27", "2027-01-29",
                  "2027-02-26", "2027-04-30", "2027-05-28", "2027-06-25"):
        agregar(fecha, "consejo", "Consejo Tecnico Escolar")
    for fecha in ("2026-09-16", "2026-11-02", "2026-11-16", "2026-12-25",
                  "2027-01-01", "2027-01-06", "2027-02-01", "2027-03-15", "2027-05-05"):
        agregar(fecha, "suspension", "Suspension de labores docentes")
    rango("2026-12-21", "2027-01-05", "vacaciones", "Vacaciones de invierno")
    rango("2027-03-22", "2027-04-02", "vacaciones", "Vacaciones de primavera")
    rango("2027-07-10", "2027-07-31", "receso", "Receso escolar")
    for fecha, descripcion in (
        ("2026-08-31", "Inicio de clases"),
        ("2026-09-07", "Jornada de concientizacion"),
        ("2026-11-13", "Registro de calificaciones"),
        ("2027-03-05", "Registro de calificaciones"),
        ("2027-07-02", "Registro de calificaciones"),
        ("2027-07-09", "Fin de clases"),
    ):
        agregar(fecha, "informativo", descripcion)
    for inicio, fin, descripcion in (
        ("2026-11-23", "2026-11-26", "Evaluacion"),
        ("2027-02-02", "2027-02-05", "Preinscripciones"),
        ("2027-02-08", "2027-02-12", "Preinscripciones"),
        ("2027-03-16", "2027-03-19", "Evaluacion"),
        ("2027-07-08", "2027-07-09", "Evaluacion"),
    ):
        rango(inicio, fin, "informativo", descripcion)


class Migration(migrations.Migration):
    dependencies = [("asistencias", "0008_diaescolar")]
    operations = [migrations.RunPython(cargar_calendario, migrations.RunPython.noop)]
