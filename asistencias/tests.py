import json
from datetime import timedelta

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Alumno, CicloEscolar, Grado, Grupo, RegistroAsistencia


class PrefecturaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        hoy = timezone.localdate()
        ciclo = CicloEscolar.objects.create(
            nombre="Pruebas", fecha_inicio=hoy - timedelta(days=30),
            fecha_fin=hoy + timedelta(days=300),
        )
        grado = Grado.objects.create(nombre="1ro", orden=1)
        grupo = Grupo.objects.create(grado=grado, nombre="A", ciclo_escolar=ciclo)
        cls.alumno = Alumno.objects.create(
            matricula="TEST-PREF-001", nombres="Ana", apellido_paterno="Lopez",
            grupo=grupo, codigo_qr="qr-test-prefecto",
        )
        prefectos = Group.objects.get(name="Prefectos")
        cls.prefecto_1 = User.objects.create_user(
            username="prefecto1", password="clave-prueba", first_name="Uno",
        )
        cls.prefecto_2 = User.objects.create_user(
            username="prefecto2", password="clave-prueba", first_name="Dos",
        )
        cls.ajeno = User.objects.create_user(username="ajeno", password="clave-prueba")
        cls.prefecto_1.groups.add(prefectos)
        cls.prefecto_2.groups.add(prefectos)

    def test_kiosco_cerrado_y_prefectura_requiere_acceso(self):
        self.assertEqual(self.client.get("/kiosco/").status_code, 404)
        self.assertEqual(self.client.get("/profesor/").status_code, 302)
        self.assertRedirects(
            self.client.get(reverse("asistencias:prefectos")),
            "/prefectos/ingresar/?next=/prefectos/",
        )
        self.client.force_login(self.ajeno)
        self.assertEqual(self.client.get(reverse("asistencias:prefectos")).status_code, 403)
        self.assertEqual(
            self.client.post(reverse("asistencias:registrar_prefecto"),
                             data=json.dumps({"codigo": self.alumno.codigo_qr}),
                             content_type="application/json").status_code,
            403,
        )

    def test_login_no_acepta_usuario_ajeno(self):
        response = self.client.post(
            reverse("asistencias:prefecto_login"),
            {"username": "ajeno", "password": "clave-prueba"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        self.client.force_login(self.prefecto_1)
        scanner = self.client.get(reverse("asistencias:prefectos"))
        self.assertContains(scanner, "Prefectura")
        self.assertContains(scanner, "Uno")
        self.assertContains(scanner, 'rel="manifest"')

    def test_escaneo_conserva_quien_registro_y_ajusto(self):
        url = reverse("asistencias:registrar_prefecto")
        payload = json.dumps({"codigo": self.alumno.codigo_qr})
        self.client.force_login(self.prefecto_1)
        response = self.client.post(url, data=payload, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tipo"], "registrado")
        self.assertEqual(response.json()["grado_orden"], 1)

        self.client.force_login(self.prefecto_2)
        repeated = self.client.post(url, data=payload, content_type="application/json")
        self.assertEqual(repeated.json()["tipo"], "repetido")
        registro = RegistroAsistencia.objects.get(alumno=self.alumno)
        self.assertEqual(registro.registrado_por, self.prefecto_1)
        self.assertIsNone(registro.modificado_por)

        self.client.post(reverse("asistencias:marcar_manual"), {
            "alumno_id": self.alumno.id, "fecha": str(timezone.localdate()),
            "estado": "retardo",
        })
        registro.refresh_from_db()
        self.assertEqual(registro.estado, RegistroAsistencia.Estado.RETARDO)
        self.assertEqual(registro.registrado_por, self.prefecto_1)
        self.assertEqual(registro.modificado_por, self.prefecto_2)
        profile = self.client.get(reverse("asistencias:perfil_alumno", args=[self.alumno.id]))
        self.assertContains(profile, "Detalles de asistencia")
        self.assertContains(profile, "Uno")
        self.assertContains(profile, "Dos")
        self.assertContains(profile, 'class="grade-1 can-manage"')

    def test_vista_publica_sin_controles_y_manifest(self):
        profile = self.client.get(reverse("asistencias:perfil_alumno", args=[self.alumno.id]))
        self.assertContains(profile, 'class="grade-1"')
        self.assertNotContains(profile, 'class="grade-1 can-manage"')
        manifest = self.client.get(reverse("asistencias:prefecto_manifest"))
        self.assertEqual(manifest.status_code, 200)
        self.assertEqual(manifest.json()["start_url"], "/prefectos/")
        self.assertEqual(len(manifest.json()["icons"]), 2)

    def test_reporte_ausencias_distingue_faltas_de_sin_registro(self):
        url = reverse("asistencias:reporte_ausencias")
        self.assertRedirects(self.client.get(url), f"/prefectos/ingresar/?next={url}")
        self.client.force_login(self.ajeno)
        self.assertEqual(self.client.get(url).status_code, 403)

        grupo = self.alumno.grupo
        pendiente = Alumno.objects.create(
            matricula="TEST-PEND-002", nombres="Beto", apellido_paterno="Martinez",
            grupo=grupo, codigo_qr="qr-test-pendiente",
        )
        RegistroAsistencia.objects.create(
            alumno=self.alumno, tipo=RegistroAsistencia.TipoRegistro.ENTRADA,
            fecha=timezone.localdate(), estado=RegistroAsistencia.Estado.AUSENTE,
            registrado_por=self.prefecto_1,
        )
        self.client.force_login(self.prefecto_1)
        response = self.client.get(url, {"grado": "1", "grupo": "A"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["totales"]["faltas"], 1)
        self.assertEqual(response.context["totales"]["sin_registro"], 1)
        self.assertEqual(response.context["secciones"][0]["faltas"], [self.alumno])
        self.assertEqual(response.context["secciones"][0]["sin_registro"], [pendiente])
        self.assertContains(response, "Imprimir / Guardar PDF")
        self.assertContains(response, "No se considera una falta confirmada")
        self.assertEqual(self.client.get(url, {"fecha": "fecha-invalida"}).status_code, 400)
        futuro = timezone.localdate() + timedelta(days=1)
        self.assertEqual(self.client.get(url, {"fecha": futuro.isoformat()}).status_code, 400)
