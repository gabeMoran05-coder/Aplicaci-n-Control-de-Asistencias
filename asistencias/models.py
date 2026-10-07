from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class CicloEscolar(TimeStampedModel):
    nombre = models.CharField(max_length=20, unique=True)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "ciclo escolar"
        verbose_name_plural = "ciclos escolares"
        ordering = ["-fecha_inicio"]

    def __str__(self):
        return self.nombre


class DiaEscolar(TimeStampedModel):
    class Tipo(models.TextChoices):
        SUSPENSION = "suspension", "Suspension oficial"
        VACACIONES = "vacaciones", "Vacaciones"
        RECESO = "receso", "Receso escolar"
        CONSEJO = "consejo", "Consejo Tecnico"
        REGISTRO = "registro", "Registro de calificaciones"
        INFORMATIVO = "informativo", "Actividad escolar"
        CANCELACION = "cancelacion", "Cancelacion de Direccion"

    ciclo_escolar = models.ForeignKey(CicloEscolar, on_delete=models.CASCADE, related_name="dias_escolares")
    fecha = models.DateField()
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    descripcion = models.CharField(max_length=160)
    registrado_por = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["fecha", "tipo"]
        constraints = [models.UniqueConstraint(fields=["ciclo_escolar", "fecha", "tipo"], name="dia_escolar_unico_por_tipo")]

    @property
    def sin_clases(self):
        return self.tipo != self.Tipo.INFORMATIVO


class EventoEscolar(TimeStampedModel):
    ciclo_escolar = models.ForeignKey(CicloEscolar, on_delete=models.CASCADE, related_name="eventos_escolares")
    fecha = models.DateField()
    titulo = models.CharField(max_length=100)
    detalle = models.CharField(max_length=300, blank=True)
    registrado_por = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["fecha", "titulo"]

    @property
    def descripcion(self):
        return self.titulo

    @property
    def tipo(self):
        return "evento"

    @property
    def sin_clases(self):
        return False


class Grado(TimeStampedModel):
    nombre = models.CharField(max_length=30, unique=True)
    orden = models.PositiveSmallIntegerField(unique=True)

    class Meta:
        verbose_name = "grado"
        verbose_name_plural = "grados"
        ordering = ["orden"]

    def __str__(self):
        return self.nombre


class Grupo(TimeStampedModel):
    grado = models.ForeignKey(Grado, on_delete=models.PROTECT, related_name="grupos")
    nombre = models.CharField(max_length=10)
    ciclo_escolar = models.ForeignKey(
        CicloEscolar,
        on_delete=models.PROTECT,
        related_name="grupos",
    )
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "grupo"
        verbose_name_plural = "grupos"
        ordering = ["grado__orden", "nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["grado", "nombre", "ciclo_escolar"],
                name="grupo_unico_por_ciclo",
            ),
        ]

    def __str__(self):
        return f"{self.grado} {self.nombre}"


class Tutor(TimeStampedModel):
    class Parentesco(models.TextChoices):
        MADRE = "madre", "Madre"
        PADRE = "padre", "Padre"
        TUTOR = "tutor", "Tutor"
        OTRO = "otro", "Otro"

    nombre = models.CharField(max_length=120)
    parentesco = models.CharField(
        max_length=20,
        choices=Parentesco.choices,
        default=Parentesco.TUTOR,
    )
    telefono_whatsapp = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    recibe_notificaciones = models.BooleanField(default=True)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "tutor"
        verbose_name_plural = "tutores"
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.nombre} ({self.get_parentesco_display()})"


class Alumno(TimeStampedModel):
    matricula = models.CharField(max_length=30, unique=True)
    nombres = models.CharField(max_length=80)
    apellido_paterno = models.CharField(max_length=80)
    apellido_materno = models.CharField(max_length=80, blank=True)
    fecha_nacimiento = models.DateField(null=True, blank=True)
    foto = models.ImageField(upload_to="alumnos/fotos/", blank=True)
    tipo_sangre = models.CharField(max_length=5, blank=True)
    informacion_medica = models.TextField(blank=True)
    contacto_emergencia_nombre = models.CharField(max_length=120, blank=True)
    contacto_emergencia_telefono = models.CharField(max_length=20, blank=True)
    grupo = models.ForeignKey(Grupo, on_delete=models.PROTECT, related_name="alumnos")
    tutores = models.ManyToManyField(Tutor, related_name="alumnos", blank=True)
    codigo_qr = models.CharField(max_length=80, unique=True)
    codigo_nfc = models.CharField(max_length=80, unique=True, null=True, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "alumno"
        verbose_name_plural = "alumnos"
        ordering = ["apellido_paterno", "apellido_materno", "nombres"]

    def __str__(self):
        return self.nombre_completo

    @property
    def nombre_completo(self):
        partes = [self.nombres, self.apellido_paterno, self.apellido_materno]
        return " ".join(parte for parte in partes if parte).strip()

    @property
    def edad(self):
        if not self.fecha_nacimiento:
            return None
        hoy = timezone.localdate()
        return (
            hoy.year
            - self.fecha_nacimiento.year
            - ((hoy.month, hoy.day) < (self.fecha_nacimiento.month, self.fecha_nacimiento.day))
        )

    @property
    def grado_nombre(self):
        return self.grupo.grado.nombre


class CuentaAlumno(TimeStampedModel):
    alumno = models.OneToOneField(Alumno, on_delete=models.CASCADE, related_name="cuenta")
    usuario = models.OneToOneField("auth.User", on_delete=models.CASCADE, related_name="cuenta_alumno")

    class Meta:
        verbose_name = "cuenta de alumno"
        verbose_name_plural = "cuentas de alumnos"

    def __str__(self):
        return self.alumno.nombre_completo


class RegistroAsistencia(TimeStampedModel):
    class TipoRegistro(models.TextChoices):
        ENTRADA = "entrada", "Entrada"
        SALIDA = "salida", "Salida"

    class Estado(models.TextChoices):
        A_TIEMPO = "a_tiempo", "A tiempo"
        RETARDO = "retardo", "Retardo"
        JUSTIFICADO = "justificado", "Justificado"
        AUSENTE = "ausente", "Ausente"
        MANUAL = "manual", "Manual"

    alumno = models.ForeignKey(
        Alumno,
        on_delete=models.PROTECT,
        related_name="registros_asistencia",
    )
    tipo = models.CharField(max_length=10, choices=TipoRegistro.choices)
    fecha = models.DateField(default=timezone.localdate)
    hora = models.TimeField(default=timezone.localtime)
    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.A_TIEMPO,
    )
    registrado_por = models.ForeignKey(
        "auth.User",
        on_delete=models.PROTECT,
        related_name="registros_asistencia",
        null=True,
        blank=True,
    )
    modificado_por = models.ForeignKey(
        "auth.User",
        on_delete=models.PROTECT,
        related_name="ajustes_asistencia",
        null=True,
        blank=True,
    )
    observaciones = models.TextField(blank=True)

    class Meta:
        verbose_name = "registro de asistencia"
        verbose_name_plural = "registros de asistencia"
        ordering = ["-fecha", "-hora"]
        constraints = [
            models.UniqueConstraint(
                fields=["alumno", "fecha", "tipo"],
                name="registro_unico_por_alumno_fecha_tipo",
            ),
        ]

    def __str__(self):
        return f"{self.alumno} - {self.get_tipo_display()} {self.fecha} {self.hora}"


class NotificacionWhatsApp(TimeStampedModel):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        ENVIADA = "enviada", "Enviada"
        FALLIDA = "fallida", "Fallida"

    registro = models.ForeignKey(
        RegistroAsistencia,
        on_delete=models.CASCADE,
        related_name="notificaciones_whatsapp",
    )
    tutor = models.ForeignKey(
        Tutor,
        on_delete=models.PROTECT,
        related_name="notificaciones_whatsapp",
    )
    telefono_destino = models.CharField(max_length=20)
    mensaje = models.TextField()
    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.PENDIENTE,
    )
    enviado_en = models.DateTimeField(null=True, blank=True)
    respuesta_proveedor = models.TextField(blank=True)

    class Meta:
        verbose_name = "notificacion de WhatsApp"
        verbose_name_plural = "notificaciones de WhatsApp"
        ordering = ["-creado_en"]

    def __str__(self):
        return f"{self.tutor} - {self.get_estado_display()}"



