from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Alumno, CicloEscolar, Grado, Grupo, Tutor


class PrefectoCuentaForm(forms.ModelForm):
    metodo_contrasena = forms.ChoiceField(
        label="Contraseña",
        choices=[("generar", "Generar contraseña segura"), ("manual", "Escribir contraseña")],
        widget=forms.RadioSelect,
        initial="generar",
    )
    contrasena_manual = forms.CharField(
        label="Contraseña manual", required=False, strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    class Meta:
        model = get_user_model()
        fields = ["first_name", "last_name", "username"]
        labels = {"first_name": "Nombre", "last_name": "Apellidos", "username": "Usuario"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["metodo_contrasena"].choices = [
                ("conservar", "Conservar contraseña actual"),
                ("generar", "Generar nueva contraseña"),
                ("manual", "Escribir nueva contraseña"),
            ]
            self.fields["metodo_contrasena"].initial = "conservar"
        for nombre in ("first_name", "last_name", "username"):
            self.fields[nombre].required = True

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if get_user_model().objects.filter(username__iexact=username).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ese usuario ya existe.")
        return username

    def clean(self):
        data = super().clean()
        if data.get("metodo_contrasena") == "manual":
            contrasena = data.get("contrasena_manual")
            if not contrasena:
                self.add_error("contrasena_manual", "Escribe una contraseña.")
            elif len(contrasena) < 12:
                self.add_error("contrasena_manual", "Usa al menos 12 caracteres.")
            else:
                try:
                    validate_password(contrasena, user=self.instance)
                except ValidationError as error:
                    self.add_error("contrasena_manual", error)
        return data


class DestinoEscolarForm(forms.Form):
    ciclo = forms.ModelChoiceField(queryset=CicloEscolar.objects.none(), label="Ciclo escolar")
    grado = forms.ModelChoiceField(queryset=Grado.objects.filter(orden__in=[1, 2, 3]), label="Grado")
    letra = forms.ChoiceField(choices=[(letra, letra) for letra in "ABCD"], label="Grupo")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ciclo"].queryset = CicloEscolar.objects.filter(activo=True).order_by("-fecha_inicio")
        self.fields["ciclo"].initial = self.fields["ciclo"].queryset.first()

    def clean(self):
        data = super().clean()
        if all(data.get(key) for key in ("ciclo", "grado", "letra")):
            grupo = Grupo.objects.filter(
                ciclo_escolar=data["ciclo"], grado=data["grado"], nombre=data["letra"], activo=True
            ).first()
            if not grupo:
                self.add_error("letra", "Ese grupo no existe en el ciclo seleccionado.")
            else:
                data["grupo_destino"] = grupo
        return data


class AlumnoAltaForm(DestinoEscolarForm, forms.ModelForm):
    class Meta:
        model = Alumno
        fields = ["matricula", "nombres", "apellido_paterno", "apellido_materno",
                  "fecha_nacimiento", "foto", "contacto_emergencia_nombre", "contacto_emergencia_telefono"]
        widgets = {"fecha_nacimiento": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def clean_foto(self):
        foto = self.cleaned_data.get("foto")
        if foto and foto.size > 5 * 1024 * 1024:
            raise forms.ValidationError("La foto debe pesar menos de 5 MB.")
        return foto


class ListaPDFForm(DestinoEscolarForm):
    archivo = forms.FileField(label="Lista PDF")

    def clean_archivo(self):
        archivo = self.cleaned_data["archivo"]
        if not archivo.name.lower().endswith(".pdf") or archivo.size > 10 * 1024 * 1024:
            raise forms.ValidationError("Selecciona un PDF de hasta 10 MB.")
        return archivo


class CicloNuevoForm(forms.Form):
    nombre = forms.RegexField(regex=r"^\d{4}-\d{4}$", max_length=9, label="Nuevo ciclo")
    fecha_inicio = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), label="Inicio de clases")
    fecha_fin = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), label="Fin de clases")
    confirmar = forms.BooleanField(label="Confirmo la promocion y egreso de tercero")

    def __init__(self, *args, ciclo_origen=None, **kwargs):
        self.ciclo_origen = ciclo_origen
        super().__init__(*args, **kwargs)
        if ciclo_origen and ciclo_origen.nombre[:4].isdigit():
            year = int(ciclo_origen.nombre[:4]) + 1
            self.fields["nombre"].initial = f"{year}-{year + 1}"

    def clean(self):
        data = super().clean()
        nombre, inicio, fin = (data.get(key) for key in ("nombre", "fecha_inicio", "fecha_fin"))
        if nombre and int(nombre[:4]) + 1 != int(nombre[5:]):
            self.add_error("nombre", "El ciclo debe indicar anos consecutivos.")
        if nombre and inicio and int(nombre[:4]) != inicio.year:
            self.add_error("nombre", "El nombre debe comenzar con el ano de inicio.")
        if nombre and CicloEscolar.objects.filter(nombre=nombre).exists():
            self.add_error("nombre", "Ese ciclo ya existe.")
        if inicio and fin and inicio >= fin:
            self.add_error("fecha_fin", "La fecha final debe ser posterior al inicio.")
        if self.ciclo_origen and inicio and inicio <= self.ciclo_origen.fecha_fin:
            self.add_error("fecha_inicio", "El nuevo ciclo debe iniciar despues del anterior.")
        if self.ciclo_origen and inicio and inicio.year != self.ciclo_origen.fecha_inicio.year + 1:
            self.add_error("fecha_inicio", "Selecciona el ciclo siguiente al actual.")
        if inicio and inicio > timezone.localdate():
            self.add_error("fecha_inicio", "La promocion se realiza al iniciar el nuevo ciclo, no antes.")
        return data


class AlumnoEditarForm(forms.ModelForm):
    madre_nombre = forms.CharField(max_length=120, required=False, label="Nombre de la madre")
    madre_telefono = forms.CharField(max_length=20, required=False, label="Telefono de la madre")
    padre_nombre = forms.CharField(max_length=120, required=False, label="Nombre del padre")
    padre_telefono = forms.CharField(max_length=20, required=False, label="Telefono del padre")
    quitar_foto = forms.BooleanField(required=False, label="Quitar foto actual")

    class Meta:
        model = Alumno
        fields = ["nombres", "apellido_paterno", "apellido_materno", "matricula", "grupo",
                  "fecha_nacimiento", "tipo_sangre", "informacion_medica",
                  "contacto_emergencia_nombre", "contacto_emergencia_telefono", "foto"]
        widgets = {"fecha_nacimiento": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
                   "informacion_medica": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["grupo"].queryset = Grupo.objects.filter(activo=True).select_related("grado").order_by("grado__orden", "nombre")
        self.fields["fecha_nacimiento"].input_formats = ["%Y-%m-%d"]
        if self.instance.pk:
            for parentesco in (Tutor.Parentesco.MADRE, Tutor.Parentesco.PADRE):
                tutor = self.instance.tutores.filter(parentesco=parentesco, activo=True).first()
                if tutor:
                    self.fields[f"{parentesco}_nombre"].initial = tutor.nombre
                    self.fields[f"{parentesco}_telefono"].initial = tutor.telefono_whatsapp

    def clean_foto(self):
        foto = self.cleaned_data.get("foto")
        if foto and hasattr(foto, "size"):
            if foto.size > 5 * 1024 * 1024:
                raise forms.ValidationError("La foto debe pesar menos de 5 MB.")
            if getattr(foto, "image", None) and foto.image.format not in {"JPEG", "PNG", "WEBP"}:
                raise forms.ValidationError("Usa una foto JPG, PNG o WebP.")
        return foto

    def clean(self):
        data = super().clean()
        for parentesco in ("madre", "padre"):
            if data.get(f"{parentesco}_nombre") and not data.get(f"{parentesco}_telefono"):
                self.add_error(f"{parentesco}_telefono", "Captura un telefono para este tutor.")
            if data.get(f"{parentesco}_telefono") and not data.get(f"{parentesco}_nombre"):
                self.add_error(f"{parentesco}_nombre", "Captura el nombre de este tutor.")
        return data


class EventoEscolarForm(forms.Form):
    fecha = forms.DateField(input_formats=["%Y-%m-%d"])
    titulo = forms.CharField(max_length=100, strip=True)
    detalle = forms.CharField(max_length=300, required=False, strip=True)
