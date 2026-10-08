import re

from django.db import migrations


def reparar_tutores_invertidos(apps, schema_editor):
    Tutor = apps.get_model("asistencias", "Tutor")
    for tutor in Tutor.objects.filter(parentesco__in=["madre", "padre"]).iterator():
        nombre = tutor.nombre.strip()
        telefono = tutor.telefono_whatsapp.strip()
        if re.fullmatch(r"\+?\d{10,15}", nombre) and any(letra.isalpha() for letra in telefono):
            tutor.nombre = telefono
            tutor.telefono_whatsapp = nombre
            tutor.save(update_fields=["nombre", "telefono_whatsapp"])


class Migration(migrations.Migration):
    dependencies = [("asistencias", "0016_alter_tutor_recibe_notificaciones")]

    operations = [migrations.RunPython(reparar_tutores_invertidos, migrations.RunPython.noop)]
