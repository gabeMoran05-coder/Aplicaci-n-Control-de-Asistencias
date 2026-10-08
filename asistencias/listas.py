import re

import pymupdf


PATRON_ALUMNO = re.compile(r"(?m)^(\d{1,2})\n(\d{9})\n([A-ZÁÉÍÓÚÑÜ ]+)\n")


def separar_nombre(nombre):
    partes = nombre.split()
    if len(partes) < 3:
        raise ValueError(f"Nombre incompleto: {nombre}")

    def tomar_apellido(restantes):
        if restantes[:2] == ["DE", "LA"]:
            longitud = 3
        elif restantes[0] in {"DE", "DEL"}:
            longitud = 2
        else:
            longitud = 1
        return " ".join(restantes[:longitud]), restantes[longitud:]

    paterno, restantes = tomar_apellido(partes)
    if not restantes:
        raise ValueError(f"Falta apellido materno: {nombre}")
    materno, nombres = tomar_apellido(restantes)
    if not nombres:
        raise ValueError(f"Faltan nombres: {nombre}")
    return " ".join(nombres).title(), paterno.title(), materno.title()


def extraer_lista_pdf(archivo, ciclo, grado, letra):
    if not archivo.read(4) == b"%PDF":
        raise ValueError("El archivo no es un PDF valido.")
    archivo.seek(0)
    try:
        with pymupdf.open(stream=archivo.read(), filetype="pdf") as documento:
            if len(documento) > 20:
                raise ValueError("El PDF tiene demasiadas paginas para una sola lista.")
            texto = "\n".join(pagina.get_text() for pagina in documento)
    except ValueError:
        raise
    except Exception as error:
        raise ValueError("No se pudo abrir el PDF.") from error

    encabezado = re.compile(
        rf"(?m)^\s*{grado}\n{re.escape(letra)}\n[A-ZÁÉÍÓÚÑÜ]+\n{re.escape(ciclo)}\n"
    )
    if not encabezado.search(texto):
        raise ValueError("El grado, grupo o ciclo no coincide con el encabezado del PDF.")
    coincidencias = PATRON_ALUMNO.findall(texto)
    numeros = [int(numero) for numero, _, _ in coincidencias]
    if not coincidencias or numeros != list(range(1, len(coincidencias) + 1)):
        raise ValueError("No se pudo leer una lista consecutiva completa. Revisa el PDF.")
    matriculas = [matricula for _, matricula, _ in coincidencias]
    if len(matriculas) != len(set(matriculas)):
        raise ValueError("La lista contiene matriculas repetidas.")
    filas = []
    for _, matricula, nombre in coincidencias:
        nombres, paterno, materno = separar_nombre(nombre)
        filas.append({"matricula": matricula, "nombres": nombres,
                      "apellido_paterno": paterno, "apellido_materno": materno})
    return filas
