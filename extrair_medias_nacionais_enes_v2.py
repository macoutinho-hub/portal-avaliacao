"""
Versão 2 — extrai médias nacionais ENES (secundário) de PDFs da DGE,
agora cobrindo 2012-2024, com deteção automática do formato do relatório
(o layout mudou várias vezes ao longo dos anos):

  Formato A (até ~2014): coluna "Total" isolada — é directamente a média
            nacional de exame (0-200), antes das colunas "Internos"/"CIF".
            Cabeçalho: "Médias Exame Média Correl. %"

  Formato B (~2015-2019): separa "Internos" de "Autopropostos", sem uma
            média nacional combinada directa. Reconstrói-se por média
            ponderada pelo nº de provas de cada grupo:
                média = (n_int*média_int + n_auto*média_auto) / (n_int+n_auto)
            Cabeçalho: "Internos ... Autopropostos ... Total"

  Formato C (2020 em diante): uma única coluna "Média do Exame" — é
            directamente a média nacional (0-200).
            Cabeçalho: "Inscrições/Inscritos ... Faltas ... Média"

O ano e a fase são lidos do título e subtítulo de cada página
("EXAMES ... SECUNDÁRIO <ano>" / "Resultados de Exames da <fase> Fase"),
não do nome do ficheiro — mais robusto a nomes inconsistentes.

Saída: `medias_nacionais_enes_v2.csv` (substitui/complementa a v1),
já convertida para 0-20 e mapeada para as abreviaturas do portal.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path

import pdfplumber

PASTA = Path("/sessions/gracious-charming-edison/mnt/uploads")
PASTA_2013 = Path("/sessions/gracious-charming-edison/mnt/outputs/zip2013")
SAIDA = "medias_nacionais_enes_v2.csv"

FICHEIROS = (
    list(PASTA.glob("enes_hmlg*resumo*.pdf"))
    + list(PASTA.glob("*secun*dadosestat*.pdf"))
    + list(PASTA_2013.glob("enes_hmlg*resumo*.pdf"))
)

MAPA_DISCIPLINA = {
    "Português": "PORT.",
    "Matemática A": "MAT.A",
    "Matemática B": "MAT.B",
    "Física e Química A": "FÍS.QUÍM.A",
    "Biologia e Geologia": "BIO.GEO.",
    "Economia A": "ECON.A",
    "Filosofia": "FILO.",
    "Geometria Descritiva A": "GEO.DESC.A",
    "Geografia A": "GEOG.A",
    "História A": "HIST.A",
    "História B": "HIST. B",
    "Literatura Portuguesa": "LIT.PORT.",
    "História da Cultura e das Artes": "HCA",
    "Desenho A": "DES.A",
    "Matemática Aplic. às Ciências Soc.": "MACS",
    "Matemática Aplic. às Ciências": "MACS",
    "Matemática Aplicada às Ciências": "MACS",
    "Matemática Aplicada às Ciências Sociais": "MACS",
}

RE_TITULO_ANO = re.compile(r"ENSINO SECUND[ÁA]RIO\s+(\d{4})")
RE_FASE = re.compile(r"(\d)[ªa]\s+Fase", re.IGNORECASE)

# Formatos "AD": a média nacional ("Total") aparece em coluna isolada,
# logo a seguir à % de faltas — tanto faz se o que vem depois é a
# desagregação Internos/CIF (até 2014, 1ª fase) ou Internos/Autopropostos
# (2014, 2ª fase). Basta capturar o primeiro número a seguir à %.
PAD_AD = re.compile(
    r"(\d{2}/\d{2})\s+(\d{3})\s+(.+?)\s+(\d{4}):\s+"
    r"(\d[\d ]*\d|\d)\s+(\d[\d ]*\d|\d)\s+(\d[\d ]*\d|\d)\s+(\d+)%\s+"
    r"(\d{2,3})\b"
)
# Formato "B": só dá médias separadas de "Internos" e "Autopropostos" —
# reconstrói-se a média nacional por ponderação pelo nº de provas de cada
# grupo. CIF/correlação podem vir com vírgula OU ponto decimal (mudou ao
# longo dos anos), por isso aceitamos ambos.
PAD_B = re.compile(
    r"(\d{2}/\d{2})\s+(\d{3})\s+(.+?)\s+(\d{4}):\s+"
    r"(\d+)\s+(\d+)\s+([\d.,]+)\s+([-−.,\d]+)\s+(\d+)%\s+"
    r"(\d+)\s+(\d+)\s+(\d+)%"
)
# Formato "C" (2020 em diante): coluna única "Média do Exame" — é
# directamente a média nacional.
PAD_C = re.compile(
    r"(\d{2}/\d{2})\s+(\d{2}:\d{2})\s+(\d{3})\s+(.+?)\s+"
    r"([\d ]{1,7})\s+([\d ]{1,7})\s+([\d ]{1,6})\s+(\d+)%\s+(\d{2,3})\s*$"
)


def normalizar(nome: str) -> str:
    """Remove acentos/maiúsculas para comparações tolerantes."""
    n = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return n.lower().strip()


def detetar_formato(texto_pagina: str) -> str | None:
    """Decide o formato pela ORDEM relativa de 'total' e 'internos' no
    cabeçalho — é o que distingue de forma fiável as várias variantes que
    a DGE usou ao longo dos anos (ver docstring do módulo)."""
    t = normalizar(texto_pagina)
    i_total = t.find("total")
    i_internos = t.find("internos")

    if i_internos == -1:
        # Sem desagregação Internos/Autopropostos -> formato simples (C)
        if "media do exame" in t or "média do exame" in texto_pagina.lower():
            return "C"
        return None

    if i_total == -1 or i_total < i_internos:
        return "AD"
    return "B"


def processar_pagina(linhas, formato, ano, fase, registos, nao_mapeadas):
    for linha in linhas:
        l = linha.strip()

        if formato == "AD":
            m = PAD_AD.match(l)
            if not m or m.group(4) != ano:
                continue
            nome_oficial = m.group(3).strip()
            media_0_200 = int(m.group(9))

        elif formato == "B":
            m = PAD_B.match(l)
            if not m or m.group(4) != ano:
                continue
            nome_oficial = m.group(3).strip()
            n_int, med_int = int(m.group(5)), int(m.group(6))
            n_auto, med_auto = int(m.group(10)), int(m.group(11))
            total = n_int + n_auto
            if total == 0:
                continue
            media_0_200 = round((n_int * med_int + n_auto * med_auto) / total)

        elif formato == "C":
            m = PAD_C.match(l)
            if not m:
                continue
            nome_oficial = m.group(4).strip()
            media_0_200 = int(m.group(9))

        else:
            continue

        abrev = MAPA_DISCIPLINA.get(nome_oficial)
        if abrev is None:
            nao_mapeadas.add(nome_oficial)

        registos.append({
            "ano_civil_exame": ano,
            "fase": fase,
            "disciplina_oficial": nome_oficial,
            "disciplina_portal": abrev or "",
            "media_nacional_0_200": media_0_200,
            "media_nacional_0_20": round(media_0_200 / 10, 1),
            "formato_origem": formato,
        })


def extrair():
    registos = []
    nao_mapeadas = set()
    ficheiros_processados = []
    ficheiros_ignorados = []

    for caminho in sorted(set(FICHEIROS)):
        # As versões "eneb_*" são de ciclo básico (Nível 1-5), não secundário — ignorar aqui
        if "eneb" in caminho.name.lower():
            continue

        encontrou_algo = False
        with pdfplumber.open(caminho) as pdf:
            ano_doc = None
            for pagina in pdf.pages:
                texto = pagina.extract_text(layout=True)
                if not texto:
                    continue
                if ano_doc is None:
                    m_ano = RE_TITULO_ANO.search(texto)
                    if m_ano:
                        ano_doc = m_ano.group(1)
                m_fase = RE_FASE.search(texto)
                fase = m_fase.group(1) if m_fase else None
                formato = detetar_formato(texto)
                if not (ano_doc and fase and formato):
                    continue
                antes = len(registos)
                processar_pagina(texto.splitlines(), formato, ano_doc, fase, registos, nao_mapeadas)
                if len(registos) > antes:
                    encontrou_algo = True

        if encontrou_algo:
            ficheiros_processados.append(caminho.name)
        else:
            ficheiros_ignorados.append(caminho.name)

    return registos, nao_mapeadas, ficheiros_processados, ficheiros_ignorados


def main():
    registos, nao_mapeadas, processados, ignorados = extrair()

    # Remover duplicados (o mesmo (ano,fase,disciplina) pode aparecer em mais
    # do que um ficheiro, p.ex. quando o ano N também é referido como "ano
    # anterior" no relatório de N+1 — mantemos a 1ª ocorrência só)
    vistos = set()
    unicos = []
    for r in registos:
        chave = (r["ano_civil_exame"], r["fase"], r["disciplina_portal"] or r["disciplina_oficial"])
        if chave in vistos:
            continue
        vistos.add(chave)
        unicos.append(r)

    with open(SAIDA, "w", newline="", encoding="utf-8") as f:
        campos = list(unicos[0].keys())
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(unicos)

    anos_fases = sorted(set((r["ano_civil_exame"], r["fase"]) for r in unicos))
    print(f"Ficheiros processados com sucesso ({len(processados)}): {processados}")
    if ignorados:
        print(f"\nFicheiros sem correspondência (formato não detetado / ano não confirmado): {ignorados}")
    print(f"\nRegistos únicos extraídos: {len(unicos)}  -> {SAIDA}")
    print(f"Cobertura (ano, fase): {anos_fases}")
    if nao_mapeadas:
        print(f"\nDisciplinas sem mapeamento ({len(nao_mapeadas)}):")
        for n in sorted(nao_mapeadas):
            print(f"  - {n}")


if __name__ == "__main__":
    main()
