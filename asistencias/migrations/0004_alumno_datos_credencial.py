from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("asistencias", "0003_alter_registroasistencia_estado"),
    ]

    operations = [
        migrations.AddField(
            model_name="alumno",
            name="contacto_emergencia_nombre",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="alumno",
            name="contacto_emergencia_telefono",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name="alumno",
            name="fecha_nacimiento",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="alumno",
            name="informacion_medica",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="alumno",
            name="tipo_sangre",
            field=models.CharField(blank=True, max_length=5),
        ),
    ]
