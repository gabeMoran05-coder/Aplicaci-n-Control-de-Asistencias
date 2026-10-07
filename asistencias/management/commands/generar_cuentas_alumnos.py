import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from asistencias.cuentas import emitir_acceso
from asistencias.models import Alumno


class Command(BaseCommand):
    help = "Crea accesos para alumnos activos y escribe contrasenas de entrega en un CSV local."

    def add_arguments(self, parser):
        parser.add_argument("--output", default="private/credenciales_alumnos.csv")
        parser.add_argument("--restablecer", action="store_true")

    def handle(self, *args, **options):
        destino = Path(options["output"])
        destino.parent.mkdir(parents=True, exist_ok=True)
        if destino.exists():
            raise CommandError(f"El archivo ya existe: {destino}. Usa otra ruta para no sobrescribir credenciales.")

        alumnos = Alumno.objects.filter(activo=True).order_by(
            "apellido_paterno", "apellido_materno", "nombres"
        )
        creados = 0
        with destino.open("x", encoding="utf-8-sig", newline="") as archivo:
            escritor = csv.writer(archivo)
            escritor.writerow(["Matricula", "Alumno", "Grado", "Grupo", "Usuario", "Contrasena"])
            for alumno in alumnos:
                acceso = emitir_acceso(alumno.pk, restablecer=options["restablecer"])
                if acceso:
                    escritor.writerow([
                        alumno.matricula, alumno.nombre_completo, alumno.grado_nombre,
                        alumno.grupo.nombre, acceso["usuario"], acceso["contrasena"],
                    ])
                    creados += 1
        self.stdout.write(self.style.SUCCESS(f"{creados} accesos emitidos en {destino}. Entrega el archivo de forma privada."))
