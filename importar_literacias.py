"""
Script para importar as notas de "Literacias" (11º ano, 2º semestre, 2025/2026).

O ficheiro tem o formato "LIT_POLÍTICA_CDF": uma lista contínua, agrupada por
turno/professor (linhas que começam por 'PT' e que devem ser ignoradas), com
colunas (nº de processo, nome do aluno, nota).

Execute:
    python importar_literacias.py [caminho_para_o_ficheiro.xlsx]

Por omissão lê 'notas/notas_literacias_2526.xlsx'.
"""

import sqlite3
import openpyxl
import sys
import os
import unicodedata
import re

DATABASE   = "portal.db"
ANO_LETIVO = "2025/2026"
SEMESTRE   = 2          # Literacias só existe no 2º semestre
DISCIPLINA = "Literacias"
DEFAULT_FICHEIRO = os.path.join("notas", "notas_literacias_2526.xlsx")


def normalizar(s):
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = s.encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


def parse_nota(v):
    """Converte célula em nota numérica (0-20) ou None se inválida/em falta."""
    if v is None:
        return None
    s = str(v).strip()
    if s in ("-", "", "NP", "NP.", "NE", "NA", "—", "#VALOR!", "#VALUE!"):
        return None
    try:
        n = float(s)
    except ValueError:
        return None
    if not (0 <= n <= 20):
        return None
    return n


def parse_ficheiro(path):
    """
    Devolve lista de dicts: {numero, nome, nota}
    Ignora linhas de cabeçalho de turno (coluna A == 'PT').
    """
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active

    registos = []
    for row in ws.iter_rows(min_row=1, values_only=True):
        numero, nome, nota_val = (row + (None, None, None))[:3]
        if numero is None or nome is None:
            continue
        numero_s = str(numero).strip()
        nome_s   = str(nome).strip()
        if not numero_s or not nome_s:
            continue
        if numero_s.upper() == "PT":          # linha de cabeçalho de turno/professor
            continue
        registos.append({
            "numero": numero_s,
            "nome":   nome_s,
            "nota":   parse_nota(nota_val),
            "nota_bruta": nota_val,
        })
    return registos


def encontrar_aluno(db, numero, nome):
    """Procura aluno por nº de processo (com/sem zeros à esquerda) no ano letivo,
    confirmando o nome por aproximação; fallback: procura só por nome."""
    candidatos = []
    for cand_num in {numero, numero.lstrip("0") or "0", numero.zfill(4)}:
        rows = db.execute(
            "SELECT id, numero, nome, turma FROM alunos WHERE numero=? AND ano_letivo=?",
            (cand_num, ANO_LETIVO)
        ).fetchall()
        candidatos.extend(rows)

    if len(candidatos) == 1:
        return candidatos[0]
    if len(candidatos) > 1:
        # desambiguar por nome
        alvo = normalizar(nome)
        for c in candidatos:
            if normalizar(c["nome"]) == alvo:
                return c
        return candidatos[0]

    # fallback: procurar por nome exacto no ano letivo (11º ano)
    alvo = normalizar(nome)
    rows = db.execute(
        "SELECT id, numero, nome, turma FROM alunos WHERE ano_letivo=?",
        (ANO_LETIVO,)
    ).fetchall()
    for r in rows:
        if normalizar(r["nome"]) == alvo:
            return r
    return None


def main():
    ficheiro = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_FICHEIRO
    if not os.path.exists(ficheiro):
        print(f"ERRO: ficheiro não encontrado: {ficheiro}")
        sys.exit(1)

    if not os.path.exists(DATABASE):
        print(f"ERRO: base de dados '{DATABASE}' não encontrada nesta pasta.")
        sys.exit(1)

    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row

    registos = parse_ficheiro(ficheiro)
    print(f"Lidos {len(registos)} registos de alunos em '{ficheiro}'.\n")

    importados   = 0
    actualizados = 0
    sem_nota     = []
    nao_enc      = []

    for reg in registos:
        aluno = encontrar_aluno(db, reg["numero"], reg["nome"])
        if not aluno:
            nao_enc.append(reg)
            continue

        if reg["nota"] is None:
            sem_nota.append(reg)
            continue

        existente = db.execute(
            "SELECT id, nota FROM notas WHERE aluno_id=? AND disciplina=? AND periodo=?",
            (aluno["id"], DISCIPLINA, SEMESTRE)
        ).fetchone()

        if existente:
            if existente["nota"] != reg["nota"]:
                db.execute("UPDATE notas SET nota=? WHERE id=?", (reg["nota"], existente["id"]))
                actualizados += 1
        else:
            db.execute(
                "INSERT INTO notas (aluno_id, disciplina, periodo, nota) VALUES (?,?,?,?)",
                (aluno["id"], DISCIPLINA, SEMESTRE, reg["nota"])
            )
            importados += 1

    db.commit()

    print(f"✓ Notas novas inseridas:      {importados}")
    print(f"✓ Notas actualizadas:         {actualizados}")

    if sem_nota:
        print(f"\n⚠ {len(sem_nota)} aluno(s) sem nota válida (ex.: '#VALOR!') — não importados:")
        for r in sem_nota:
            print(f"   nº {r['numero']:>5}  {r['nome']:<55}  valor original: {r['nota_bruta']!r}")

    if nao_enc:
        print(f"\n⚠ {len(nao_enc)} aluno(s) não encontrados na BD ({ANO_LETIVO}):")
        for r in nao_enc:
            print(f"   nº {r['numero']:>5}  {r['nome']}")

    print(f"\nDisciplina '{DISCIPLINA}' importada como {SEMESTRE}º semestre de {ANO_LETIVO}.")


if __name__ == "__main__":
    main()
