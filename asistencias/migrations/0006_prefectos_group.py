from django.db import migrations


def crear_grupo_prefectos(apps, schema_editor):
    grupo_modelo = apps.get_model("auth", "Group")
    usuario_modelo = apps.get_model("auth", "User")
    base = schema_editor.connection.alias
    grupo, _ = grupo_modelo.objects.using(base).get_or_create(name="Prefectos")
    usuario = usuario_modelo.objects.using(base).filter(username="profe").first()
    if usuario:
        usuario.groups.add(grupo)


class Migration(migrations.Migration):
    dependencies = [
        ("asistencias", "0005_registroasistencia_modificado_por"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [migrations.RunPython(crear_grupo_prefectos, migrations.RunPython.noop)]
