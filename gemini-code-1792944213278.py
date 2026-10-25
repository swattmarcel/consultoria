import hashlib
from datetime import datetime, date
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import create_engine, text

# ==========================================
# 1. CONFIGURAÇÃO DA PÁGINA E CONEXÃO SQLALCHEMY
# ==========================================
st.set_page_config(page_title="Sistema de Consultoria Empresarial", layout="wide")


@st.cache_resource
def get_engine():
  # Pega a URL dos Secrets do Streamlit Cloud ou usa um fallback local para testes
  database_url = st.secrets.get(
      "DATABASE_URL",
      "postgresql://postgres:sua_senha@db.xxxx.supabase.co:5432/postgres",
  )
  if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
  return create_engine(database_url)


engine = get_engine()


def hash_senha(senha: str) -> str:
  return hashlib.sha256(senha.encode("utf-8")).hexdigest()


def init_db():
  with engine.begin() as conn:
    # 1. Empresas
    conn.execute(
        text("""
            CREATE TABLE IF NOT EXISTS empresas (
                id SERIAL PRIMARY KEY,
                razao_social TEXT NOT NULL,
                cnpj TEXT UNIQUE NOT NULL,
                regime_tributario TEXT,
                segmento TEXT,
                data_cadastro TEXT
            )
        """)
    )

    # 2. Usuários (RBAC)
    conn.execute(
        text("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                senha_hash TEXT NOT NULL,
                nome_completo TEXT NOT NULL,
                perfil TEXT NOT NULL,
                empresa_id INTEGER REFERENCES empresas(id)
            )
        """)
    )

    # Criar admin padrão se não existir
    res = conn.execute(
        text("SELECT COUNT(*) FROM usuarios")
    ).scalar()
    if res == 0:
      conn.execute(
          text("""
                INSERT INTO usuarios (username, senha_hash, nome_completo, perfil, empresa_id)
                VALUES (:u, :s, :n, :p, NULL)
            """),
          {
              "u": "admin",
              "s": hash_senha("admin123"),
              "n": "Consultor Sênior (Admin)",
              "p": "consultor",
          },
      )

    # 3. Diagnóstico 360
    conn.execute(
        text("""
            CREATE TABLE IF NOT EXISTS diagnostico_360 (
                id SERIAL PRIMARY KEY,
                empresa_id INTEGER REFERENCES empresas(id),
                data_avaliacao TEXT,
                pilar TEXT,
                pergunta TEXT,
                nota INTEGER,
                observacao TEXT
            )
        """)
    )

    # 4. Plano de Ação 5W2H
    conn.execute(
        text("""
            CREATE TABLE IF NOT EXISTS plano_5w2h (
                id SERIAL PRIMARY KEY,
                empresa_id INTEGER REFERENCES empresas(id),
                pilar_origem TEXT,
                what_oque TEXT NOT NULL,
                why_porque TEXT,
                where_onde TEXT,
                when_prazo TEXT,
                who_quem TEXT,
                how_como TEXT,
                how_much_custo REAL,
                status TEXT DEFAULT 'Pendente'
            )
        """)
    )

    # 5. Lançamentos Financeiros (DRE e Caixa)
    conn.execute(
        text("""
            CREATE TABLE IF NOT EXISTS lancamentos_financeiros (
                id SERIAL PRIMARY KEY,
                empresa_id INTEGER REFERENCES empresas(id),
                data_lancamento TEXT NOT NULL,
                tipo TEXT NOT NULL,
                grupo_dre TEXT NOT NULL,
                categoria TEXT NOT NULL,
                descricao TEXT,
                valor REAL NOT NULL,
                status TEXT DEFAULT 'Realizado'
            )
        """)
    )

    # 6. MASP / Ishikawa
    conn.execute(
        text("""
            CREATE TABLE IF NOT EXISTS analises_masp (
                id SERIAL PRIMARY KEY,
                empresa_id INTEGER REFERENCES empresas(id),
                data_analise TEXT,
                problema TEXT NOT NULL,
                setor TEXT,
                m_metodo TEXT,
                m_maquina TEXT,
                m_mao_obra TEXT,
                m_material TEXT,
                m_meio_ambiente TEXT,
                m_medida TEXT,
                pq1 TEXT,
                pq2 TEXT,
                pq3 TEXT,
                pq4 TEXT,
                pq5 TEXT,
                causa_raiz TEXT NOT NULL,
                status_masp TEXT DEFAULT 'Em Análise'
            )
        """)
    )

    # 7. Pareto
    conn.execute(
        text("""
            CREATE TABLE IF NOT EXISTS ocorrencias_pareto (
                id SERIAL PRIMARY KEY,
                empresa_id INTEGER REFERENCES empresas(id),
                data_registro TEXT,
                tipo_problema TEXT NOT NULL,
                setor TEXT,
                frequencia INTEGER NOT NULL,
                custo_estimado REAL DEFAULT 0.0
            )
        """)
    )

    # 8. Auditoria 5S
    conn.execute(
        text("""
            CREATE TABLE IF NOT EXISTS auditorias_5s (
                id SERIAL PRIMARY KEY,
                empresa_id INTEGER REFERENCES empresas(id),
                data_auditoria TEXT,
                setor_auditado TEXT NOT NULL,
                s1_utilizacao INTEGER,
                s2_organizacao INTEGER,
                s3_limpeza INTEGER,
                s4_padronizacao INTEGER,
                s5_disciplina INTEGER,
                observacoes TEXT
            )
        """)
    )

    # 9. Relatórios Executivos
    conn.execute(
        text("""
            CREATE TABLE IF NOT EXISTS relatorios_executivos (
                id SERIAL PRIMARY KEY,
                empresa_id INTEGER REFERENCES empresas(id),
                data_emissao TEXT,
                consultor_nome TEXT,
                periodo_referencia TEXT,
                parecer_consultor TEXT,
                proximos_passos TEXT
            )
        """)
    )


init_db()

# ==========================================
# 2. CONTROLE DE SESSÃO E LOGIN
# ==========================================
if "autenticado" not in st.session_state:
  st.session_state.autenticado = False
  st.session_state.usuario = None


def realizar_logout():
  st.session_state.autenticado = False
  st.session_state.usuario = None
  st.rerun()


if not st.session_state.autenticado:
  col_esq, col_centro, col_dir = st.columns([1, 1.2, 1])
  with col_centro:
    st.markdown("## 🔐 Portal de Gestão & Consultoria")
    st.caption("Acesse com suas credenciais de Consultor ou Portal do Cliente.")

    with st.form("form_login"):
      user_input = st.text_input("Usuário")
      pass_input = st.text_input("Senha", type="password")
      btn_entrar = st.form_submit_button("Entrar", use_container_width=True)

      if btn_entrar:
        with engine.connect() as conn:
          res = conn.execute(
              text(
                  "SELECT id, username, nome_completo, perfil, empresa_id FROM"
                  " usuarios WHERE username = :u AND senha_hash = :s"
              ),
              {"u": user_input.strip(), "s": hash_senha(pass_input)},
          ).fetchone()

        if res:
          st.session_state.autenticado = True
          st.session_state.usuario = {
              "id": res[0],
              "username": res[1],
              "nome": res[2],
              "perfil": res[3],
              "empresa_id": res[4],
          }
          st.rerun()
        else:
          st.error("Usuário ou senha inválidos.")

    st.info(
        "💡 **Primeiro acesso:**\n- **Usuário:** `admin`\n- **Senha:**"
        " `admin123`"
    )
  st.stop()

# ==========================================
# 3. ESTRUTURAS E NAVEGAÇÃO
# ==========================================
QUESTIONARIO_PADRAO = {
    "1. Finanças & Controladoria": [
        "Separação rigorosa entre contas PF (sócios) e PJ (pró-labore definido)",
        "Fluxo de Caixa projetado vs. realizado atualizado diariamente",
        "DRE Gerencial apurada mensalmente com análise de margens",
        "Precificação baseada em custos reais, impostos e margem de contribuição",
    ],
    "2. Processos & Qualidade (BPM/Lean)": [
        "Processos críticos mapeados e padronizados (POPs documentados)",
        "Aplicação prática de organização e limpeza (Programa 5S)",
        "Uso de metodologias estruturadas para solução de problemas"
        " (PDCA/MASP)",
        "Controle de perdas, retrabalho e indicadores de produtividade (KPIs)",
    ],
    "3. Estratégia & Governança": [
        "Metas anuais e trimestrais claras e desdobradas por setor",
        "Papéis e responsabilidades bem definidos (Organograma / Matriz RACI)",
        "Conformidade legal, tributária e proteção de dados (Compliance/LGPD)",
        "Reuniões mensais de análise crítica de resultados com a liderança",
    ],
    "4. Comercial & Operações": [
        "Funil de vendas estruturado e acompanhamento de taxa de conversão",
        "Planejamento e Controle da Produção/Estoque (PCP) alinhado à demanda",
        "Pesquisa de satisfação de clientes e tratamento de não-conformidades",
        "Gestão de fornecedores e controle de custos de compras (CMV/insumos)",
    ],
}

PLANO_CONTAS_DRE = {
    "1. Receita Operacional Bruta": {
        "tipo": "Entrada",
        "categorias": [
            "Vendas de Produtos",
            "Prestação de Serviços",
            "Receitas Recorrentes / Contratos",
        ],
    },
    "2. Deduções e Impostos s/ Vendas": {
        "tipo": "Saída",
        "categorias": [
            "Simples Nacional / DAS",
            "ICMS / ISS / PIS / COFINS",
            "Devoluções e Cancelamentos",
            "Taxas de Cartão / Marketplace",
        ],
    },
    "3. Custos e Despesas Variáveis (CMV/CSV)": {
        "tipo": "Saída",
        "categorias": [
            "Matéria-Prima / Mercadoria p/ Revenda",
            "Insumos e Embalagens",
            "Comissões de Vendas",
            "Fretes sobre Vendas",
        ],
    },
    "4. Custos e Despesas Fixas Operacionais": {
        "tipo": "Saída",
        "categorias": [
            "Folha de Pagamento e Encargos",
            "Pró-Labore Oficial (Sócios)",
            "Aluguel, Energia e Telecom",
            "Software, Marketing e Administrativo",
            "Honorários Contábeis / Consultoria",
        ],
    },
    "5. Não Operacional / Despesas PF Sócios": {
        "tipo": "Saída",
        "categorias": [
            "Pagamento de Contas Pessoais Sócios (Mistura PF/PJ)",
            "Retirada de Lucros Extraordinária",
            "Amortização de Empréstimos / Juros",
            "Compra de Ativos / Investimentos (CAPEX)",
        ],
    },
}

user_logado = st.session_state.usuario
eh_consultor = user_logado["perfil"] == "consultor"

st.sidebar.markdown(f"👤 **{user_logado['nome']}**")
st.sidebar.caption(
    "Perfil: "
    + ("Consultor (Acesso Total)" if eh_consultor else "Portal do Cliente")
)
st.sidebar.button(
    "Sair (Logout)", on_click=realizar_logout, use_container_width=True
)
st.sidebar.markdown("---")

df_empresas = pd.read_sql("SELECT * FROM empresas", engine)

if eh_consultor:
  opcoes_menu = [
      "1. Carteira de Clientes & Acessos",
      "2. Diagnóstico 360º",
      "3. Finanças & DRE Gerencial",
      "4. Qualidade, MASP & 5S",
      "5. Plano de Ação (5W2H)",
      "6. Relatório Executivo (Dossiê PDF)",
  ]
else:
  opcoes_menu = [
      "2. Diagnóstico 360º",
      "3. Finanças & DRE Gerencial",
      "4. Qualidade, MASP & 5S",
      "5. Plano de Ação (5W2H)",
      "6. Relatório Executivo (Dossiê PDF)",
  ]

menu = st.sidebar.radio("Navegação:", opcoes_menu)
st.sidebar.markdown("---")

if eh_consultor:
  if not df_empresas.empty:
    empresa_selecionada = st.sidebar.selectbox(
        "Cliente Ativo:", df_empresas["razao_social"].tolist()
    )
    dados_empresa_ativa = df_empresas[
        df_empresas["razao_social"] == empresa_selecionada
    ].iloc[0]
    empresa_id = int(dados_empresa_ativa["id"])
  else:
    empresa_selecionada = None
    empresa_id = None
    st.sidebar.warning("Cadastre uma empresa no Módulo 1.")
else:
  empresa_id = user_logado["empresa_id"]
  df_emp_cli = df_empresas[df_empresas["id"] == empresa_id]
  if not df_emp_cli.empty:
    dados_empresa_ativa = df_emp_cli.iloc[0]
    empresa_selecionada = dados_empresa_ativa["razao_social"]
    st.sidebar.info(f"🏢 **Empresa:**\n{empresa_selecionada}")
  else:
    st.error("Conta não vinculada a nenhuma empresa ativa.")
    st.stop()


def gerar_html_dossie(
    dados_emp,
    kpis_fin,
    df_dre,
    nota_maturidade,
    df_criticos,
    df_masp,
    score_5s,
    df_5w2h,
    consultor,
    periodo,
    parecer,
    prox_passos,
):
  linhas_dre_html = ""
  for _, r in df_dre.iterrows():
    destaque = (
        "font-weight: bold; background-color: #f1f5f9;"
        if "(=)" in r["Estrutura DRE"]
        else ""
    )
    linhas_dre_html += (
        f"<tr style='{destaque}'><td>{r['Estrutura DRE']}</td>"
        f"<td style='text-align:right;'>R$ {r['Valor (R$)']:,.2f}</td>"
        f"<td style='text-align:right;'>{r['% AV']}</td></tr>"
    )

  linhas_5w2h_html = ""
  if not df_5w2h.empty:
    for _, r in df_5w2h.iterrows():
      cor_status = (
          "#16a34a"
          if r["status"] == "Concluído"
          else ("#dc2626" if r["status"] == "Atrasado" else "#d97706")
      )
      linhas_5w2h_html += f"""
            <tr>
                <td>{r['pilar_origem']}</td>
                <td><strong>{r['what_oque']}</strong><br><small style='color:#64748b;'>{r['why_porque']}</small></td>
                <td>{r['who_quem']}</td>
                <td>{r['when_prazo']}</td>
                <td>R$ {r['how_much_custo']:,.2f}</td>
                <td><span style='color:{cor_status}; font-weight:bold;'>{r['status']}</span></td>
            </tr>"""
  else:
    linhas_5w2h_html = (
        "<tr><td colspan='6' style='text-align:center;'>Nenhuma ação"
        " cadastrada no plano 5W2H.</td></tr>"
    )

  gargalos_html = ""
  if not df_criticos.empty:
    for _, r in df_criticos.iterrows():
      gargalos_html += (
          f"<li><strong>[{r['pilar']}]</strong> {r['pergunta']} —"
          f" <em>Nota: {r['nota']}/5</em> ({r['observacao'] or 'Sem observação'})</li>"
      )
  else:
    gargalos_html = (
        "<li>Nenhum critério avaliado com nota crítica (1 ou 2).</li>"
    )

  return f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <title>Dossiê Executivo - {dados_emp['razao_social']}</title>
        <style>
            body {{ font-family: 'Segoe UI', Roboto, sans-serif; color: #1e293b; margin: 30px; line-height: 1.5; background: #fff; }}
            .header {{ border-bottom: 3px solid #0f172a; padding-bottom: 15px; margin-bottom: 25px; display: flex; justify-content: space-between; align-items: flex-end; }}
            .header h1 {{ margin: 0; font-size: 24px; color: #0f172a; text-transform: uppercase; }}
            .header p {{ margin: 3px 0 0 0; font-size: 13px; color: #475569; }}
            .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 25px; }}
            .kpi-card {{ background: #f8fafc; border: 1px solid #cbd5e1; border-left: 4px solid #1e3a8a; padding: 12px; border-radius: 4px; }}
            .kpi-card h4 {{ margin: 0; font-size: 11px; text-transform: uppercase; color: #64748b; }}
            .kpi-card p {{ margin: 6px 0 0 0; font-size: 18px; font-weight: bold; color: #0f172a; }}
            h2 {{ font-size: 16px; background: #0f172a; color: #fff; padding: 7px 12px; border-radius: 4px; margin-top: 25px; margin-bottom: 12px; }}
            table {{ width: 100%; border-collapse: collapse; margin-bottom: 18px; font-size: 12px; }}
            th, td {{ border: 1px solid #cbd5e1; padding: 8px 10px; text-align: left; }}
            th {{ background-color: #f1f5f9; font-weight: 600; color: #0f172a; }}
            .parecer-box {{ background: #f8fafc; border: 1px solid #94a3b8; padding: 15px; border-radius: 4px; white-space: pre-wrap; font-size: 13px; }}
            .assinaturas {{ margin-top: 50px; display: flex; justify-content: space-around; text-align: center; font-size: 13px; }}
            .linha-ass {{ border-top: 1px solid #334155; width: 280px; padding-top: 6px; }}
            .no-print-btn {{ background: #1e3a8a; color: white; padding: 10px 18px; border: none; border-radius: 4px; cursor: pointer; font-weight: bold; margin-bottom: 20px; }}
            @media print {{ body {{ margin: 10mm; }} .no-print-btn {{ display: none; }} h2, .kpi-card {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }} }}
        </style>
    </head>
    <body>
        <button class="no-print-btn" onclick="window.print()">🖨️ Imprimir / Salvar como PDF (A4)</button>
        <div class="header">
            <div>
                <h1>Dossiê Executivo de Gestão & Consultoria</h1>
                <p><strong>Cliente:</strong> {dados_emp['razao_social']} | <strong>CNPJ:</strong> {dados_emp['cnpj']} | <strong>Regime:</strong> {dados_emp['regime_tributario']}</p>
            </div>
            <div style="text-align: right;">
                <p><strong>Período:</strong> {periodo} | <strong>Consultor:</strong> {consultor}</p>
                <p><strong>Emissão:</strong> {date.today().strftime('%d/%m/%Y')}</p>
            </div>
        </div>
        <div class="kpi-grid">
            <div class="kpi-card"><h4>Maturidade 360º</h4><p>{nota_maturidade:.2f} / 5.00 ({(nota_maturidade/5)*100:.0f}%)</p></div>
            <div class="kpi-card"><h4>Receita Bruta</h4><p>R$ {kpis_fin['rec_bruta']:,.2f}</p></div>
            <div class="kpi-card"><h4>EBITDA Operacional</h4><p>R$ {kpis_fin['ebitda']:,.2f} ({kpis_fin['margem_ebitda']:.1f}%)</p></div>
            <div class="kpi-card"><h4>Ponto de Equilíbrio</h4><p>R$ {kpis_fin['pe']:,.2f}</p></div>
        </div>
        <h2>1. Parecer Técnico da Consultoria & Diagnóstico Executivo</h2>
        <div class="parecer-box">{parecer}</div>
        <h2>2. Demonstrativo de Resultado Gerencial (DRE)</h2>
        <table><thead><tr><th>Estrutura DRE</th><th style="text-align:right;">Valor (R$)</th><th style="text-align:right;">% AV</th></tr></thead><tbody>{linhas_dre_html}</tbody></table>
        <h2>3. Gargalos Críticos de Maturidade & Qualidade (MASP / 5S)</h2>
        <p style="font-size: 13px;"><strong>Último Score 5S:</strong> {score_5s} | <strong>Protocolos MASP:</strong> {len(df_masp)}</p>
        <ul style="font-size: 12.5px;">{gargalos_html}</ul>
        <h2>4. Quadro de Acompanhamento do Plano de Ação (5W2H)</h2>
        <table><thead><tr><th>Origem</th><th>O Quê & Por Quê</th><th>Responsável</th><th>Prazo</th><th>Orçamento</th><th>Status</th></tr></thead><tbody>{linhas_5w2h_html}</tbody></table>
        <h2>5. Diretrizes e Próximos Passos</h2>
        <div class="parecer-box">{prox_passos}</div>
        <div class="assinaturas">
            <div class="linha-ass"><strong>{consultor}</strong><br>Consultoria Empresarial</div>
            <div class="linha-ass"><strong>Representante Legal</strong><br>{dados_emp['razao_social']}</div>
        </div>
    </body>
    </html>
    """


# ==========================================
# MÓDULOS (1 a 6)
# ==========================================
if menu == "1. Carteira de Clientes & Acessos" and eh_consultor:
  st.header("Gestão da Carteira de Clientes & Acessos")
  tab_emp, tab_usr = st.tabs(
      ["1. Empresas Atendidas", "2. Credenciais de Acesso"]
  )
  with tab_emp:
    with st.expander("Cadastrar Nova Empresa", expanded=df_empresas.empty):
      with st.form("form_empresa", clear_on_submit=True):
        c1, c2 = st.columns(2)
        razao = c1.text_input("Razão Social *")
        cnpj = c2.text_input("CNPJ *")
        regime = c1.selectbox(
            "Regime Tributário",
            ["Simples Nacional", "Lucro Presumido", "Lucro Real", "MEI"],
        )
        segmento = c2.selectbox(
            "Segmento",
            ["Indústria", "Comércio", "Serviços", "E-commerce", "Tecnologia"],
        )
        if st.form_submit_button("Salvar Empresa"):
          if razao and cnpj:
            try:
              with engine.begin() as conn:
                conn.execute(
                    text("""
                            INSERT INTO empresas (razao_social, cnpj, regime_tributario, segmento, data_cadastro)
                            VALUES (:r, :c, :reg, :seg, :d)
                        """),
                    {
                        "r": razao,
                        "c": cnpj,
                        "reg": regime,
                        "seg": segmento,
                        "d": datetime.now().strftime("%Y-%m-%d"),
                    },
                )
              st.success("Empresa cadastrada!")
              st.rerun()
            except Exception as e:
              st.error(f"Erro ao cadastrar: {e}")
    if not df_empresas.empty:
      st.dataframe(df_empresas, use_container_width=True, hide_index=True)

  with tab_usr:
    with st.expander("Criar Novo Usuário", expanded=True):
      with st.form("form_novo_usuario", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        nome_usr = c1.text_input("Nome Completo *")
        login_usr = c2.text_input("Login *")
        senha_usr = c3.text_input("Senha *", type="password")
        c4, c5 = st.columns(2)
        perfil_usr = c4.selectbox("Perfil", ["cliente", "consultor"])
        opcoes_emp = {
            row["razao_social"]: row["id"] for _, row in df_empresas.iterrows()
        }
        emp_vinc = c5.selectbox(
            "Empresa Vinculada",
            ["Nenhuma (Consultor Global)"] + list(opcoes_emp.keys()),
        )
        if st.form_submit_button("Criar Conta"):
          if nome_usr and login_usr and senha_usr:
            e_id = (
                None
                if emp_vinc == "Nenhuma (Consultor Global)"
                else opcoes_emp[emp_vinc]
            )
            try:
              with engine.begin() as conn:
                conn.execute(
                    text("""
                            INSERT INTO usuarios (username, senha_hash, nome_completo, perfil, empresa_id)
                            VALUES (:u, :s, :n, :p, :e)
                        """),
                    {
                        "u": login_usr.strip(),
                        "s": hash_senha(senha_usr),
                        "n": nome_usr,
                        "p": perfil_usr,
                        "e": e_id,
                    },
                )
              st.success("Usuário criado!")
              st.rerun()
            except Exception as e:
              st.error(f"Erro: {e}")

    df_u = pd.read_sql(
        """
        SELECT u.id, u.username, u.nome_completo, u.perfil, COALESCE(e.razao_social, 'Global') as empresa
        FROM usuarios u LEFT JOIN empresas e ON u.empresa_id = e.id
    """,
        engine,
    )
    st.dataframe(df_u, use_container_width=True, hide_index=True)

elif menu == "2. Diagnóstico 360º":
  if empresa_id:
    st.header(f"Diagnóstico 360º — {empresa_selecionada}")
    if eh_consultor:
      tab_app, tab_res = st.tabs(
          ["Aplicar Diagnóstico", "Dashboard & Radar"]
      )
    else:
      tab_res = st.container()
      tab_app = None

    if eh_consultor and tab_app:
      with tab_app:
        with st.form("form_diag"):
          res_t = []
          for pilar, perguntas in QUESTIONARIO_PADRAO.items():
            st.subheader(pilar)
            for idx, p in enumerate(perguntas):
              c1, c2 = st.columns([2, 3])
              nota = c1.slider(p, 1, 5, 3, key=f"{pilar}_{idx}")
              obs = c2.text_input("Evidência", key=f"obs_{pilar}_{idx}")
              res_t.append({
                  "empresa_id": empresa_id,
                  "data_avaliacao": date.today().isoformat(),
                  "pilar": pilar,
                  "pergunta": p,
                  "nota": nota,
                  "observacao": obs,
              })
            st.markdown("---")
          if st.form_submit_button("Salvar Diagnóstico"):
            with engine.begin() as conn:
              conn.execute(
                  text(
                      "DELETE FROM diagnostico_360 WHERE empresa_id = :eid"
                  ),
                  {"eid": empresa_id},
              )
              for r in res_t:
                conn.execute(
                    text("""
                            INSERT INTO diagnostico_360 (empresa_id, data_avaliacao, pilar, pergunta, nota, observacao)
                            VALUES (:empresa_id, :data_avaliacao, :pilar, :pergunta, :nota, :observacao)
                        """),
                    r,
                )
            st.success("Salvo com sucesso!")
            st.rerun()

    with tab_res:
      df_diag = pd.read_sql(
          text("SELECT * FROM diagnostico_360 WHERE empresa_id = :eid"),
          engine,
          params={"eid": empresa_id},
      )
      if not df_diag.empty:
        df_m = df_diag.groupby("pilar")["nota"].mean().reset_index()
        df_m["Pct"] = (df_m["nota"] / 5.0) * 100
        c_g, c_k = st.columns([3, 2])
        with c_g:
          fig = px.line_polar(
              df_m,
              r="nota",
              theta="pilar",
              line_close=True,
              range_r=[0, 5],
              markers=True,
          )
          fig.update_traces(fill="toself")
          st.plotly_chart(fig, use_container_width=True)
        with c_k:
          st.metric("Maturidade Geral", f"{df_diag['nota'].mean():.2f} / 5.0")
          st.dataframe(df_m, use_container_width=True, hide_index=True)
      else:
        st.info("Nenhum diagnóstico registrado.")

elif menu == "3. Finanças & DRE Gerencial":
  if empresa_id:
    st.header(f"Finanças & DRE — {empresa_selecionada}")
    t_lanc, t_dre, t_cx = st.tabs(["Lançamentos", "DRE & PE", "Fluxo de Caixa"])
    with t_lanc:
      if eh_consultor and st.button("Carregar Dados de Exemplo"):
        m = date.today().strftime("%Y-%m")
        ex = [
            {
                "empresa_id": empresa_id,
                "data_lancamento": f"{m}-05",
                "tipo": "Entrada",
                "grupo_dre": "1. Receita Operacional Bruta",
                "categoria": "Vendas de Produtos",
                "descricao": "Faturamento",
                "valor": 85000.0,
                "status": "Realizado",
            },
            {
                "empresa_id": empresa_id,
                "data_lancamento": f"{m}-20",
                "tipo": "Saída",
                "grupo_dre": "2. Deduções e Impostos s/ Vendas",
                "categoria": "Simples Nacional / DAS",
                "descricao": "DAS",
                "valor": 10800.0,
                "status": "Realizado",
            },
            {
                "empresa_id": empresa_id,
                "data_lancamento": f"{m}-10",
                "tipo": "Saída",
                "grupo_dre": "3. Custos e Despesas Variáveis (CMV/CSV)",
                "categoria": "Matéria-Prima / Mercadoria p/ Revenda",
                "descricao": "Matéria-prima",
                "valor": 42000.0,
                "status": "Realizado",
            },
            {
                "empresa_id": empresa_id,
                "data_lancamento": f"{m}-05",
                "tipo": "Saída",
                "grupo_dre": "4. Custos e Despesas Fixas Operacionais",
                "categoria": "Folha de Pagamento e Encargos",
                "descricao": "Salários",
                "valor": 22000.0,
                "status": "Realizado",
            },
        ]
        with engine.begin() as conn:
          for item in ex:
            conn.execute(
                text("""
                        INSERT INTO lancamentos_financeiros (empresa_id, data_lancamento, tipo, grupo_dre, categoria, descricao, valor, status)
                        VALUES (:empresa_id, :data_lancamento, :tipo, :grupo_dre, :categoria, :descricao, :valor, :status)
                    """),
                item,
            )
        st.rerun()

      with st.form("form_fin", clear_on_submit=True):
        g_sel = st.selectbox("Grupo DRE", list(PLANO_CONTAS_DRE.keys()))
        t_auto = PLANO_CONTAS_DRE[g_sel]["tipo"]
        cat_sel = st.selectbox("Categoria", PLANO_CONTAS_DRE[g_sel]["categorias"])
        c1, c2, c3 = st.columns(3)
        d_lanc = c1.date_input("Data", value=date.today())
        s_lanc = c2.selectbox("Status", ["Realizado", "Projetado"])
        v_lanc = c3.number_input("Valor (R$)", min_value=0.01, step=100.0)
        desc = st.text_input("Descrição *")
        if st.form_submit_button("Registrar"):
          if desc and v_lanc > 0:
            with engine.begin() as conn:
              conn.execute(
                  text("""
                        INSERT INTO lancamentos_financeiros (empresa_id, data_lancamento, tipo, grupo_dre, categoria, descricao, valor, status)
                        VALUES (:eid, :dl, :tp, :gd, :cat, :des, :val, :sta)
                    """),
                  {
                      "eid": empresa_id,
                      "dl": d_lanc.isoformat(),
                      "tp": t_auto,
                      "gd": g_sel,
                      "cat": cat_sel,
                      "des": desc,
                      "val": v_lanc,
                      "sta": s_lanc,
                  },
              )
            st.success("Registrado!")
            st.rerun()

      df_f = pd.read_sql(
          text(
              "SELECT * FROM lancamentos_financeiros WHERE empresa_id = :eid"
              " ORDER BY data_lancamento DESC"
          ),
          engine,
          params={"eid": empresa_id},
      )
      if not df_f.empty:
        st.dataframe(df_f.drop(columns=["empresa_id"]), use_container_width=True)

    with t_dre:
      df_f = pd.read_sql(
          text(
              "SELECT * FROM lancamentos_financeiros WHERE empresa_id = :eid"
          ),
          engine,
          params={"eid": empresa_id},
      )
      if not df_f.empty:
        rb = df_f[df_f["grupo_dre"] == "1. Receita Operacional Bruta"][
            "valor"
        ].sum()
        ded = df_f[df_f["grupo_dre"] == "2. Deduções e Impostos s/ Vendas"][
            "valor"
        ].sum()
        rl = rb - ded
        cv = df_f[
            df_f["grupo_dre"]
            == "3. Custos e Despesas Variáveis (CMV/CSV)"
        ]["valor"].sum()
        mc = rl - cv
        cf = df_f[
            df_f["grupo_dre"] == "4. Custos e Despesas Fixas Operacionais"
        ]["valor"].sum()
        eb = mc - cf
        imc = (mc / rb) if rb > 0 else 0
        pe = (cf / imc) if imc > 0 else 0

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Receita Bruta", f"R$ {rb:,.2f}")
        k2.metric("Margem Contribuição", f"R$ {mc:,.2f}", f"{imc*100:.1f}%")
        k3.metric("EBITDA", f"R$ {eb:,.2f}")
        k4.metric("Ponto de Equilíbrio", f"R$ {pe:,.2f}")

        linhas = [
            ("Receita Bruta", rb),
            ("Deduções/Impostos", -ded),
            ("Receita Líquida", rl),
            ("Custos Variáveis", -cv),
            ("Margem de Contribuição", mc),
            ("Custos Fixos", -cf),
            ("EBITDA", eb),
        ]
        st.dataframe(
            pd.DataFrame(linhas, columns=["Conta", "Valor"]),
            use_container_width=True,
            hide_index=True,
        )

    with t_cx:
      df_f = pd.read_sql(
          text(
              "SELECT * FROM lancamentos_financeiros WHERE empresa_id = :eid"
              " ORDER BY data_lancamento ASC"
          ),
          engine,
          params={"eid": empresa_id},
      )
      if not df_f.empty:
        df_d = (
            df_f.groupby(["data_lancamento", "tipo"])["valor"]
            .sum()
            .unstack(fill_value=0)
            .reset_index()
        )
        if "Entrada" not in df_d.columns:
          df_d["Entrada"] = 0.0
        if "Saída" not in df_d.columns:
          df_d["Saída"] = 0.0
        df_d["Acumulado"] = (df_d["Entrada"] - df_d["Saída"]).cumsum()
        fig_c = px.line(
            df_d,
            x="data_lancamento",
            y="Acumulado",
            markers=True,
            title="Evolução de Caixa",
        )
        st.plotly_chart(fig_c, use_container_width=True)

elif menu == "4. Qualidade, MASP & 5S":
  if empresa_id:
    st.header(f"Qualidade & Lean — {empresa_selecionada}")
    t_m, t_p, t_5 = st.tabs(["MASP", "Pareto", "Auditoria 5S"])
    with t_m:
      if eh_consultor:
        with st.expander("Novo Protocolo MASP"):
          with st.form("form_masp", clear_on_submit=True):
            prob = st.text_input("Problema / Anomalia *")
            setor = st.text_input("Setor *")
            causa = st.text_input("Causa Raiz Definitiva *")
            if st.form_submit_button("Salvar"):
              if prob and causa:
                with engine.begin() as conn:
                  conn.execute(
                      text("""
                            INSERT INTO analises_masp (empresa_id, data_analise, problema, setor, causa_raiz)
                            VALUES (:eid, :da, :p, :s, :c)
                        """),
                      {
                          "eid": empresa_id,
                          "da": date.today().isoformat(),
                          "p": prob,
                          "s": setor,
                          "c": causa,
                      },
                  )
                st.rerun()
      df_masp = pd.read_sql(
          text("SELECT * FROM analises_masp WHERE empresa_id = :eid"),
          engine,
          params={"eid": empresa_id},
      )
      if not df_masp.empty:
        st.dataframe(df_masp, use_container_width=True, hide_index=True)

    with t_p:
      with st.form("form_par", clear_on_submit=True):
        f_prob = st.text_input("Tipo de Falha *")
        f_freq = st.number_input("Ocorrências", 1, step=1)
        if st.form_submit_button("Adicionar"):
          if f_prob:
            with engine.begin() as conn:
              conn.execute(
                  text("""
                        INSERT INTO ocorrencias_pareto (empresa_id, data_registro, tipo_problema, frequencia)
                        VALUES (:eid, :dr, :tp, :f)
                    """),
                  {
                      "eid": empresa_id,
                      "dr": date.today().isoformat(),
                      "tp": f_prob,
                      "f": f_freq,
                  },
              )
            st.rerun()
      df_par = pd.read_sql(
          text("SELECT * FROM ocorrencias_pareto WHERE empresa_id = :eid"),
          engine,
          params={"eid": empresa_id},
      )
      if not df_par.empty:
        fig_par = px.bar(
            df_par, x="tipo_problema", y="frequencia", title="Pareto de Falhas"
        )
        st.plotly_chart(fig_par, use_container_width=True)

    with t_5:
      if eh_consultor:
        with st.form("form_5s"):
          s_nom = st.text_input("Setor Auditado")
          s1 = st.slider("1. Utilização", 1, 5, 3)
          s2 = st.slider("2. Organização", 1, 5, 3)
          s3 = st.slider("3. Limpeza", 1, 5, 3)
          s4 = st.slider("4. Padronização", 1, 5, 3)
          s5 = st.slider("5. Disciplina", 1, 5, 3)
          if st.form_submit_button("Salvar 5S"):
            with engine.begin() as conn:
              conn.execute(
                  text("""
                        INSERT INTO auditorias_5s (empresa_id, data_auditoria, setor_auditado, s1_utilizacao, s2_organizacao, s3_limpeza, s4_padronizacao, s5_disciplina)
                        VALUES (:eid, :da, :set, :s1, :s2, :s3, :s4, :s5)
                    """),
                  {
                      "eid": empresa_id,
                      "da": date.today().isoformat(),
                      "set": s_nom,
                      "s1": s1,
                      "s2": s2,
                      "s3": s3,
                      "s4": s4,
                      "s5": s5,
                  },
              )
            st.rerun()
      df_5s = pd.read_sql(
          text("SELECT * FROM auditorias_5s WHERE empresa_id = :eid"),
          engine,
          params={"eid": empresa_id},
      )
      if not df_5s.empty:
        st.dataframe(df_5s, use_container_width=True, hide_index=True)

elif menu == "5. Plano de Ação (5W2H)":
  if empresa_id:
    st.header(f"Plano 5W2H — {empresa_selecionada}")
    if eh_consultor:
      with st.expander("Nova Ação 5W2H"):
        with st.form("form_5w", clear_on_submit=True):
          what = st.text_input("O Quê (What) *")
          who = st.text_input("Quem (Who) *")
          when = st.date_input("Prazo (When)")
          if st.form_submit_button("Salvar Ação"):
            if what and who:
              with engine.begin() as conn:
                conn.execute(
                    text("""
                            INSERT INTO plano_5w2h (empresa_id, what_oque, who_quem, when_prazo, status)
                            VALUES (:eid, :wh, :wq, :wp, 'Pendente')
                        """),
                    {
                        "eid": empresa_id,
                        "wh": what,
                        "wq": who,
                        "wp": when.isoformat(),
                    },
                )
              st.rerun()

    df_5 = pd.read_sql(
        text("SELECT * FROM plano_5w2h WHERE empresa_id = :eid"),
        engine,
        params={"eid": empresa_id},
    )
    if not df_5.empty:
      travado = (
          ["id", "what_oque", "who_quem", "when_prazo"]
          if not eh_consultor
          else ["id"]
      )
      df_ed = st.data_editor(
          df_5,
          disabled=travado,
          column_config={
              "status": st.column_config.SelectboxColumn(
                  "Status",
                  options=["Pendente", "Em Andamento", "Atrasado", "Concluído"],
              )
          },
          hide_index=True,
          use_container_width=True,
      )
      if st.button("Salvar Alterações"):
        with engine.begin() as conn:
          for _, r in df_ed.iterrows():
            conn.execute(
                text(
                    "UPDATE plano_5w2h SET status = :st WHERE id = :id"
                ),
                {"st": r["status"], "id": r["id"]},
            )
        st.success("Atualizado!")
        st.rerun()

elif menu == "6. Relatório Executivo (Dossiê PDF)":
  if empresa_id:
    st.header(f"Dossiê Executivo — {empresa_selecionada}")
    df_diag = pd.read_sql(
        text("SELECT * FROM diagnostico_360 WHERE empresa_id = :eid"),
        engine,
        params={"eid": empresa_id},
    )
    df_fin = pd.read_sql(
        text("SELECT * FROM lancamentos_financeiros WHERE empresa_id = :eid"),
        engine,
        params={"eid": empresa_id},
    )
    df_masp = pd.read_sql(
        text("SELECT * FROM analises_masp WHERE empresa_id = :eid"),
        engine,
        params={"eid": empresa_id},
    )
    df_5s = pd.read_sql(
        text("SELECT * FROM auditorias_5s WHERE empresa_id = :eid"),
        engine,
        params={"eid": empresa_id},
    )
    df_5w = pd.read_sql(
        text("SELECT * FROM plano_5w2h WHERE empresa_id = :eid"),
        engine,
        params={"eid": empresa_id},
    )

    mat = df_diag["nota"].mean() if not df_diag.empty else 0.0
    rb = (
        df_fin[df_fin["grupo_dre"] == "1. Receita Operacional Bruta"][
            "valor"
        ].sum()
        if not df_fin.empty
        else 0.0
    )
    cf = (
        df_fin[df_fin["grupo_dre"] == "4. Custos e Despesas Fixas Operacionais"][
            "valor"
        ].sum()
        if not df_fin.empty
        else 0.0
    )
    kpis = {"rec_bruta": rb, "ebitda": 0, "margem_ebitda": 0, "pe": cf}
    df_dre_rel = pd.DataFrame(columns=["Estrutura DRE", "Valor (R$)", "% AV"])

    html_dossie = gerar_html_dossie(
        dados_empresa_ativa,
        kpis,
        df_dre_rel,
        mat,
        pd.DataFrame(),
        df_masp,
        "N/A",
        df_5w,
        "Consultor",
        date.today().strftime("%m/%Y"),
        "Parecer executivo gerado automaticamente.",
        "Acompanhar planos.",
    )

    st.download_button(
        "📥 Baixar Dossiê (.html para Impressão/PDF)",
        data=html_dossie,
        file_name=f"Dossie_{empresa_selecionada}.html",
        mime="text/html",
    )
    st.components.v1.html(html_dossie, height=600, scrolling=True)