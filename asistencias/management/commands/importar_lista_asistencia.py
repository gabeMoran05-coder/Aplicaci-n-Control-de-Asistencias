import re
from pathlib import Path
from uuid import uuid4

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from asistencias.models import Alumno, Grupo


PATRON_ALUMNO = re.compile(r"(?m)^(\d{1,2})\n(\d{9})\n([A-ZÁÉÍÓÚÑ ]+)\n")


def separar_nombre(nombre):
    partes = nombre.split()
    if len(partes) < 3:
        raise ValueError(f"Nombre incompleto: {nombre}")
    apellido_paterno = partes[0]
    if partes[1:4] == ["DE", "LA", "CRUZ"]:
        apellido_materno = "DE LA CRUZ"
        nombres = partes[4:]
    else:
        apellido_materno = partes[1]
        nombres = partes[2:]
    if not nombres:
        raise ValueError(f"Faltan nombres: {nombre}")
    return " ".join(nombres).title(), apellido_paterno.title(), apellido_materno.title()


class Command(BaseCommand):
    help = "Importa una lista escolar en PDF por número de control, sin reemplazar alumnos existentes."

    def add_arguments(self, parser):
        parser.add_argument("pdf", type=Path)
        parser.add_argument("--ciclo", required=True)
        parser.add_argument("--grado", type=int, required=True)
        parser.add_argument("--grupo", required=True)

    def handle(self, *args, **options):
        try:
            import pymupdf
        except ImportError as error:
            raise CommandError("Instala las dependencias de requirements.txt.") from error

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

        with pymupdf.open(pdf) as documento:
            texto = "\n".join(pagina.get_text() for pagina in documento)
        encabezado = re.compile(
            rf"(?m)^\s*{options['grado']}\n{re.escape(options['grupo'].upper())}\n"
            rf"[A-ZÁÉÍÓÚÑ]+\n{re.escape(options['ciclo'])}\n"
        )
        if not encabezado.search(texto):
            raise CommandError("El grado, grupo o ciclo no coincide con el encabezado del PDF.")
        filas = PATRON_ALUMNO.findall(texto)
        numeros = [int(numero) for numero, _, _ in filas]
        if not filas or numeros != list(range(1, len(filas) + 1)):
            raise CommandError("No se pudo leer una lista consecutiva completa; no se importó nada.")
        matriculas = [matricula for _, matricula, _ in filas]
        if len(matriculas) != len(set(matriculas)):
            raise CommandError("El PDF contiene números de control repetidos; no se importó nada.")

        creados = 0
        omitidos = 0
        with transaction.atomic():
            for _, matricula, nombre in filas:
                try:
                    nombres, paterno, materno = separar_nombre(nombre)
                except ValueError as error:
                    raise CommandError(str(error)) from error
                alumno, nuevo = Alumno.objects.get_or_create(
                    matricula=matricula,
                    defaults={
                        "nombres": nombres,
                        "apellido_paterno": paterno,
                        "apellido_materno": materno,
                        "grupo": grupo,
                        "codigo_qr": uuid4().hex,
                    },
                )
                if nuevo:
                    creados += 1
                else:
                    omitidos += 1
                    if alumno.grupo_id != grupo.id:
                        self.stderr.write(
                            f"Matrícula {matricula} ya pertenece a otro grupo; no se modificó."
                        )
        self.stdout.write(self.style.SUCCESS(
            f"{grupo} ({options['ciclo']}): {creados} creados, {omitidos} existentes."
        ))
