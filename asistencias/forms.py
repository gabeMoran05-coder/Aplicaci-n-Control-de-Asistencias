from django import forms
from .models import Alumno, Grupo, Tutor


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
