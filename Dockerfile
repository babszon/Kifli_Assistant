# Kifli asszisztens - szerveren futtatva (Synology NAS, VPS, bármi)
#
# A hangot a böngésző veszi, nem a szerver. Ide csak a logika kell:
# Python a vezérléshez, Node.js a Kifli kapcsolathoz.

FROM python:3.12-slim

# A rohlik-mcp Node.js-t igényel, az npx hívja meg futásidőben
RUN apt-get update \
 && apt-get install -y --no-install-recommends nodejs npm ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Az MCP szervert előre letöltjük, hogy az első indítás ne legyen lassú
RUN npm install -g @tomaspavlin/rohlik-mcp \
 && npm cache clean --force

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./
COPY webui/ ./webui/
COPY normalizalo_prompt.md ./

# A .env és az adatbázis kívülről csatolva, hogy frissítésnél megmaradjon
VOLUME ["/app/adat"]
ENV KIFLI_DB=/app/adat/kifli.db

EXPOSE 8420 8421

# Nem rootként fut. A felhasználó azonosítóját a docker-compose adja
# meg (user: "1026:100"), mert NAS-onként eltér - ha ez nem egyezik az
# adat/ mappa tulajdonosával, az adatbázis írásvédett lenne.
RUN chmod -R a+rX /app

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s \
  CMD python3 -c "import urllib.request; \
      urllib.request.urlopen('http://127.0.0.1:8420/beallitas.json', timeout=5)" \
      || exit 1

CMD ["python3", "gui.py", "--port", "8420", "--cim", "0.0.0.0", \
     "--nyitas-nelkul", "--db", "/app/adat/kifli.db"]
