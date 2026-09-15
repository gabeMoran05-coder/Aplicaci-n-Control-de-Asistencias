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


class RegistroAsistencia(TimeStampedModel):
    class TipoRegistro(models.TextChoices):
        ENTRADA = "entrada", "Entrada"
        SALIDA = "salida", "Salida"

    class Estado(models.TextChoices):
        A_TIEMPO = "a_tiempo", "A tiempo"
        RETARDO = "retardo", "Retardo"
        JUSTIFICADO = "justificado", "Justificado"
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

