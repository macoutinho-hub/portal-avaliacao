# -*- coding: utf-8 -*-
"""
Motor de análise estatística global — Portal de Avaliação CPA
=============================================================

Funções para a área de Estatísticas Globais (admin):
- comparação entre disciplinas (médias, desvio-padrão, distribuição)
- por disciplina: nº de alunos para quem é a melhor / está acima da média pessoal
- nota real vs. nota esperada (modelo pooled) por disciplina, turma e professor
- comparação entre turmas na mesma disciplina
- comparação entre professores: notas atribuídas vs. esperadas por disciplina/turma

Sem dependências externas — usa apenas stdlib (statistics).
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Dict, List, Optional, Tuple


# ──────────────────────────────────────────────────────────────────────────────
# Utilitários
# ──────────────────────────────────────────────────────────────────────────────

EXCLUIR_DISC = {"Hora de PT", "Tempo de Trabalho Autónomo"}


def _notas_validas(notas: list[float]) -> list[float]:
    return [n for n in notas if n is not None and 0 <= n <= 20]


def _safe_mean(vals):
    v = _notas_validas(vals)
    return round(statistics.mean(v), 2) if v else None


def _safe_median(vals):
    v = _notas_validas(vals)
    return round(statistics.median(v), 2) if v else None


def _safe_stdev(vals):
    v = _notas_validas(vals)
    return round(statistics.stdev(v), 2) if len(v) >= 2 else None


def _safe_pct(num, denom):
    return round(100 * num / denom, 1) if denom else None


def _filtrar_obs(obs, ano_letivo=None, periodo=None, disciplinas_excluir=None):
    """Filtra lista de observações por ano letivo e/ou período."""
    excluir = disciplinas_excluir or EXCLUIR_DISC
    result = [o for o in obs if o["disciplina"] not in excluir]
    if ano_letivo:
        result = [o for o in result if o["ano_letivo"] == ano_letivo]
    if periodo is not None:
        result = [o for o in result if o["periodo"] == periodo]
    return result


# ──────────────────────────────────────────────────────────────────────────────
# 1. Comparação entre disciplinas
# ──────────────────────────────────────────────────────────────────────────────

def comparacao_disciplinas(obs, ano_letivo=None, periodo=None):
    """Estatísticas globais por disciplina.

    Devolve lista de dicts ordenada por média descendente:
      {disciplina, n_alunos, media, mediana, desvio_padrao,
       pct_negativas, pct_positivas, pct_excelencia,
       n_melhor_disciplina, pct_melhor_disciplina,
       n_acima_media_pessoal, pct_acima_media_pessoal,
       distribuicao: {<0: n, 10-13: n, 14-17: n, 18-20: n}}
    """
    dados = _filtrar_obs(obs, ano_letivo, periodo)
    if not dados:
        return []

    # Agrupar notas por disciplina
    por_disc: Dict[str, list] = defaultdict(list)
    for o in dados:
        por_disc[o["disciplina"]].append(o["nota"])

    # Média pessoal por (aluno_id, ano_letivo, periodo)
    media_pessoal = _calcular_medias_pessoais(dados)

    # Para cada aluno, qual é a sua melhor disciplina (por periodo/ano)
    melhor_disc_aluno = _melhor_disciplina_por_aluno(dados)

    # Disciplina acima da média pessoal
    acima_media = _disciplina_acima_media_pessoal(dados, media_pessoal)

    resultado = []
    for disc, notas in por_disc.items():
        n = len(notas)
        n_melhor = melhor_disc_aluno.get(disc, 0)
        n_acima = acima_media.get(disc, 0)
        resultado.append({
            "disciplina":              disc,
            "n_alunos":                n,
            "media":                   _safe_mean(notas),
            "mediana":                 _safe_median(notas),
            "desvio_padrao":           _safe_stdev(notas),
            "pct_negativas":           _safe_pct(sum(1 for v in notas if v < 10), n),
            "pct_positivas":           _safe_pct(sum(1 for v in notas if v >= 10), n),
            "pct_excelencia":          _safe_pct(sum(1 for v in notas if v >= 18), n),
            "n_melhor_disciplina":     n_melhor,
            "pct_melhor_disciplina":   _safe_pct(n_melhor, n),
            "n_acima_media_pessoal":   n_acima,
            "pct_acima_media_pessoal": _safe_pct(n_acima, n),
            "distribuicao": {
                "neg":    sum(1 for v in notas if v < 10),
                "suf":    sum(1 for v in notas if 10 <= v <= 13),
                "bom":    sum(1 for v in notas if 14 <= v <= 17),
                "exc":    sum(1 for v in notas if v >= 18),
            },
        })

    resultado.sort(key=lambda x: (x["media"] or 0), reverse=True)
    return resultado


def _calcular_medias_pessoais(dados):
    """Devolve dict {(aluno_id, ano_letivo, periodo): media_pessoal}."""
    agrup = defaultdict(list)
    for o in dados:
        agrup[(o["aluno_id"], o["ano_letivo"], o["periodo"])].append(o["nota"])
    return {k: statistics.mean(v) for k, v in agrup.items() if v}


def _melhor_disciplina_por_aluno(dados):
    """Para cada aluno (por periodo/ano), determina qual é a sua disciplina
    com nota mais alta. Devolve {disciplina: nº de alunos para quem é a melhor}.
    Empates: conta nas várias disciplinas."""
    # Agrupar por aluno/periodo/ano
    aluno_notas: Dict[tuple, Dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for o in dados:
        chave = (o["aluno_id"], o["ano_letivo"], o["periodo"])
        aluno_notas[chave][o["disciplina"]].append(o["nota"])

    contagem: Dict[str, int] = defaultdict(int)
    for chave, discs in aluno_notas.items():
        medias = {d: statistics.mean(ns) for d, ns in discs.items() if ns}
        if not medias:
            continue
        max_nota = max(medias.values())
        for d, m in medias.items():
            if m == max_nota:
                contagem[d] += 1
    return dict(contagem)


def _disciplina_acima_media_pessoal(dados, media_pessoal):
    """Para cada disciplina, conta quantos alunos têm nota acima da sua
    média pessoal nesse período/ano. Devolve {disciplina: n_alunos}."""
    contagem: Dict[str, int] = defaultdict(int)
    for o in dados:
        chave = (o["aluno_id"], o["ano_letivo"], o["periodo"])
        mp = media_pessoal.get(chave)
        if mp is not None and o["nota"] > mp:
            contagem[o["disciplina"]] += 1
    return dict(contagem)


# ──────────────────────────────────────────────────────────────────────────────
# 2. Comparação entre turmas
# ──────────────────────────────────────────────────────────────────────────────

def comparacao_turmas(obs, disciplina=None, ano_letivo=None, periodo=None):
    """Compara turmas numa disciplina (ou em todas, se disciplina=None).

    Devolve lista de dicts:
      {turma, disciplina, n_alunos, media, mediana, desvio_padrao,
       pct_negativas, pct_excelencia, desvio_vs_media_escola}
    """
    dados = _filtrar_obs(obs, ano_letivo, periodo)
    if disciplina:
        dados = [o for o in dados if o["disciplina"] == disciplina]
    if not dados:
        return []

    # Média global da escola por disciplina (para calcular desvio)
    media_escola: Dict[str, float] = {}
    por_disc_global: Dict[str, list] = defaultdict(list)
    for o in dados:
        por_disc_global[o["disciplina"]].append(o["nota"])
    for d, ns in por_disc_global.items():
        m = _safe_mean(ns)
        if m is not None:
            media_escola[d] = m

    # Agrupar por (turma, disciplina)
    agrup: Dict[tuple, list] = defaultdict(list)
    for o in dados:
        agrup[(o["turma"], o["disciplina"])].append(o["nota"])

    resultado = []
    for (turma, disc), notas in agrup.items():
        n = len(notas)
        media = _safe_mean(notas)
        me = media_escola.get(disc)
        resultado.append({
            "turma":               turma,
            "disciplina":          disc,
            "n_alunos":            n,
            "media":               media,
            "mediana":             _safe_median(notas),
            "desvio_padrao":       _safe_stdev(notas),
            "pct_negativas":       _safe_pct(sum(1 for v in notas if v < 10), n),
            "pct_excelencia":      _safe_pct(sum(1 for v in notas if v >= 18), n),
            "media_escola":        me,
            "desvio_vs_escola":    round(media - me, 2) if (media is not None and me is not None) else None,
        })

    resultado.sort(key=lambda x: (x["disciplina"], -(x["media"] or 0)))
    return resultado


# ──────────────────────────────────────────────────────────────────────────────
# 3. Nota real vs. nota esperada (modelo pooled)
# ──────────────────────────────────────────────────────────────────────────────

def desvio_esperado_disciplina(obs, modelo, ano_letivo=None, periodo=None):
    """Para cada disciplina, calcula a média do desvio (nota real − nota esperada)
    e o nº de alunos com desvio positivo / negativo / neutro (|desvio| < 0.5).

    Usa o modelo pooled de `analytics.py`.

    Devolve lista de dicts:
      {disciplina, n_obs, media_real, media_esperada, desvio_medio,
       n_acima_esperado, n_abaixo_esperado, n_neutro,
       pct_acima_esperado, pct_abaixo_esperado}
    """
    from analytics import nota_esperada_e_desvio  # import local para evitar circular

    dados = _filtrar_obs(obs, ano_letivo, periodo)
    if not dados or modelo is None:
        return []

    por_disc: Dict[str, dict] = defaultdict(lambda: {
        "reais": [], "esperadas": [], "desvios": [],
        "acima": 0, "abaixo": 0, "neutro": 0
    })

    for o in dados:
        res = nota_esperada_e_desvio(modelo, o["aluno_id"], o["disciplina"],
                                     o["periodo"], o["ano_letivo"])
        if res is None or res.get("nota_esperada") is None:
            continue
        esp = res["nota_esperada"]
        real = o["nota"]
        desvio = real - esp
        d = por_disc[o["disciplina"]]
        d["reais"].append(real)
        d["esperadas"].append(esp)
        d["desvios"].append(desvio)
        if desvio > 0.5:
            d["acima"] += 1
        elif desvio < -0.5:
            d["abaixo"] += 1
        else:
            d["neutro"] += 1

    resultado = []
    for disc, d in por_disc.items():
        n = len(d["desvios"])
        if n == 0:
            continue
        resultado.append({
            "disciplina":         disc,
            "n_obs":              n,
            "media_real":         _safe_mean(d["reais"]),
            "media_esperada":     _safe_mean(d["esperadas"]),
            "desvio_medio":       round(statistics.mean(d["desvios"]), 2),
            "n_acima_esperado":   d["acima"],
            "n_abaixo_esperado":  d["abaixo"],
            "n_neutro":           d["neutro"],
            "pct_acima_esperado": _safe_pct(d["acima"], n),
            "pct_abaixo_esperado":_safe_pct(d["abaixo"], n),
        })

    resultado.sort(key=lambda x: x["desvio_medio"], reverse=True)
    return resultado


def desvio_esperado_turma(obs, modelo, disciplina=None, ano_letivo=None, periodo=None):
    """Como `desvio_esperado_disciplina` mas agrupado por (turma, disciplina).

    Devolve lista de dicts:
      {turma, disciplina, n_obs, media_real, media_esperada, desvio_medio,
       n_acima_esperado, n_abaixo_esperado}
    """
    from analytics import nota_esperada_e_desvio

    dados = _filtrar_obs(obs, ano_letivo, periodo)
    if disciplina:
        dados = [o for o in dados if o["disciplina"] == disciplina]
    if not dados or modelo is None:
        return []

    agrup: Dict[tuple, dict] = defaultdict(lambda: {
        "reais": [], "esperadas": [], "desvios": [],
        "acima": 0, "abaixo": 0
    })

    for o in dados:
        res = nota_esperada_e_desvio(modelo, o["aluno_id"], o["disciplina"],
                                     o["periodo"], o["ano_letivo"])
        if res is None or res.get("nota_esperada") is None:
            continue
        esp = res["nota_esperada"]
        real = o["nota"]
        desvio = real - esp
        d = agrup[(o["turma"], o["disciplina"])]
        d["reais"].append(real)
        d["esperadas"].append(esp)
        d["desvios"].append(desvio)
        if desvio > 0.5:
            d["acima"] += 1
        elif desvio < -0.5:
            d["abaixo"] += 1

    resultado = []
    for (turma, disc), d in agrup.items():
        n = len(d["desvios"])
        if n == 0:
            continue
        resultado.append({
            "turma":              turma,
            "disciplina":         disc,
            "n_obs":              n,
            "media_real":         _safe_mean(d["reais"]),
            "media_esperada":     _safe_mean(d["esperadas"]),
            "desvio_medio":       round(statistics.mean(d["desvios"]), 2),
            "n_acima_esperado":   d["acima"],
            "n_abaixo_esperado":  d["abaixo"],
            "pct_acima_esperado": _safe_pct(d["acima"], n),
            "pct_abaixo_esperado":_safe_pct(d["abaixo"], n),
        })

    resultado.sort(key=lambda x: (x["disciplina"], x["turma"]))
    return resultado


# ──────────────────────────────────────────────────────────────────────────────
# 4. Comparação por professor
# ──────────────────────────────────────────────────────────────────────────────

def carregar_mapeamento_professores(db, ano_letivo=None):
    """Lê a tabela `prof_disc` e devolve dict:
      {(turma, disciplina): professor}
    """
    query = "SELECT professor, turma, disciplina FROM prof_disc"
    params = []
    if ano_letivo:
        query += " WHERE ano_letivo = ?"
        params.append(ano_letivo)
    rows = db.execute(query, params).fetchall()
    return {(r["turma"], r["disciplina"]): r["professor"] for r in rows}


def comparacao_professores(obs, modelo, mapeamento_prof, ano_letivo=None, periodo=None):
    """Para cada professor (identificado via mapeamento_prof), calcula:
    - média das notas que atribui por disciplina/turma
    - média das notas esperadas para os mesmos alunos (modelo pooled)
    - desvio médio (real − esperado)

    `mapeamento_prof` = {(turma, disciplina): professor}

    Devolve lista de dicts:
      {professor, disciplina, turma, n_obs,
       media_real, media_esperada, desvio_medio,
       n_acima_esperado, n_abaixo_esperado,
       pct_acima_esperado, pct_abaixo_esperado}
    """
    from analytics import nota_esperada_e_desvio

    dados = _filtrar_obs(obs, ano_letivo, periodo)
    if not dados or modelo is None or not mapeamento_prof:
        return []

    agrup: Dict[tuple, dict] = defaultdict(lambda: {
        "reais": [], "esperadas": [], "desvios": [],
        "acima": 0, "abaixo": 0
    })

    for o in dados:
        chave_mapa = (o["turma"], o["disciplina"])
        prof = mapeamento_prof.get(chave_mapa)
        if prof is None:
            continue
        res = nota_esperada_e_desvio(modelo, o["aluno_id"], o["disciplina"],
                                     o["periodo"], o["ano_letivo"])
        if res is None or res.get("nota_esperada") is None:
            continue
        esp = res["nota_esperada"]
        real = o["nota"]
        desvio = real - esp
        chave = (prof, o["disciplina"], o["turma"])
        d = agrup[chave]
        d["reais"].append(real)
        d["esperadas"].append(esp)
        d["desvios"].append(desvio)
        if desvio > 0.5:
            d["acima"] += 1
        elif desvio < -0.5:
            d["abaixo"] += 1

    resultado = []
    for (prof, disc, turma), d in agrup.items():
        n = len(d["desvios"])
        if n == 0:
            continue
        resultado.append({
            "professor":          prof,
            "disciplina":         disc,
            "turma":              turma,
            "n_obs":              n,
            "media_real":         _safe_mean(d["reais"]),
            "media_esperada":     _safe_mean(d["esperadas"]),
            "desvio_medio":       round(statistics.mean(d["desvios"]), 2),
            "n_acima_esperado":   d["acima"],
            "n_abaixo_esperado":  d["abaixo"],
            "pct_acima_esperado": _safe_pct(d["acima"], n),
            "pct_abaixo_esperado":_safe_pct(d["abaixo"], n),
        })

    resultado.sort(key=lambda x: (x["professor"], x["disciplina"], x["turma"]))
    return resultado


def resumo_por_professor(resultados_prof):
    """Agrega resultados por professor (somando todas as turmas/disciplinas).

    Devolve lista de dicts:
      {professor, n_turmas, n_disciplinas, n_obs_total,
       media_real_global, media_esperada_global, desvio_medio_global}
    """
    agrup: Dict[str, dict] = defaultdict(lambda: {
        "turmas": set(), "disciplinas": set(),
        "reais": [], "esperadas": [], "desvios": []
    })
    for r in resultados_prof:
        p = r["professor"]
        agrup[p]["turmas"].add(r["turma"])
        agrup[p]["disciplinas"].add(r["disciplina"])
        n = r["n_obs"]
        # reconstruir listas aproximadas para médias ponderadas
        agrup[p]["reais"].extend([r["media_real"]] * n if r["media_real"] else [])
        agrup[p]["esperadas"].extend([r["media_esperada"]] * n if r["media_esperada"] else [])
        agrup[p]["desvios"].extend([r["desvio_medio"]] * n)

    resultado = []
    for prof, d in agrup.items():
        n = len(d["desvios"])
        resultado.append({
            "professor":              prof,
            "n_turmas":               len(d["turmas"]),
            "n_disciplinas":          len(d["disciplinas"]),
            "n_obs_total":            n,
            "media_real_global":      _safe_mean(d["reais"]),
            "media_esperada_global":  _safe_mean(d["esperadas"]),
            "desvio_medio_global":    round(statistics.mean(d["desvios"]), 2) if d["desvios"] else None,
        })
    resultado.sort(key=lambda x: (x["desvio_medio_global"] or 0), reverse=True)
    return resultado


# ──────────────────────────────────────────────────────────────────────────────
# 5. Listas auxiliares para filtros na página
# ──────────────────────────────────────────────────────────────────────────────

def anos_letivos_disponiveis(obs):
    return sorted({o["ano_letivo"] for o in obs}, reverse=True)


def periodos_disponiveis(obs, ano_letivo=None):
    dados = obs if not ano_letivo else [o for o in obs if o["ano_letivo"] == ano_letivo]
    return sorted({o["periodo"] for o in dados})


def disciplinas_disponiveis(obs, ano_letivo=None, periodo=None):
    dados = _filtrar_obs(obs, ano_letivo, periodo)
    return sorted({o["disciplina"] for o in dados})


def turmas_disponiveis(obs, ano_letivo=None):
    dados = obs if not ano_letivo else [o for o in obs if o["ano_letivo"] == ano_letivo]
    return sorted({o["turma"] for o in dados})
