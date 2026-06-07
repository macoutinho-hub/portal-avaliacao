# -*- coding: utf-8 -*-
"""
Motor de análise pedagógica — Portal de Avaliação CPA
======================================================

Módulo de cálculo para o dashboard de análise do administrador.
Não depende de numpy/pandas — apenas da biblioteca padrão (statistics),
para se manter leve e compatível com o ambiente de produção (Render).

Conceitos-chave
---------------
* "turma"  → turma real do aluno num dado período (ex: "11ºA1 CT")
* "ano"    → conjunto de todas as turmas do mesmo nível curricular
             (10º/11º/12º), independentemente do curso — usa-se
             `nivel_curricular` guardado em `notas` (ou derivado da turma)
* "obs"    → uma observação = uma nota concreta de um aluno, numa
             disciplina, num período, num ano letivo

Modelo de "Nota Esperada"
-------------------------
Regressão linear múltipla (OLS, equações normais resolvidas por
eliminação de Gauss — sem dependências externas), treinada de forma
"pooled" sobre todas as observações disponíveis, prevendo a nota a
partir de:

  x1 = média histórica do aluno NESSA disciplina (excluindo a obs. atual)
  x2 = média histórica global do aluno NOUTRAS disciplinas
  x3 = média da turma/ano nessa disciplina e período (contexto)
  x4 = tendência recente do aluno (declive da média global ao longo dos períodos)

  nota_esperada = b0 + b1·x1 + b2·x2 + b3·x3 + b4·x4

O desvio (nota real − nota esperada) é depois comparado com o desvio-
padrão dos resíduos do modelo para sinalizar outliers (|z| ≥ 1.5 → alerta
moderado; |z| ≥ 2.0 → alerta forte).

Esta abordagem pooled é preferível a um modelo por disciplina/aluno
porque o histórico disponível por aluno é, tipicamente, escasso
(poucos períodos), o que tornaria uma regressão individual instável.
"""

from __future__ import annotations

import statistics
from collections import defaultdict


# ─── Pequena biblioteca de álgebra linear (sem numpy) ──────────────────────────

def _matmul_t(X):
    """Devolve X^T·X (matriz simétrica) como lista de listas."""
    n_cols = len(X[0])
    result = [[0.0] * n_cols for _ in range(n_cols)]
    for row in X:
        for i in range(n_cols):
            for j in range(n_cols):
                result[i][j] += row[i] * row[j]
    return result


def _matvec_t(X, y):
    """Devolve X^T·y como vetor (lista)."""
    n_cols = len(X[0])
    result = [0.0] * n_cols
    for row, yi in zip(X, y):
        for i in range(n_cols):
            result[i] += row[i] * yi
    return result


def _solve_linear_system(A, b):
    """Resolve A·x = b por eliminação de Gauss com pivot parcial.

    A: matriz quadrada (lista de listas), b: vetor.
    Devolve x (lista) ou None se o sistema for singular.
    """
    n = len(A)
    # Construir matriz aumentada
    M = [row[:] + [b[i]] for i, row in enumerate(A)]

    for col in range(n):
        # Pivot parcial: escolher a linha com maior valor absoluto na coluna
        pivot_row = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[pivot_row][col]) < 1e-12:
            return None  # sistema singular / quase singular
        M[col], M[pivot_row] = M[pivot_row], M[col]

        # Normalizar a linha do pivot
        pivot_val = M[col][col]
        M[col] = [v / pivot_val for v in M[col]]

        # Eliminar nas outras linhas
        for r in range(n):
            if r != col:
                factor = M[r][col]
                M[r] = [M[r][k] - factor * M[col][k] for k in range(n + 1)]

    return [M[i][n] for i in range(n)]


def ols_fit(X, y):
    """Ajusta uma regressão linear múltipla por OLS (equações normais).

    X: lista de listas de features (SEM coluna de intercepto — é adicionada aqui)
    y: lista de valores-alvo

    Devolve (coeficientes, resíduos) ou (None, None) se não for possível ajustar.
    coeficientes[0] é o intercepto.
    """
    if len(X) < len(X[0]) + 2:
        return None, None  # dados insuficientes para um ajuste estável

    X_design = [[1.0] + list(row) for row in X]
    XtX = _matmul_t(X_design)
    Xty = _matvec_t(X_design, y)
    coefs = _solve_linear_system(XtX, Xty)
    if coefs is None:
        return None, None

    residuos = []
    for row, yi in zip(X_design, y):
        pred = sum(c * v for c, v in zip(coefs, row))
        residuos.append(yi - pred)

    return coefs, residuos


def ols_predict(coefs, features):
    """Prevê um valor a partir dos coeficientes (coefs[0] = intercepto)."""
    return coefs[0] + sum(c * v for c, v in zip(coefs[1:], features))


# ─── Recolha de dados ──────────────────────────────────────────────────────────

def nivel_de_turma(turma):
    """Extrai o nível curricular (10/11/12) do nome da turma. Default: 11."""
    import re
    m = re.match(r"(\d+)", str(turma or ""))
    return int(m.group(1)) if m else 11


def carregar_observacoes(db):
    """Carrega TODAS as observações de notas (todas as turmas/anos letivos)
    já enriquecidas com identificação do aluno (numero), turma, nível e ano.

    Devolve uma lista de dicts:
      {numero, nome, aluno_id, turma, nivel, ano_letivo, disciplina, periodo, nota}

    Apenas considera notas numéricas (0-20); ignora notas qualitativas
    (nota_texto sem valor numérico em `nota`).
    """
    rows = db.execute("""
        SELECT n.aluno_id, n.disciplina, n.periodo, n.nota, n.nivel_curricular,
               a.numero, a.nome, a.turma, a.ano_letivo
        FROM notas n
        JOIN alunos a ON a.id = n.aluno_id
        WHERE n.nota IS NOT NULL
    """).fetchall()

    obs = []
    for r in rows:
        nivel = r["nivel_curricular"] if r["nivel_curricular"] else nivel_de_turma(r["turma"])
        obs.append({
            "aluno_id":   r["aluno_id"],
            "numero":     r["numero"],
            "nome":       r["nome"],
            "turma":      r["turma"],
            "nivel":      nivel,
            "ano_letivo": r["ano_letivo"],
            "disciplina": r["disciplina"],
            "periodo":    r["periodo"],
            "nota":       float(r["nota"]),
        })
    return obs


# ─── Posicionamento relativo (ranking / percentil) ─────────────────────────────

def _ranking_e_percentil(valores, valor_alvo):
    """Calcula posição (1 = melhor) e percentil de `valor_alvo` dentro de `valores`.

    Ranking por "competição" (empates partilham posição; salta posições a seguir).
    Percentil = % de colegas com nota estritamente inferior (0-100).
    """
    n = len(valores)
    if n == 0:
        return None, None
    posicao = 1 + sum(1 for v in valores if v > valor_alvo)
    inferiores = sum(1 for v in valores if v < valor_alvo)
    percentil = round(100 * inferiores / n) if n > 1 else 100
    return posicao, percentil


def posicionamento_por_disciplina(observacoes, aluno_id, ano_letivo, periodo=None):
    """Para um aluno, devolve o posicionamento em cada disciplina no
    período mais recente disponível (ou no `periodo` indicado), face à
    turma e ao ano (mesmo nível curricular, todas as turmas).

    Devolve lista de dicts ordenada pela ordem natural das disciplinas:
      {disciplina, periodo, nota, media_turma, media_ano,
       pos_turma, n_turma, pos_ano, n_ano, percentil_ano}
    """
    # Filtrar pelo ano letivo do aluno (posicionamento é sempre dentro do
    # mesmo ano letivo / mesmo grupo de colegas)
    obs_ano = [o for o in observacoes if o["ano_letivo"] == ano_letivo]
    if not obs_ano:
        return []

    aluno_obs = [o for o in obs_ano if o["aluno_id"] == aluno_id]
    if not aluno_obs:
        return []

    turma_aluno = aluno_obs[0]["turma"]
    nivel_aluno = aluno_obs[0]["nivel"]

    # Para cada disciplina, escolher o período mais recente em que o
    # aluno tem nota (ou o `periodo` pedido, se especificado e existir)
    por_disciplina = defaultdict(list)
    for o in aluno_obs:
        por_disciplina[o["disciplina"]].append(o)

    resultado = []
    for disciplina, lst in por_disciplina.items():
        if periodo is not None:
            candidatos = [o for o in lst if o["periodo"] == periodo]
            alvo = candidatos[-1] if candidatos else max(lst, key=lambda o: o["periodo"])
        else:
            alvo = max(lst, key=lambda o: o["periodo"])

        p = alvo["periodo"]
        nota_aluno = alvo["nota"]

        # Colegas de turma (mesma disciplina/período/turma exata)
        notas_turma = [o["nota"] for o in obs_ano
                       if o["disciplina"] == disciplina and o["periodo"] == p
                       and o["turma"] == turma_aluno]
        # Colegas de ano (mesmo nível curricular, todas as turmas)
        notas_ano = [o["nota"] for o in obs_ano
                     if o["disciplina"] == disciplina and o["periodo"] == p
                     and o["nivel"] == nivel_aluno]

        pos_turma, _ = _ranking_e_percentil(notas_turma, nota_aluno)
        pos_ano, percentil_ano = _ranking_e_percentil(notas_ano, nota_aluno)

        resultado.append({
            "disciplina":     disciplina,
            "periodo":        p,
            "nota":           nota_aluno,
            "media_turma":    round(statistics.mean(notas_turma), 1) if notas_turma else None,
            "media_ano":      round(statistics.mean(notas_ano), 1) if notas_ano else None,
            "pos_turma":      pos_turma,
            "n_turma":        len(notas_turma),
            "pos_ano":        pos_ano,
            "n_ano":          len(notas_ano),
            "percentil_ano":  percentil_ano,
        })

    resultado.sort(key=lambda r: r["disciplina"])
    return resultado


# ─── Perfil académico individual (padrão habitual + desvios) ───────────────────

def perfil_academico(observacoes, aluno_id, limiar_z=1.0):
    """Constrói o perfil do aluno: para cada disciplina onde tem histórico,
    compara a média do aluno NESSA disciplina com a sua média pessoal global,
    usando um z-score baseado na variabilidade pessoal entre disciplinas.

    Devolve dict:
      {
        "media_global": float,
        "desvio_padrao_pessoal": float,
        "disciplinas": [
            {disciplina, media_aluno, n_obs, diferenca, z, classificacao}
            ...
        ],
        "pontos_fortes": [...],   # claramente acima do seu padrão
        "pontos_fracos": [...],   # claramente abaixo do seu padrão
      }

    `classificacao` ∈ {"acima", "abaixo", "habitual"}; baseada no z-score
    da média-por-disciplina face à distribuição das médias do próprio aluno
    pelas várias disciplinas (limiar_z, default 1.0 desvio-padrão).
    """
    aluno_obs = [o for o in observacoes if o["aluno_id"] == aluno_id]
    if not aluno_obs:
        return None

    medias_disc = {}
    contagens = {}
    for disciplina in {o["disciplina"] for o in aluno_obs}:
        notas = [o["nota"] for o in aluno_obs if o["disciplina"] == disciplina]
        medias_disc[disciplina] = statistics.mean(notas)
        contagens[disciplina] = len(notas)

    valores = list(medias_disc.values())
    media_global = statistics.mean(valores)
    desvio_pessoal = statistics.pstdev(valores) if len(valores) > 1 else 0.0

    disciplinas = []
    for disciplina, media in sorted(medias_disc.items()):
        diferenca = media - media_global
        z = (diferenca / desvio_pessoal) if desvio_pessoal > 1e-9 else 0.0
        if z >= limiar_z:
            classificacao = "acima"
        elif z <= -limiar_z:
            classificacao = "abaixo"
        else:
            classificacao = "habitual"
        disciplinas.append({
            "disciplina":   disciplina,
            "media_aluno":  round(media, 1),
            "n_obs":        contagens[disciplina],
            "diferenca":    round(diferenca, 1),
            "z":            round(z, 2),
            "classificacao": classificacao,
        })

    pontos_fortes = [d for d in disciplinas if d["classificacao"] == "acima"]
    pontos_fracos = [d for d in disciplinas if d["classificacao"] == "abaixo"]

    return {
        "media_global":          round(media_global, 1),
        "desvio_padrao_pessoal": round(desvio_pessoal, 2),
        "disciplinas":           disciplinas,
        "pontos_fortes":         sorted(pontos_fortes, key=lambda d: -d["z"]),
        "pontos_fracos":         sorted(pontos_fracos, key=lambda d: d["z"]),
    }


# ─── Modelo "Nota Esperada" (regressão pooled) ─────────────────────────────────

def _tendencia_recente(serie_periodos):
    """Calcula o declive (tendência) de uma série [(periodo, media), ...]
    ordenada por período, via regressão linear simples. Devolve 0.0 se
    houver menos de 2 pontos distintos.
    """
    pontos = sorted(set(serie_periodos))
    if len(pontos) < 2:
        return 0.0
    xs = [p[0] for p in pontos]
    ys = [p[1] for p in pontos]
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = sum((x - mx) ** 2 for x in xs)
    return (num / den) if den > 1e-9 else 0.0


def construir_modelo_nota_esperada(observacoes):
    """Treina um modelo de regressão pooled sobre TODAS as observações
    disponíveis (todas as turmas/anos letivos) para prever a nota
    esperada de qualquer (aluno, disciplina, período).

    Devolve um dict com o modelo treinado e estruturas de apoio, ou None
    se não houver dados suficientes:
      {coefs, desvio_residuos, cache_features: {(aluno_id,disciplina,periodo,ano): features}}

    As features de cada observação são calculadas EXCLUINDO essa própria
    observação (evita circularidade): médias do aluno calculadas sobre o
    resto do seu histórico.
    """
    if len(observacoes) < 30:
        return None

    # Indexar observações por aluno e por (disciplina, periodo, ano, turma/nivel)
    por_aluno = defaultdict(list)
    for o in observacoes:
        por_aluno[o["aluno_id"]].append(o)

    # Pré-calcular médias de contexto (turma+ano+disciplina+periodo e nivel+ano+disciplina+periodo)
    contexto_turma = defaultdict(list)
    contexto_ano = defaultdict(list)
    for o in observacoes:
        contexto_turma[(o["ano_letivo"], o["turma"], o["disciplina"], o["periodo"])].append(o["nota"])
        contexto_ano[(o["ano_letivo"], o["nivel"], o["disciplina"], o["periodo"])].append(o["nota"])

    X, y, chaves = [], [], []

    for aluno_id, obs_aluno in por_aluno.items():
        if len(obs_aluno) < 3:
            continue  # histórico demasiado curto para gerar features fiáveis

        for idx, o in enumerate(obs_aluno):
            resto = obs_aluno[:idx] + obs_aluno[idx + 1:]
            if not resto:
                continue

            mesma_disc = [r["nota"] for r in resto if r["disciplina"] == o["disciplina"]]
            outras_disc = [r["nota"] for r in resto if r["disciplina"] != o["disciplina"]]
            if not outras_disc:
                continue

            x1 = statistics.mean(mesma_disc) if mesma_disc else statistics.mean(outras_disc)
            x2 = statistics.mean(outras_disc)

            # Contexto (turma/ano), excluindo a própria nota
            ctx_turma = [v for v in contexto_turma[(o["ano_letivo"], o["turma"], o["disciplina"], o["periodo"])]]
            ctx_ano = [v for v in contexto_ano[(o["ano_letivo"], o["nivel"], o["disciplina"], o["periodo"])]]
            # Remover uma ocorrência da própria nota (aprox. — não rastreamos índice exato)
            if o["nota"] in ctx_turma:
                ctx_turma = ctx_turma[:]
                ctx_turma.remove(o["nota"])
            if o["nota"] in ctx_ano:
                ctx_ano = ctx_ano[:]
                ctx_ano.remove(o["nota"])
            x3 = statistics.mean(ctx_ano) if ctx_ano else (statistics.mean(ctx_turma) if ctx_turma else x2)

            # Tendência: média global do aluno por período (excluindo esta obs)
            por_periodo = defaultdict(list)
            for r in resto:
                por_periodo[r["periodo"]].append(r["nota"])
            serie = [(p, statistics.mean(notas)) for p, notas in por_periodo.items()]
            x4 = _tendencia_recente(serie)

            X.append([x1, x2, x3, x4])
            y.append(o["nota"])
            chaves.append((aluno_id, o["disciplina"], o["periodo"], o["ano_letivo"]))

    if len(X) < 30:
        return None

    coefs, residuos = ols_fit(X, y)
    if coefs is None:
        return None

    desvio_residuos = statistics.pstdev(residuos) if len(residuos) > 1 else 1.0
    cache_features = {chave: feats for chave, feats in zip(chaves, X)}

    return {
        "coefs":           coefs,
        "desvio_residuos": round(desvio_residuos, 2) if desvio_residuos else 1.0,
        "cache_features":  cache_features,
        "n_observacoes":   len(X),
    }


def nota_esperada_e_desvio(modelo, aluno_id, disciplina, periodo, ano_letivo):
    """Devolve (nota_esperada, desvio, z_desvio) para uma observação concreta,
    usando o modelo pooled treinado. Se a combinação não existir na cache de
    features (ex.: aluno com histórico demasiado curto), devolve (None, None, None).
    """
    if modelo is None:
        return None, None, None

    chave = (aluno_id, disciplina, periodo, ano_letivo)
    feats = modelo["cache_features"].get(chave)
    if feats is None:
        return None, None, None

    esperada = ols_predict(modelo["coefs"], feats)
    return round(esperada, 1), feats, modelo["desvio_residuos"]


# ─── Evolução temporal ─────────────────────────────────────────────────────────

def evolucao_temporal(observacoes, aluno_id):
    """Série temporal da média global do aluno e, quando possível, da sua
    posição relativa (ranking/percentil no ano), ao longo dos
    (ano_letivo, período) disponíveis, ordenada cronologicamente.

    Devolve lista de dicts:
      {ano_letivo, periodo, media_aluno, media_ano, percentil_ano, n_disciplinas}
    """
    aluno_obs = [o for o in observacoes if o["aluno_id"] == aluno_id]
    if not aluno_obs:
        return []

    chaves = sorted({(o["ano_letivo"], o["periodo"]) for o in aluno_obs})

    serie = []
    for ano_letivo, periodo in chaves:
        obs_periodo = [o for o in aluno_obs if o["ano_letivo"] == ano_letivo and o["periodo"] == periodo]
        media_aluno = statistics.mean(o["nota"] for o in obs_periodo)
        nivel = obs_periodo[0]["nivel"]

        # Média global de todos os colegas do mesmo ano/nível neste período
        # (média das médias individuais, para não enviesar por nº de disciplinas)
        colegas = defaultdict(list)
        for o in observacoes:
            if o["ano_letivo"] == ano_letivo and o["periodo"] == periodo and o["nivel"] == nivel:
                colegas[o["aluno_id"]].append(o["nota"])
        medias_colegas = [statistics.mean(notas) for notas in colegas.values()]

        pos, percentil = _ranking_e_percentil(medias_colegas, media_aluno)

        serie.append({
            "ano_letivo":    ano_letivo,
            "periodo":       periodo,
            "media_aluno":   round(media_aluno, 1),
            "media_ano":     round(statistics.mean(medias_colegas), 1) if medias_colegas else None,
            "pos_ano":       pos,
            "n_ano":         len(medias_colegas),
            "percentil_ano": percentil,
            "n_disciplinas": len(obs_periodo),
        })

    return serie


def deteccao_mudancas_bruscas(serie_evolucao, limiar=2.0):
    """A partir da evolução temporal (lista ordenada cronologicamente),
    sinaliza transições onde a média global do aluno varia mais do que
    `limiar` valores entre dois períodos consecutivos.

    Devolve lista de dicts: {de, para, variacao, tipo: "melhoria"|"deterioracao"}
    """
    alertas = []
    for i in range(1, len(serie_evolucao)):
        anterior, atual = serie_evolucao[i - 1], serie_evolucao[i]
        variacao = atual["media_aluno"] - anterior["media_aluno"]
        if abs(variacao) >= limiar:
            alertas.append({
                "de":        f"{anterior['ano_letivo']} — {anterior['periodo']}º Sem.",
                "para":      f"{atual['ano_letivo']} — {atual['periodo']}º Sem.",
                "variacao":  round(variacao, 1),
                "tipo":      "melhoria" if variacao > 0 else "deterioracao",
            })
    return alertas


# ─── Análise completa de um aluno (ponto de entrada) ───────────────────────────

def analisar_aluno(db, aluno_id):
    """Ponto de entrada principal: recolhe observações, treina o modelo
    pooled (cacheável a montante pelo chamador) e devolve toda a análise
    pronta a renderizar para um aluno específico.

    Devolve None se o aluno não tiver notas registadas.
    """
    observacoes = carregar_observacoes(db)
    aluno_obs = [o for o in observacoes if o["aluno_id"] == aluno_id]
    if not aluno_obs:
        return None

    ano_letivo_aluno = max(o["ano_letivo"] for o in aluno_obs)

    modelo = construir_modelo_nota_esperada(observacoes)

    posicionamento = posicionamento_por_disciplina(observacoes, aluno_id, ano_letivo_aluno)
    perfil = perfil_academico(observacoes, aluno_id)
    evolucao = evolucao_temporal(observacoes, aluno_id)
    mudancas = deteccao_mudancas_bruscas(evolucao)

    # Nota esperada vs real para a disciplina/período mais recente de cada disciplina
    outliers = []
    nota_esperada_tabela = []
    for p in posicionamento:
        esperada, feats, desvio_residuos = nota_esperada_e_desvio(
            modelo, aluno_id, p["disciplina"], p["periodo"], ano_letivo_aluno
        )
        linha = {
            "disciplina":   p["disciplina"],
            "periodo":      p["periodo"],
            "nota_real":    p["nota"],
            "nota_esperada": esperada,
        }
        if esperada is not None:
            desvio = round(p["nota"] - esperada, 1)
            z = round(desvio / desvio_residuos, 2) if desvio_residuos else 0.0
            linha["desvio"] = desvio
            linha["z"] = z
            if z <= -1.5:
                tipo = "abaixo_forte" if z <= -2.0 else "abaixo"
                outliers.append({**linha, "tipo": tipo})
            elif z >= 1.5:
                tipo = "acima_forte" if z >= 2.0 else "acima"
                outliers.append({**linha, "tipo": tipo})
        nota_esperada_tabela.append(linha)

    # Indicadores de risco / potencial (resumo)
    disciplinas_alerta = [o for o in outliers if o["tipo"].startswith("abaixo")]
    disciplinas_excelencia = [o for o in outliers if o["tipo"].startswith("acima")]

    return {
        "ano_letivo":            ano_letivo_aluno,
        "posicionamento":        posicionamento,
        "perfil":                perfil,
        "evolucao":              evolucao,
        "mudancas_bruscas":      mudancas,
        "nota_esperada_tabela":  nota_esperada_tabela,
        "outliers":              outliers,
        "disciplinas_alerta":    disciplinas_alerta,
        "disciplinas_excelencia": disciplinas_excelencia,
        "modelo_disponivel":     modelo is not None,
        "modelo_n_obs":          modelo["n_observacoes"] if modelo else 0,
    }


# ─── Resumo agregado por turma (para navegação rápida) ─────────────────────────

def resumo_indicadores_turma(db, turma):
    """Calcula, para cada aluno de uma turma, um resumo leve de indicadores
    de risco/potencial — pensado para ser apresentado como badges na lista
    de alunos da turma, permitindo identificação precoce sem ter de abrir
    a análise individual de cada um.

    Devolve dict {aluno_id: {"n_alerta", "n_excelencia", "media_global",
                              "tendencia": "melhoria"|"estavel"|"deterioracao"|None}}

    Treina o modelo pooled UMA SÓ VEZ (sobre toda a escola) e reutiliza-o
    para todos os alunos da turma — evita o custo de o recalcular por aluno.
    """
    observacoes = carregar_observacoes(db)
    if not observacoes:
        return {}

    modelo = construir_modelo_nota_esperada(observacoes)

    alunos_turma = {o["aluno_id"] for o in observacoes if o["turma"] == turma}
    resumo = {}

    for aluno_id in alunos_turma:
        aluno_obs = [o for o in observacoes if o["aluno_id"] == aluno_id]
        if not aluno_obs:
            continue
        ano_letivo_aluno = max(o["ano_letivo"] for o in aluno_obs)

        posicionamento = posicionamento_por_disciplina(observacoes, aluno_id, ano_letivo_aluno)
        perfil = perfil_academico(observacoes, aluno_id)
        evolucao = evolucao_temporal(observacoes, aluno_id)

        n_alerta = n_excelencia = 0
        for p in posicionamento:
            esperada, _feats, desvio_residuos = nota_esperada_e_desvio(
                modelo, aluno_id, p["disciplina"], p["periodo"], ano_letivo_aluno
            )
            if esperada is None or not desvio_residuos:
                continue
            z = (p["nota"] - esperada) / desvio_residuos
            if z <= -1.5:
                n_alerta += 1
            elif z >= 1.5:
                n_excelencia += 1

        tendencia = None
        if len(evolucao) >= 2:
            variacao = evolucao[-1]["media_aluno"] - evolucao[-2]["media_aluno"]
            if variacao >= 1.0:
                tendencia = "melhoria"
            elif variacao <= -1.0:
                tendencia = "deterioracao"
            else:
                tendencia = "estavel"

        resumo[aluno_id] = {
            "n_alerta":      n_alerta,
            "n_excelencia":  n_excelencia,
            "media_global":  perfil["media_global"] if perfil else None,
            "tendencia":     tendencia,
        }

    return resumo
