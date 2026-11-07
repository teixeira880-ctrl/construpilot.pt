"""Constantes do BIM Studio (sem dependências pesadas — importável mesmo sem IfcOpenShell)."""

CATEGORIES = {
    "paredes": "Paredes", "portas": "Portas", "janelas": "Janelas", "lajes": "Lajes",
    "pilares": "Pilares", "vigas": "Vigas", "coberturas": "Coberturas", "escadas": "Escadas",
    "pavimentos": "Pavimentos", "revestimentos": "Revestimentos", "espacos": "Espaços e divisões",
    "estrutura": "Outros elementos estruturais", "fachadas": "Fachadas e caixilharia",
    "guardas": "Guardas e corrimãos", "instalacoes": "Instalações (MEP)", "mobiliario": "Mobiliário",
    "outros": "Outros elementos",
}

# Quantidade principal usada para orçamentar cada categoria.
PRIMARY = {
    "paredes": "area", "portas": "count", "janelas": "count", "lajes": "area", "pilares": "volume",
    "vigas": "volume", "coberturas": "area", "escadas": "count", "pavimentos": "area",
    "revestimentos": "area", "espacos": "area", "estrutura": "volume", "fachadas": "area",
    "guardas": "length", "instalacoes": "count", "mobiliario": "count", "outros": "count",
}

UNIT_OF = {"area": "m²", "area_gross": "m²", "volume": "m³", "volume_gross": "m³", "length": "m",
           "width": "m", "height": "m", "thickness": "m", "perimeter": "m", "count": "u",
           "weight": "kg", "section_area": "m²", "surface_area": "m²"}

QTY_LABELS = {"area": "Área", "area_gross": "Área bruta", "volume": "Volume", "volume_gross": "Volume bruto",
              "length": "Comprimento", "width": "Largura", "height": "Altura", "thickness": "Espessura",
              "perimeter": "Perímetro", "count": "Quantidade", "weight": "Peso",
              "section_area": "Área de secção", "surface_area": "Área de superfície"}

