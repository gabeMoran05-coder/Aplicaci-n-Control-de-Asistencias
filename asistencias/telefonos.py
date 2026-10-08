import re
from functools import lru_cache

import phonenumbers
from babel import Locale


@lru_cache(maxsize=1)
def opciones_paises():
    nombres = Locale.parse("es").territories
    opciones = []
    for region in phonenumbers.SUPPORTED_REGIONS:
        lada = phonenumbers.country_code_for_region(region)
        if lada:
            nombre = nombres.get(region, region)
            opciones.append((region, f"+{lada} · {nombre}"))
    return sorted(opciones, key=lambda opcion: opcion[1].casefold())


def normalizar_telefono(valor, region="MX"):
    if not re.fullmatch(r"[+0-9().\s-]+", valor or ""):
        raise ValueError("El telefono solo puede contener numeros y separadores.")
    try:
        numero = phonenumbers.parse(valor, region)
    except phonenumbers.NumberParseException as error:
        raise ValueError("Escribe un numero de telefono valido para el pais seleccionado.") from error
    if not phonenumbers.is_valid_number_for_region(numero, region):
        raise ValueError("Escribe un numero de telefono valido para el pais seleccionado.")
    return phonenumbers.format_number(numero, phonenumbers.PhoneNumberFormat.E164)


def telefono_para_formulario(valor):
    if not valor:
        return "MX", ""
    try:
        numero = phonenumbers.parse(valor, None if valor.startswith("+") else "MX")
    except phonenumbers.NumberParseException:
        return "MX", valor
    if not phonenumbers.is_valid_number(numero):
        return "MX", valor
    region = phonenumbers.region_code_for_number(numero) or "MX"
    if region not in phonenumbers.SUPPORTED_REGIONS:
        region = "MX"
    if region == "MX":
        digitos = str(numero.national_number)
        if len(digitos) == 10:
            return region, f"{digitos[:3]}-{digitos[3:6]}-{digitos[6:]}"
    return region, phonenumbers.format_number(numero, phonenumbers.PhoneNumberFormat.NATIONAL)


def telefono_visible(valor):
    if not valor:
        return ""
    region, nacional = telefono_para_formulario(valor)
    if nacional == valor:
        return valor
    lada = phonenumbers.country_code_for_region(region)
    return f"+{lada} {nacional}" if lada else nacional
