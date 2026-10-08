from django.db import migrations, models
import django.db.models.deletion


def registrar_inscripciones_actuales(apps, schema_editor):
    Alumno = apps.get_model("asistencias", "Alumno")
    Inscripcion = apps.get_model("asistencias", "Inscripcion")
    alias = schema_editor.connection.alias
    for alumno in Alumno.objects.using(alias).select_related("grupo").iterator():
        Inscripcion.objects.using(alias).get_or_create(
            alumno_id=alumno.pk,
            ciclo_escolar_id=alumno.grupo.ciclo_escolar_id,
            defaults={"grupo_id": alumno.grupo_id},
        )


class Migration(migrations.Migration):
    dependencies = [("asistencias", "0014_alumno_foto")]

    operations = [
        migrations.CreateModel(
            name="Inscripcion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("actualizado_en", models.DateTimeField(auto_now=True)),
                ("alumno", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="inscripciones", to="asistencias.alumno")),
                ("ciclo_escolar", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="inscripciones", to="asistencias.cicloescolar")),
                ("grupo", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="inscripciones", to="asistencias.grupo")),
            ],
            options={"ordering": ["-ciclo_escolar__fecha_inicio"]},
        ),
        migrations.AddConstraint(
            model_name="inscripcion",
            constraint=models.UniqueConstraint(fields=("alumno", "ciclo_escolar"), name="inscripcion_unica_por_ciclo"),
        ),
        migrations.RunPython(registrar_inscripciones_actuales, migrations.RunPython.noop),
    ]
