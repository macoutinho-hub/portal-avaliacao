"""
Script para criar as contas dos diretores de turma.
Execute:  python criar_diretores.py

Gera também 'credenciais_diretores.txt' para distribuição.
"""

import sqlite3
import secrets
import string
from werkzeug.security import generate_password_hash

DATABASE = "portal.db"

# ─── DIRETORES — dados reais (Turmas.xlsx + PTs.xlsx) ─────────────────────────
# Formato: ("Nome Completo", "email@colegiopedroarrupe.pt", "TURMA1,TURMA2,...")
DIRETORES = [
    ("Ana Patrícia Abrantes Saraiva Silva",
        "patricia.silva@colegiopedroarrupe.pt",       "10B1"),
    ("Ana Patrícia Bento Neto",
        "patricia.neto@colegiopedroarrupe.pt",         "11A2"),
    ("Ana Raquel Pereira Aires",
        "ana.aires@colegiopedroarrupe.pt",             "12B2 AV,12B2 CT,12B2 SE,10C2"),
    ("André Eduardo Camilo Matos de Barros e Teles",
        "andre.teles@colegiopedroarrupe.pt",           "12E2 CT,12E2 SE,10B2"),
    ("André Leitão Gouveia",
        "andre.gouveia@colegiopedroarrupe.pt",         "12A1 AV,12A1 CT,12A1 SE,12A1 LH"),
    ("Céu da Conceição Martins Casares",
        "ceu.casares@colegiopedroarrupe.pt",           "11E1"),
    ("Helena Maria Velez do Peso",
        "helena.velez@colegiopedroarrupe.pt",          "12C1 AV,12C1 CT,12C1 SE,12C1 LH"),
    ("João Miguel Santos Cardoso Cerqueira",
        "joao.cerqueira@colegiopedroarrupe.pt",        "12C2 CT,12C2 SE"),
    ("Kajal Surendra Parshotam",
        "kajal.parshotam@colegiopedroarrupe.pt",       "11D2"),
    ("Maria Adelaide Graça Amaro Rebelo",
        "adelaide.amaro@colegiopedroarrupe.pt",        "12B1 CT,12B1 SE"),
    ("Maria João Simão da Assunção Morgado",
        "mariajoao.morgado@colegiopedroarrupe.pt",     "12D1 CT,12D1 SE"),
    ("Maria Manuela Gomes Francisco Fonseca",
        "manuela.fonseca@colegiopedroarrupe.pt",       "11E2"),
    ("Maria Olímpia Gonçalves de Almeida",
        "olimpia.almeida@colegiopedroarrupe.pt",       "10D1,11B1"),
    ("Nuno Miguel Agostinho Pedroso",
        "nuno.pedroso@colegiopedroarrupe.pt",          "11B2"),
    ("Nuno Miguel Faria dos Santos",
        "nuno.santos@colegiopedroarrupe.pt",           "10C1"),
    ("Paula Cristina Mendes Henrique Gabellieri",
        "paula.gabellieri@colegiopedroarrupe.pt",      "10A1,11A1"),
    ("Pedro Quintans da Silva",
        "pedro.quintans@colegiopedroarrupe.pt",        "12E1 CT,12E1 SE,11D1,12E1 LH"),
    ("Raquel Tavares Carreiro Nunes Mascarenhas",
        "raquel.mascarenhas@colegiopedroarrupe.pt",    "12D2 CT,12D2 SE,10D2,12D2 LH"),
    ("Ricardo Neto Henriques",
        "ricardo.henriques@colegiopedroarrupe.pt",     "10E2"),
    ("Rui Pedro Lopes Nunes",
        "rui.nunes@colegiopedroarrupe.pt",             "10A2"),
    ("Tiago Alexandre da Silva Pereira Alho",
        "tiago.alho@colegiopedroarrupe.pt",            "11C2"),
    ("Vanessa Azenha Pedro Neves",
        "vanessa.neves@colegiopedroarrupe.pt",         "12A2 SE,10E1,12A2 LH"),
    ("Zita Maria Rodrigues Diz da Silva Nunes Botelho",
        "zita.botelho@colegiopedroarrupe.pt",          "11C1"),
]
# ──────────────────────────────────────────────────────────────────────────────

def gerar_password(n=10):
    chars = string.ascii_letters + string.digits
    return "".join(secrets.choice(chars) for _ in range(n))

def main():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row

    linhas = [
        "CREDENCIAIS DIRETORES DE TURMA — Portal de Avaliação",
        "Colégio Pedro Arrupe · Ano letivo 2025/2026",
        "=" * 56,
        "",
    ]
    criados = 0
    ignorados = 0

    for nome, email, turmas in DIRETORES:
        existing = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if existing:
            print(f"[IGNORADO] {email} já existe.")
            ignorados += 1
            continue
        pwd = gerar_password()
        db.execute(
            "INSERT INTO users (email, password, nome, turma, role) VALUES (?,?,?,?,?)",
            (email, generate_password_hash(pwd), nome, turmas, "diretor")
        )
        turmas_display = turmas.replace(",", ", ")
        linhas.append(f"Nome   : {nome}")
        linhas.append(f"Turmas : {turmas_display}")
        linhas.append(f"Email  : {email}")
        linhas.append(f"Pass   : {pwd}")
        linhas.append("")
        criados += 1
        print(f"[OK] {nome} ({turmas_display})")

    db.commit()
    db.close()

    with open("credenciais_diretores.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(linhas))

    print(f"\n✓ {criados} utilizador(es) criado(s). {ignorados} ignorado(s).")
    print("→ Credenciais guardadas em 'credenciais_diretores.txt'")

if __name__ == "__main__":
    main()
