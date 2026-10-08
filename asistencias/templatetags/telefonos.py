from django import template

from asistencias.telefonos import telefono_visible


register = template.Library()
register.filter("telefono_visible", telefono_visible)
