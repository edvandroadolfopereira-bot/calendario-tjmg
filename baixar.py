# -*- coding: utf-8 -*-
"""Baixa do TJMG a pagina "Feriados Locais" de TODOS os anos que o proprio seletor oferece,
e a pagina de pesquisa do Guia Judiciario (codigos das localidades).

Fonte: https://www8.tjmg.jus.br/servicos/gj/calendario/
Grava paginas/AAAA.html (bytes como vieram, ISO-8859-1) so' quando a pagina passa na conferencia
minima; pagina ruim nao sobrescreve a boa que ja' esta' no disco.
Saida: 0 todos os anos baixados, 1 falha real em algum ano, 75 a fonte recusou (429).
"""
import datetime
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
PAGINAS = os.path.join(AQUI, "paginas")
URL = ("https://www8.tjmg.jus.br/servicos/gj/calendario/index.jsp?tipoFeriado=todos"
       "&comarca=null&mes=null&ano=%d&btn_pesquisar=Pesquisar")
GUIA = "https://www8.tjmg.jus.br/servicos/gj/guia/primeira_instancia/pesquisa.do"
# populacao por municipio de MG: estimativas anuais (agregado 6579) e Censo 2022 (agregado 4714)
IBGE = {"ibge-populacao-estimada.json": "https://servicodados.ibge.gov.br/api/v3/agregados/6579/periodos/all/variaveis/9324?localidades=N6[N3[31]]",
        "ibge-populacao-censo-2022.json": "https://servicodados.ibge.gov.br/api/v3/agregados/4714/periodos/2022/variaveis/93?localidades=N6[N3[31]]"}
TENTATIVAS = 3
MAX_ANOS = 60  # teto do laco: o seletor tem 13 anos em 30/09/2026


class Recusou(Exception):
    pass


def baixar(u):
    ultimo = None
    for n in range(TENTATIVAS):
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (coletor Grupo Nomos)"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise Recusou("HTTP 429, Retry-After=%s" % e.headers.get("Retry-After"))
            ultimo = e
        except Exception as e:  # familia inteira do transporte
            ultimo = e
        time.sleep(5 * (n + 1))
    raise OSError("sem resposta apos %d tentativas: %r" % (TENTATIVAS, ultimo))


def gravar(caminho, dados):
    with open(caminho + ".tmp", "wb") as f:
        f.write(dados)
    os.replace(caminho + ".tmp", caminho)


def boa(dados, ano):
    """Conferencia minima: a pagina tem o seletor de comarcas, datas do ano pedido e o Natal."""
    t = dados.decode("latin-1")
    return ('<select name="comarca"' in t and len(re.findall(r"<b>\d\d/\d\d/%d</b>" % ano, t)) >= 20
            and "25/12/%d" % ano in t)


def main():
    os.makedirs(PAGINAS, exist_ok=True)
    try:
        primeira = baixar(URL % datetime.date.today().year)
        sel = re.search(r'<select name="ano".*?</select>', primeira.decode("latin-1"), re.S)
        anos = sorted({int(a) for a in re.findall(r'<option[^>]*value="(\d{4})"', sel.group(0))}) if sel else []
        if not anos:
            print("FALHA REAL: a pagina do TJMG veio sem o seletor de anos")
            return 1
        falhas = []
        lido_p = os.path.join(PAGINAS, "lido.json")
        lido = json.load(open(lido_p, encoding="utf-8")) if os.path.exists(lido_p) else {}
        hoje = datetime.date.today().strftime("%d/%m/%Y")
        for ano in anos[:MAX_ANOS]:
            try:
                dados = baixar(URL % ano)
            except OSError as e:
                falhas.append((ano, str(e)))
                continue
            if boa(dados, ano):
                gravar(os.path.join(PAGINAS, "%d.html" % ano), dados)
                lido[str(ano)] = hoje
                print("%d: %d bytes" % (ano, len(dados)), flush=True)
            else:
                falhas.append((ano, "pagina sem seletor de comarcas, sem datas do ano ou sem o Natal"))
            time.sleep(0.5)
        gravar(lido_p, json.dumps(lido, indent=1, sort_keys=True).encode("utf-8"))
        for nome, u in IBGE.items():
            try:
                d = baixar(u)
                if len(json.loads(d.decode("utf-8"))[0]["resultados"][0]["series"]) == 853:
                    gravar(os.path.join(AQUI, nome), d)
                else:
                    falhas.append((nome, "o IBGE nao devolveu os 853 municipios"))
            except (OSError, ValueError, KeyError, IndexError) as e:
                falhas.append((nome, str(e)))
        try:
            g = baixar(GUIA)
            if b'name="codigoComposto"' in g:
                gravar(os.path.join(AQUI, "guia-pesquisa.html"), g)
            else:
                falhas.append(("guia", "pagina de pesquisa sem a lista de localidades"))
        except OSError as e:
            falhas.append(("guia", str(e)))
    except Recusou as e:
        print("NAO CONCLUIU: a fonte recusou (%s)" % e)
        return 75
    except OSError as e:
        print("FALHA REAL: %s" % e)
        return 1
    for a, e in falhas:
        print("FALHA REAL:", a, "|", e)
    print("anos no seletor: %s | baixados: %d" % (anos, len(anos) - sum(1 for a, _ in falhas if isinstance(a, int))))
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
