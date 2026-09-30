# Calendário TJMG: dias úteis por comarca

Dados da página [Calendário TJMG](https://gruponomos.com/calendario-tjmg.html), do Grupo Nomos.

Toda segunda-feira, a rotina deste repositório lê de novo as fontes oficiais, refaz a conta e publica os dados em `docs/`:

- **TJMG, Guia Judiciário, Feriados Locais**, todos os anos que o seletor da página oferece: <https://www8.tjmg.jus.br/servicos/gj/calendario/>
- **TJMG, Guia Judiciário, Municípios e Distritos Integrantes** de cada comarca: <https://www8.tjmg.jus.br/servicos/gj/guia/primeira_instancia/pesquisa.do>
- **IBGE**: malha e divisão regional dos 853 municípios de Minas Gerais, estimativas anuais de população e Censo 2022.

Dia útil é o dia de segunda a sexta que o TJMG não registra como feriado, recesso, ponto facultativo ou suspensão de expediente (CPC, art. 216). A contagem é feita duas vezes por caminhos diferentes em `gerar.py` e nada é gravado se elas divergirem.

O TJMG avisa que a página Feriados Locais não substitui as comunicações e publicações oficiais sobre plantões, suspensões de expediente e suspensões de prazos. Estes dados também não.

| Arquivo | O que faz |
|---|---|
| `baixar.py` | baixa as páginas do TJMG e a população do IBGE |
| `coletar_guia.py` | consulta a composição das 298 comarcas |
| `gerar.py` | confere, calcula e grava `docs/` |
