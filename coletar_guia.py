# -*- coding: utf-8 -*-
"""Coleta, no Guia Judiciario do TJMG (consulta ao vivo), os municipios e distritos
integrantes de cada comarca do calendario.

Fonte: https://www8.tjmg.jus.br/servicos/gj/guia/primeira_instancia/pesquisa.do
       (consulta.do, opcao 3, "Municipios e Distritos Integrantes")

Uma chamada por comarca, em sequencia, com pausa. Resumivel: o trecho de resultado de cada
comarca fica em guia-html/<codigo>.html e nao e' baixado de novo. Grava guia-comarcas.json.
Saida: 0 todas as comarcas lidas, 1 falha real (alguma comarca sem resultado), 75 fonte recusou (429).
"""
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

import glob

import gerar
from gerar import norm

AQUI = os.path.dirname(os.path.abspath(__file__))
PASTA = os.path.join(AQUI, "guia-html")
BASE = "https://www8.tjmg.jus.br/servicos/gj/guia/primeira_instancia/consulta.do"
# o calendario grafa Brasopolis e Jabuticatubas; o Guia, Brazopolis e Jaboticatubas
GRAFIA = {"brasopolis": "brazopolis", "jabuticatubas": "jaboticatubas"}
TENTATIVAS = 3


class Recusou(Exception):
    pass


def baixar(cod):
    u = (BASE + "?codigoMunp=%s&codigoComposto=MG_%s&opcConsulta=3&paginaFlag=&pagina=0"
         "&paginaForum=1&paginaJuizado=1&pesquisa=Pesquisar" % (cod, cod))
    ultimo = None
    for n in range(TENTATIVAS):
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (coletor Grupo Nomos)"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("latin-1")
        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise Recusou("HTTP 429, Retry-After=%s" % e.headers.get("Retry-After"))
            ultimo = e
        except Exception as e:  # familia inteira do transporte (URLError, IncompleteRead, reset, timeout)
            ultimo = e
        time.sleep(5 * (n + 1))
    raise OSError("sem resposta apos %d tentativas: %r" % (TENTATIVAS, ultimo))


def resultado(h):
    i = h.find("Resultado da Busca")
    if i < 0:
        return ""
    j = h.find("</table>", i)
    return h[i:j]


def ler_resultado(trecho):
    """-> (sede, [municipios], [distritos])"""
    sede, muns, dist = None, [], []
    for m in re.finditer(r'<td width="50%" colspan="2" nowrap>(.*?)</td>|<td width="25%" nowrap>(.*?)</td>', trecho, re.S):
        if m.group(1) is not None:
            nome = gerar.limpar(m.group(1))
            if nome.endswith("(Comarca)"):
                nome = nome[:-len("(Comarca)")].strip()
                sede = nome
            muns.append(nome)
        else:
            dist.append(gerar.limpar(m.group(2)))
    return sede, muns, dist


def main():
    os.makedirs(PASTA, exist_ok=True)
    ultima = sorted(glob.glob(os.path.join(AQUI, "paginas", "[0-9][0-9][0-9][0-9].html")))[-1]
    comarcas, _, _ = gerar.ler(ultima, int(os.path.basename(ultima).split(".")[0]))
    t = io.open(os.path.join(AQUI, "guia-pesquisa.html"), encoding="latin-1").read()
    sel = re.search(r'<select name="codigoComposto".*?</select>', t, re.S).group(0)
    codigos = {}
    for v, r in re.findall(r'<option value="MG_(\d+)"[^>]*>(.*?)</option>', sel, re.S):
        codigos.setdefault(norm(gerar.limpar(r)), []).append(v)

    saida, falhas = {}, []
    for n, c in enumerate(comarcas, 1):
        chave = GRAFIA.get(norm(c), norm(c))
        achou = False
        for cod in codigos.get(chave, []):
            arq = os.path.join(PASTA, cod + ".html")
            if os.path.exists(arq):
                trecho = io.open(arq, encoding="utf-8").read()
            else:
                try:
                    trecho = resultado(baixar(cod))
                except Recusou as e:
                    print("NAO CONCLUIU: a fonte recusou (%s) na comarca %d de %d" % (e, n, len(comarcas)))
                    return 75
                except OSError as e:
                    falhas.append((c, str(e)))
                    continue
                with io.open(arq + ".tmp", "w", encoding="utf-8") as f:
                    f.write(trecho)
                os.replace(arq + ".tmp", arq)
                time.sleep(0.4)
            sede, muns, dist = ler_resultado(trecho)
            if sede and norm(sede) == chave:
                saida[c] = {"codigo": cod, "municipios": muns, "distritos": dist}
                achou = True
                break
        if not achou and not any(f[0] == c for f in falhas):
            falhas.append((c, "nenhum codigo devolveu a comarca como sede: %s" % codigos.get(chave)))
        if n % 25 == 0 or n == len(comarcas):
            print("%d de %d comarcas (%d%%), falhas %d" % (n, len(comarcas), 100 * n // len(comarcas), len(falhas)), flush=True)

    for c, e in falhas:
        print("FALHA REAL:", c, "|", e)
    if falhas:  # coleta incompleta nao sobrescreve a boa que ja' esta' no disco
        return 1
    with io.open(os.path.join(AQUI, "guia-comarcas.json.tmp"), "w", encoding="utf-8") as f:
        json.dump({"fonte": BASE, "coletado_em": time.strftime("%d/%m/%Y %H:%M"), "comarcas": saida,
                   "falhas": falhas}, f, ensure_ascii=False, indent=1)
    os.replace(os.path.join(AQUI, "guia-comarcas.json.tmp"), os.path.join(AQUI, "guia-comarcas.json"))
    print("comarcas lidas: %d de %d | municipios listados: %d" % (
        len(saida), len(comarcas), sum(len(v["municipios"]) for v in saida.values())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
