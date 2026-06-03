"""
Script de configuração completa do Portal de Avaliação.
Execute UMA VEZ após instalar os pacotes:

    pip install flask openpyxl werkzeug gunicorn
    python setup_completo.py

O que faz:
  1. Cria/inicializa a base de dados (portal.db)
  2. Importa os 424 alunos (turmas alunos.xlsx)
  3. Importa as notas do 1º semestre (pasta notas/)
  4. Cria as 23 contas dos diretores de turma
  5. Mostra resumo final
"""

import os, sys, subprocess

def run(script, *args):
    cmd = [sys.executable, script] + list(args)
    result = subprocess.run(cmd, capture_output=False)
    return result.returncode == 0

print("=" * 56)
print("  PORTAL DE AVALIAÇÃO — Colégio Pedro Arrupe")
print("  Configuração inicial")
print("=" * 56)

# 1. Inicializar BD via app.py
print("\n[1/4] A inicializar base de dados...")
import sqlite3
from werkzeug.security import generate_password_hash

DATABASE = "portal.db"
db = sqlite3.connect(DATABASE)
db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        nome TEXT NOT NULL,
        turma TEXT,
        role TEXT NOT NULL DEFAULT 'diretor'
    );
    CREATE TABLE IF NOT EXISTS alunos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero TEXT NOT NULL,
        nome TEXT NOT NULL,
        turma TEXT NOT NULL,
        ano_letivo TEXT NOT NULL DEFAULT '2025/2026',
        UNIQUE(numero, ano_letivo)
    );
    CREATE TABLE IF NOT EXISTS notas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        aluno_id INTEGER NOT NULL REFERENCES alunos(id) ON DELETE CASCADE,
        disciplina TEXT NOT NULL,
        periodo INTEGER NOT NULL,
        nota REAL,
        observacoes TEXT
    );
""")
# Admin por defeito
cur = db.execute("SELECT id FROM users WHERE role='admin'")
if not cur.fetchone():
    db.execute(
        "INSERT INTO users (email, password, nome, role) VALUES (?,?,?,?)",
        ("admin@colegiopedroarrupe.pt", generate_password_hash("admin2026"), "Administrador", "admin")
    )
    print("  → Admin criado: admin@colegiopedroarrupe.pt / admin2026")
db.commit()
db.close()
print("  ✓ Base de dados inicializada")

# 2. Importar alunos
print("\n[2/4] A importar alunos...")
if os.path.exists("turmas alunos.xlsx"):
    run("importar_alunos.py", "turmas alunos.xlsx")
else:
    print("  AVISO: 'turmas alunos.xlsx' não encontrado. Coloque o ficheiro na mesma pasta.")

# 3. Importar notas
print("\n[3/4] A importar notas (pasta notas/)...")
run("importar_notas.py")

# 4. Criar diretores
print("\n[4/4] A criar contas dos diretores de turma...")
run("criar_diretores.py")

# Resumo
print("\n" + "=" * 56)
db = sqlite3.connect(DATABASE)
db.row_factory = sqlite3.Row
n_alunos  = db.execute("SELECT COUNT(*) FROM alunos").fetchone()[0]
n_notas   = db.execute("SELECT COUNT(*) FROM notas").fetchone()[0]
n_users   = db.execute("SELECT COUNT(*) FROM users WHERE role='diretor'").fetchone()[0]
db.close()

print(f"  Alunos:   {n_alunos}")
print(f"  Notas:    {n_notas}")
print(f"  Diretores:{n_users}")
print("=" * 56)
print("\nPara iniciar o servidor local:")
print("  python app.py")
print("  Abrir: http://localhost:5000")
print("\nAdmin: admin@colegiopedroarrupe.pt  /  admin2026")
print("(Altere a password após o primeiro login!)")
