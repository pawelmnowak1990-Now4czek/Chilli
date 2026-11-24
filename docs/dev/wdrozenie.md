# Wdrożenie na VPS (<server>)

Jednorazowe przygotowanie serwera i pierwsze uruchomienie Chilli. Kolejność ma znaczenie.
Drugiego pipeline'u (docker compose z MariaDB) ani istniejących stron nginx nie ruszamy.

Stan: przewodnik napisany bez dostępu do serwera. nginx i docker compose nie były testowane
na żywo (na Macu nie ma ani Dockera, ani nginx). Każdy krok ma polecenie sprawdzające, puść je.

## 1. Restart serwera

System zgłasza „System restart required". Zrób to, gdy drugi pipeline nie pracuje.

```bash
docker ps                        # upewnij się, że nic ważnego nie liczy się teraz
sudo reboot
```

Po restarcie: `docker ps` powinien pokazać, że kontenery drugiego pipeline'u wstały same
(mają `restart: unless-stopped` albo `always`; jeśli nie, uruchom je tak jak zwykle).

## 2. Swap 2 GB

Serwer ma ok. 2,5 GB wolnego RAM i zero swapu. Model embeddingów w kroku 4 przy starcie
chwilowo zjada sporo pamięci, a bez swapu kernel zabija wtedy losowy proces (może trafić w MariaDB).

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab     # żeby swap przetrwał restart
echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-swappiness.conf
sudo sysctl --system
```

Sprawdzenie: `free -h` pokazuje `Swap: 2.0Gi`. `swappiness=10` znaczy: używaj swapu dopiero w potrzebie,
nie przerzucaj tam aktywnych danych bazy.

## 3. Rekord DNS

U dostawcy domeny `example.com`: rekord typu **A**, nazwa `chilli`, wartość = publiczny IPv4 serwera
(ten sam co dla istniejącej strony). Jeśli ona ma też rekord AAAA, dodaj analogiczny AAAA dla `chilli`.

Sprawdzenie (z dowolnego komputera, może potrwać kilka minut):

```bash
dig +short chilli.example.com
dig +short other-site.example.com      # powinien być ten sam adres
```

## 4. Kod na serwerze

Repo jest prywatne, więc serwer potrzebuje dostępu do odczytu. Najprościej klucz tylko do odczytu (deploy key):

```bash
ssh-keygen -t ed25519 -f ~/.ssh/chilli_deploy -N ""
cat ~/.ssh/chilli_deploy.pub
```

Treść klucza publicznego wklej w GitHub: repo Chilli → Settings → Deploy keys → Add deploy key (bez „Allow write access").
Potem:

```bash
sudo mkdir -p /opt/chilli && sudo chown "$USER" /opt/chilli
GIT_SSH_COMMAND="ssh -i ~/.ssh/chilli_deploy" git clone git@github.com:<owner>/chilli.git /opt/chilli
cd /opt/chilli
git config core.sshCommand "ssh -i ~/.ssh/chilli_deploy"      # kolejne `git pull` użyją tego klucza
```

## 5. Plik .env

```bash
cd /opt/chilli
cp .env.example .env
chmod 600 .env
openssl rand -hex 32      # wynik do CAPTURE_TOKEN
openssl rand -hex 32      # wynik do MCP_SECRET
openssl rand -hex 24      # wynik do POSTGRES_PASSWORD
nano .env
```

Ustaw `ENV=prod`. `ANTHROPIC_API_KEY` i `VISION_MODEL` są potrzebne dopiero od kroku 4, mogą na razie zostać puste.
`CAPTURE_TOKEN` zapisz też w menedżerze haseł, przyda się do Skrótu na iPhonie.

Uwaga: `POSTGRES_PASSWORD` jest wczytywane tylko przy pierwszym utworzeniu bazy. Późniejsza zmiana w `.env`
nie zmienia hasła w istniejącej bazie (trzeba by zrobić `ALTER USER` w psql).

## 6. Start kontenerów

Najpierw sprawdź, czy port 8000 jest wolny (drugi pipeline mógłby go używać):

```bash
sudo ss -ltnp | grep ':8000' || echo "port 8000 wolny"
```

Jeśli zajęty, daj znać, zmienimy port w `docker-compose.yml` i w nginx.

```bash
cd /opt/chilli
docker compose up -d --build
docker compose ps                         # db: healthy, api: running
curl -s http://127.0.0.1:8000/health      # {"status":"ok","env":"prod","db":"ok"}
```

Projekt nazywa się `chilli` (od nazwy katalogu), więc kontenery i wolumeny nie zderzą się z drugim pipeline'em.

## 7. nginx i certyfikat

```bash
cd /opt/chilli
sudo cp deploy/nginx/chilli.conf /etc/nginx/sites-available/chilli
sudo ln -s /etc/nginx/sites-available/chilli /etc/nginx/sites-enabled/chilli
sudo nginx -t                    # musi być "syntax is ok" i "test is successful"
sudo systemctl reload nginx
curl -s http://chilli.example.com/health
```

Dopiero gdy działa po http (DNS już wskazuje serwer), certyfikat:

```bash
sudo certbot --nginx -d chilli.example.com
```

Certbot dopisze do `/etc/nginx/sites-available/chilli` część z portem 443 i przekierowanie z http.
Odnawianie jest już skonfigurowane dla istniejącej strony (timer certbota), obejmie też nowy certyfikat.

Sprawdzenie:

```bash
curl -s https://chilli.example.com/health
sudo certbot renew --dry-run
```

Do zrobienia przy kroku 6 (serwer MCP), żeby sekretny adres nie trafił do logów w dwóch miejscach,
których ta konfiguracja jeszcze nie łapie:

- blok `server` na porcie 80 dopisany przez certbota (przekierowanie na https) loguje zapytania, więc wejście
  na `http://.../mcp/<sekret>` zostawi ślad; trzeba tam dodać `access_log off;` albo osobne `location /mcp`,
- uvicorn wypisuje ścieżkę każdego żądania do `docker compose logs api`; trzeba wyciąć `/mcp` z jego logu dostępu.

Gdyby `nginx -t` padł: `sudo rm /etc/nginx/sites-enabled/chilli && sudo systemctl reload nginx` przywraca stan sprzed zmian.

## Aktualizacja po zmianach w kodzie

```bash
cd /opt/chilli
git pull
docker compose up -d --build
```

Zmiany w `db/schema.sql` nie zadziałają same na istniejącej bazie (patrz `docs/dev/01-baza.md`).

## Zużycie pamięci

Budżet Chilli to ok. 1-1,5 GB. Podgląd: `docker stats --no-stream`.
