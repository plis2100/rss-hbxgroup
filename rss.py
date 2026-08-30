import re
import urllib.request
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin


WEB_URL = "https://www.hbxgroup.com/news-room/press-release"
BASE_URL = "https://www.hbxgroup.com"
ARCHIVO_RSS = "hbxgroup.xml"

MESES = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def descargar_pagina(url):
    solicitud = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,*/*;q=0.8"
            ),
            "Accept-Language": "en-GB,en;q=0.9,es;q=0.8",
            "Cache-Control": "no-cache",
        },
    )

    with urllib.request.urlopen(solicitud, timeout=60) as respuesta:
        return respuesta.read()


def limpiar_texto(texto):
    return re.sub(r"\s+", " ", texto or "").strip()


def extraer_fecha(soup):
    texto = limpiar_texto(soup.get_text(" ", strip=True))

    coincidencia = re.search(
        r"\b(\d{1,2})\s+"
        r"(January|February|March|April|May|June|July|August|"
        r"September|October|November|December)"
        r"\s+(\d{4})\b",
        texto,
        re.IGNORECASE,
    )

    if not coincidencia:
        return None, None

    dia = int(coincidencia.group(1))
    mes = MESES[coincidencia.group(2).lower()]
    anio = int(coincidencia.group(3))

    fecha = datetime(
        anio,
        mes,
        dia,
        8,
        0,
        tzinfo=timezone.utc,
    )

    return fecha, format_datetime(fecha)


def extraer_descripcion(soup):
    for atributo in (
        {"property": "og:description"},
        {"name": "description"},
    ):
        meta = soup.find("meta", attrs=atributo)

        if meta and meta.get("content"):
            descripcion = limpiar_texto(meta["content"])

            if len(descripcion) >= 40:
                return descripcion[:700]

    principal = soup.find("main") or soup.find("article")

    if principal:
        for parrafo in principal.find_all("p"):
            texto = limpiar_texto(parrafo.get_text(" ", strip=True))

            if len(texto) >= 100:
                return texto[:700]

    return "Nota de prensa publicada por HBX Group."


def obtener_enlaces():
    enlaces = []
    vistos = set()

    # Lee las dos primeras páginas para mantener suficientes noticias
    # en el RSS, aunque normalmente las nuevas aparecen en la primera.
    for numero_pagina in range(2):
        if numero_pagina == 0:
            url_pagina = WEB_URL
        else:
            url_pagina = f"{WEB_URL}?page={numero_pagina}"

        contenido = descargar_pagina(url_pagina)
        soup = BeautifulSoup(contenido, "html.parser")

        for enlace in soup.find_all("a", href=True):
            titulo = limpiar_texto(enlace.get_text(" ", strip=True))
            url = urljoin(BASE_URL, enlace["href"])
            url = url.split("#")[0].split("?")[0].rstrip("/")

            prefijo = f"{BASE_URL}/news-room/press-release/"

            if not url.startswith(prefijo):
                continue

            if url == WEB_URL:
                continue

            if len(titulo) < 20:
                continue

            if url in vistos:
                continue

            vistos.add(url)
            enlaces.append((titulo, url))

    if not enlaces:
        raise RuntimeError(
            "No se encontraron notas de prensa de HBX Group"
        )

    return enlaces[:30]


def obtener_noticias():
    noticias = []

    for titulo_inicial, url in obtener_enlaces():
        try:
            contenido = descargar_pagina(url)
            soup = BeautifulSoup(contenido, "html.parser")

            encabezado = soup.find("h1")

            if encabezado:
                titulo = limpiar_texto(
                    encabezado.get_text(" ", strip=True)
                )
            else:
                titulo = titulo_inicial

            fecha_orden, fecha_rss = extraer_fecha(soup)
            descripcion = extraer_descripcion(soup)

            noticias.append(
                {
                    "titulo": titulo,
                    "url": url,
                    "fecha_orden": fecha_orden,
                    "fecha_rss": fecha_rss,
                    "descripcion": descripcion,
                }
            )

            print(f"Noticia encontrada: {titulo}")

        except Exception as error:
            print(f"No se pudo procesar {url}: {error}")

            noticias.append(
                {
                    "titulo": titulo_inicial,
                    "url": url,
                    "fecha_orden": None,
                    "fecha_rss": None,
                    "descripcion": (
                        "Nota de prensa publicada por HBX Group."
                    ),
                }
            )

    if not noticias:
        raise RuntimeError(
            "La RSS de HBX Group no contiene noticias"
        )

    noticias.sort(
        key=lambda noticia: (
            noticia["fecha_orden"]
            or datetime(1970, 1, 1, tzinfo=timezone.utc)
        ),
        reverse=True,
    )

    return noticias


def crear_rss(noticias):
    rss = ET.Element(
        "rss",
        {
            "version": "2.0",
            "xmlns:atom": "http://www.w3.org/2005/Atom",
        },
    )

    canal = ET.SubElement(rss, "channel")

    ET.SubElement(canal, "title").text = (
        "HBX Group – Notas de prensa"
    )
    ET.SubElement(canal, "link").text = WEB_URL
    ET.SubElement(canal, "description").text = (
        "Últimas notas de prensa publicadas por HBX Group"
    )
    ET.SubElement(canal, "language").text = "en"

    ET.SubElement(
        canal,
        "{http://www.w3.org/2005/Atom}link",
        {
            "href": (
                "https://raw.githubusercontent.com/"
                "plis2100/rss-hbxgroup/main/hbxgroup.xml"
            ),
            "rel": "self",
            "type": "application/rss+xml",
        },
    )

    ahora = datetime.now(timezone.utc)

    ET.SubElement(
        canal,
        "lastBuildDate",
    ).text = format_datetime(ahora)

    for noticia in noticias:
        elemento = ET.SubElement(canal, "item")

        ET.SubElement(
            elemento,
            "title",
        ).text = noticia["titulo"]

        ET.SubElement(
            elemento,
            "link",
        ).text = noticia["url"]

        ET.SubElement(
            elemento,
            "guid",
            {"isPermaLink": "true"},
        ).text = noticia["url"]

        ET.SubElement(
            elemento,
            "description",
        ).text = noticia["descripcion"]

        if noticia["fecha_rss"]:
            ET.SubElement(
                elemento,
                "pubDate",
            ).text = noticia["fecha_rss"]

    arbol = ET.ElementTree(rss)
    ET.indent(arbol, space="  ")

    arbol.write(
        ARCHIVO_RSS,
        encoding="utf-8",
        xml_declaration=True,
    )


def main():
    noticias = obtener_noticias()
    crear_rss(noticias)

    archivo = Path(ARCHIVO_RSS)

    if not archivo.exists() or archivo.stat().st_size < 500:
        raise RuntimeError(
            "El archivo RSS no se creó correctamente"
        )

    print(
        f"RSS creada correctamente: "
        f"{ARCHIVO_RSS} ({len(noticias)} noticias)"
    )


if __name__ == "__main__":
    main()
