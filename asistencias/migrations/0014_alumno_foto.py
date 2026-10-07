from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("asistencias", "0013_cuentaalumno")]

    operations = [migrations.AddField(
        model_name="alumno", name="foto",
        field=models.ImageField(blank=True, upload_to="alumnos/fotos/"),
    )]
