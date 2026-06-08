"""
Preparação de dados de avaliação (AVAL_CPA.xlsx) para treino de modelos
de "nota esperada" — quer para notas internas, quer para notas de exame.

Resumo do que este script faz:

1. Lê a folha "Registos Biográficos Disciplina" do ficheiro original.
2. Remove linhas anómalas (registo com nível "Regular" / códigos N0xx —
   erro de desalinhamento de colunas, sem nº de aluno recuperável).
3. Normaliza as notas de exame (CE 1 / CE 2) para a escala 0-20, aplicando
   a regra de conversão correta consoante o nível de ensino e, no caso do
   4º ano, também o ano letivo (porque a escala mudou de 1-5 para 0-100
   entre 2012/2013 e 2013/2014 — um "regime change" real nos dados).
4. Classifica cada observação de exame num de dois grupos estruturalmente
   distintos:
     - "ciclo"      → Provas finais de ciclo (4º, 6º, 9º anos), escala
                      original 0-100 (ou 1-5 em 2012/2013 no 4º ano)
     - "secundario" → Exames nacionais do secundário (10º-12º), escala
                      original 0-200
5. Escreve dois ficheiros CSV de saída, um por grupo, prontos a usar como
   base de treino de modelos de previsão de exame — mais um terceiro CSV
   com as notas internas (períodos + CIF/CFD) já limpas, para o modelo de
   notas internas.

Notas de transparência:
  - Os anos lectivos 2019/2020 a 2021/2022 têm muito poucos registos de
    exame no secundário (provavelmente por causa da pandemia — exames
    cancelados ou com regras excecionais). Ficam marcados com a flag
    `epoca_atipica=True` em vez de excluídos, para que o utilizador
    decida se os quer incluir no treino.
"""

from __future__ import annotations

import csv
import sys
from collections import Counter

import openpyxl

ORIGEM = "/sessions/gracious-charming-edison/mnt/uploads/AVAL_CPA.xlsx"
SAIDA_CICLO = "exames_ciclo_basico.csv"
SAIDA_SECUNDARIO = "exames_secundario.csv"
SAIDA_INTERNAS = "notas_internas.csv"

ANOS_ATIPICOS = {"2019/2020", "2020/2021", "2021/2022"}

# Anos do 4º ano em que CE1/CE2 foram registados na escala 1-5 (qualitativa)
# em vez de 0-100 — identificado por inspeção empírica dos dados.
ANOS_4ANO_ESCALA_1A5 = {"2012/2013"}


def normalizar_exame(valor, nivel, ano_turma, ano_letivo):
    """Converte uma nota de exame (CE1/CE2) para a escala 0-20.

    Devolve (valor_normalizado, escala_original, grupo) ou (None, None, None)
    se a combinação não for reconhecida / não for um exame válido.
    """
    if valor is None:
        return None, None, None

    ano_turma = (str(ano_turma).strip() if ano_turma is not None else "")

    if nivel == "1º Ciclo do Ensino Básico" and ano_turma == "4º":
        if ano_letivo in ANOS_4ANO_ESCALA_1A5:
            # Escala 1-5 → 0-20: regra simples (nota - 1) / 4 * 20, alinhada
            # com a forma como o portal já converte níveis qualitativos.
            # Mantemos como está para já: assumimos 1↔4 e 5↔20 (linear).
            return round((valor - 1) / 4 * 20, 1), "1-5", "ciclo"
        else:
            return round(valor / 100 * 20, 1), "0-100", "ciclo"

    if nivel == "2º Ciclo do Ensino Básico" and ano_turma == "6º":
        return round(valor / 100 * 20, 1), "0-100", "ciclo"

    if nivel == "3º Ciclo do Ensino Básico" and ano_turma == "9º":
        return round(valor / 100 * 20, 1), "0-100", "ciclo"

    if nivel == "Ensino Secundário" and ano_turma in {"10º", "11º", "12º"}:
        return round(valor / 200 * 20, 1), "0-200", "secundario"

    return None, None, None


def main():
    wb = openpyxl.load_workbook(ORIGEM, read_only=True, data_only=True)
    ws = wb["Registos Biográficos Disciplina"]

    linhas_ciclo = []
    linhas_secundario = []
    linhas_internas = []

    n_total = 0
    n_excluidas_anomalas = 0
    n_exames_validos = 0
    contagem_grupo = Counter()
    contagem_escala = Counter()

    for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True)):
        n_total += 1
        (aluno, nome, doc, curso, nivel, tipo, turma, ano_turma, num,
         ano_letivo, sit_ano, data_sit, disc, cod, sit_disc, data_sit_disc,
         n1, n2, n3, cif, ce1, ce2, cfd, *resto) = row

        # Excluir linhas anómalas: registo "Regular" com nº de aluno em falta
        # (erro de desalinhamento de colunas — não recuperável com confiança)
        if aluno is None or nivel == "Regular":
            n_excluidas_anomalas += 1
            continue

        ano_turma_str = (str(ano_turma).strip() if ano_turma is not None else "")
        epoca_atipica = ano_letivo in ANOS_ATIPICOS

        # ── Notas internas (períodos + CIF/CFD) ──────────────────────────
        if any(v is not None for v in (n1, n2, n3, cif, cfd)):
            linhas_internas.append({
                "aluno_id": aluno,
                "ano_letivo": ano_letivo,
                "nivel": nivel,
                "ano_turma": ano_turma_str,
                "turma": turma,
                "disciplina": disc,
                "nota_p1": n1,
                "nota_p2": n2,
                "nota_p3": n3,
                "cif": cif,
                "cfd": cfd,
            })

        # ── Notas de exame (CE1 / CE2), normalizadas e segmentadas ───────
        for campo, valor in (("CE1", ce1), ("CE2", ce2)):
            norm, escala, grupo = normalizar_exame(valor, nivel, ano_turma_str, ano_letivo)
            if norm is None:
                continue

            n_exames_validos += 1
            contagem_grupo[grupo] += 1
            contagem_escala[(grupo, escala, ano_letivo if grupo == "ciclo" and ano_turma_str == "4º" else "")] += 1

            linha = {
                "aluno_id": aluno,
                "ano_letivo": ano_letivo,
                "nivel": nivel,
                "ano_turma": ano_turma_str,
                "turma": turma,
                "disciplina": disc,
                "fase": campo,
                "nota_exame_original": valor,
                "escala_original": escala,
                "nota_exame_norm_0_20": norm,
                "nota_p1": n1,
                "nota_p2": n2,
                "nota_p3": n3,
                "cif": cif,
                "cfd": cfd,
                "epoca_atipica": epoca_atipica,
            }

            if grupo == "ciclo":
                linhas_ciclo.append(linha)
            else:
                linhas_secundario.append(linha)

    # ── Escrever CSVs de saída ────────────────────────────────────────────
    def escrever_csv(nome_ficheiro, linhas):
        if not linhas:
            return
        campos = list(linhas[0].keys())
        with open(nome_ficheiro, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=campos)
            w.writeheader()
            w.writerows(linhas)

    escrever_csv(SAIDA_CICLO, linhas_ciclo)
    escrever_csv(SAIDA_SECUNDARIO, linhas_secundario)
    escrever_csv(SAIDA_INTERNAS, linhas_internas)

    # ── Relatório-resumo ──────────────────────────────────────────────────
    print(f"Linhas lidas no ficheiro original:        {n_total}")
    print(f"Linhas anómalas excluídas:                 {n_excluidas_anomalas}")
    print(f"Observações de notas internas exportadas:  {len(linhas_internas)}  -> {SAIDA_INTERNAS}")
    print(f"Observações de exame válidas (CE1+CE2):     {n_exames_validos}")
    print(f"  - grupo 'ciclo' (4º/6º/9º):               {contagem_grupo['ciclo']}  -> {SAIDA_CICLO}")
    print(f"  - grupo 'secundario' (10º-12º):           {contagem_grupo['secundario']}  -> {SAIDA_SECUNDARIO}")
    print()
    print("Detalhe da conversão de escala aplicada no 4º ano (por ano letivo):")
    for (grupo, escala, ano), n in sorted(contagem_escala.items()):
        if grupo == "ciclo" and ano:
            print(f"  {ano}: escala original {escala}  ({n} observações)")
    print()
    n_atip = sum(1 for l in linhas_secundario if l["epoca_atipica"])
    print(f"Observações em anos atípicos (pandemia, 2019/2020-2021/2022): {n_atip}")
    print("  (mantidas no CSV, mas marcadas com epoca_atipica=True para decisão do utilizador)")


if __name__ == "__main__":
    sys.exit(main())
