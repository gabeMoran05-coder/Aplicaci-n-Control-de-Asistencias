import json
import os
import tempfile
from datetime import date, timedelta
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from .cuentas import emitir_acceso
from .listas import extraer_lista_pdf, separar_nombre
from .ciclos import crear_ciclo_y_promover
from .models import Alumno, CicloEscolar, CuentaAlumno, DiaEscolar, EventoEscolar, Grado, Grupo, Inscripcion, NotificacionWhatsApp, RegistroAsistencia, Tutor


class PrefecturaTests(TestCase):
    def test_bootstrap_direccion_crea_acceso_solo_una_vez(self):
        with patch.dict(os.environ, {
            "DJANGO_BOOTSTRAP_USERNAME": "director-inicial",
            "DJANGO_BOOTSTRAP_PASSWORD": "ContrasenaTemporalSegura123",
        }):
            call_command("bootstrap_direccion", verbosity=0)
            call_command("bootstrap_direccion", verbosity=0)
        usuario = User.objects.get(username="director-inicial")
        self.assertTrue(usuario.check_password("ContrasenaTemporalSegura123"))
        self.assertTrue(usuario.groups.filter(name="Direccion").exists())
        self.assertTrue(usuario.is_staff)

    def test_importador_conserva_apellidos_compuestos(self):
        casos = {
            "CAMACHO DE LA CRUZ JOSE LUIS": ("Jose Luis", "Camacho", "De La Cruz"),
            "MORENO DE LEON CARLOS DANIEL": ("Carlos Daniel", "Moreno", "De Leon"),
            "DE COSS FARRERA CITLALI": ("Citlali", "De Coss", "Farrera"),
            "DE LA MORA MARTINEZ EDGAR GERARDO": ("Edgar Gerardo", "De La Mora", "Martinez"),
            "DEL VILLAR MARTINEZ LHEON": ("Lheon", "Del Villar", "Martinez"),
        }
        for nombre, esperado in casos.items():
            with self.subTest(nombre=nombre):
                self.assertEqual(separar_nombre(nombre), esperado)

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
            contacto_emergencia_nombre="Contacto Privado",
            contacto_emergencia_telefono="5550001234",
            informacion_medica="Alergia Privada",
        )
        prefectos = Group.objects.get(name="Prefectos")
        direccion = Group.objects.get(name="Direccion")
        cls.prefecto_1 = User.objects.create_user(
            username="prefecto1", password="clave-prueba", first_name="Uno",
        )
        cls.prefecto_2 = User.objects.create_user(
            username="prefecto2", password="clave-prueba", first_name="Dos",
        )
        cls.ajeno = User.objects.create_user(username="ajeno", password="clave-prueba")
        cls.director = User.objects.create_user(
            username="jorge.moran", password="clave-direccion-prueba",
            first_name="Jorge", last_name="Moran",
        )
        cls.director.groups.add(direccion)
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

    def test_direccion_puede_escanear_con_su_propia_cuenta(self):
        self.client.force_login(self.director)
        self.assertContains(self.client.get(reverse("asistencias:prefectos")), "Volver al panel")
        response = self.client.post(
            reverse("asistencias:registrar_prefecto"),
            data=json.dumps({"codigo": self.alumno.codigo_qr}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(RegistroAsistencia.objects.get(alumno=self.alumno).registrado_por, self.director)

    def test_prefecto_desactivado_no_puede_escanear(self):
        self.prefecto_1.is_active = False
        self.prefecto_1.save(update_fields=["is_active"])
        self.client.force_login(self.prefecto_1)
        self.assertNotEqual(self.client.get(reverse("asistencias:prefectos")).status_code, 200)
        self.assertNotEqual(self.client.post(
            reverse("asistencias:registrar_prefecto"),
            data=json.dumps({"codigo": self.alumno.codigo_qr}),
            content_type="application/json",
        ).status_code, 200)
        self.assertFalse(RegistroAsistencia.objects.filter(alumno=self.alumno).exists())

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
        self.assertEqual(
            self.client.get(reverse("asistencias:perfil_alumno", args=[self.alumno.id])).status_code,
            403,
        )
        self.client.force_login(self.director)
        profile = self.client.get(reverse("asistencias:perfil_alumno", args=[self.alumno.id]))
        self.assertContains(profile, 'class="compact-calendar grade-1"')
        self.assertNotContains(profile, 'class="attendance-details"')
        self.assertContains(profile, "Uno")
        self.assertContains(profile, "Dos")
        self.assertContains(profile, 'class="date-button')

    @override_settings(
        WHATSAPP_ENABLED=True,
        WHATSAPP_ACCESS_TOKEN="token-prueba",
        WHATSAPP_PHONE_NUMBER_ID="123456789",
        WHATSAPP_TEMPLATE_NAME="aviso_asistencia_escolar",
        WHATSAPP_TEMPLATE_LANGUAGE="es_MX",
        WHATSAPP_API_VERSION="v26.0",
        WHATSAPP_DEFAULT_COUNTRY_CODE="52",
    )
    def test_escaneo_envia_una_plantilla_a_padres_autorizados(self):
        madre = Tutor.objects.create(
            nombre="Maria", parentesco=Tutor.Parentesco.MADRE,
            telefono_whatsapp="5551234567", recibe_notificaciones=True,
        )
        padre = Tutor.objects.create(
            nombre="Pedro", parentesco=Tutor.Parentesco.PADRE,
            telefono_whatsapp="5551234567", recibe_notificaciones=True,
        )
        sin_permiso = Tutor.objects.create(
            nombre="Otra persona", telefono_whatsapp="5559876543",
            recibe_notificaciones=False,
        )
        self.alumno.tutores.add(madre, padre, sin_permiso)
        self.client.force_login(self.prefecto_1)
        url = reverse("asistencias:registrar_prefecto")
        payload = json.dumps({"codigo": self.alumno.codigo_qr})
        with patch("asistencias.whatsapp.urlopen") as enviar:
            enviar.return_value.__enter__.return_value = BytesIO(
                b'{"messages": [{"id": "wamid.prueba"}]}'
            )
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(self.client.post(url, payload, content_type="application/json").status_code, 200)
            self.assertEqual(enviar.call_count, 1)
            solicitud = enviar.call_args.args[0]
            cuerpo = json.loads(solicitud.data)
            self.assertEqual(cuerpo["to"], "525551234567")
            self.assertEqual(cuerpo["template"]["name"], "aviso_asistencia_escolar")
            self.assertEqual(cuerpo["template"]["components"][0]["parameters"][0]["text"], self.alumno.nombre_completo)
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(self.client.post(url, payload, content_type="application/json").json()["tipo"], "repetido")
            self.assertEqual(enviar.call_count, 1)
        aviso = NotificacionWhatsApp.objects.get(registro__alumno=self.alumno)
        self.assertEqual(aviso.estado, NotificacionWhatsApp.Estado.ENVIADA)
        self.assertEqual(aviso.respuesta_proveedor, "wamid.prueba")
        self.assertIsNotNone(aviso.enviado_en)

    @override_settings(
        WHATSAPP_ENABLED=True,
        WHATSAPP_ACCESS_TOKEN="token-prueba", WHATSAPP_PHONE_NUMBER_ID="123456789",
        WHATSAPP_TEMPLATE_NAME="aviso_asistencia_escolar", WHATSAPP_API_VERSION="v26.0",
        WHATSAPP_TEMPLATE_LANGUAGE="es_MX", WHATSAPP_DEFAULT_COUNTRY_CODE="52",
    )
    def test_fallo_de_meta_no_revierte_asistencia(self):
        from urllib.error import HTTPError

        tutor = Tutor.objects.create(
            nombre="Maria", telefono_whatsapp="5551234567", recibe_notificaciones=True,
        )
        self.alumno.tutores.add(tutor)
        self.client.force_login(self.prefecto_1)
        with patch("asistencias.whatsapp.urlopen", side_effect=HTTPError("https://graph.facebook.com", 400, "", {}, None)):
            with self.captureOnCommitCallbacks(execute=True):
                respuesta = self.client.post(
                    reverse("asistencias:registrar_prefecto"),
                    json.dumps({"codigo": self.alumno.codigo_qr}),
                    content_type="application/json",
                )
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(RegistroAsistencia.objects.filter(alumno=self.alumno).exists())
        self.assertEqual(NotificacionWhatsApp.objects.get(registro__alumno=self.alumno).estado,
                         NotificacionWhatsApp.Estado.FALLIDA)

    @override_settings(WHATSAPP_ENABLED=False)
    def test_sin_configuracion_no_se_crean_avisos_antiguos(self):
        tutor = Tutor.objects.create(
            nombre="Maria", telefono_whatsapp="5551234567", recibe_notificaciones=True,
        )
        self.alumno.tutores.add(tutor)
        self.client.force_login(self.prefecto_1)
        self.assertEqual(self.client.post(
            reverse("asistencias:registrar_prefecto"),
            json.dumps({"codigo": self.alumno.codigo_qr}), content_type="application/json",
        ).status_code, 200)
        self.assertFalse(NotificacionWhatsApp.objects.filter(registro__alumno=self.alumno).exists())

    def test_vista_publica_sin_controles_y_manifest(self):
        profile_url = reverse("asistencias:perfil_alumno", args=[self.alumno.id])
        self.assertRedirects(
            self.client.get(profile_url),
            f"/control/ingresar/?next={profile_url}",
        )
        self.assertRedirects(
            self.client.get(reverse("asistencias:credencial_alumno", args=[self.alumno.id])),
            f"/control/ingresar/?next=/alumnos/{self.alumno.id}/credencial/",
        )
        qr_url = reverse("asistencias:alumno_publico", args=[self.alumno.codigo_qr])
        self.assertRedirects(self.client.get(qr_url), f"/estudiantes/ingresar/?next={qr_url}")
        acceso = emitir_acceso(self.alumno.pk)
        self.assertTrue(self.client.login(username=acceso["usuario"], password=acceso["contrasena"]))
        self.assertRedirects(self.client.get(qr_url), reverse("asistencias:portal_alumno"))
        portal = self.client.get(reverse("asistencias:portal_alumno"))
        self.assertContains(portal, "Ana")
        self.assertContains(portal, 'class="compact-calendar grade-1"')
        for privado in ("Contacto de emergencia", "Contacto Privado", "5550001234", "Alergia Privada", self.alumno.matricula):
            self.assertNotContains(portal, privado)
        manifest = self.client.get(reverse("asistencias:prefecto_manifest"))
        self.assertEqual(manifest.status_code, 200)
        self.assertEqual(manifest.json()["start_url"], "/prefectos/")
        self.assertEqual(len(manifest.json()["icons"]), 2)
        self.assertEqual(self.client.get(reverse("asistencias:estudiante_manifest")).json()["start_url"], "/estudiantes/")

    def test_cuentas_alumnos_solo_direccion_y_contrasenas_no_reutilizadas(self):
        url = reverse("asistencias:cuentas_alumnos")
        self.assertRedirects(self.client.get(url), f"/control/ingresar/?next={url}")
        self.client.force_login(self.prefecto_1)
        self.assertEqual(self.client.post(url, {"accion": "crear_faltantes"}).status_code, 403)
        self.client.force_login(self.director)
        response = self.client.post(url, {"accion": "crear_faltantes"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["accesos"]), 1)
        acceso = response.context["accesos"][0]
        cuenta = CuentaAlumno.objects.get(alumno=self.alumno)
        self.assertNotEqual(cuenta.usuario.password, acceso["contrasena"])
        self.assertTrue(cuenta.usuario.check_password(acceso["contrasena"]))
        self.assertEqual(len(self.client.post(url, {"accion": "crear_faltantes"}).context["accesos"]), 0)
        nuevo = self.client.post(url, {"accion": "restablecer", "alumno_id": self.alumno.pk}).context["accesos"][0]
        cuenta.usuario.refresh_from_db()
        self.assertFalse(cuenta.usuario.check_password(acceso["contrasena"]))
        self.assertTrue(cuenta.usuario.check_password(nuevo["contrasena"]))

    def test_estudiante_solo_ve_su_propio_historial(self):
        otro = Alumno.objects.create(
            matricula="TEST-OTRO-002", nombres="Beto", apellido_paterno="Martinez",
            grupo=self.alumno.grupo, codigo_qr="qr-test-otro",
        )
        acceso = emitir_acceso(self.alumno.pk)
        emitir_acceso(otro.pk)
        login = reverse("asistencias:estudiante_login")
        denegado = self.client.post(login, {"username": "prefecto1", "password": "clave-prueba"})
        self.assertEqual(denegado.status_code, 200)
        self.assertFalse(denegado.wsgi_request.user.is_authenticated)
        self.assertTrue(self.client.login(username=acceso["usuario"], password=acceso["contrasena"]))
        self.assertEqual(self.client.get(reverse("asistencias:alumno_publico", args=[otro.codigo_qr])).status_code, 403)
        self.assertEqual(self.client.get(reverse("asistencias:vista_alumno", args=[otro.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("asistencias:perfil_alumno", args=[otro.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("asistencias:cuentas_alumnos")).status_code, 403)
        portal = self.client.get(reverse("asistencias:portal_alumno"))
        self.assertEqual(portal.status_code, 200)
        self.assertContains(portal, "Ana")
        self.assertNotContains(portal, "Beto")
        self.assertIn("no-store", portal.headers["Cache-Control"])

    def test_reporte_ausencias_distingue_faltas_de_sin_registro(self):
        url = reverse("asistencias:reporte_ausencias")
        self.assertRedirects(self.client.get(url), f"/control/ingresar/?next={url}")
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
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.director)
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

    def test_direccion_login_y_salida_protegen_directorio(self):
        control = reverse("asistencias:control")
        login = reverse("asistencias:direccion_login")
        self.assertRedirects(self.client.get(control), f"{login}?next={control}")

        self.assertRedirects(self.client.get(reverse("asistencias:inicio")),
                             f"{login}?next=/")
        response = self.client.post(login, {
            "username": "prefecto1", "password": "clave-prueba",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        self.client.force_login(self.prefecto_1)
        self.assertEqual(self.client.get(control).status_code, 403)
        self.client.logout()
        self.assertTrue(self.client.login(username="jorge.moran", password="clave-direccion-prueba"))
        response = self.client.get(control)
        self.assertContains(response, "Directorio escolar")
        self.assertContains(response, "Salir")
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertContains(
            self.client.get(reverse("asistencias:perfil_alumno", args=[self.alumno.id])),
            "Alergia Privada",
        )
        self.assertEqual(self.client.get(reverse("asistencias:direccion_logout")).status_code, 405)
        salida = self.client.post(reverse("asistencias:direccion_logout"))
        self.assertRedirects(salida, login)
        self.assertRedirects(self.client.get(control), f"{login}?next={control}")

    def test_panel_visual_conserva_qr_impresion_y_navegacion(self):
        self.client.force_login(self.director)
        for nombre in ("control", "calendario_escolar", "cuentas_alumnos", "reporte_ausencias"):
            pagina = self.client.get(reverse(f"asistencias:{nombre}"))
            self.assertEqual(pagina.status_code, 200)
            self.assertContains(pagina, "asistencias/dashboard")
            self.assertNotContains(pagina, 'class="dashboard-sidebar"')
            self.assertContains(pagina, reverse("asistencias:direccion_logout"))
        perfil = self.client.get(reverse("asistencias:perfil_alumno", args=[self.alumno.pk]))
        self.assertContains(perfil, reverse("asistencias:qr_alumno", args=[self.alumno.pk]))
        self.assertContains(perfil, reverse("asistencias:vista_alumno", args=[self.alumno.pk]))
        self.assertContains(perfil, reverse("asistencias:credencial_alumno", args=[self.alumno.pk]))
        credencial = self.client.get(reverse("asistencias:credencial_alumno", args=[self.alumno.pk]))
        self.assertContains(credencial, 'window.print()')
        self.assertContains(credencial, reverse("asistencias:qr_alumno", args=[self.alumno.pk]))
        self.assertContains(credencial, "asistencias/credencial")
        self.assertContains(credencial, "asistencias/escuela-fmptm")
        self.assertContains(credencial, "asistencias/colima-escudo")
        self.assertContains(credencial, "Contacto Privado")
        self.assertContains(credencial, "5550001234")
        self.assertContains(credencial, 'class="card front grade-1"')
        self.assertContains(credencial, 'class="card back grade-1"')

    def test_direccion_puede_previsualizar_portal_sin_abrirlo_a_otros(self):
        vista = reverse("asistencias:vista_alumno", args=[self.alumno.pk])
        qr = reverse("asistencias:alumno_publico", args=[self.alumno.codigo_qr])
        self.assertRedirects(self.client.get(vista), f"/control/ingresar/?next={vista}")
        self.client.force_login(self.director)
        pagina = self.client.get(vista)
        self.assertContains(pagina, "Vista previa del alumno")
        self.assertContains(pagina, reverse("asistencias:perfil_alumno", args=[self.alumno.pk]))
        self.assertNotContains(pagina, reverse("asistencias:estudiante_logout"))
        self.assertRedirects(self.client.get(qr), vista)
        self.client.force_login(self.prefecto_1)
        self.assertEqual(self.client.get(vista).status_code, 403)

    def test_directorio_abre_perfil_y_ordenamiento(self):
        self.client.force_login(self.director)
        pagina = self.client.get(reverse("asistencias:control"))
        self.assertContains(pagina, reverse("asistencias:perfil_alumno", args=[self.alumno.pk]))
        self.assertContains(pagina, "asistencias/directorio")
        self.assertContains(pagina, 'data-sort="0"')
        self.assertContains(pagina, 'data-sort="4"')

    def test_direccion_edita_datos_y_tutores(self):
        ruta = reverse("asistencias:editar_alumno", args=[self.alumno.pk])
        self.assertEqual(self.client.get(ruta).status_code, 302)
        self.client.force_login(self.prefecto_1)
        self.assertEqual(self.client.get(ruta).status_code, 403)
        self.client.force_login(self.director)
        response = self.client.post(ruta, {
            "nombres": "Ana Maria", "apellido_paterno": "Lopez", "apellido_materno": "Rios",
            "matricula": self.alumno.matricula, "grupo": self.alumno.grupo_id,
            "fecha_nacimiento": "2012-04-12", "tipo_sangre": "O+",
            "informacion_medica": "Alergia", "contacto_emergencia_nombre": "Contacto",
            "contacto_emergencia_telefono": "5550011223",
            "madre_nombre": "Maria Lopez", "madre_telefono": "5551234567",
            "madre_notificar": "on",
            "padre_nombre": "", "padre_telefono": "",
        })
        self.assertRedirects(response, reverse("asistencias:perfil_alumno", args=[self.alumno.pk]))
        self.alumno.refresh_from_db()
        self.assertEqual(self.alumno.nombres, "Ana Maria")
        self.assertEqual(self.alumno.tipo_sangre, "O+")
        self.assertTrue(self.alumno.tutores.filter(parentesco=Tutor.Parentesco.MADRE, nombre="Maria Lopez").exists())
        self.assertTrue(self.alumno.tutores.get(parentesco=Tutor.Parentesco.MADRE).recibe_notificaciones)

    def test_foto_privada_y_visible_en_credencial(self):
        image = BytesIO()
        Image.new("RGB", (50, 60), "blue").save(image, format="JPEG")
        foto = SimpleUploadedFile("foto.jpg", image.getvalue(), content_type="image/jpeg")
        ruta = reverse("asistencias:editar_alumno", args=[self.alumno.pk])
        foto_ruta = reverse("asistencias:foto_alumno", args=[self.alumno.pk])
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            self.client.force_login(self.director)
            response = self.client.post(ruta, {
                "nombres": self.alumno.nombres, "apellido_paterno": self.alumno.apellido_paterno,
                "apellido_materno": "", "matricula": self.alumno.matricula,
                "grupo": self.alumno.grupo_id, "fecha_nacimiento": "", "tipo_sangre": "",
                "informacion_medica": "", "contacto_emergencia_nombre": "",
                "contacto_emergencia_telefono": "", "madre_nombre": "", "madre_telefono": "",
                "padre_nombre": "", "padre_telefono": "", "foto": foto,
            })
            self.assertEqual(response.status_code, 302)
            foto_response = self.client.get(foto_ruta)
            self.assertEqual(foto_response.status_code, 200)
            self.assertEqual(foto_response["Content-Type"], "image/jpeg")
            foto_response.close()
            self.assertContains(self.client.get(reverse("asistencias:credencial_alumno", args=[self.alumno.pk])), foto_ruta)
            self.client.logout()
            self.assertEqual(self.client.get(foto_ruta).status_code, 302)

    def test_accesos_comparten_control_de_contrasena(self):
        for nombre in ("direccion_login", "prefecto_login", "estudiante_login"):
            pagina = self.client.get(reverse(f"asistencias:{nombre}"))
            self.assertEqual(pagina.status_code, 200)
            self.assertContains(pagina, "asistencias/login")
            self.assertContains(pagina, 'class="password-toggle"')
            self.assertContains(pagina, 'type="password"')
            self.assertContains(pagina, 'type="button"')

    def test_calendario_oficial_y_fines_de_semana(self):
        ciclo = CicloEscolar.objects.get(nombre="2026-2027")
        self.assertEqual(ciclo.fecha_inicio, date(2026, 8, 31))
        self.assertEqual(ciclo.fecha_fin, date(2027, 7, 9))
        cierres = set(DiaEscolar.objects.filter(ciclo_escolar=ciclo).exclude(tipo="informativo").values_list("fecha", flat=True))
        dia, lectivos = ciclo.fecha_inicio, 0
        while dia <= ciclo.fecha_fin:
            lectivos += dia.weekday() < 5 and dia not in cierres
            dia += timedelta(days=1)
        self.assertEqual(lectivos, 185)
        self.assertTrue(DiaEscolar.objects.filter(ciclo_escolar=ciclo, fecha=date(2026, 10, 30), tipo="consejo").exists())
        self.alumno.grupo.ciclo_escolar = ciclo
        self.alumno.grupo.save(update_fields=["ciclo_escolar"])
        self.client.force_login(self.director)
        profile = self.client.get(reverse("asistencias:perfil_alumno", args=[self.alumno.pk]), {"mes": "2026-10"})
        self.assertContains(profile, 'class="date-button fin_semana"')
        self.assertContains(profile, "Consejo Tecnico Escolar")
        self.assertNotContains(profile, 'name="fecha" value="2026-10-30"')
        calendar_page = self.client.get(reverse("asistencias:calendario_escolar"), {"ciclo": ciclo.pk, "mes": "2026-10"})
        self.assertContains(calendar_page, "Consejo Tecnico Escolar")
        self.assertContains(calendar_page, 'class="day weekend"')
        self.assertContains(calendar_page, 'role="tablist"')

    def test_dialogo_calendario_y_registros_del_mes(self):
        ciclo = CicloEscolar.objects.get(nombre="2026-2027")
        octubre = DiaEscolar.objects.create(
            ciclo_escolar=ciclo, fecha=date(2026, 10, 21),
            tipo=DiaEscolar.Tipo.CANCELACION, descripcion="Huracan: Alerta",
            registrado_por=self.director,
        )
        noviembre = DiaEscolar.objects.create(
            ciclo_escolar=ciclo, fecha=date(2026, 11, 4),
            tipo=DiaEscolar.Tipo.CANCELACION, descripcion="Sismo: Revision",
            registrado_por=self.director,
        )
        self.client.force_login(self.director)
        url = reverse("asistencias:calendario_escolar")
        respuesta = self.client.get(url, {"ciclo": ciclo.pk, "mes": "2026-10"})
        self.assertContains(respuesta, 'id="calendar-editor"')
        self.assertContains(respuesta, 'id="cancel-editor"')
        self.assertContains(respuesta, 'id="event-editor"')
        self.assertContains(respuesta, "asistencias/direccion_calendar")
        self.assertContains(respuesta, "Cancelaciones de octubre")
        self.assertEqual(list(respuesta.context["cancelaciones_mes"]), [octubre])
        respuesta = self.client.get(url, {"ciclo": ciclo.pk, "mes": "2026-11"})
        self.assertContains(respuesta, "Cancelaciones de noviembre")
        self.assertEqual(list(respuesta.context["cancelaciones_mes"]), [noviembre])

    def test_solo_direccion_cancela_y_restaura(self):
        ciclo = CicloEscolar.objects.get(nombre="2026-2027")
        self.alumno.grupo.ciclo_escolar = ciclo
        self.alumno.grupo.save(update_fields=["ciclo_escolar"])
        url = reverse("asistencias:cancelar_dia")
        payload = {"ciclo_id": ciclo.pk, "fecha": "2026-10-02", "motivo": "huracan", "nota": "Alerta local"}
        self.client.force_login(self.prefecto_1)
        self.assertEqual(self.client.post(url, payload).status_code, 403)
        self.client.force_login(self.director)
        self.assertEqual(self.client.post(url, payload).status_code, 302)
        cierre = DiaEscolar.objects.get(ciclo_escolar=ciclo, fecha=date(2026, 10, 2), tipo="cancelacion")
        self.assertEqual(cierre.registrado_por, self.director)
        self.assertIn("Alerta local", cierre.descripcion)
        self.client.force_login(self.prefecto_1)
        self.assertEqual(self.client.post(reverse("asistencias:marcar_manual"), {
            "alumno_id": self.alumno.pk, "fecha": "2026-10-02", "estado": "ausente",
        }).status_code, 409)
        self.client.force_login(self.director)
        self.assertEqual(self.client.post(url, {**payload, "fecha": "2026-10-30"}).status_code, 409)
        RegistroAsistencia.objects.create(alumno=self.alumno, fecha=date(2026, 10, 2),
                                          tipo="entrada", estado="ausente", registrado_por=self.prefecto_1)
        report = self.client.get(reverse("asistencias:reporte_ausencias"), {"fecha": "2026-10-02"})
        self.assertEqual(report.context["totales"]["sin_registro"], 0)
        self.assertEqual(report.context["totales"]["faltas"], 0)
        self.assertContains(report, "Alerta local")
        profile = self.client.get(reverse("asistencias:perfil_alumno", args=[self.alumno.pk]), {"mes": "2026-10"})
        self.assertEqual(profile.context["resumen"]["ausentes"], 0)
        self.assertEqual(self.client.post(reverse("asistencias:restaurar_dia"), {"ciclo_id": ciclo.pk, "fecha": "2026-10-02"}).status_code, 302)
        self.assertFalse(DiaEscolar.objects.filter(pk=cierre.pk).exists())

    def test_direccion_gestiona_eventos_y_alumnos_los_ven(self):
        ciclo = CicloEscolar.objects.get(nombre="2026-2027")
        self.alumno.grupo.ciclo_escolar = ciclo
        self.alumno.grupo.save(update_fields=["ciclo_escolar"])
        guardar = reverse("asistencias:guardar_evento")
        eliminar = reverse("asistencias:eliminar_evento")
        datos = {"ciclo_id": ciclo.pk, "fecha": "2026-10-08", "titulo": "Feria de ciencias", "detalle": "Patio central"}
        self.client.force_login(self.prefecto_1)
        self.assertEqual(self.client.post(guardar, datos).status_code, 403)
        self.client.force_login(self.director)
        self.assertEqual(self.client.post(guardar, datos).status_code, 302)
        evento = EventoEscolar.objects.get(ciclo_escolar=ciclo, titulo="Feria de ciencias")
        self.assertEqual(evento.registrado_por, self.director)
        self.assertEqual(self.client.post(guardar, {**datos, "evento_id": evento.pk, "titulo": "Feria escolar"}).status_code, 302)
        evento.refresh_from_db()
        self.assertEqual(evento.titulo, "Feria escolar")
        self.assertEqual(self.client.post(guardar, {**datos, "titulo": "", "evento_id": ""}).status_code, 400)
        self.assertEqual(self.client.post(guardar, {**datos, "fecha": "2027-08-01"}).status_code, 404)
        profile = self.client.get(reverse("asistencias:perfil_alumno", args=[self.alumno.pk]), {"mes": "2026-10"})
        self.assertContains(profile, "Feria escolar")
        acceso = emitir_acceso(self.alumno.pk)
        self.assertTrue(self.client.login(username=acceso["usuario"], password=acceso["contrasena"]))
        portal = self.client.get(reverse("asistencias:portal_alumno"), {"mes": "2026-10"})
        self.assertContains(portal, "Feria escolar")
        self.client.force_login(self.prefecto_1)
        self.assertEqual(self.client.post(eliminar, {"ciclo_id": ciclo.pk, "evento_id": evento.pk}).status_code, 403)
        self.client.force_login(self.director)
        self.assertEqual(self.client.post(eliminar, {"ciclo_id": ciclo.pk, "evento_id": evento.pk}).status_code, 302)
        self.assertFalse(EventoEscolar.objects.filter(pk=evento.pk).exists())
        self.assertTrue(DiaEscolar.objects.filter(ciclo_escolar=ciclo, fecha=date(2026, 10, 30), tipo="consejo").exists())


class GestionEscolarTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ciclo = CicloEscolar.objects.get(nombre="2026-2027")
        cls.grados = [Grado.objects.get_or_create(orden=orden, defaults={"nombre": nombre})[0]
                      for orden, nombre in [(1, "1ro"), (2, "2do"), (3, "3ro")]]
        cls.grupos = [Grupo.objects.get_or_create(
            ciclo_escolar=cls.ciclo, grado=grado, nombre=letra
        )[0] for grado, letra in zip(cls.grados, "ABC")]
        cls.director = User.objects.create_user(username="director-gestion", password="clave-prueba")
        cls.director.groups.add(Group.objects.get(name="Direccion"))
        cls.ajeno = User.objects.create_user(username="ajeno-gestion", password="clave-prueba")

    def test_alta_individual_protegida_crea_cuenta_e_inscripcion(self):
        url = reverse("asistencias:agregar_alumno")
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.ajeno)
        self.assertEqual(self.client.post(url, {}).status_code, 403)
        self.client.force_login(self.director)
        response = self.client.post(url, {
            "ciclo": self.ciclo.pk, "grado": self.grados[0].pk, "letra": "A",
            "matricula": "123456789", "nombres": "Ana", "apellido_paterno": "Lopez",
            "apellido_materno": "Martinez",
            "madre_nombre": "Maria Lopez", "madre_telefono": "5551234567", "madre_notificar": "on",
            "padre_nombre": "Pedro Lopez", "padre_telefono": "5559876543",
        })
        self.assertEqual(response.status_code, 200)
        alumno = Alumno.objects.get(matricula="123456789")
        self.assertEqual(alumno.grupo, self.grupos[0])
        self.assertEqual(Inscripcion.objects.get(alumno=alumno).grupo, self.grupos[0])
        self.assertTrue(alumno.tutores.get(parentesco=Tutor.Parentesco.MADRE).recibe_notificaciones)
        self.assertFalse(alumno.tutores.get(parentesco=Tutor.Parentesco.PADRE).recibe_notificaciones)
        self.assertTrue(alumno.cuenta.usuario.check_password(response.context["acceso"]["contrasena"]))
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_importacion_pdf_con_vista_previa_y_conflictos(self):
        import pymupdf

        documento = pymupdf.open()
        pagina = documento.new_page()
        pagina.insert_text((40, 40), "ESCUELA\n1\nA\nMATUTINO\n2026-2027\n1\n123456789\nLOPEZ MARTINEZ ANA\n2\n987654321\nPEREZ GOMEZ LUIS", fontsize=11)
        contenido = documento.tobytes()
        documento.close()
        with BytesIO(contenido) as archivo:
            self.assertEqual(len(extraer_lista_pdf(archivo, "2026-2027", 1, "A")), 2)
        url = reverse("asistencias:importar_lista")
        self.client.force_login(self.director)
        response = self.client.post(url, {
            "ciclo": self.ciclo.pk, "grado": self.grados[0].pk, "letra": "A",
            "archivo": SimpleUploadedFile("lista.pdf", contenido, content_type="application/pdf"),
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["vista"]), 2)
        self.assertFalse(Alumno.objects.filter(matricula="123456789").exists())
        token = response.context["vista_previa"]
        confirmacion = self.client.post(url, {"accion": "confirmar", "vista_previa": token})
        self.assertEqual(confirmacion.context["resultado"]["creados"], 2)
        self.assertEqual(Inscripcion.objects.filter(ciclo_escolar=self.ciclo).count(), 2)
        self.assertEqual(len(confirmacion.context["accesos"]), 2)
        repetida = self.client.post(url, {"accion": "confirmar", "vista_previa": token})
        self.assertEqual(repetida.context["resultado"]["creados"], 0)

        alumno = Alumno.objects.get(matricula="123456789")
        alumno.grupo = self.grupos[1]
        alumno.save(update_fields=["grupo"])
        conflicto = self.client.post(url, {"accion": "confirmar", "vista_previa": token})
        self.assertIn("otro grupo", conflicto.context["error"])

    def test_gestion_de_listas_y_ciclos_requiere_direccion(self):
        for nombre in ("importar_lista", "ciclos_escolares"):
            url = reverse(f"asistencias:{nombre}")
            self.assertEqual(self.client.get(url).status_code, 302)
            self.client.force_login(self.ajeno)
            self.assertEqual(self.client.get(url).status_code, 403)
            self.client.force_login(self.director)
            self.assertEqual(self.client.get(url).status_code, 200)
            self.client.logout()

    def test_ciclo_no_promueve_antes_de_iniciar(self):
        with patch("asistencias.ciclos.timezone.localdate", return_value=date(2027, 7, 20)):
            with self.assertRaisesMessage(Exception, "cuando inicia el nuevo ciclo"):
                crear_ciclo_y_promover(self.ciclo, "2027-2028", date(2027, 8, 30), date(2028, 7, 7))
        self.assertFalse(CicloEscolar.objects.filter(nombre="2027-2028").exists())

    def test_promocion_conserva_historial_y_egresa_tercero(self):
        alumnos = []
        for indice, grupo in enumerate(self.grupos):
            alumno = Alumno.objects.create(
                matricula=f"TEST-PROM-{indice}", nombres=f"Alumno{indice}",
                apellido_paterno="Prueba", grupo=grupo, codigo_qr=f"qr-prom-{indice}",
            )
            Inscripcion.objects.create(alumno=alumno, ciclo_escolar=self.ciclo, grupo=grupo)
            alumnos.append(alumno)
        cuenta = emitir_acceso(alumnos[0].pk)
        RegistroAsistencia.objects.create(
            alumno=alumnos[0], fecha=date(2026, 10, 1), tipo="entrada", estado="a_tiempo"
        )
        with patch("asistencias.ciclos.timezone.localdate", return_value=date(2027, 8, 30)):
            nuevo, promovidos, egresados = crear_ciclo_y_promover(
                self.ciclo, "2027-2028", date(2027, 8, 30), date(2028, 7, 7)
            )
        self.assertEqual((promovidos, egresados), (2, 1))
        self.assertEqual(Grupo.objects.filter(ciclo_escolar=nuevo).count(), 12)
        for indice, alumno in enumerate(alumnos):
            alumno.refresh_from_db()
            if indice < 2:
                self.assertEqual(alumno.grupo.grado.orden, indice + 2)
                self.assertEqual(alumno.grupo.nombre, "AB"[indice])
                self.assertEqual(alumno.inscripciones.count(), 2)
            else:
                self.assertFalse(alumno.activo)
                self.assertEqual(alumno.inscripciones.count(), 1)
        self.assertTrue(alumnos[0].cuenta.usuario.check_password(cuenta["contrasena"]))
        self.client.force_login(self.director)
        report = self.client.get(reverse("asistencias:reporte_ausencias"), {"fecha": "2026-10-01"})
        self.assertEqual(report.context["totales"]["alumnos"], 3)
        self.assertEqual(report.context["totales"]["presentes"], 1)
        perfil = self.client.get(reverse("asistencias:perfil_alumno", args=[alumnos[0].pk]), {"mes": "2026-10"})
        self.assertEqual(perfil.context["resumen"]["presentes"], 1)


class GestionPrefectosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.grupo_prefectos = Group.objects.get(name="Prefectos")
        cls.director = User.objects.create_user(username="director-prueba", password="ClaveDirector12345")
        cls.director.groups.add(Group.objects.get(name="Direccion"))
        cls.ajeno = User.objects.create_user(username="ajeno-prueba", password="ClaveAjena12345")

    def datos(self, username="prefecto-nuevo", metodo="generar", contrasena=""):
        return {
            "first_name": "Ana", "last_name": "Lopez", "username": username,
            "metodo_contrasena": metodo, "contrasena_manual": contrasena,
        }

    def test_solo_direccion_puede_gestionar_cuentas(self):
        url = reverse("asistencias:gestionar_prefectos")
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.ajeno)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, self.datos()).status_code, 403)
        self.client.force_login(self.director)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_generacion_y_cambio_de_contrasena(self):
        self.client.force_login(self.director)
        response = self.client.post(reverse("asistencias:gestionar_prefectos"), self.datos())
        self.assertEqual(response.status_code, 200)
        clave = response.context["acceso"]["contrasena"]
        prefecto = User.objects.get(username="prefecto-nuevo")
        self.assertTrue(prefecto.check_password(clave))
        self.assertNotEqual(prefecto.password, clave)
        self.assertTrue(prefecto.groups.filter(name="Prefectos").exists())
        self.assertNotContains(self.client.get(reverse("asistencias:gestionar_prefectos")), clave)

        editar = reverse("asistencias:editar_prefecto", args=[prefecto.pk])
        datos = self.datos(metodo="manual", contrasena="OtraClaveSegura123")
        datos["first_name"] = "Adriana"
        self.assertEqual(self.client.post(editar, datos).status_code, 302)
        prefecto.refresh_from_db()
        self.assertEqual(prefecto.first_name, "Adriana")
        self.assertTrue(prefecto.check_password("OtraClaveSegura123"))
        self.assertFalse(prefecto.check_password(clave))

    def test_clave_debil_y_usuario_repetido_se_rechazan(self):
        self.client.force_login(self.director)
        url = reverse("asistencias:gestionar_prefectos")
        response = self.client.post(url, self.datos(metodo="manual", contrasena="corta"))
        self.assertContains(response, "12 caracteres")
        self.assertFalse(User.objects.filter(username="prefecto-nuevo").exists())
        self.client.post(url, self.datos(metodo="manual", contrasena="ClavePrefectoSegura123"))
        response = self.client.post(url, self.datos(username="PREFECTO-NUEVO"))
        self.assertContains(response, "Ese usuario ya existe")

    def test_prefectos_sin_limite_y_reactivacion(self):
        self.client.force_login(self.director)
        url = reverse("asistencias:gestionar_prefectos")
        for indice in range(3):
            self.client.post(url, self.datos(username=f"prefecto-{indice}"))
        self.assertEqual(User.objects.filter(groups=self.grupo_prefectos, is_active=True).count(), 3)
        response = self.client.post(url, self.datos(username="prefecto-cuarto"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(User.objects.filter(username="prefecto-cuarto").exists())
        self.assertEqual(User.objects.filter(groups=self.grupo_prefectos, is_active=True).count(), 4)

        primero = User.objects.get(username="prefecto-0")
        estado = reverse("asistencias:cambiar_estado_prefecto", args=[primero.pk])
        self.assertEqual(self.client.get(estado).status_code, 405)
        self.client.post(estado, {"accion": "desactivar"})
        primero.refresh_from_db()
        self.assertFalse(primero.is_active)
        self.assertFalse(self.client.login(username=primero.username, password="clave-inexistente"))
        self.client.force_login(self.director)
        self.client.post(estado, {"accion": "activar"})
        primero.refresh_from_db()
        self.assertTrue(primero.is_active)
        self.assertEqual(User.objects.filter(groups=self.grupo_prefectos, is_active=True).count(), 4)

    def test_panel_sin_menu_lateral(self):
        self.client.force_login(self.director)
        response = self.client.get(reverse("asistencias:gestionar_prefectos"))
        self.assertContains(response, "Importar listas")
        self.assertNotContains(response, 'class="dashboard-sidebar"')
