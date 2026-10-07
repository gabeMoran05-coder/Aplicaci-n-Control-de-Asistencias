import os

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Crea el primer acceso de Direccion usando variables de entorno privadas."

    def handle(self, *args, **options):
        username = os.environ.get("DJANGO_BOOTSTRAP_USERNAME", "").strip()
        password = os.environ.get("DJANGO_BOOTSTRAP_PASSWORD", "")
        User = get_user_model()
        if not username or not password:
            if User.objects.filter(groups__name="Direccion", is_staff=True).exists():
                self.stdout.write("Ya existe una cuenta de Direccion; no se hicieron cambios.")
                return
            if os.environ.get("RENDER"):
                raise CommandError("Configura DJANGO_BOOTSTRAP_USERNAME y DJANGO_BOOTSTRAP_PASSWORD en Render.")
            self.stdout.write("Acceso inicial no configurado; no se hicieron cambios.")
            return
        if len(password) < 12:
            raise CommandError("La contrasena inicial debe tener al menos 12 caracteres.")

        existing = User.objects.filter(username=username).first()
        if existing:
            if not existing.groups.filter(name="Direccion").exists():
                raise CommandError("El usuario inicial ya existe sin acceso de Direccion.")
            self.stdout.write("La cuenta inicial ya existe; no se modifico su contrasena.")
            return
        user = User.objects.create_superuser(username=username, email="", password=password)
        user.groups.add(Group.objects.get(name="Direccion"))
        self.stdout.write("Acceso inicial de Direccion creado.")
