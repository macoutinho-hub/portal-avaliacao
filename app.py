# Portal de Avaliação — Colégio Pedro Arrupe
import os
import sqlite3
import secrets
from functools import wraps
from datetime import datetime

from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, g, jsonify)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import openpyxl

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

DATABASE = os.environ.get("DATABASE", "portal.db")
UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", "uploads")
FOTOS_FOLDER  = os.environ.get("FOTOS_FOLDER", os.path.join(os.path.dirname(DATABASE) if os.path.dirname(DATABASE) else ".", "fotos"))
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(FOTOS_FOLDER,  exist_ok=True)

# Inicializar BD ao arrancar (funciona com gunicorn e python app.py)
# Chamado depois de 'app' ser criado, via with app.app_context()
def _auto_init():
    with app.app_context():
        init_db()

import atexit as _atexit

# ─── DB ────────────────────────────────────────────────────────────────────────

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop("db", None)
    if db:
        db.close()

def init_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            email     TEXT UNIQUE NOT NULL,
            password  TEXT NOT NULL,
            nome      TEXT NOT NULL,
            turma     TEXT,          -- NULL = admin
            role      TEXT NOT NULL DEFAULT 'diretor'  -- 'admin' | 'diretor'
        );

        CREATE TABLE IF NOT EXISTS alunos (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            numero     TEXT NOT NULL,
            nome       TEXT NOT NULL,
            turma      TEXT NOT NULL,
            ano_letivo TEXT NOT NULL DEFAULT '2025/2026',
            UNIQUE(numero, ano_letivo)
        );

        CREATE TABLE IF NOT EXISTS notas (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            aluno_id     INTEGER NOT NULL REFERENCES alunos(id) ON DELETE CASCADE,
            disciplina   TEXT NOT NULL,
            periodo      INTEGER NOT NULL,
            nota         REAL,
            observacoes  TEXT
        );

        CREATE TABLE IF NOT EXISTS notas_reuniao (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            aluno_id     INTEGER NOT NULL REFERENCES alunos(id) ON DELETE CASCADE,
            categoria    TEXT NOT NULL,
            texto        TEXT NOT NULL DEFAULT '',
            updated_at   TEXT,
            updated_by   INTEGER REFERENCES users(id),
            UNIQUE(aluno_id, categoria)
        );
    """)
    db.commit()
    # Create default admin if not exists
    cur = db.execute("SELECT id FROM users WHERE role='admin'")
    if not cur.fetchone():
        db.execute(
            "INSERT INTO users (email, password, nome, role) VALUES (?,?,?,?)",
            ("admin@escola.pt", generate_password_hash("admin123"), "Administrador", "admin")
        )
        db.commit()
    db.close()

# ─── Auth helpers ──────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Acesso restrito a administradores.", "danger")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated

# ─── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["nome"] = user["nome"]
            session["role"] = user["role"]
            session["turma"] = user["turma"]
            return redirect(url_for("dashboard"))
        flash("Email ou password incorretos.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

def calcular_alunos_info(db, turma):
    """Devolve lista de alunos com média e nº de negativas para uma turma."""
    alunos = db.execute(
        "SELECT * FROM alunos WHERE turma=? ORDER BY nome", (turma,)
    ).fetchall()
    alunos_info = []
    for a in alunos:
        periodos = db.execute(
            "SELECT DISTINCT periodo FROM notas WHERE aluno_id=? ORDER BY periodo DESC",
            (a["id"],)
        ).fetchall()
        ultimo_periodo = periodos[0]["periodo"] if periodos else None
        media = None
        num_negas = 0
        if ultimo_periodo:
            notas = db.execute(
                "SELECT nota FROM notas WHERE aluno_id=? AND periodo=? AND nota IS NOT NULL",
                (a["id"], ultimo_periodo)
            ).fetchall()
            vals = [n["nota"] for n in notas if n["nota"] is not None]
            media = round(sum(vals) / len(vals), 1) if vals else None
            num_negas = sum(1 for v in vals if v < 10)
        alunos_info.append({
            "id": a["id"], "numero": a["numero"], "nome": a["nome"],
            "turma": a["turma"], "media": media, "periodo": ultimo_periodo,
            "num_negas": num_negas
        })
    return alunos_info

def calcular_stats_turma(db, turma, periodo_sel=None):
    """Calcula médias por disciplina e comparação entre períodos para uma turma."""
    alunos = db.execute("SELECT id FROM alunos WHERE turma=?", (turma,)).fetchall()
    ids = [a["id"] for a in alunos]
    if not ids:
        return {}, [], None, []

    periodos_disponiveis = [r["periodo"] for r in db.execute(
        f"SELECT DISTINCT periodo FROM notas WHERE aluno_id IN ({','.join('?'*len(ids))}) ORDER BY periodo",
        ids
    ).fetchall()]

    if not periodo_sel or periodo_sel not in periodos_disponiveis:
        periodo_sel = periodos_disponiveis[-1] if periodos_disponiveis else None

    # Médias por disciplina no período seleccionado
    medias_disciplinas = []
    if periodo_sel:
        rows = db.execute(
            f"SELECT disciplina, AVG(nota) as media FROM notas "
            f"WHERE aluno_id IN ({','.join('?'*len(ids))}) AND periodo=? AND nota IS NOT NULL "
            f"GROUP BY disciplina ORDER BY disciplina",
            ids + [periodo_sel]
        ).fetchall()
        medias_disciplinas = [(r["disciplina"], round(r["media"], 1)) for r in rows]

    # Comparação 1º vs 2º semestre
    comparacao = []
    if len(periodos_disponiveis) >= 2:
        p1, p2 = periodos_disponiveis[0], periodos_disponiveis[1]
        discs1 = {r["disciplina"]: r["media"] for r in db.execute(
            f"SELECT disciplina, AVG(nota) as media FROM notas "
            f"WHERE aluno_id IN ({','.join('?'*len(ids))}) AND periodo=? AND nota IS NOT NULL GROUP BY disciplina",
            ids + [p1]
        ).fetchall()}
        discs2 = {r["disciplina"]: r["media"] for r in db.execute(
            f"SELECT disciplina, AVG(nota) as media FROM notas "
            f"WHERE aluno_id IN ({','.join('?'*len(ids))}) AND periodo=? AND nota IS NOT NULL GROUP BY disciplina",
            ids + [p2]
        ).fetchall()}
        for disc in set(discs1) & set(discs2):
            comparacao.append((disc, round(discs1[disc], 1), round(discs2[disc], 1),
                                round(discs2[disc] - discs1[disc], 1)))

    return medias_disciplinas, periodos_disponiveis, periodo_sel, comparacao

@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    if session["role"] == "admin":
        turmas = db.execute(
            "SELECT turma, COUNT(*) as total FROM alunos GROUP BY turma ORDER BY turma"
        ).fetchall()
        return render_template("dashboard_admin.html", turmas=turmas)
    else:
        # turma pode ser "12A1 AV" ou "12A1 AV,12A1 CT,12A1 SE"
        turmas_str = session.get("turma") or ""
        turmas_lista = [t.strip() for t in turmas_str.split(",") if t.strip()]

        turma_sel = request.args.get("turma", turmas_lista[0] if turmas_lista else "")
        if turma_sel not in turmas_lista:
            turma_sel = turmas_lista[0] if turmas_lista else ""
        periodo_sel = request.args.get("periodo", None)
        if periodo_sel:
            try: periodo_sel = int(periodo_sel)
            except: periodo_sel = None

        alunos_info = calcular_alunos_info(db, turma_sel) if turma_sel else []
        medias_disc, periodos_disp, periodo_sel, comparacao = calcular_stats_turma(db, turma_sel, periodo_sel)

        kwargs = dict(alunos=alunos_info, turma=turma_sel,
                      medias_disciplinas=medias_disc,
                      periodos_disponiveis=periodos_disp,
                      periodo_sel=periodo_sel,
                      comparacao_periodos=comparacao)
        if len(turmas_lista) > 1:
            kwargs["turmas_multiplas"] = turmas_lista
        return render_template("dashboard.html", **kwargs)

@app.route("/aluno/<int:aluno_id>")
@login_required
def aluno(aluno_id):
    db = get_db()
    a = db.execute("SELECT * FROM alunos WHERE id=?", (aluno_id,)).fetchone()
    if not a:
        flash("Aluno não encontrado.", "danger")
        return redirect(url_for("dashboard"))
    # Verificar permissão (suporta múltiplas turmas)
    turmas_user = [t.strip() for t in (session.get("turma") or "").split(",")]
    if session["role"] != "admin" and a["turma"] not in turmas_user:
        flash("Não tem permissão para ver este aluno.", "danger")
        return redirect(url_for("dashboard"))

    # ── Recolher todos os dados de notas (ano actual + anteriores) ────────────
    todos_alunos_ids = {a["ano_letivo"]: aluno_id}
    if a["numero"]:
        for outro in db.execute(
            "SELECT id, ano_letivo FROM alunos WHERE numero=? AND ano_letivo!=? ORDER BY ano_letivo",
            (a["numero"], a["ano_letivo"])
        ).fetchall():
            todos_alunos_ids[outro["ano_letivo"]] = outro["id"]

    # notas_por_ano: {ano_letivo: {disciplina: {periodo: nota}}}
    notas_por_ano = {}
    for ano, aid in todos_alunos_ids.items():
        rows = db.execute(
            "SELECT disciplina, periodo, nota FROM notas WHERE aluno_id=? ORDER BY disciplina, periodo",
            (aid,)
        ).fetchall()
        if rows:
            notas_por_ano[ano] = {}
            for r in rows:
                d = r["disciplina"]
                notas_por_ano[ano].setdefault(d, {})[r["periodo"]] = r["nota"]

    # ── Abreviaturas das disciplinas ──────────────────────────────────────────
    ABREVIATURAS = {
        "Português": "POR", "Inglês": "ING", "Filosofia": "FIL",
        "Educação Física": "EF", "Religião": "REL", "Matemática A": "MAT_A",
        "Matemática Geral": "MAT_G", "Desenho A": "DES_A", "Desenho Geral": "DES_G",
        "História A": "HIST_A", "História Geral": "HIST_G", "Geografia A": "GEO_A",
        "Biologia": "BIO", "Biologia e Geologia": "BG", "Física": "FIS",
        "Física e Química A": "FQ_A", "Química": "QUI",
        "Economia A": "ECO_A", "Economia C": "ECO_C",
        "Geometria Descritiva A": "GD_A",
        "Aplicações Informáticas B": "AI_B",
        "Psicologia B": "PSI_B", "Ciência Política": "CP",
        "Filosofia A": "FIL_A",
        "Oficinas": "OFI",
        "Hora de PT": "PT", "Projeto": "PROJ",
        "Tempo de Trabalho Autónomo": "TTA",
        "Líng. Estrang. I - Inglês": "ING",
    }

    # ── Lista ordenada de todas as disciplinas ────────────────────────────────
    todas_disciplinas = sorted({d for ano_d in notas_por_ano.values() for d in ano_d})

    # Separador: disciplinas específicas aparecem depois das gerais
    # (heurística: disciplinas com sufixo A/B/C ou nomes específicos)
    disc_especificas_keywords = ["_A", "_B", "_C", "Desenho", "História A", "Biologia e G",
                                  "Física e Q", "Geometria", "Economia A", "Geografia"]
    def e_especifica(d):
        return any(k in d for k in disc_especificas_keywords)

    gerais  = [d for d in todas_disciplinas if not e_especifica(d)]
    especif = [d for d in todas_disciplinas if e_especifica(d)]
    todas_disciplinas = gerais + especif
    separador_idx = len(gerais) if especif else None

    # ── Construir linhas da tabela ────────────────────────────────────────────
    ano_atual = a["ano_letivo"]
    linhas = []

    def media_notas(notas_dict):
        vals = [v for v in notas_dict.values() if v is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    # Extrair ano escolar da turma (ex: "10D1" → "10º Ano", "12A1 CT" → "12º Ano")
    import re as _re
    def ano_da_turma(turma_str):
        m = _re.match(r"(\d+)", str(turma_str or ""))
        return (m.group(1) + "º Ano") if m else "Ano ?"

    for ano in sorted(notas_por_ano.keys()):
        disc_ano = notas_por_ano[ano]
        periodos = sorted({p for d in disc_ano.values() for p in d})
        # Obter a turma do aluno neste ano letivo
        aluno_ano = db.execute(
            "SELECT turma FROM alunos WHERE numero=? AND ano_letivo=?",
            (a["numero"], ano)
        ).fetchone()
        turma_ano = aluno_ano["turma"] if aluno_ano else a["turma"]
        ano_escolar = ano_da_turma(turma_ano)

        for p in periodos:
            notas_linha = {d: disc_ano.get(d, {}).get(p) for d in todas_disciplinas}
            vals = [v for v in notas_linha.values() if v is not None]
            linhas.append({
                "label": f"{ano_escolar} — {p}º Sem.",
                "tipo": "semestre",
                "atual": ano == ano_atual,
                "notas": notas_linha,
                "media": round(sum(vals) / len(vals), 1) if vals else None,
            })

        # CIF por disciplina (média dos semestres) — sem indicação de ano
        cif_notas = {}
        for d in todas_disciplinas:
            vals_d = [disc_ano.get(d, {}).get(p) for p in periodos
                      if disc_ano.get(d, {}).get(p) is not None]
            cif_notas[d] = round(sum(vals_d) / len(vals_d), 1) if vals_d else None
        cif_vals = [v for v in cif_notas.values() if v is not None]
        linhas.append({
            "label": "CIF",
            "tipo": "cif",
            "atual": ano == ano_atual,
            "notas": cif_notas,
            "media": round(sum(cif_vals) / len(cif_vals), 1) if cif_vals else None,
        })

    # Linha de Exame (vazia por enquanto)
    linhas.append({
        "label": "Exame",
        "tipo": "exame",
        "atual": False,
        "notas": {d: None for d in todas_disciplinas},
        "media": None,
    })

    # CFD = CIF (sem exame por enquanto)
    ultimo_cif = next((l for l in reversed(linhas) if l["tipo"] == "cif" and l["atual"]), None)
    linhas.append({
        "label": "CFD",
        "tipo": "cfd",
        "atual": False,
        "notas": ultimo_cif["notas"] if ultimo_cif else {d: None for d in todas_disciplinas},
        "media": ultimo_cif["media"] if ultimo_cif else None,
    })

    # ── Resumo para cabeçalho ─────────────────────────────────────────────────
    ultima_linha_sem = next((l for l in reversed(linhas)
                             if l["tipo"] == "semestre" and l["atual"]), None)
    resumo = None
    if ultima_linha_sem:
        negas = [(d, n) for d, n in ultima_linha_sem["notas"].items() if n is not None and n < 10]
        resumo = {
            "media_atual": ultima_linha_sem["media"],
            "num_negas": len(negas),
            "negas": sorted(negas, key=lambda x: x[1]),
        }

    # Verificar se existe foto
    foto_url = None
    if a["numero"]:
        for ext in ("jpg", "jpeg", "png", "webp"):
            if os.path.exists(os.path.join(FOTOS_FOLDER, f"{a['numero']}.{ext}")):
                foto_url = url_for("foto_aluno", numero=a["numero"])
                break

    # Notas de reunião
    notas_reun_rows = db.execute(
        "SELECT categoria, texto, updated_at FROM notas_reuniao WHERE aluno_id=?",
        (aluno_id,)
    ).fetchall()
    notas_reuniao = {r["categoria"]: {"texto": r["texto"], "updated_at": r["updated_at"]}
                     for r in notas_reun_rows}

    # Permissão de edição
    turmas_user = [t.strip() for t in (session.get("turma") or "").split(",")]
    pode_editar = session["role"] == "admin" or a["turma"] in turmas_user

    return render_template("aluno.html", aluno=a,
                           todas_disciplinas=todas_disciplinas,
                           abreviaturas=ABREVIATURAS,
                           separador_idx=separador_idx,
                           linhas=linhas,
                           resumo=resumo,
                           foto_url=foto_url,
                           notas_reuniao=notas_reuniao,
                           categorias_reuniao=CATEGORIAS_REUNIAO,
                           pode_editar=pode_editar)

# ─── Notas de reunião ─────────────────────────────────────────────────────────

CATEGORIAS_REUNIAO = [
    ("observacoes",   "Observações Gerais",      "bi-journal-text",       "#2563eb"),
    ("preocupacoes",  "Preocupações / Alertas",  "bi-exclamation-triangle","#dc3545"),
    ("positivos",     "Pontos Positivos",         "bi-star",               "#16a34a"),
    ("apoio_caa",     "Medidas de Apoio / CAA",   "bi-life-preserver",     "#9333ea"),
]

@app.route("/aluno/<int:aluno_id>/notas-reuniao", methods=["POST"])
@login_required
def guardar_nota_reuniao(aluno_id):
    db = get_db()
    a = db.execute("SELECT * FROM alunos WHERE id=?", (aluno_id,)).fetchone()
    if not a:
        return jsonify({"ok": False, "erro": "Aluno não encontrado"}), 404

    turmas_user = [t.strip() for t in (session.get("turma") or "").split(",")]
    if session["role"] != "admin" and a["turma"] not in turmas_user:
        return jsonify({"ok": False, "erro": "Sem permissão"}), 403

    data = request.get_json()
    categoria = data.get("categoria", "").strip()
    texto     = data.get("texto", "").strip()

    cats_validas = [c[0] for c in CATEGORIAS_REUNIAO]
    if categoria not in cats_validas:
        return jsonify({"ok": False, "erro": "Categoria inválida"}), 400

    from datetime import datetime as _dt
    agora = _dt.now().strftime("%Y-%m-%d %H:%M")

    existing = db.execute(
        "SELECT id FROM notas_reuniao WHERE aluno_id=? AND categoria=?",
        (aluno_id, categoria)
    ).fetchone()

    if existing:
        db.execute(
            "UPDATE notas_reuniao SET texto=?, updated_at=?, updated_by=? WHERE id=?",
            (texto, agora, session["user_id"], existing["id"])
        )
    else:
        db.execute(
            "INSERT INTO notas_reuniao (aluno_id, categoria, texto, updated_at, updated_by) VALUES (?,?,?,?,?)",
            (aluno_id, categoria, texto, agora, session["user_id"])
        )
    db.commit()
    return jsonify({"ok": True, "updated_at": agora})


# ─── Edição de nota ───────────────────────────────────────────────────────────

@app.route("/aluno/<int:aluno_id>/editar-nota", methods=["POST"])
@login_required
def editar_nota(aluno_id):
    db = get_db()
    a = db.execute("SELECT * FROM alunos WHERE id=?", (aluno_id,)).fetchone()
    if not a:
        return jsonify({"ok": False, "erro": "Aluno não encontrado"}), 404

    turmas_user = [t.strip() for t in (session.get("turma") or "").split(",")]
    if session["role"] != "admin" and a["turma"] not in turmas_user:
        return jsonify({"ok": False, "erro": "Sem permissão"}), 403

    data = request.get_json()
    disciplina = (data.get("disciplina") or "").strip()
    periodo    = data.get("periodo")
    nota_str   = str(data.get("nota") or "").strip()

    if not disciplina or periodo is None:
        return jsonify({"ok": False, "erro": "Dados incompletos"}), 400

    # Converter nota
    if nota_str in ("", "-", "—"):
        nota = None
    else:
        try:
            nota = float(nota_str.replace(",", "."))
            if not (0 <= nota <= 20):
                return jsonify({"ok": False, "erro": "Nota deve ser entre 0 e 20"}), 400
        except ValueError:
            return jsonify({"ok": False, "erro": "Valor inválido"}), 400

    existing = db.execute(
        "SELECT id FROM notas WHERE aluno_id=? AND disciplina=? AND periodo=?",
        (aluno_id, disciplina, periodo)
    ).fetchone()

    if existing:
        if nota is None:
            db.execute("DELETE FROM notas WHERE id=?", (existing["id"],))
        else:
            db.execute("UPDATE notas SET nota=? WHERE id=?", (nota, existing["id"]))
    elif nota is not None:
        db.execute(
            "INSERT INTO notas (aluno_id, disciplina, periodo, nota) VALUES (?,?,?,?)",
            (aluno_id, disciplina, periodo, nota)
        )

    db.commit()
    return jsonify({"ok": True, "nota": nota})


# ─── Fotos ────────────────────────────────────────────────────────────────────

@app.route("/foto/<numero>")
@login_required
def foto_aluno(numero):
    from flask import send_file
    for ext in ("jpg", "jpeg", "png", "webp"):
        path = os.path.join(FOTOS_FOLDER, f"{numero}.{ext}")
        if os.path.exists(path):
            return send_file(path)
    # Foto não encontrada — devolver placeholder SVG
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80" viewBox="0 0 80 80">
      <circle cx="40" cy="40" r="40" fill="#2563eb"/>
      <circle cx="40" cy="32" r="14" fill="rgba(255,255,255,.7)"/>
      <ellipse cx="40" cy="72" rx="24" ry="18" fill="rgba(255,255,255,.7)"/>
    </svg>'''
    from flask import Response
    return Response(svg, mimetype="image/svg+xml")


# ─── Admin routes ──────────────────────────────────────────────────────────────

@app.route("/admin")
@login_required
@admin_required
def admin_panel():
    db = get_db()
    users = db.execute("SELECT * FROM users ORDER BY role, turma, nome").fetchall()
    return render_template("admin.html", users=users)

@app.route("/admin/criar_utilizador", methods=["POST"])
@login_required
@admin_required
def criar_utilizador():
    email = request.form["email"].strip().lower()
    nome = request.form["nome"].strip()
    turma = request.form["turma"].strip().upper()
    password = request.form["password"]
    role = request.form.get("role", "diretor")
    db = get_db()
    try:
        db.execute(
            "INSERT INTO users (email, password, nome, turma, role) VALUES (?,?,?,?,?)",
            (email, generate_password_hash(password), nome, turma or None, role)
        )
        db.commit()
        flash(f"Utilizador {nome} criado com sucesso.", "success")
    except sqlite3.IntegrityError:
        flash("Email já existe.", "danger")
    return redirect(url_for("admin_panel"))

@app.route("/admin/editar_utilizador/<int:uid>", methods=["POST"])
@login_required
@admin_required
def editar_utilizador(uid):
    db = get_db()
    nome = request.form["nome"].strip()
    turma = request.form["turma"].strip().upper()
    role = request.form.get("role", "diretor")
    nova_pass = request.form.get("nova_password", "").strip()
    if nova_pass:
        db.execute(
            "UPDATE users SET nome=?, turma=?, role=?, password=? WHERE id=?",
            (nome, turma or None, role, generate_password_hash(nova_pass), uid)
        )
    else:
        db.execute(
            "UPDATE users SET nome=?, turma=?, role=? WHERE id=?",
            (nome, turma or None, role, uid)
        )
    db.commit()
    flash("Utilizador atualizado.", "success")
    return redirect(url_for("admin_panel"))

@app.route("/admin/apagar_utilizador/<int:uid>", methods=["POST"])
@login_required
@admin_required
def apagar_utilizador(uid):
    db = get_db()
    db.execute("DELETE FROM users WHERE id=?", (uid,))
    db.commit()
    flash("Utilizador removido.", "success")
    return redirect(url_for("admin_panel"))

@app.route("/admin/importar", methods=["GET", "POST"])
@login_required
@admin_required
def importar_excel():
    if request.method == "POST":
        f = request.files.get("ficheiro")
        ano = request.form.get("ano_letivo", "2025/2026")
        periodo = int(request.form.get("periodo", 1))
        if not f or not f.filename.endswith((".xlsx", ".xls")):
            flash("Por favor carregue um ficheiro Excel (.xlsx).", "danger")
            return redirect(url_for("importar_excel"))

        filename = secure_filename(f.filename)
        path = os.path.join(UPLOAD_FOLDER, filename)
        f.save(path)

        try:
            wb = openpyxl.load_workbook(path, data_only=True)
            ws = wb.active
            headers = [str(c.value).strip() if c.value else "" for c in ws[1]]

            # Detetar colunas obrigatórias (case-insensitive)
            # Suporta prefixos como "Aluno: Nome", "Aluno: Turma", etc.
            import re as _re
            def _strip_prefix(h):
                return _re.sub(r'^[^:]+:\s*', '', h).strip().lower()

            h_lower   = [h.lower() for h in headers]
            h_stripped = [_strip_prefix(h) for h in headers]

            def col_idx(names):
                for n in names:
                    nl = n.lower()
                    # tenta match exacto primeiro
                    for i, h in enumerate(h_lower):
                        if nl == h:
                            return i
                    # depois sem prefixo
                    for i, h in enumerate(h_stripped):
                        if nl == h or h.startswith(nl):
                            return i
                return None

            idx_num   = col_idx(["numero interno", "numero", "nº", "n.º", "num"])
            idx_nome  = col_idx(["nome", "name"])
            idx_turma = col_idx(["turma", "classe", "class"])

            if idx_nome is None or idx_turma is None:
                flash("Colunas 'Nome' e 'Turma' não encontradas no ficheiro.", "danger")
                return redirect(url_for("importar_excel"))

            # Colunas de disciplinas = todas as restantes (exceto as de controlo)
            skip = {idx_num, idx_nome, idx_turma}
            # Colunas que podem ser observações: terminam em "_obs" ou "observ"
            disc_cols = []
            for i, h in enumerate(headers):
                if i in skip or not h:
                    continue
                disc_cols.append((i, h))

            db = get_db()
            count_alunos = 0
            count_notas = 0

            for row in ws.iter_rows(min_row=2, values_only=True):
                nome_val = row[idx_nome] if idx_nome is not None else None
                if not nome_val:
                    continue
                turma_val = str(row[idx_turma]).strip().upper() if row[idx_turma] else ""
                num_val = str(row[idx_num]).strip() if idx_num is not None and row[idx_num] else ""

                # Inserir/ignorar aluno
                cur = db.execute(
                    "INSERT OR IGNORE INTO alunos (numero, nome, turma, ano_letivo) VALUES (?,?,?,?)",
                    (num_val, str(nome_val).strip(), turma_val, ano)
                )
                if cur.rowcount == 0:
                    # já existe, atualizar nome/turma
                    db.execute(
                        "UPDATE alunos SET nome=?, turma=? WHERE numero=? AND ano_letivo=?",
                        (str(nome_val).strip(), turma_val, num_val, ano)
                    )
                else:
                    count_alunos += 1

                aluno_row = db.execute(
                    "SELECT id FROM alunos WHERE numero=? AND ano_letivo=?", (num_val, ano)
                ).fetchone()
                if not aluno_row:
                    continue
                aluno_id = aluno_row["id"]

                for col_i, disc_name in disc_cols:
                    val = row[col_i]
                    # Detetar se é observação (coluna seguinte pode ser _obs)
                    is_obs = any(k in disc_name.lower() for k in ["obs", "observ", "nota_text", "descrit"])
                    if is_obs:
                        continue  # tratadas em conjunto com a nota

                    nota_num = None
                    try:
                        nota_num = float(val) if val is not None and str(val).strip() != "" else None
                    except (ValueError, TypeError):
                        nota_num = None

                    # Procurar coluna de observações correspondente
                    obs_text = None
                    obs_col_name = disc_name + "_obs"
                    for oi, oh in disc_cols:
                        if oh.lower() == obs_col_name.lower() or (disc_name.lower() in oh.lower() and "obs" in oh.lower()):
                            obs_text = str(row[oi]).strip() if row[oi] else None
                            break

                    # Upsert nota
                    existing = db.execute(
                        "SELECT id FROM notas WHERE aluno_id=? AND disciplina=? AND periodo=?",
                        (aluno_id, disc_name, periodo)
                    ).fetchone()
                    if existing:
                        db.execute(
                            "UPDATE notas SET nota=?, observacoes=? WHERE id=?",
                            (nota_num, obs_text, existing["id"])
                        )
                    else:
                        db.execute(
                            "INSERT INTO notas (aluno_id, disciplina, periodo, nota, observacoes) VALUES (?,?,?,?,?)",
                            (aluno_id, disc_name, periodo, nota_num, obs_text)
                        )
                    count_notas += 1

            db.commit()
            flash(f"Importação concluída: {count_alunos} alunos novos, {count_notas} notas processadas.", "success")

        except Exception as e:
            flash(f"Erro ao processar ficheiro: {e}", "danger")

        return redirect(url_for("importar_excel"))

    return render_template("importar.html")

@app.route("/apresentacao/<path:turma>")
@login_required
def apresentacao(turma):
    import json
    db = get_db()

    # Verificar permissão
    turmas_user = [t.strip() for t in (session.get("turma") or "").split(",")]
    if session["role"] != "admin" and turma not in turmas_user:
        flash("Sem permissão para esta turma.", "danger")
        return redirect(url_for("dashboard"))

    alunos = db.execute(
        "SELECT * FROM alunos WHERE turma=? ORDER BY nome", (turma,)
    ).fetchall()

    alunos_json = []
    for a in alunos:
        # Notas
        rows = db.execute(
            "SELECT disciplina, periodo, nota FROM notas WHERE aluno_id=? ORDER BY disciplina, periodo",
            (a["id"],)
        ).fetchall()

        notas_por_ano = {a["ano_letivo"]: {}}
        for r in rows:
            notas_por_ano[a["ano_letivo"]].setdefault(r["disciplina"], {})[r["periodo"]] = r["nota"]

        # Anos anteriores
        if a["numero"]:
            for outro in db.execute(
                "SELECT id, ano_letivo FROM alunos WHERE numero=? AND ano_letivo!=? ORDER BY ano_letivo",
                (a["numero"], a["ano_letivo"])
            ).fetchall():
                rows_ant = db.execute(
                    "SELECT disciplina, periodo, nota FROM notas WHERE aluno_id=?",
                    (outro["id"],)
                ).fetchall()
                if rows_ant:
                    notas_por_ano[outro["ano_letivo"]] = {}
                    for r in rows_ant:
                        notas_por_ano[outro["ano_letivo"]].setdefault(r["disciplina"], {})[r["periodo"]] = r["nota"]

        # Disciplinas e abreviaturas
        ABREVS = {
            "Português":"POR","Inglês":"ING","Filosofia":"FIL","Educação Física":"EF",
            "Religião":"REL","Matemática A":"MAT_A","Matemática Geral":"MAT_G",
            "Desenho A":"DES_A","Desenho Geral":"DES_G","História A":"HIST_A",
            "História Geral":"HIST_G","Geografia A":"GEO_A","Biologia":"BIO",
            "Biologia e Geologia":"BG","Física":"FIS","Física e Química A":"FQ_A",
            "Química":"QUI","Economia A":"ECO_A","Economia C":"ECO_C",
            "Geometria Descritiva A":"GD_A","Aplicações Informáticas B":"AI_B",
            "Psicologia B":"PSI_B","Ciência Política":"CP","Filosofia A":"FIL_A",
            "Oficinas":"OFI","Hora de PT":"PT","Projeto":"PROJ",
            "Tempo de Trabalho Autónomo":"TTA","Líng. Estrang. I - Inglês":"ING",
        }
        todas = sorted({d for ano_d in notas_por_ano.values() for d in ano_d})
        disc_esp_kw = ["_A","_B","_C","Desenho","História A","Biologia e G","Física e Q","Geometria","Economia A","Geografia"]
        gerais  = [d for d in todas if not any(k in d for k in disc_esp_kw)]
        especif = [d for d in todas if any(k in d for k in disc_esp_kw)]
        todas = gerais + especif
        sep_idx = len(gerais) if especif else None

        import re as _re
        def ano_turma(t):
            m = _re.match(r"(\d+)", str(t or ""))
            return (m.group(1) + "º Ano") if m else "Ano ?"

        linhas = []
        for ano in sorted(notas_por_ano.keys()):
            disc_ano = notas_por_ano[ano]
            periodos = sorted({p for d in disc_ano.values() for p in d})
            al_ano = db.execute("SELECT turma FROM alunos WHERE numero=? AND ano_letivo=?",
                                (a["numero"], ano)).fetchone()
            t_ano = al_ano["turma"] if al_ano else a["turma"]
            ano_esc = ano_turma(t_ano)

            for p in periodos:
                nl = {d: disc_ano.get(d, {}).get(p) for d in todas}
                vals = [v for v in nl.values() if v is not None]
                linhas.append({"label": f"{ano_esc} — {p}º Sem.", "tipo": "semestre",
                                "atual": ano == a["ano_letivo"], "notas": nl,
                                "media": round(sum(vals)/len(vals),1) if vals else None})

            cif = {d: None for d in todas}
            for d in todas:
                vd = [disc_ano.get(d,{}).get(p) for p in periodos if disc_ano.get(d,{}).get(p) is not None]
                cif[d] = round(sum(vd)/len(vd),1) if vd else None
            cv = [v for v in cif.values() if v is not None]
            linhas.append({"label":"CIF","tipo":"cif","atual": ano==a["ano_letivo"],
                           "notas":cif,"media":round(sum(cv)/len(cv),1) if cv else None})

        linhas.append({"label":"Exame","tipo":"exame","atual":False,
                       "notas":{d:None for d in todas},"media":None})
        uc = next((l for l in reversed(linhas) if l["tipo"]=="cif" and l["atual"]), None)
        linhas.append({"label":"CFD","tipo":"cfd","atual":False,
                       "notas":uc["notas"] if uc else {d:None for d in todas},
                       "media":uc["media"] if uc else None})

        # Notas de reunião
        nr_rows = db.execute(
            "SELECT categoria, texto FROM notas_reuniao WHERE aluno_id=?", (a["id"],)
        ).fetchall()
        notas_r = {r["categoria"]: r["texto"] for r in nr_rows}

        # Negativos última linha semestre
        ul = next((l for l in reversed(linhas) if l["tipo"]=="semestre" and l["atual"]), None)
        negas = []
        if ul:
            negas = [[d, n] for d, n in ul["notas"].items() if n is not None and n < 10]
            negas.sort(key=lambda x: x[1])

        # Foto
        foto_url = None
        if a["numero"]:
            for ext in ("jpg","jpeg","png","webp"):
                if os.path.exists(os.path.join(FOTOS_FOLDER, f"{a['numero']}.{ext}")):
                    foto_url = url_for("foto_aluno", numero=a["numero"])
                    break

        alunos_json.append({
            "id": a["id"], "nome": a["nome"], "numero": a["numero"] or "",
            "turma": a["turma"], "foto_url": foto_url,
            "disciplinas": todas, "abrevs": ABREVS,
            "separador_idx": sep_idx, "linhas": linhas,
            "notas_reuniao": notas_r, "negas": negas,
        })

    return render_template("apresentacao.html",
                           turma=turma,
                           alunos=alunos,
                           alunos_json=json.dumps(alunos_json))


@app.route("/admin/turma/<path:turma>")
@login_required
@admin_required
def ver_turma(turma):
    db = get_db()
    periodo_sel = request.args.get("periodo", None)
    if periodo_sel:
        try: periodo_sel = int(periodo_sel)
        except: periodo_sel = None
    alunos_info = calcular_alunos_info(db, turma)
    medias_disc, periodos_disp, periodo_sel, comparacao = calcular_stats_turma(db, turma, periodo_sel)
    return render_template("dashboard.html", alunos=alunos_info, turma=turma,
                           medias_disciplinas=medias_disc,
                           periodos_disponiveis=periodos_disp,
                           periodo_sel=periodo_sel,
                           comparacao_periodos=comparacao)

# ─── Importar notas via web (admin) ───────────────────────────────────────────

@app.route("/admin/upload-fotos", methods=["GET", "POST"])
@login_required
@admin_required
def upload_fotos():
    if request.method == "POST":
        f = request.files.get("ficheiro")
        if not f or not f.filename.lower().endswith(".zip"):
            flash("Por favor carregue um ficheiro .zip.", "danger")
            return redirect(url_for("upload_fotos"))

        import zipfile, io

        db = get_db()
        # Obter todos os números de alunos válidos
        numeros = {r["numero"] for r in db.execute("SELECT DISTINCT numero FROM alunos").fetchall() if r["numero"]}

        try:
            zf = zipfile.ZipFile(io.BytesIO(f.read()))
            guardadas = 0
            ignoradas = 0

            for nome in zf.namelist():
                basename = os.path.basename(nome)
                if not basename:
                    continue
                # Extrair número do nome do ficheiro (ex: "3023.jpg" → "3023")
                raiz, ext = os.path.splitext(basename)
                if ext.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
                    continue
                # Normalizar: remover zeros à esquerda para comparação
                raiz_strip = raiz.strip()
                # Verificar se corresponde a um aluno (com ou sem zeros à esquerda)
                match = raiz_strip in numeros or raiz_strip.lstrip("0") in {n.lstrip("0") for n in numeros}
                if not match:
                    ignoradas += 1
                    continue
                # Guardar com o número original do aluno
                numero_aluno = next((n for n in numeros if n.lstrip("0") == raiz_strip.lstrip("0")), raiz_strip)
                dest = os.path.join(FOTOS_FOLDER, f"{numero_aluno}{ext.lower()}")
                with zf.open(nome) as src, open(dest, "wb") as dst:
                    dst.write(src.read())
                guardadas += 1

            flash(f"✓ {guardadas} fotos importadas, {ignoradas} ignoradas (não correspondem a alunos).", "success")
        except Exception as e:
            flash(f"Erro ao processar ZIP: {e}", "danger")

        return redirect(url_for("upload_fotos"))

    # Contar fotos já existentes
    try:
        n_fotos = len([f for f in os.listdir(FOTOS_FOLDER) if f.lower().endswith((".jpg",".jpeg",".png",".webp"))])
    except:
        n_fotos = 0

    return render_template("upload_fotos.html", n_fotos=n_fotos)


@app.route("/admin/importar-notas", methods=["GET", "POST"])
@login_required
@admin_required
def importar_notas_web():
    """Importa ficheiros de Avaliação Contínua (formato Grelha)."""
    if request.method == "POST":
        ficheiros = request.files.getlist("ficheiros")
        semestre  = int(request.form.get("semestre", 1))
        ano       = request.form.get("ano_letivo", "2025/2026")

        if not ficheiros or all(f.filename == "" for f in ficheiros):
            flash("Selecione pelo menos um ficheiro.", "danger")
            return redirect(url_for("importar_notas_web"))

        import re as _re, unicodedata as _uc

        def _normalizar(s):
            s = _uc.normalize("NFKD", str(s or ""))
            s = s.encode("ascii", "ignore").decode()
            return _re.sub(r"\s+", " ", s).strip().lower()

        def _parse_nota(v):
            if v is None: return None
            s = str(v).strip()
            if s in ("-", "", "NP", "NP.", "NE", "NA", "—"): return None
            try: return float(s)
            except: return None

        def _extrair_turma(val):
            s = str(val).strip()
            return s.split(" - ", 1)[1].strip() if " - " in s else s

        db = get_db()
        # Cache alunos
        alunos_cache = {}
        for a in db.execute("SELECT id, nome, turma FROM alunos WHERE ano_letivo=?", (ano,)).fetchall():
            alunos_cache[(_normalizar(a["nome"]), a["turma"])] = a["id"]
        alunos_por_nome = {}
        for (n, t), aid in alunos_cache.items():
            alunos_por_nome.setdefault(n, []).append((t, aid))

        total_notas = 0
        nao_enc     = set()

        for f in ficheiros:
            if not f.filename.endswith((".xlsx", ".xls")):
                continue
            path = os.path.join(UPLOAD_FOLDER, secure_filename(f.filename))
            f.save(path)

            wb   = openpyxl.load_workbook(path, data_only=True)
            ws   = wb.active
            rows = list(ws.iter_rows(values_only=True))

            header_idx = None
            for i, row in enumerate(rows):
                if row[0] and "Nome" in str(row[0]) and "Turma" in str(row[0]):
                    header_idx = i; break
            if header_idx is None:
                flash(f"Estrutura não reconhecida: {f.filename}", "warning")
                continue

            disc_row = rows[header_idx - 2]
            np_row   = rows[header_idx]
            disc_cols_sorted = sorted([i for i, v in enumerate(disc_row)
                                       if v and str(v).strip()
                                       and "Nome" not in str(v)
                                       and "Número" not in str(v)])
            disc_np_map = {}
            for idx, dc in enumerate(disc_cols_sorted):
                end = disc_cols_sorted[idx+1] if idx+1 < len(disc_cols_sorted) else len(np_row)
                dname = str(disc_row[dc]).strip()
                for c in range(dc, min(end, len(np_row))):
                    if np_row[c] and str(np_row[c]).strip() == "NP.":
                        disc_np_map[dname] = c; break

            turma_atual = None
            for row in rows[header_idx + 2:]:
                if row[0] and str(row[0]).strip():
                    turma_atual = _extrair_turma(row[0])
                nome_val = row[7] if len(row) > 7 else None
                if not nome_val or not str(nome_val).strip(): continue
                nome_n = _normalizar(str(nome_val))

                aluno_id = alunos_cache.get((nome_n, turma_atual))
                if aluno_id is None and nome_n in alunos_por_nome:
                    cands = alunos_por_nome[nome_n]
                    aluno_id = cands[0][1] if len(cands) == 1 else None
                if aluno_id is None:
                    nao_enc.add(f"{nome_val} ({turma_atual})")
                    continue

                for disc, col_np in disc_np_map.items():
                    nota = _parse_nota(row[col_np] if col_np < len(row) else None)
                    if nota is None: continue
                    ex = db.execute(
                        "SELECT id FROM notas WHERE aluno_id=? AND disciplina=? AND periodo=?",
                        (aluno_id, disc, semestre)
                    ).fetchone()
                    if ex:
                        db.execute("UPDATE notas SET nota=? WHERE id=?", (nota, ex["id"]))
                    else:
                        db.execute(
                            "INSERT INTO notas (aluno_id, disciplina, periodo, nota) VALUES (?,?,?,?)",
                            (aluno_id, disc, semestre, nota)
                        )
                    total_notas += 1

        db.commit()
        msg = f"Importação concluída: {total_notas} notas carregadas."
        if nao_enc:
            msg += f" {len(nao_enc)} aluno(s) não encontrado(s)."
        flash(msg, "success" if not nao_enc else "warning")
        return redirect(url_for("importar_notas_web"))

    return render_template("importar_notas.html")


# ─── Run ───────────────────────────────────────────────────────────────────────

# Garantir que a BD existe ao arrancar (gunicorn ou python app.py)
try:
    init_db()
except Exception as _e:
    print(f"[AVISO] init_db: {_e}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
