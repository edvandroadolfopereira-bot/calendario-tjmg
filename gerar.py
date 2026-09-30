# -*- coding: utf-8 -*-
"""Dias uteis, nao uteis e corridos por comarca de MG, para cada ano que o TJMG publica,
e a pagina "Calendario TJMG" do gruponomos.com, com mapa das comarcas.

Bases (todas oficiais, baixadas por baixar.py e coletar_guia.py):
  paginas/AAAA.html            pagina "Feriados Locais" do Guia Judiciario do TJMG, um arquivo por ano
  guia-comarcas.json           municipios integrantes de cada comarca (consulta ao vivo do Guia)
  ibge-municipios-mg.json      853 municipios, com mesorregiao, microrregiao e regioes geograficas
  ibge-malha-mg.geojson        malha municipal
  ibge-populacao-*.json        estimativas anuais (agregado 6579) e Censo 2022 (agregado 4714)

Criterio: dia util = segunda a sexta que a fonte nao registra como feriado, recesso, ponto
facultativo ou suspensao de expediente. CPC, art. 216: sao feriados, para efeito forense, os
sabados, os domingos e os dias em que nao haja expediente forense.
Entrada "Comarca - descricao" e' feriado municipal; entrada sem comarca vale para todo o Estado.

Saidas: docs/ (dados, servidos pelo GitHub Pages) e, se existir nesta maquina, a pasta do site
(pagina, dados de reserva, sitemap). Saida 0 fez, 1 falha de conferencia (nada e' gravado).
"""
import csv
import datetime
import glob
import hashlib
import html
import io
import json
import math
import os
import re
import sys
import unicodedata

AQUI = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(AQUI, "docs")
SITE = os.path.join(os.path.expanduser("~"), "OneDrive", ".claude", "Biblioteca-Academica-Direito",
                    "conteudo-juridico-pericial", "site-gruponomos")
REMOTO = "https://edvandroadolfopereira-bot.github.io/calendario-tjmg/"
URL = "https://www8.tjmg.jus.br/servicos/gj/calendario/"
PRIMEIRO_ANO_POP = 2016  # o calendario do TJMG comeca em 2016
# grafia do Guia e do calendario -> grafia do IBGE; cada par casa um a um com o municipio que sobrava
ALIAS = {"maxacalis": "machacalis", "dona eusebia": "dona euzebia", "matias lobato": "mathias lobato",
         "venceslau bras": "wenceslau braz", "itamoji": "itamogi", "itapajipe": "itapagipe",
         "jabuticatubas": "jaboticatubas", "itabirinha de mantena": "itabirinha",
         "sao sebastiao da vargem": "sao sebastiao da vargem alegre", "estrela d alva": "estrela dalva",
         "santa rita do ibitipoca": "santa rita de ibitipoca",
         "amparo da serra": "amparo do serra", "santa rita do jacutinga": "santa rita de jacutinga"}


def norm(s):
    s = unicodedata.normalize("NFD", s.casefold())
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def limpar(s):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s)).replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()


# Feriados nacionais: Lei 662/1949, art. 1o, na redacao da Lei 10.607/2002 (1/1, 21/4, 1/5, 7/9, 2/11,
# 15/11, 25/12), Lei 6.802/1980 (12/10) e Lei 14.759/2023 (20/11). Conferido no Planalto em 30/09/2026.
NACIONAIS = ("confraternizacao universal", "tiradentes", "dia do trabalho", "independencia do brasil",
             "nossa senhora aparecida", "finados", "proclamacao da republica", "consciencia negra")
# Feriados forenses da Justica mineira: a propria fonte os fundamenta na LC estadual 59/2001 e na Res. 458/2004
ESTADUAIS = ("carnaval", "cinzas", "quarta feira santa", "quinta feira santa", "paixao de cristo", "dia da justica")


def categoria(desc):
    """N feriado nacional; E feriado forense estadual; R recesso forense (LC 59/2001, art. 313);
    P ponto facultativo ou suspensao por portaria do TJMG; ? entrada que a regra nao conhece."""
    d = norm(desc)
    if re.search(r"portaria|funcionario publico|servidor publico", d):
        return "P"
    if any(n in d for n in NACIONAIS) or d.startswith("natal"):
        return "N"
    if d.startswith("susp") or d.startswith("vespera"):
        return "R"
    if any(e in d for e in ESTADUAIS):
        return "E"
    return "?"


def ler(caminho, ano):
    t = io.open(caminho, encoding="latin-1").read()
    sel = re.search(r'<select name="comarca".*?</select>', t, re.S).group(0)
    comarcas = [limpar(o) for o in re.findall(r"<option[^>]*>(.*?)</option>", sel, re.S)]
    comarcas = [c for c in comarcas if c and c.lower() != "todas"]
    # a pagina grafa de um jeito na lista e de outro no seletor: "del-Rei" e "Del-Rei",
    # "Brazópolis" e "Brasópolis", "Jaboticatubas" e "Jabuticatubas". Vale o nome do seletor.
    oficial = {norm(c): c for c in comarcas}
    seletor = {"brazopolis": "brasopolis", "jaboticatubas": "jabuticatubas"}
    gerais, locais = {}, {}
    partes = re.split(r"<b>(\d\d)/(\d\d)/%d</b>" % ano, t)
    for i in range(1, len(partes), 3):
        chave = "%s-%s" % (partes[i + 1], partes[i])  # MM-DD
        bloco = partes[i + 2].split("</td>")[0]
        for item in re.split(r"<br\s*/?>", bloco):
            if "&nbsp;-&nbsp;" in item:
                com, desc = [limpar(x) for x in item.split("&nbsp;-&nbsp;", 1)]
                com = oficial.get(seletor.get(norm(com), norm(com)), com)
                locais.setdefault(com, {}).setdefault(chave, []).append(desc)
            elif limpar(item):
                gerais.setdefault(chave, []).append(limpar(item))
    return comarcas, gerais, locais


def dias_do_ano(ano):
    d, fim = datetime.date(ano, 1, 1), datetime.date(ano, 12, 31)
    while d <= fim:
        yield d
        d += datetime.timedelta(1)


def semana(ano, chave):
    return datetime.date(ano, int(chave[:2]), int(chave[3:])).weekday() < 5


def prazo_suspenso(chave):
    """CPC, art. 220: o curso do prazo processual fica suspenso de 20 de dezembro a 20 de janeiro, inclusive."""
    return chave <= "01-20" or chave >= "12-20"


def calcular(ano, comarcas, gerais, locais):
    todos = list(dias_do_ano(ano))
    fds = sum(1 for d in todos if d.weekday() >= 5)
    cat = {k: categoria(" ".join(v)) for k, v in gerais.items()}
    por_cat = {c: sum(1 for k in gerais if cat[k] == c and semana(ano, k)) for c in "NERP"}
    g = sum(por_cat.values())
    linhas = []
    for c in comarcas:
        loc = locais.get(c, {})
        ls = sum(1 for k in loc if semana(ano, k) and k not in gerais)
        susp = sum(1 for d in todos if d.weekday() < 5 and prazo_suspenso(d.strftime("%m-%d"))
                   and d.strftime("%m-%d") not in gerais and d.strftime("%m-%d") not in loc)
        linhas.append({"comarca": c, "corridos": len(todos), "fds": fds, "N": por_cat["N"], "E": por_cat["E"], "R": por_cat["R"],
                       "P": por_cat["P"], "locais": ls, "susp": susp, "uteis": len(todos) - fds - g - ls,
                       "nao_uteis": fds + g + ls})
    return linhas, cat


def conferir(ano, comarcas, gerais, locais, linhas):
    erros = []
    if len(comarcas) != len(set(comarcas)) or len(comarcas) < 250:
        erros.append("lista de comarcas repetida ou curta demais: %d" % len(comarcas))
    fora = sorted(set(locais) - set(comarcas))
    if fora:
        erros.append("comarca com feriado e fora da lista de comarcas: %s" % fora)
    esperado = 366 if (ano % 4 == 0 and (ano % 100 != 0 or ano % 400 == 0)) else 365
    if linhas[0]["corridos"] != esperado:
        erros.append("o ano deveria ter %d dias" % esperado)
    # segunda contagem, por caminho independente: percorre o ano dia a dia para cada comarca
    for l in linhas:
        n = 0
        for m in range(1, 13):
            for d in range(1, 32):
                try:
                    dt = datetime.date(ano, m, d)
                except ValueError:
                    continue
                k = "%02d-%02d" % (m, d)
                if dt.weekday() < 5 and k not in gerais and k not in locais.get(l["comarca"], {}):
                    n += 1
        if n != l["uteis"] or l["uteis"] + l["nao_uteis"] != l["corridos"]:
            erros.append("contagem divergente em %s: %d x %d" % (l["comarca"], n, l["uteis"]))
    for k, v in gerais.items():
        if categoria(" ".join(v)) == "?":
            erros.append("entrada estadual que a regra de classificacao nao conhece, em %s: %s" % (k, v))
    for nome in ("Natal", "Tiradentes", "Finados"):
        if not any(nome in " ".join(v) for v in gerais.values()):
            erros.append("feriado geral ausente na leitura: " + nome)
    return ["%d: %s" % (ano, e) for e in erros]


def populacao():
    """-> (colunas de ano, {id do municipio: [pessoas por coluna]}). 2022 e' o Censo; os demais, estimativa."""
    pop, anos = {}, set()
    for arq in ("ibge-populacao-estimada.json", "ibge-populacao-censo-2022.json"):
        j = json.load(io.open(os.path.join(AQUI, arq), encoding="utf-8"))
        for s in j[0]["resultados"][0]["series"]:
            for a, v in s["serie"].items():
                if int(a) >= PRIMEIRO_ANO_POP and re.fullmatch(r"\d+", v or ""):
                    pop.setdefault(s["localidade"]["id"], {})[int(a)] = int(v)
                    anos.add(int(a))
    cols = sorted(anos)
    return cols, {i: [d.get(a) for a in cols] for i, d in pop.items()}


def coluna_pop(ano, cols):
    """Ano de referencia da populacao: o proprio ano, ou o ultimo dado do IBGE anterior a ele."""
    ate = [c for c in cols if c <= ano]
    return max(ate) if ate else min(cols)


def mapa(comarcas):
    """Municipios do IBGE desenhados e ligados a comarca (Guia Judiciario), com regioes e populacao."""
    guia = json.load(io.open(os.path.join(AQUI, "guia-comarcas.json"), encoding="utf-8"))
    if guia["falhas"] or set(guia["comarcas"]) != set(comarcas):
        raise SystemExit("FALHA: a coleta do Guia Judiciario esta' incompleta ou a lista de comarcas mudou; "
                         "rode coletar_guia.py")
    ibge = json.load(io.open(os.path.join(AQUI, "ibge-municipios-mg.json"), encoding="utf-8"))
    por_nome = {norm(m["nome"]): m for m in ibge}
    por_id = {str(m["id"]): m for m in ibge}
    dono, ruins = {}, []
    for i, c in enumerate(comarcas):
        for n in guia["comarcas"][c]["municipios"]:
            m = por_nome.get(ALIAS.get(norm(n), norm(n)))
            if m is None or str(m["id"]) in dono:
                ruins.append((c, n))
                continue
            dono[str(m["id"])] = i
    if ruins or len(dono) != len(ibge):
        raise SystemExit("FALHA: o Guia nao fecha com os %d municipios do IBGE. Sem casar ou repetido: %s. "
                         "Sem comarca: %s" % (len(ibge), ruins, [m["nome"] for m in ibge if str(m["id"]) not in dono]))

    cols, pop = populacao()
    sem_pop = [m["nome"] for m in ibge if str(m["id"]) not in pop or None in pop[str(m["id"])]]
    if sem_pop:
        raise SystemExit("FALHA: municipio sem populacao em algum ano do IBGE: %s" % sem_pop)

    def regioes(m):
        return (m["microrregiao"]["mesorregiao"]["nome"], m["microrregiao"]["nome"],
                m["regiao-imediata"]["regiao-intermediaria"]["nome"], m["regiao-imediata"]["nome"])
    listas = [sorted({regioes(m)[j] for m in ibge}) for j in range(4)]

    def polo(m):
        """2 polo de regiao intermediaria, 1 polo de regiao imediata: o IBGE nomeia a regiao pelo(s) polo(s)."""
        _, _, inter, imed = regioes(m)
        # por norm(): o IBGE grafa a regiao "Juíz de Fora" e o municipio "Juiz de Fora"
        if norm(m["nome"]) in [norm(p) for p in inter.split(" - ")]:
            return 2
        return 1 if norm(m["nome"]) in [norm(p) for p in imed.split(" - ")] else 0
    polos = {str(m["id"]): polo(m) for m in ibge}
    for j, nivel in ((2, 2), (3, 1)):
        sem = [r for r in listas[j] if not any(regioes(m)[j] == r and polos[str(m["id"])] >= nivel for m in ibge)]
        if sem:
            raise SystemExit("FALHA: regiao do IBGE sem municipio-polo identificado: %s" % sem)

    geo = json.load(io.open(os.path.join(AQUI, "ibge-malha-mg.geojson"), encoding="utf-8"))["features"]
    aneis = []
    for ft in geo:
        g = ft["geometry"]
        polis = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        aneis.append((ft["properties"]["codarea"], [a for po in polis for a in po]))
    xs = [x for _, an in aneis for a in an for x, _ in a]
    ys = [y for _, an in aneis for a in an for _, y in a]
    k = math.cos(math.radians((min(ys) + max(ys)) / 2))
    esc = 1000.0 / ((max(xs) - min(xs)) * k)
    px = lambda x: (x - min(xs)) * k * esc
    py = lambda y: (max(ys) - y) * esc
    itens = []
    # sede da comarca: o municipio que lhe da' o nome, e onde fica o forum
    sede = lambda c: ALIAS.get({"brasopolis": "brazopolis"}.get(norm(c), norm(c)), {"brasopolis": "brazopolis"}.get(norm(c), norm(c)))
    for cod, an in aneis:
        m = por_id[cod]
        d = "".join("M" + "L".join("%.1f %.1f" % (px(x), py(y)) for x, y in a) + "Z" for a in an)
        maior = max(an, key=len)  # centro aproximado: media dos vertices do maior anel
        r = regioes(m)
        itens.append([dono[cod], m["nome"], d] + [listas[j].index(r[j]) for j in range(4)] +
                     [polos[cod], round(sum(px(x) for x, _ in maior) / len(maior), 1),
                      round(sum(py(y) for _, y in maior) / len(maior), 1), pop[cod],
                      1 if norm(m["nome"]) == sede(comarcas[dono[cod]]) else 0])
    if sum(i[11] for i in itens) != len(comarcas):
        raise SystemExit("FALHA: deveria haver uma sede por comarca, ha' %d em %d" % (sum(i[11] for i in itens), len(comarcas)))
    if len(itens) != len(ibge):
        raise SystemExit("FALHA: a malha deveria ter %d municipios, tem %d" % (len(ibge), len(itens)))
    return {"h": round((max(ys) - min(ys)) * esc), "c": comarcas, "lido": guia["coletado_em"].split(" ")[0],
            "reg": listas, "pa": cols, "m": itens}


def gravar(caminho, texto, enc="utf-8"):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with io.open(caminho + ".tmp", "w", encoding=enc, newline="\n") as f:
        f.write(texto)
    os.replace(caminho + ".tmp", caminho)


PAGINA = r"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Calendário TJMG: dias úteis por comarca | Grupo Nomos</title>
<meta name="description" content="Dias úteis, não úteis e corridos em cada comarca de Minas Gerais, ano a ano, calculados a partir da página Feriados Locais do TJMG. Mapa das comarcas com municípios, regiões e população do IBGE, calendário interativo e visão de todo o Estado.">
<link rel="canonical" href="https://gruponomos.com/calendario-tjmg.html">
<link rel="icon" href="/assets/favicon.ico">
<style>
:root{--fundo:#F7F4EF;--tinta:#1F1820;--ouro:#B59A63;--faixa:#353036;--fds:#ddd6cc;--N:#b5523b;--E:#c77d2e;--R:#6d4c41;--P:#7a4a8c;--L:#2f5d8a}
*{box-sizing:border-box}
body{margin:0;background:var(--fundo);color:var(--tinta);font:17px/1.6 Georgia,"Times New Roman",serif}
header{background:var(--faixa);color:#fff;padding:24px 16px}
header div,main,footer div{max-width:1100px;margin:0 auto}
header small{color:var(--ouro);letter-spacing:.2em;font:600 13px/1 Arial,sans-serif}
header a{color:#fff;text-decoration:none;font:700 28px/1.2 Arial,sans-serif}
nav a{color:#fff;font:14px Arial,sans-serif;margin-right:14px}
main{padding:32px 16px 48px}
h1{font:700 30px/1.25 Arial,sans-serif;margin:0 0 8px}
h2{font:700 21px/1.3 Arial,sans-serif;margin:36px 0 10px;color:var(--faixa)}
h3{font:700 17px/1.3 Arial,sans-serif;margin:24px 0 8px;color:var(--faixa)}
.meta,.nota{color:#5d545a;font:15px/1.5 Arial,sans-serif}
a{color:#7a5f2c}
label{font:700 15px Arial,sans-serif;display:block;margin:0 0 4px}
select,input{font:16px Arial,sans-serif;padding:8px;border:1px solid #8b8086;border-radius:6px;background:#fff;color:var(--tinta);max-width:100%}
select:focus,input:focus,th button:focus{outline:3px solid var(--ouro);outline-offset:2px}
.campos{display:flex;flex-wrap:wrap;gap:12px 24px;margin:14px 0}
#ano{font-weight:700;font-size:18px}
.cartoes{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:14px 0}
.cartao{background:#fff;border-left:4px solid var(--ouro);padding:10px 12px;font:14px/1.3 Arial,sans-serif}
.cartao b{display:block;font-size:26px;line-height:1.2}
.legenda{display:flex;flex-wrap:wrap;gap:6px 16px;font:14px Arial,sans-serif;margin:10px 0}
.legenda span::before{content:"";display:inline-block;width:14px;height:14px;margin-right:6px;vertical-align:-2px;border:1px solid #8b8086;background:var(--c,#fff)}
.legenda span.bola::before{border-radius:50%;background:#1F1820;border:2px solid #fff;outline:1px solid #1F1820}
.legenda span.forum::before{border-radius:50%;background:#e0a100;border:1px solid #5b3a00;width:9px;height:9px}
.legenda span.bolinha::before{border-radius:50%;background:#fff;border:2px solid #1F1820;width:9px;height:9px}
.meses{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:14px}
.mes{background:#fff;padding:10px;border:1px solid #d8cfc2}
.mes table{border-collapse:collapse;width:100%;font:14px Arial,sans-serif;text-align:center}
.mes caption{font:700 15px Arial,sans-serif;padding-bottom:4px;text-align:left}
.mes caption small{font-weight:400;color:#5d545a}
.mes th{color:#5d545a;font-weight:600;padding:2px}
.mes td{padding:5px 0;border:1px solid #efe9df}
td.fds{background:var(--fds)}
td.S{background:repeating-linear-gradient(45deg,#fff,#fff 4px,#e6d9ee 4px,#e6d9ee 8px);box-shadow:inset 0 0 0 1px var(--P)}
.legenda span.l-S::before{background:repeating-linear-gradient(45deg,#fff,#fff 3px,#e6d9ee 3px,#e6d9ee 6px);border-color:var(--P)}
td.N,td.E,td.R,td.P,td.L{color:#fff;font-weight:700}
td.N{background:var(--N)}td.E{background:var(--E)}td.R{background:var(--R)}td.P{background:var(--P)}td.L{background:var(--L)}
.rolagem{overflow-x:auto}
table.dados{border-collapse:collapse;width:100%;font:15px Arial,sans-serif;background:#fff}
table.dados th,table.dados td{border:1px solid #d8cfc2;padding:6px 8px;text-align:right}
table.dados th:first-child,table.dados td:first-child,table.dados td.e,table.dados th.e{text-align:left}
table.dados th{background:#ece5d8}
table.dados tfoot td{font-weight:700;background:#f4efe6}
th button{all:unset;cursor:pointer;font-weight:700}
th button::after{content:" \2195";color:#8b8086}
#lista{font:15px/1.5 Arial,sans-serif;padding-left:20px}
.aviso{background:#fff;border-left:4px solid var(--N);padding:10px 14px;font:15px/1.5 Arial,sans-serif;margin:12px 0}
.destaque{background:#fff;border-left:4px solid var(--ouro);padding:10px 14px;font:16px/1.5 Arial,sans-serif;margin:12px 0}
#mapa{display:block;width:100%;max-width:860px;height:auto;margin:0 auto;background:#fff;border:1px solid #d8cfc2}
#mapa path{stroke:#fff;stroke-width:.5;cursor:pointer}
#mapa path.sobre{stroke:#1F1820;stroke-width:1.4}
#mapa path.sel{fill:var(--L)}
#mapa circle{pointer-events:none}
#info{min-height:4.5em;text-align:center}
footer{background:var(--faixa);color:#fff;padding:24px 16px;font:14px/1.6 Arial,sans-serif}footer a{color:#fff}
</style>
</head>
<body>
<header><div><small>GRUPO</small><br><a href="/">nomos</a><br><nav><a href="/">Início</a><a href="/blog/">Blog</a><a href="/calendario-tjmg.html">Calendário TJMG</a></nav></div></header>
<main>
<h1>Calendário TJMG: dias úteis por comarca</h1>
<p class="meta">Fonte dos feriados e suspensões: página <a href="__URL__" target="_blank" rel="noopener">Feriados Locais, do Guia Judiciário do TJMG</a>, e só ela. <span id="lido"></span></p>
<div class="campos"><div><label for="ano">Ano</label><select id="ano"></select></div></div>
<div id="alerta-ano"></div>

<h2>Visão de todo o Estado em <span class="v-ano"></span></h2>
<div class="cartoes" id="estado"></div>
<p class="nota" id="faixa"></p>

<h2>Mapa das comarcas</h2>
<p class="nota">Passe o ponteiro sobre o mapa para ver o município, a comarca e as regiões, e clique para abrir o calendário da comarca. Quem navega pelo teclado usa a lista de comarcas logo abaixo, que traz os mesmos dados.</p>
<div class="campos"><div><label for="pintar">Colorir o mapa por</label><select id="pintar">
<option value="u">Dias úteis da comarca no ano</option><option value="0">Mesorregião (IBGE)</option><option value="1">Microrregião (IBGE)</option>
<option value="2">Região geográfica intermediária (IBGE)</option><option value="3">Região geográfica imediata (IBGE)</option></select></div></div>
<div class="legenda" id="escala" aria-hidden="true"></div>
<div class="legenda" aria-hidden="true"><span class="bola">Cidade-polo de região intermediária</span><span class="bolinha">Cidade-polo de região imediata</span><span class="forum">Sede de comarca, onde fica o fórum do TJMG</span></div>
<svg id="mapa" role="img" aria-label="Mapa de Minas Gerais dividido por município e comarca"></svg>
<p class="nota" id="info" aria-live="polite">Nenhum município apontado.</p>

<h2 id="t-cal">Calendário por comarca em <span class="v-ano"></span></h2>
<label for="comarca">Comarca</label>
<select id="comarca"></select>
<div class="cartoes" id="resumo" aria-live="polite"></div>
<div id="alerta"></div>
<div id="abrangencia"></div>
<div class="legenda" aria-hidden="true"><span>Dia útil</span><span class="l-S">Dia útil com prazo processual suspenso</span><span style="--c:var(--fds)">Sábado ou domingo</span><span style="--c:var(--N)">Feriado nacional</span><span style="--c:var(--E)">Feriado estadual (Justiça mineira)</span><span style="--c:var(--R)">Recesso forense (estadual)</span><span style="--c:var(--P)">Ponto facultativo ou suspensão por portaria do TJMG</span><span style="--c:var(--L)">Feriado municipal da comarca</span></div>
<div class="meses" id="meses"></div>
<h3>Dias não úteis além de sábados e domingos</h3>
<ul id="lista"></ul>

<h2>Todas as comarcas em <span class="v-ano"></span></h2>
<label for="filtro">Filtrar pelo nome</label>
<input id="filtro" type="search" autocomplete="off">
<p class="nota">Clique no título da coluna para ordenar, e no nome da comarca para ver o calendário dela. <a id="csv" href="#" download>Baixar a tabela deste ano (CSV)</a>.</p>
<div class="rolagem"><table class="dados" id="tabela"><thead><tr>
<th><button type="button" data-k="0">Comarca</button></th><th><button type="button" data-k="1">Municípios</button></th>
<th><button type="button" data-k="2">População</button></th><th><button type="button" data-k="3">Dias corridos</button></th>
<th><button type="button" data-k="4">Dias úteis</button></th><th><button type="button" data-k="5">Dias não úteis</button></th>
<th><button type="button" data-k="6">Feriados municipais em dia de semana</button></th></tr></thead><tbody></tbody></table></div>

<h2>Como a conta é feita</h2>
<p class="nota">Dia útil, aqui, é o dia de segunda a sexta que a página do TJMG não registra como feriado, recesso, ponto facultativo ou suspensão de expediente. Todo o resto é dia não útil. Dias corridos são todos os dias do ano, 365 ou 366. Feriado que cai em sábado ou domingo não reduz a contagem, porque o dia já não era útil.</p>
<p class="nota"><strong>Ponto facultativo também conta como dia não útil.</strong> O Código de Processo Civil, no art. 216, trata como feriado, para efeito forense, além dos declarados em lei, os sábados, os domingos e os dias em que não haja expediente forense. No TJMG, os pontos facultativos e as pontes de feriado são fixados por portaria e aparecem na fonte como suspensão de expediente, com o número da portaria; o Dia do Funcionário Público entra do mesmo modo. Nesta página eles têm cor própria e contagem separada: em <span class="v-ano"></span>, <span id="n-portaria"></span>.</p>
<p class="nota"><strong>Nacional, estadual e municipal.</strong> <em>Feriado nacional</em> é o que a lei federal declara: 1º de janeiro, 21 de abril, 1º de maio, 7 de setembro, 2 de novembro, 15 de novembro e 25 de dezembro (Lei 662/1949, art. 1º, na redação da Lei 10.607/2002), 12 de outubro (Lei 6.802/1980) e 20 de novembro (Lei 14.759/2023). <em>Feriado estadual</em>, aqui, é o feriado forense da Justiça mineira, que o TJMG fundamenta na Lei Complementar estadual 59/2001 e na Resolução 458/2004: segunda e terça de Carnaval, Quarta-feira de Cinzas, quarta, quinta e sexta da Semana Santa e o Dia da Justiça, em 8 de dezembro. O <em>recesso forense</em>, de 20 de dezembro a 6 de janeiro, também é estadual (LC 59/2001, art. 313). <em>Ponto facultativo ou suspensão por portaria</em> é o que o Tribunal fixa ano a ano. <em>Feriado municipal</em> é o que vale só na comarca: aniversário da cidade, padroeiro e demais dias de guarda declarados em lei do município.</p>
<p class="nota"><strong>Corpus Christi não é feriado nacional.</strong> Ele não está entre as datas que a lei federal declara. A Lei 9.093/1995, art. 2º, diz que os feriados religiosos são os dias de guarda declarados em lei municipal, até quatro por município. Por isso o TJMG registra Corpus Christi comarca por comarca, junto dos feriados municipais, e não na lista que vale para todo o Estado. <span id="nota-cc"></span></p>
<p class="nota"><strong>Anos futuros ficam incompletos por um tempo.</strong> O TJMG registra os feriados municipais e as portarias aos poucos. Enquanto o registro de um ano não termina, a contagem de dias úteis daquele ano fica maior do que será no fim. A página avisa, no alto, quando o ano escolhido está nessa situação, e os dados são lidos de novo no TJMG toda semana.</p>
<p class="nota"><strong>Suspensão dos prazos processuais.</strong> O Código de Processo Civil, no art. 220, suspende o curso do prazo processual nos dias de 20 de dezembro a 20 de janeiro, inclusive: são 32 dias corridos, 12 em dezembro e 20 em janeiro. Suspensão de prazo não é suspensão de expediente. De 20 de dezembro a 6 de janeiro o fórum está em recesso, e esses dias já são não úteis. De 7 a 20 de janeiro o fórum funciona e atende, mas o prazo não corre: esses dias aparecem hachurados no calendário, continuam contados como dias úteis de expediente e são descontados na linha "dias úteis com prazo correndo". A regra é a do processo civil; a contagem de um prazo concreto segue a lei do processo e a intimação recebida.</p>
<p class="nota"><strong>Horas de atendimento.</strong> A conta de horas multiplica os dias úteis pelo horário de atendimento ao público nos fóruns, das __H1__h às __H2__h, seis horas por dia. É uma medida de abrangência, e não inclui plantão, atendimento eletrônico nem expediente interno.</p>
<p class="nota"><strong>Mapa e comarcas:</strong> a composição de cada comarca vem da consulta "Municípios e Distritos Integrantes" do <a href="https://www8.tjmg.jus.br/servicos/gj/guia/primeira_instancia/pesquisa.do" target="_blank" rel="noopener">Guia Judiciário do TJMG</a>, feita comarca por comarca<span id="lido-mapa"></span>: cada um dos 853 municípios em uma só comarca. O mapa mostra a divisão atual, inclusive nos anos anteriores. Os limites municipais são da malha do IBGE, em traçado simplificado, que serve para localizar e não para medir divisa.</p>
<p class="nota"><strong>Fórum:</strong> o ponto dourado marca o município-sede de cada comarca, que é onde o Guia Judiciário do TJMG registra o fórum. Os demais municípios da comarca são atendidos por esse fórum.</p>
<p class="nota"><strong>Regiões e cidades-polo:</strong> mesorregião e microrregião são a divisão regional do IBGE de 1989; regiões geográficas intermediárias e imediatas são a divisão de 2017, que as substituiu. O IBGE não tem divisão chamada macrorregião dentro do Estado: o nível mais amplo é a mesorregião, na divisão antiga, e a região intermediária, na atual. O IBGE dá a cada região intermediária e imediata o nome do município que a polariza, e é esse município que aparece aqui como cidade-polo.</p>
<p class="nota"><strong>População:</strong> estimativas anuais da população residente do IBGE, por município, e o Censo Demográfico no ano de 2022. Quando o IBGE não tem número para o ano escolhido, a página usa o último anterior e diz qual foi.</p>
<p class="nota">O TJMG avisa que a página Feriados Locais não substitui as comunicações e publicações oficiais sobre plantões, suspensões de expediente e suspensões de prazos. Esta página também não.</p>
</main>
<footer><div>Grupo Nomos, Perícia Contábil · CNPJ 42.216.511/0001-95 · <a href="/politica-de-privacidade.html">Política de Privacidade</a> · <a href="/politica-de-cookies.html">Política de Cookies</a> · <a href="/termos-de-uso.html">Termos de Uso</a></div></footer>
<script>
(function () {
  "use strict";
  var REMOTO = "__REMOTO__", HORAS = __H2__ - __H1__, CAL = window.NOMOS_CAL = window.NOMOS_CAL || {}, origem = {};
  var MESES = ["Janeiro","Fevereiro","Março","Abril","Maio","Junho","Julho","Agosto","Setembro","Outubro","Novembro","Dezembro"];
  var SEM = ["domingo","segunda-feira","terça-feira","quarta-feira","quinta-feira","sexta-feira","sábado"];
  var NOMECAT = { N: "feriado nacional", E: "feriado estadual", R: "recesso forense", P: "ponto facultativo ou suspensão por portaria", L: "feriado municipal" };
  var NIVEL = ["Mesorregião", "Microrregião", "Região intermediária", "Região imediata"];
  var CORES = ["#8c6d31","#2f5d8a","#b5523b","#5b8c5a","#7a4a8c","#c9a227","#3d8b8b","#a05a7a","#6d4c41","#90a955","#4a6fa5","#d08c60","#555b6e","#c2b280"];
  var ANO, D, DIAS, porNome, min, max, porU, M, doComarca = {}, colPop, anoPop;
  function $(id) { return document.getElementById(id); }
  function k(m, d) { return (m < 9 ? "0" : "") + (m + 1) + "-" + (d < 10 ? "0" : "") + d; }
  function cartao(n, t) { return '<div class="cartao"><b>' + n + "</b>" + t + "</div>"; }
  function texto(s) { var e = document.createElement("span"); e.textContent = s; return e.innerHTML.replace(/"/g, "&quot;"); }
  function plural(n, um, varios) { return n + " " + (n === 1 ? um : varios); }
  function mil(n) { return n.toLocaleString("pt-BR"); }

  /* os dados vem primeiro do endereco atualizado toda semana; se ele falhar, da copia do proprio site */
  function carrega(u, ok, falha) { var s = document.createElement("script"); s.src = u; s.onload = ok; s.onerror = falha; document.head.appendChild(s); }
  function semDados() { $("alerta-ano").innerHTML = '<p class="aviso">Não foi possível carregar os dados agora. Tente de novo em instantes.</p>'; }
  /* a lista de anos e' pequena e vem sempre fresca; ela traz a versao dos dados, que entra no endereco dos demais */
  function buscar(nome, pronto, feito) {
    var v = window.NOMOS_ANOS ? "?v=" + window.NOMOS_ANOS.v : "?t=" + Date.now();
    function local() { carrega("/" + nome + v, function () { if (pronto()) feito("/"); else semDados(); }, semDados); }
    carrega(REMOTO + nome + v, function () { if (pronto()) feito(REMOTO); else local(); }, local);
  }

  /* CPC, art. 220: prazo processual suspenso de 20 de dezembro a 20 de janeiro, inclusive */
  function suspenso(c) { return c <= "01-20" || c >= "12-20"; }
  /* conta a partir dos feriados; serve para o calendario e para conferir a tabela calculada na geracao */
  function contar(loc) {
    var r = { uteis: 0, fds: 0, N: 0, E: 0, R: 0, P: 0, locais: 0, susp: 0, mes: [] };
    for (var m = 0; m < 12; m++) {
      var u = 0, n = new Date(ANO, m + 1, 0).getDate();
      for (var d = 1; d <= n; d++) {
        var w = new Date(ANO, m, d).getDay(), c = k(m, d);
        if (w === 0 || w === 6) r.fds++;
        else if (D.gerais[c]) r[D.gerais[c][0]]++;
        else if (loc[c]) r.locais++;
        else { r.uteis++; u++; if (suspenso(c)) r.susp++; }
      }
      r.mes.push([u, n]);
    }
    return r;
  }

  var mapa = $("mapa"), info = $("info"), sel = $("comarca"), selAno = $("ano"), pintar = $("pintar");
  function cor(u) {
    var t = max > min ? (u - min) / (max - min) : 1, a = [91, 58, 30], b = [243, 233, 210];
    return "rgb(" + a.map(function (v, j) { return Math.round(v + (b[j] - v) * t); }).join(",") + ")";
  }
  function pop(p) { return p[10][colPop]; }
  function popComarca(i) { return (doComarca[i] || []).reduce(function (s, p) { return s + pop(p); }, 0); }
  function fontePop() { return anoPop === 2022 ? "Censo 2022 do IBGE" : "estimativa do IBGE para " + anoPop; }
  function frase(nome) {
    var c = porNome[nome]; if (!c) return "comarca de " + nome + ": sem dados neste ano";
    return "comarca de " + nome + " em " + ANO + ": " + c[1] + " dias úteis, " + (DIAS - c[1]) + " não úteis, " + DIAS + " corridos";
  }
  function regioes(p) { return [3, 4, 5, 6].map(function (j, n) { return NIVEL[n].toLowerCase() + " de " + M.reg[n][p[j]]; }).join("; "); }
  function forum(p) { return p[11] ? " (sede da comarca, com fórum)" : ""; }
  function polo(p) { return p[7] === 2 ? " (cidade-polo de região intermediária)" : p[7] === 1 ? " (cidade-polo de região imediata)" : ""; }
  function falar(p) {
    info.textContent = p[1] + forum(p) + polo(p) + ", " + mil(pop(p)) + " habitantes (" + fontePop() + "). " + frase(M.c[p[0]]).replace(/^c/, "C") + ". " + regioes(p).replace(/^m/, "M") + ".";
  }
  function marcar(i, classe, liga) {
    Array.prototype.forEach.call(mapa.querySelectorAll('path[data-c="' + i + '"]'), function (p) { p.classList.toggle(classe, liga); });
  }
  function desenhar() {
    M = window.NOMOS_MAPA;
    M.m.forEach(function (p) { (doComarca[p[0]] = doComarca[p[0]] || []).push(p); });
    mapa.setAttribute("viewBox", "0 0 1000 " + M.h);
    mapa.innerHTML = M.m.map(function (p, j) { return '<path d="' + p[2] + '" data-c="' + p[0] + '" data-j="' + j + '"><title></title></path>'; }).join("") +
      M.m.filter(function (p) { return p[7]; }).sort(function (a, b) { return a[7] - b[7]; }).map(function (p) {
        return p[7] === 2 ? '<circle cx="' + p[8] + '" cy="' + p[9] + '" r="6" fill="#1F1820" stroke="#fff" stroke-width="2"/>'
          : '<circle cx="' + p[8] + '" cy="' + p[9] + '" r="3.4" fill="#fff" stroke="#1F1820" stroke-width="1.5"/>';
      }).join("") +
      M.m.filter(function (p) { return p[11]; }).map(function (p) {
        return '<circle cx="' + p[8] + '" cy="' + p[9] + '" r="2" fill="#e0a100" stroke="#5b3a00" stroke-width=".6"/>';
      }).join("");
    $("lido-mapa").textContent = " em " + M.lido;
    mapa.addEventListener("mouseover", function (e) {
      var p = e.target.closest("path"); if (!p) return;
      marcar(p.dataset.c, "sobre", true); falar(M.m[p.dataset.j]);
    });
    mapa.addEventListener("mouseout", function (e) { var p = e.target.closest("path"); if (p) marcar(p.dataset.c, "sobre", false); });
    mapa.addEventListener("click", function (e) {
      var p = e.target.closest("path"); if (!p) return;
      sel.value = M.c[p.dataset.c]; mostrar(); falar(M.m[p.dataset.j]);
      $("t-cal").scrollIntoView({ behavior: "smooth" });
    });
  }
  function colorir() {
    var modo = pintar.value, n = +modo;
    Array.prototype.forEach.call(mapa.querySelectorAll("path"), function (el) {
      var p = M.m[el.dataset.j], c = porNome[M.c[p[0]]];
      el.setAttribute("fill", modo === "u" ? (c ? cor(c[1]) : "#ccc") : CORES[p[3 + n] % CORES.length]);
      el.firstChild.textContent = p[1] + ", " + frase(M.c[p[0]]);
    });
    if (modo === "u") {
      $("escala").innerHTML = Object.keys(porU).sort().map(function (u) { return '<span style="--c:' + cor(+u) + '">' + u + " úteis (" + porU[u] + ")</span>"; }).join("");
    } else if (M.reg[n].length <= 14) {
      $("escala").innerHTML = M.reg[n].map(function (r, j) { return '<span style="--c:' + CORES[j % CORES.length] + '">' + texto(r) + "</span>"; }).join("");
    } else {
      $("escala").innerHTML = "<span>" + M.reg[n].length + " regiões, com cores que se repetem: o nome de cada uma aparece ao apontar o município</span>";
    }
  }

  function trocarAno() {
    var a = +selAno.value;
    if (CAL[a]) return render(a);
    buscar("calendario-tjmg-" + a + ".js", function () { return CAL[a]; }, function (o) { origem[a] = o; render(a); });
  }

  function render(a) {
    ANO = a; D = CAL[a]; DIAS = D.dias; porNome = {}; porU = {};
    D.comarcas.forEach(function (c) { porNome[c[0]] = c; porU[c[1]] = (porU[c[1]] || 0) + 1; });
    anoPop = M.pa.filter(function (x) { return x <= ANO; }).pop() || M.pa[0]; colPop = M.pa.indexOf(anoPop);
    var us = D.comarcas.map(function (c) { return c[1]; }), base = contar({});
    min = Math.min.apply(null, us); max = Math.max.apply(null, us);
    Array.prototype.forEach.call(document.querySelectorAll(".v-ano"), function (e) { e.textContent = ANO; });
    $("lido").textContent = "Dados de " + ANO + " lidos no TJMG em " + D.lido + ". O ano tem " + DIAS + " dias corridos em todas as comarcas.";
    $("csv").href = (origem[a] || "/") + "calendario-tjmg-" + ANO + ".csv";
    var av = "";
    if (D.nl === 0) av = "Para " + ANO + ", o TJMG ainda não registrou nenhum feriado municipal. Os números abaixo contam só os feriados estaduais e o recesso, e vão diminuir quando o registro for feito.";
    else if (D.cc) av = "O registro de " + ANO + " no TJMG ainda está incompleto: Corpus Christi (" + D.cc[0].slice(3) + "/" + D.cc[0].slice(0, 2) + "/" + ANO + ") aparece em " + D.cc[1] + " das " + D.comarcas.length + " comarcas, e " + (D.comarcas.length - D.nl) + " comarcas estão sem nenhum feriado municipal. A contagem vai diminuir quando o registro terminar.";
    if (base.P === 0) av += (av ? " " : "") + "Ainda não há ponto facultativo nem suspensão por portaria registrados para " + ANO + ".";
    $("alerta-ano").innerHTML = av ? '<p class="aviso">' + av + "</p>" : "";
    $("n-portaria").textContent = base.P ? "são " + plural(base.P, "dia", "dias") + " de semana nessa situação" : "a fonte ainda não registra nenhum";
    $("nota-cc").textContent = D.ncc ? "Em " + ANO + ", a fonte traz Corpus Christi em " + D.ncc + " das " + D.comarcas.length + " comarcas" +
      (D.semcc.length && D.semcc.length <= 15 ? "; não traz em " + D.semcc.join(", ") + "." : ".") : "Em " + ANO + ", a fonte ainda não traz Corpus Christi em nenhuma comarca.";
    var popMG = M.m.reduce(function (s, p) { return s + pop(p); }, 0);
    $("estado").innerHTML = cartao(DIAS, "dias corridos") + cartao(base.fds, "sábados e domingos") +
      cartao(base.N, "feriados nacionais em dia de semana") + cartao(base.E, "feriados estaduais em dia de semana") +
      cartao(base.R, "dias de recesso forense em dia de semana") +
      cartao(base.P, "pontos facultativos e suspensões por portaria") +
      cartao(base.uteis, "dias úteis antes dos feriados municipais") +
      cartao(base.susp, "desses, com prazo processual suspenso (CPC, art. 220)") + cartao(D.comarcas.length, "comarcas, em 853 municípios") +
      cartao(mil(popMG), "habitantes em Minas Gerais (" + fontePop() + ")");
    $("faixa").textContent = "Com os feriados municipais, as comarcas ficam entre " + min + " e " + max + " dias úteis (" + (DIAS - max) + " a " + (DIAS - min) +
      " não úteis), o que dá de " + mil(min * HORAS) + " a " + mil(max * HORAS) + " horas de atendimento ao público no ano. Distribuição: " +
      Object.keys(porU).sort().reverse().map(function (u) { return u + " dias úteis em " + plural(porU[u], "comarca", "comarcas"); }).join("; ") + ".";
    var antes = sel.value;
    sel.innerHTML = '<option value="">Todo o Estado (sem feriado municipal)</option>' +
      D.comarcas.map(function (c) { return '<option value="' + texto(c[0]) + '">' + texto(c[0]) + "</option>"; }).join("");
    if (porNome[antes]) sel.value = antes;
    colorir(); tabela(); mostrar();
    /* conferencia: a contagem do navegador tem que bater com a calculada na geracao */
    window.NOMOS_DIVERGENTES = D.comarcas.filter(function (c) { var r = contar(c[2]); return r.uteis !== c[1] || r.locais !== c[3] || r.susp !== c[4]; }).map(function (c) { return c[0]; });
    if (window.NOMOS_DIVERGENTES.length) console.error("contagem divergente", ANO, window.NOMOS_DIVERGENTES);
  }

  function mostrar() {
    var nome = sel.value, c = porNome[nome], loc = c ? c[2] : {}, r = contar(loc), i = M.c.indexOf(nome);
    Array.prototype.forEach.call(mapa.querySelectorAll("path.sel"), function (p) { p.classList.remove("sel"); });
    if (c) marcar(i, "sel", true);
    $("resumo").innerHTML = cartao(r.uteis, "dias úteis") + cartao(DIAS - r.uteis, "dias não úteis") + cartao(DIAS, "dias corridos") +
      cartao(r.locais, "feriados municipais em dia de semana") +
      cartao(r.susp, "dias úteis com prazo processual suspenso") + cartao(r.uteis - r.susp, "dias úteis com prazo correndo") + cartao(mil(r.uteis * HORAS), "horas de atendimento ao público (__H1__h às __H2__h)");
    $("alerta").innerHTML = (c && D.cc && !loc[D.cc[0]]) ? '<p class="aviso">Na data da leitura, o TJMG não registrava Corpus Christi para esta comarca em ' + ANO + ". O dia está contado como útil. Confira no TJMG antes de contar prazo.</p>" : "";
    var ab = "";
    if (c && doComarca[i]) {
      var ms = doComarca[i].slice().sort(function (a, b) { return pop(b) - pop(a); }), total = popComarca(i);
      ab = '<p class="destaque">Em ' + ANO + ", a comarca de " + texto(nome) + " abrange " + plural(ms.length, "município", "municípios") + " e " + mil(total) +
        " habitantes (" + fontePop() + "), com " + r.uteis + " dias úteis de expediente. Com atendimento ao público das __H1__h às __H2__h, são " +
        r.uteis + " × " + HORAS + " = " + mil(r.uteis * HORAS) + " horas de atendimento no ano.</p>" +
        '<h3>Municípios da comarca de ' + texto(nome) + '</h3><div class="rolagem"><table class="dados"><thead><tr><th>Município</th><th>População</th>' +
        NIVEL.map(function (n) { return '<th class="e">' + n + "</th>"; }).join("") + "</tr></thead><tbody>" +
        ms.map(function (p) {
          return "<tr><td>" + (p[11] ? "<strong>" + texto(p[1]) + "</strong> (sede, fórum)" : texto(p[1])) + (p[7] ? " <em>" + polo(p).trim() + "</em>" : "") + "</td><td>" + mil(pop(p)) + "</td>" +
            [3, 4, 5, 6].map(function (j, n) { return '<td class="e">' + texto(M.reg[n][p[j]]) + "</td>"; }).join("") + "</tr>";
        }).join("") + "</tbody><tfoot><tr><td>Total da comarca</td><td>" + mil(total) + '</td><td colspan="4" class="e">' + fontePop() + "</td></tr></tfoot></table></div>";
    }
    $("abrangencia").innerHTML = ab;
    var h = "", itens = [];
    for (var m = 0; m < 12; m++) {
      var n = new Date(ANO, m + 1, 0).getDate(), p = new Date(ANO, m, 1).getDay();
      h += '<div class="mes"><table><caption>' + MESES[m] + " <small>· " + r.mes[m][0] + " úteis de " + n + "</small></caption><thead><tr>" +
        ["D","S","T","Q","Q","S","S"].map(function (x, j) { return '<th scope="col" abbr="' + SEM[j] + '">' + x + "</th>"; }).join("") + "</tr></thead><tbody><tr>" +
        new Array(p + 1).join("<td></td>");
      for (var d = 1; d <= n; d++) {
        var w = (p + d - 1) % 7, ch = k(m, d), cl = "", t = "dia útil";
        if (w === 0 || w === 6) { cl = "fds"; t = SEM[w]; }
        else if (suspenso(ch)) { cl = "S"; t = "dia útil de expediente, com prazo processual suspenso (CPC, art. 220)"; }
        if (loc[ch]) { cl = "L"; t = loc[ch]; }
        if (D.gerais[ch]) { cl = D.gerais[ch][0]; t = D.gerais[ch][1] + (loc[ch] ? "; " + loc[ch] : ""); }
        if (cl && cl !== "fds" && cl !== "S") itens.push([d, m, w, t, cl]);
        if (w === 0 && d > 1) h += "</tr><tr>";
        h += "<td" + (cl ? ' class="' + cl + '"' : "") + ' title="' + texto(t) + '">' + d + "</td>";
      }
      h += "</tr></tbody></table></div>";
    }
    $("meses").innerHTML = h;
    $("lista").innerHTML = itens.map(function (x) {
      return "<li>" + (x[0] < 10 ? "0" : "") + x[0] + "/" + (x[1] < 9 ? "0" : "") + (x[1] + 1) + "/" + ANO + " (" + SEM[x[2]] + "): " + texto(x[3]) +
        " <em>(" + NOMECAT[x[4]] + ((x[2] === 0 || x[2] === 6) ? "; já não era dia útil" : "") + ")</em></li>";
    }).join("");
  }

  var ordem = 0, sentido = 1, corpo = $("tabela").tBodies[0];
  function semAcento(s) { return s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, ""); }
  function tabela() {
    var f = semAcento($("filtro").value);
    var linhas = D.comarcas.map(function (c) {
      var i = M.c.indexOf(c[0]);
      return [c[0], (doComarca[i] || []).length, popComarca(i), DIAS, c[1], DIAS - c[1], c[3]];
    }).filter(function (l) { return semAcento(l[0]).indexOf(f) >= 0; });
    linhas.sort(function (a, b) {
      var x = a[ordem], y = b[ordem];
      return sentido * (typeof x === "string" ? x.localeCompare(y, "pt-BR") : (x - y) || a[0].localeCompare(b[0], "pt-BR"));
    });
    corpo.innerHTML = linhas.map(function (l) {
      return '<tr><td><a href="#t-cal" data-n="' + texto(l[0]) + '">' + texto(l[0]) + "</a></td><td>" + l[1] + "</td><td>" + mil(l[2]) + "</td><td>" + l[3] + "</td><td>" + l[4] + "</td><td>" + l[5] + "</td><td>" + l[6] + "</td></tr>";
    }).join("");
  }
  $("filtro").addEventListener("input", function () { if (D) tabela(); });
  $("tabela").tHead.addEventListener("click", function (e) {
    var b = e.target.closest("button"); if (!b || !D) return;
    sentido = (ordem === +b.dataset.k) ? -sentido : 1; ordem = +b.dataset.k; tabela();
  });
  corpo.addEventListener("click", function (e) { var a = e.target.closest("a"); if (a) { sel.value = a.dataset.n; mostrar(); } });
  sel.addEventListener("change", mostrar);
  selAno.addEventListener("change", trocarAno);
  pintar.addEventListener("change", function () { if (D) colorir(); });

  buscar("calendario-tjmg-anos.js", function () { return window.NOMOS_ANOS; }, function () {
    buscar("calendario-tjmg-mapa.js", function () { return window.NOMOS_MAPA; }, function () {
      desenhar();
      var anos = window.NOMOS_ANOS.anos, atual = new Date().getFullYear();
      selAno.innerHTML = anos.map(function (a) { return "<option>" + a + "</option>"; }).join("");
      selAno.value = anos.indexOf(atual) >= 0 ? atual : anos[anos.length - 1];
      trocarAno();
    });
  });
})();
</script>
<script src="/site-nomos.js" defer></script>
</body>
</html>
"""

CABECALHO_CSV = ["Comarca", "Ano", "Municipios da comarca", "Populacao (IBGE)", "Ano de referencia da populacao",
                 "Dias corridos", "Dias uteis", "Dias nao uteis", "Sabados e domingos",
                 "Feriados nacionais em dia de semana", "Feriados estaduais em dia de semana", "Recesso forense em dia de semana",
                 "Pontos facultativos e suspensoes por portaria em dia de semana",
                 "Feriados municipais em dia de semana", "Dias uteis com prazo processual suspenso (CPC, art. 220)",
                 "Dias uteis com prazo processual correndo", "Horas de atendimento ao publico (12h as 18h)"]
ATENDIMENTO = (12, 18)  # horario de atendimento ao publico nos foruns, informado pelo usuario


def main():
    caminhos = sorted(glob.glob(os.path.join(AQUI, "paginas", "[0-9][0-9][0-9][0-9].html")))
    if not caminhos:
        print("FALHA: nenhuma pagina em paginas/; rode baixar.py")
        return 1
    lidos = {int(os.path.basename(c)[:4]): ler(c, int(os.path.basename(c)[:4])) for c in caminhos}
    comarcas_atuais = lidos[max(lidos)][0]  # a lista de comarcas do seletor e' a atual em todos os anos
    desenho = mapa(comarcas_atuais)
    lido_p = os.path.join(AQUI, "paginas", "lido.json")
    lidos_em = json.load(io.open(lido_p, encoding="utf-8")) if os.path.exists(lido_p) else {}
    arquivos, erros, resumo = {}, [], []
    for cam in caminhos:
        ano = int(os.path.basename(cam)[:4])
        comarcas, gerais, locais = lidos[ano]
        linhas, cat = calcular(ano, comarcas, gerais, locais)
        erros += conferir(ano, comarcas, gerais, locais, linhas)
        if comarcas != comarcas_atuais:
            erros.append("%d: a lista de comarcas difere da do ano mais recente" % ano)
        # Corpus Christi e' registrado comarca por comarca: registro parcial denuncia ano ainda em cadastro
        datas_cc = [k for loc in locais.values() for k, v in loc.items() if "corpus christi" in " ".join(v).lower()]
        cc = None
        if datas_cc:
            moda = max(set(datas_cc), key=datas_cc.count)
            if datas_cc.count(moda) < 0.9 * len(comarcas):
                cc = [moda, datas_cc.count(moda)]
        lido = lidos_em.get(str(ano)) or datetime.date.fromtimestamp(os.path.getmtime(cam)).strftime("%d/%m/%Y")
        com_cc = {c for c, loc in locais.items() if any("corpus christi" in " ".join(v).lower() for v in loc.values())}
        dados = {"ano": ano, "lido": lido, "dias": linhas[0]["corridos"], "nl": len(locais), "cc": cc,
                 "ncc": len(com_cc), "semcc": [c for c in comarcas if c not in com_cc] if com_cc and not cc else [],
                 "gerais": {k: [cat[k], "; ".join(v)] for k, v in sorted(gerais.items())},
                 "comarcas": [[l["comarca"], l["uteis"],
                               {k: "; ".join(v) for k, v in sorted(locais.get(l["comarca"], {}).items())},
                               l["locais"], l["susp"]] for l in linhas]}
        arquivos["calendario-tjmg-%d.js" % ano] = (
            "window.NOMOS_CAL=window.NOMOS_CAL||{};NOMOS_CAL[%d]=%s;\n"
            % (ano, json.dumps(dados, ensure_ascii=False, separators=(",", ":"))))
        ref = coluna_pop(ano, desenho["pa"])
        col = desenho["pa"].index(ref)
        saida = io.StringIO()
        w = csv.writer(saida, delimiter=";", lineterminator="\n")
        w.writerow(CABECALHO_CSV)
        for i, l in enumerate(linhas):
            muns = [m for m in desenho["m"] if m[0] == i]
            w.writerow([l["comarca"], ano, len(muns), sum(m[10][col] for m in muns), ref, l["corridos"], l["uteis"],
                        l["nao_uteis"], l["fds"], l["N"], l["E"], l["R"], l["P"], l["locais"], l["susp"], l["uteis"] - l["susp"],
                        l["uteis"] * (ATENDIMENTO[1] - ATENDIMENTO[0])])
        arquivos["calendario-tjmg-%d.csv" % ano] = "﻿" + saida.getvalue()
        us = [l["uteis"] for l in linhas]
        resumo.append("%d | %d dias | fds %d | nacionais %d | estaduais %d | recesso %d | portaria %d | uteis sem municipal %d | "
                      "por comarca %d a %d | comarcas com feriado municipal %d de %d | Corpus Christi em %d | populacao de %d%s"
                      % (ano, linhas[0]["corridos"], linhas[0]["fds"], linhas[0]["N"], linhas[0]["E"], linhas[0]["R"], linhas[0]["P"],
                         linhas[0]["corridos"] - linhas[0]["fds"] - linhas[0]["N"] - linhas[0]["E"] - linhas[0]["R"]
                         - linhas[0]["P"],
                         min(us), max(us), len(locais), len(comarcas), len(com_cc), ref,
                         " | Corpus Christi PARCIAL: %d" % cc[1] if cc else ""))
    if erros:
        print("FALHA na conferencia, nada foi gravado:")
        for e in erros:
            print("  ", e)
        return 1

    arquivos["calendario-tjmg-mapa.js"] = ("window.NOMOS_MAPA=%s;\n"
                                           % json.dumps(desenho, ensure_ascii=False, separators=(",", ":")))
    # versao = resumo de todos os dados; muda o endereco dos arquivos e o navegador busca de novo
    versao = hashlib.sha256("".join(arquivos[n] for n in sorted(arquivos)).encode("utf-8")).hexdigest()
    arquivos["calendario-tjmg-anos.js"] = "window.NOMOS_ANOS=%s;\n" % json.dumps({"anos": sorted(lidos), "v": versao})
    pagina = (PAGINA.replace("__URL__", URL).replace("__REMOTO__", REMOTO)
              .replace("__H1__", str(ATENDIMENTO[0])).replace("__H2__", str(ATENDIMENTO[1])))
    for nome, txt in list(arquivos.items()) + [("pagina", pagina)]:
        if chr(0x2014) in txt:
            print("FALHA: travessao em", nome)
            return 1

    destinos = [DOCS] + ([SITE] if os.path.isdir(SITE) else [])
    for pasta in destinos:
        for nome, txt in arquivos.items():
            gravar(os.path.join(pasta, nome), txt)
    gravar(os.path.join(DOCS, "index.html"),
           '<!doctype html><meta charset="utf-8"><title>Calendário TJMG, dados</title>'
           '<meta http-equiv="refresh" content="0;url=https://gruponomos.com/calendario-tjmg.html">'
           '<p>Dados do <a href="https://gruponomos.com/calendario-tjmg.html">Calendário TJMG, do Grupo Nomos</a>.</p>\n')
    if os.path.isdir(SITE):
        gravar(os.path.join(SITE, "calendario-tjmg.html"), pagina)
        sm_p = os.path.join(SITE, "sitemap.xml")
        sm = io.open(sm_p, encoding="utf-8").read()
        loc = "https://gruponomos.com/calendario-tjmg.html"
        sm = re.sub(r"  <url><loc>https://gruponomos\.com/calendario-tjmg-2027\.html</loc>.*?</url>\n", "", sm)
        if loc not in sm:
            sm = sm.replace("</urlset>", "  <url><loc>%s</loc><lastmod>%s</lastmod></url>\n</urlset>"
                            % (loc, datetime.date.today().isoformat()))
        gravar(sm_p, sm)
    gravar(os.path.join(AQUI, "RESUMO.txt"), "\n".join(resumo) + "\n")
    print("\n".join(resumo))
    print("populacao: colunas do IBGE %s | regioes: %s" % (desenho["pa"], [len(x) for x in desenho["reg"]]))
    print("gravado em:", ", ".join(destinos))
    return 0


if __name__ == "__main__":
    sys.exit(main())
