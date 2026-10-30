"""Competências Transversais (CT) do Secundário — Colégio Pedro Arrupe.

Definições, descritores e procedimentos retirados do «Documento Referencial das CT».
"""

# ── Escala de níveis (1 = mínimo, 5 = máximo) ──────────────────────────────────
NIVEIS = {
    1: ("Inicial",            "Encontra-se distante do definido para a competência"),
    2: ("Em desenvolvimento", "Manifesta dificuldade em cumprir o essencial do definido para a competência"),
    3: ("Desenvolvido",       "Cumpre o essencial do definido para a competência"),
    4: ("Consolidado",        "Cumpre com qualidade o definido para a competência"),
    5: ("Avançado",           "Cumpre com elevada qualidade o definido para a competência"),
}
# Cores, na mesma lógica das notas (vermelho < laranja < verde < azul)
COR_NIVEL = {1: "#ef4444", 2: "#f59e0b", 3: "#22c55e", 4: "#3b82f6", 5: "#1d4ed8"}

# ── As sete CT ─────────────────────────────────────────────────────────────────
CT = [
    {"id": "AUTN", "nome": "Autonomia", "basica": True,
     "def": "Qualidade que permite realizar tarefas por si mesmo sem depender de apoio de outro.",
     "desc": [
         "Desenvolve a tarefa sem recorrer desnecessariamente ao professor",
         "Desenvolve um método de trabalho em contexto de aula",
         "Gere o seu tempo para a resolução e apresentação de tarefas",
         "Gere o espaço e os materiais disponíveis na resolução e apresentação de tarefas",
         "Identifica os pontos fortes e menos fortes do seu desempenho",
         "Estabelece objetivos de melhoria",
         "Planeia estratégias de recuperação e/ou consolidação visando alcançar os objetivos estabelecidos"]},
    {"id": "RESP", "nome": "Responsabilidade", "basica": True,
     "def": "Qualidade que permite responder pelo cumprimento das tarefas e ações que lhe estão conferidas.",
     "desc": [
         "Mantém o espaço e materiais de trabalho organizados.",
         "Respeita as orientações dadas pelo professor",
         "Cumpre os prazos das tarefas",
         "Adequa as suas ações aos diferentes contextos de aprendizagem",
         "Realiza as tarefas com rigor"]},
    {"id": "COOP", "nome": "Cooperação", "basica": True,
     "def": "Qualidade que permite colaborar com os colegas no sentido de atingir um objetivo próprio, "
            "comum ou do outro aluno.",
     "desc": [
         "Trabalha e colabora com todos os colegas",
         "Ouve e respeita as escolhas e opiniões dos outros",
         "Contribui ativamente para as tarefas de grupo"]},
    {"id": "CCRT", "nome": "Capacidade Crítica", "basica": False,
     "def": "Qualidade que permite questionar e mobilizar o conhecimento a partir das suas vivências, "
            "posicionando-se de forma a contribuir para a construção de uma ideia.",
     "desc": [
         "Fundamenta a sua perspetiva/posição/opção face a um tema",
         "Observa, identifica, analisa e dá sentido a uma informação",
         "Prevê e avalia o impacto da sua perspetiva/posição/opção",
         "Tem um olhar crítico para os diferentes passos de uma ideia, questionando se são viáveis "
         "e/ou fazem sentido no contexto abordado"]},
    {"id": "RSPL", "nome": "Resolução de Situações Problema", "basica": False,
     "def": "Qualidade que permite analisar situações problema, formular hipóteses de resolução e rever "
            "a validade das mesmas.",
     "desc": [
         "Analisa uma situação problema, compreendendo as variáveis envolvidas na questão formulada",
         "Procura e retira dados para a resolução de um problema",
         "Investe na formulação de hipóteses",
         "Organiza de forma lógica a sua proposta de resolução de um problema",
         "Implementa a solução encontrada"]},
    {"id": "COMN", "nome": "Comunicação", "basica": False,
     "def": "Qualidade que permite selecionar, analisar, produzir e divulgar informação, adequando a forma "
            "e conteúdo aos objetivos definidos.",
     "desc": [
         "Retira a informação relevante de uma fonte",
         "Interpreta, trata, e representa a informação de diferentes formas, selecionando a mais adequada ao contexto",
         "Esquematiza uma ideia de forma a saber explicar o seu raciocínio a outro",
         "Adequa os argumentos à evolução da discussão",
         "Comunica adequadamente em diferentes contextos, respeitando normas previamente estabelecidas",
         "Relaciona e mobiliza a informação tratada"]},
    {"id": "CRIA", "nome": "Criatividade", "basica": False,
     "def": "Qualidade que permite desenvolver uma ideia de forma inovadora, criando algo que surpreende "
            "pela originalidade.",
     "desc": [
         "Cria produtos inovadores, não se limitando a reproduzir aquilo que já conhece",
         "Investe na apresentação de várias soluções adequadas ao desafio apresentado",
         "Investe nos detalhes/pormenores na criação de um produto"]},
]
CT_POR_ID = {c["id"]: c for c in CT}
for _c in CT:   # códigos dos descritores: AUTN1, AUTN2, ...
    _c["descritores"] = [(f"{_c['id']}{i}", t) for i, t in enumerate(_c["desc"], 1)]
DESCRITORES = {cod: txt for c in CT for cod, txt in c["descritores"]}

# ── Momentos de avaliação ──────────────────────────────────────────────────────
# As 3 CT básicas (AUTN, RESP, COOP) são avaliadas por todas as disciplinas em todos os momentos. As 4
# complexas (CCRT, RSPL, COMN, CRIA) são sempre opcionais (só quando a disciplina realizou uma tarefa
# que as trabalhe), mesmo no intercalar do 1.º semestre. Os descritores a melhorar só nos dois primeiros.
BASICAS = [c["id"] for c in CT if c["basica"]]
TODAS = [c["id"] for c in CT]
MOMENTOS = [
    {"id": "intercalar_1s", "nome": "Intercalar do 1.º semestre", "cts": TODAS, "descritores": True},
    {"id": "final_1s",      "nome": "Final do 1.º semestre",      "cts": TODAS, "descritores": True},
    {"id": "final_2s",      "nome": "Final do 2.º semestre",      "cts": TODAS, "descritores": False},
]
MOMENTOS_POR_ID = {m["id"]: m for m in MOMENTOS}
MAX_DESCRITORES = 2

# ── Abreviaturas das disciplinas ───────────────────────────────────────────────
ABREV_DISC = {
    "Português": "Port", "Líng. Estrang. I - Inglês": "Ing", "Inglês": "Ing", "Filosofia": "Filo",
    "Educação Física": "Ed. Fís", "Religião": "Rel", "Projeto": "Proj", "Literacias": "Lit.",
    "Matemática A": "Mat A", "Desenho A": "Des A", "Desenho Geral": "Des G", "História A": "Hist A",
    "Biologia e Geologia": "Bio Geo", "Biologia": "Bio", "Física e Química A": "FQ A", "Física": "Fís",
    "Química": "Quím", "Geometria Descritiva A": "GDA", "Economia A": "Econ A", "Economia C": "Econ C",
    "Geografia A": "Geo A", "História Geral": "Hist B", "Matemática B": "Mat B", "Matemática Geral": "Mat G",
    "Matemática Aplicada Ciências Sociais": "MACS", "Filosofia A": "Filo A", "Ciência Política": "C. Pol",
    "Psicologia B": "Psic B", "Aplicações Informáticas B": "AI B", "Oficinas": "Ofic",
    "Literatura Portuguesa": "Lit. P", "Alemão": "Alem", "Espanhol": "Esp", "Francês": "Fr",
    "Hora de PT": "PT", "Tempo de Trabalho Autónomo": "TTA",
}

def abrev_disc(d):
    return ABREV_DISC.get(d, (d or "")[:7])

def proposta(niveis):
    """(média com 1 casa, nível proposto) a partir da lista de níveis; (None, None) se vazia."""
    ns = [n for n in niveis if n]
    if not ns:
        return None, None
    media = sum(ns) / len(ns)
    return round(media, 1), int(media + 0.5)
