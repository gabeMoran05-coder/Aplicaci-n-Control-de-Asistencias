from pathlib import Path
from uuid import uuid4

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from asistencias.listas import extraer_lista_pdf
from asistencias.models import Alumno, Grupo, Inscripcion


class Command(BaseCommand):
    help = "Importa una lista escolar en PDF por matricula, sin reemplazar alumnos existentes."

    def add_arguments(self, parser):
        parser.add_argument("pdf", type=Path)
        parser.add_argument("--ciclo", required=True)
        parser.add_argument("--grado", type=int, required=True)
        parser.add_argument("--grupo", required=True)

    def handle(self, *args, **options):
        pdf = options["pdf"]
        if not pdf.is_file():
            raise CommandError(f"No existe el PDF: {pdf}")
        try:
            grupo = Grupo.objects.get(
                grado__orden=options["grado"], nombre=options["grupo"].upper(),
                ciclo_escolar__nombre=options["ciclo"],
            )
        except Grupo.DoesNotExist as error:
            raise CommandError("No existe ese grado, grupo y ciclo escolar.") from error
        try:
            with pdf.open("rb") as archivo:
                filas = extraer_lista_pdf(archivo, options["ciclo"], options["grado"], options["grupo"].upper())
        except ValueError as error:
            raise CommandError(str(error)) from error

        creados = omitidos = 0
        with transaction.atomic():
            for fila in filas:
                alumno, nuevo = Alumno.objects.get_or_create(
                    matricula=fila["matricula"],
                    defaults={**fila, "grupo": grupo, "codigo_qr": uuid4().hex},
                )
                if nuevo:
                    creados += 1
                    Inscripcion.objects.create(alumno=alumno, ciclo_escolar=grupo.ciclo_escolar, grupo=grupo)
                else:
                    omitidos += 1
                    if alumno.grupo_id != grupo.id:
                        self.stderr.write(f"Matricula {fila['matricula']} ya pertenece a otro grupo; no se modifico.")
        self.stdout.write(self.style.SUCCESS(
            f"{grupo} ({options['ciclo']}): {creados} creados, {omitidos} existentes."
        ))
