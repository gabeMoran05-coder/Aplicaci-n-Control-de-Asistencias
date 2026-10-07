from django.db import migrations


def crear_grupo_direccion(apps, schema_editor):
    grupo_modelo = apps.get_model("auth", "Group")
    grupo_modelo.objects.using(schema_editor.connection.alias).get_or_create(name="Direccion")


class Migration(migrations.Migration):
    dependencies = [
        ("asistencias", "0006_prefectos_group"),
    ]

    operations = [migrations.RunPython(crear_grupo_direccion, migrations.RunPython.noop)]
