from django.core.management.base import BaseCommand
from django.utils import timezone

from asistencias.models import CicloEscolar, Grado, Grupo


class Command(BaseCommand):
    help = "Crea la estructura escolar base: 1ro a 3ro, grupos A a D."

    def handle(self, *args, **options):
        hoy = timezone.localdate()
        ciclo_nombre = f"{hoy.year}-{hoy.year + 1}"
        ciclo, ciclo_creado = CicloEscolar.objects.get_or_create(
            nombre=ciclo_nombre,
            defaults={
                "fecha_inicio": hoy.replace(month=8, day=1),
                "fecha_fin": hoy.replace(year=hoy.year + 1, month=7, day=15),
                "activo": True,
            },
        )

        if ciclo_creado:
            self.stdout.write(self.style.SUCCESS(f"Ciclo creado: {ciclo.nombre}"))
        else:
            self.stdout.write(f"Ciclo existente: {ciclo.nombre}")

        grados = [(1, "1ro"), (2, "2do"), (3, "3ro")]
        grupos = ["A", "B", "C", "D"]

        for orden, nombre in grados:
            grado, grado_creado = Grado.objects.get_or_create(
                orden=orden,
                defaults={"nombre": nombre},
            )
            if grado_creado:
                self.stdout.write(self.style.SUCCESS(f"Grado creado: {grado.nombre}"))

            for letra in grupos:
                grupo, grupo_creado = Grupo.objects.get_or_create(
                    grado=grado,
                    nombre=letra,
                    ciclo_escolar=ciclo,
                    defaults={"activo": True},
                )
                if grupo_creado:
                    self.stdout.write(self.style.SUCCESS(f"Grupo creado: {grupo}"))

        self.stdout.write(self.style.SUCCESS("Estructura escolar lista."))
