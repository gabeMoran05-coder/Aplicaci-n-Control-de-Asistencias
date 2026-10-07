from datetime import date

from django.db import migrations


def marcar_sin_clases(apps, schema_editor):
    Dia = apps.get_model("asistencias", "DiaEscolar")
    Dia.objects.using(schema_editor.connection.alias).filter(
        ciclo_escolar__nombre="2026-2027",
        fecha__in=[date(2026, 11, 13), date(2027, 3, 5), date(2027, 7, 2)],
        tipo="informativo",
    ).update(tipo="registro")


class Migration(migrations.Migration):
    dependencies = [("asistencias", "0009_calendario_2026_2027")]
    operations = [migrations.RunPython(marcar_sin_clases, migrations.RunPython.noop)]
