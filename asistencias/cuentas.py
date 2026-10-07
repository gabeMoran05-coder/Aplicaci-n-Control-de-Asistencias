import secrets

from django.contrib.auth.models import User
from django.db import transaction

from .models import Alumno, CuentaAlumno


@transaction.atomic
def emitir_acceso(alumno_id, restablecer=False):
    alumno = Alumno.objects.select_for_update().get(pk=alumno_id, activo=True)
    cuenta = CuentaAlumno.objects.select_related("usuario").filter(alumno=alumno).first()
    if cuenta and not restablecer:
        return None

    contrasena = secrets.token_urlsafe(12)
    if cuenta:
        usuario = cuenta.usuario
    else:
        username = f"alumno_{alumno.pk}"
        while User.objects.filter(username=username).exists():
            username = f"alumno_{alumno.pk}_{secrets.token_hex(2)}"
        usuario = User(username=username, first_name=alumno.nombres[:30])
    usuario.set_password(contrasena)
    usuario.save()
    if not cuenta:
        CuentaAlumno.objects.create(alumno=alumno, usuario=usuario)
    return {"alumno": alumno, "usuario": usuario.username, "contrasena": contrasena}
