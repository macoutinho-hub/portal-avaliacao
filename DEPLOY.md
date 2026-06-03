# Deploy no Render — Passo a Passo

## O que vai precisar
- Conta GitHub (gratuita) → https://github.com
- Conta Render (gratuita) → https://render.com

---

## 1. Colocar os ficheiros no GitHub

1. Abra https://github.com e faça login (ou crie conta)
2. Clique **New repository** → Nome: `portal-avaliacao` → **Create repository**
3. Na página do repo, clique **uploading an existing file**
4. Arraste **toda a pasta `Portal CTs`** para o browser
5. Clique **Commit changes**

> ⚠️ Não inclua a pasta `notas/` no GitHub — os ficheiros Excel ficam só localmente.

---

## 2. Criar o serviço no Render

1. Abra https://render.com → **New** → **Web Service**
2. Conecte a sua conta GitHub e selecione o repo `portal-avaliacao`
3. Preencha:
   - **Name:** `portal-avaliacao`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app --bind 0.0.0.0:$PORT`
4. Clique **Advanced** → **Add Disk**:
   - Name: `db`
   - Mount Path: `/data`
   - Size: 1 GB
5. **Add Environment Variable:**
   - `DATABASE` = `/data/portal.db`
   - `SECRET_KEY` = (clique **Generate** para gerar automaticamente)
6. Clique **Create Web Service**

O Render vai compilar e lançar o portal em ~2 minutos.

---

## 3. Primeiro login e configuração

1. Abra o URL que o Render fornece (ex: `portal-avaliacao.onrender.com`)
2. Login: `admin@colegiopedroarrupe.pt` / `admin2026`
3. Menu **Importar** → **Alunos** → carregar `turmas alunos.xlsx`
4. Menu **Importar** → **Notas** → carregar os 5 ficheiros de Avaliação Contínua
5. Menu **Utilizadores** → criar os diretores de turma

   **OU** usar o script local (requer SSH ao Render — plano pago):
   ```
   python criar_diretores.py
   ```

---

## 4. Enviar credenciais aos diretores

Após criar os utilizadores, distribua as credenciais.

Cada diretor acede em: `https://portal-avaliacao.onrender.com`

---

## Notas importantes

- **Plano gratuito do Render:** o servidor "adormece" após 15 min de inatividade — o primeiro acesso demora ~30 seg. Para uso escolar contínuo, considere o plano pago ($7/mês).
- **Base de dados:** o ficheiro `portal.db` fica no disco persistente `/data` — não se perde entre deploys.
- **Actualizar notas:** basta carregar novos ficheiros Excel em **Importar → Notas** — os dados existentes são actualizados automaticamente.
