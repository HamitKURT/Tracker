# Sistem Yöneticisi Sorun Giderme

Sunucu tarafı ve Docker ile ilgili sorunlar için sorun giderme kılavuzu.

---

## Docker Sorunları

### Konteynerler Başlamıyor

**Belirtiler:**
- `docker compose up` başarısız oluyor
- Konteynerler hemen kapanıyor

**Çözümler:**

1. **Docker'ın çalıştığını kontrol edin:**
```bash
docker info
```

2. **Docker Compose sürümünü kontrol edin:**
```bash
docker compose version
# 2.20+ gerekir
```

3. **Port çakışmalarını kontrol edin:**
```bash
# Portların kullanımda olup olmadığını kontrol edin
lsof -i :6379
lsof -i :8084
lsof -i :9200
lsof -i :5601
```

4. **Konteyner loglarını kontrol edin:**
```bash
docker compose -f docker-compose.prod.yml logs elasticsearch
docker compose -f docker-compose.prod.yml logs kibana-deployer
```

5. **Eski konteynerleri kaldırın ve tekrar deneyin:**
```bash
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d --build
```

### Port Çakışmaları

**Belirtiler:**
- Hata: `port is already allocated`

**Çözümler:**

1. **Portu kullanan işlemi bulun:**
```bash
lsof -i :8084
# veya
netstat -tulpn | grep 8084
```

2. **Çakışan işlemi sonlandırın veya `.env`'de portu değiştirin:**
```dotenv
LOG_SERVER_PORT=8085  # Farklı bir port kullanın
```

### Bellek Sorunları

**Belirtiler:**
- Konteynerler OOM (Out of Memory) ile çöküyor
- Elasticsearch başlatılamıyor

**Çözümler:**

1. **Kullanılabilir belleği kontrol edin:**
```bash
free -h
```

2. **`.env`'de Elasticsearch heap boyutunu azaltın:**
```dotenv
# 4GB RAM sunucu için
ES_JAVA_OPTS=-Xms512m -Xmx2g
```

3. **Docker bellek limitlerini kontrol edin:**
```bash
docker stats --no-stream
```

---

## Elasticsearch Sorunları

### Başlamıyor / Sağlıklı Değil

**Belirtiler:**
- `docker compose ps` elasticsearch'ü `unhealthy` olarak gösteriyor
- Kibana deployer süresiz bekliyor

**Çözümler:**

1. **Elasticsearch loglarını kontrol edin:**
```bash
docker compose -f docker-compose.prod.yml logs elasticsearch
```

2. **Yaygın neden: vm.max_map_count çok düşük**

Mevcut değeri kontrol edin:
```bash
sysctl vm.max_map_count
```

Düzeltme (Elasticsearch için gerekli):
```bash
# Geçici (yeniden başlatmaya kadar)
sudo sysctl -w vm.max_map_count=262144

# Kalıcı
echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

3. **Disk alanı sorunları:**
```bash
df -h
# Elasticsearch en az %5 boş disk alanına ihtiyaç duyar
```

4. **Veri volume'unda izin sorunları:**
```bash
# Volume'u kontrol edin
docker volume inspect tracker_es-data

# Gerekirse volume'u yeniden oluşturun
docker compose -f docker-compose.prod.yml down -v
docker compose -f docker-compose.prod.yml up -d --build
```

### Cluster Sağlığı Sarı veya Kırmızı

**Belirtiler:**
- `curl localhost:9200/_cluster/health` status: "yellow" veya "red" gösteriyor

**Çözümler:**

**Sarı durum** tek düğümlü cluster'lar için normaldir (replika shard yok). Bu beklenen bir durumdur.

**Kırmızı durum** veri kaybı veya bozulma olduğunu gösterir:
```bash
# Hangi indekslerin sorunu olduğunu kontrol edin
curl -s -u elastic:$ELASTIC_PASSWORD 'http://localhost:9200/_cat/indices?v&health=red'

# Atanmamış shard'ları kontrol edin
curl -s -u elastic:$ELASTIC_PASSWORD 'http://localhost:9200/_cat/shards?v&h=index,shard,prirep,state,unassigned.reason'
```

---

## Log Sunucusu Sorunları

### Olayları Almıyor

**Belirtiler:**
- Web uygulamaları bağlantı hatası bildiriyor
- Elasticsearch'te olay görünmüyor

**Çözümler:**

1. **Log sunucusunun çalıştığını kontrol edin:**
```bash
docker compose -f docker-compose.prod.yml ps log-server
```

2. **Sağlık endpoint'ini test edin:**
```bash
curl http://localhost:8084/health
# Dönmeli: {"status": "healthy", "redis": "connected"}
```

3. **Log sunucusu loglarını kontrol edin:**
```bash
docker compose -f docker-compose.prod.yml logs log-server
```

4. **Redis bağlantısını doğrulayın:**
```bash
docker exec redis redis-cli ping
# Dönmeli: PONG
```

### CORS Hataları

**Belirtiler:**
- Tarayıcı konsolunda CORS politikası hataları görünüyor
- Web uygulamalarından olay gönderilemiyor

**Çözümler:**

1. **Mevcut CORS yapılandırmasını kontrol edin:**
```bash
grep CORS_ALLOWED_ORIGINS .env
```

2. **`.env`'de CORS yapılandırmasını güncelleyin:**
```dotenv
# Belirli alan adları için
CORS_ALLOWED_ORIGINS=https://uygulama.example.com,https://uygulama2.example.com

# Geliştirme için (tümüne izin ver)
CORS_ALLOWED_ORIGINS=*
```

3. **Log sunucusunu yeniden başlatın:**
```bash
docker compose -f docker-compose.prod.yml restart log-server
```

---

## Redis Kuyruk Sorunları

### Kuyruk Büyüyor / İşlenmiyor

**Belirtiler:**
- Kuyruk uzunluğu sürekli artıyor
- Elasticsearch'te olay görünmüyor

**Çözümler:**

1. **Kuyruk uzunluğunu kontrol edin:**
```bash
docker exec redis redis-cli LLEN selenium_logs
```

2. **Log worker durumunu kontrol edin:**
```bash
docker compose -f docker-compose.prod.yml ps log-worker
docker compose -f docker-compose.prod.yml logs log-worker
```

3. **Worker'dan Elasticsearch bağlantısını kontrol edin:**
```bash
docker compose -f docker-compose.prod.yml logs log-worker | grep -i error
```

4. **Log worker'ı yeniden başlatın:**
```bash
docker compose -f docker-compose.prod.yml restart log-worker
```

### Worker Olayları İşlemiyor

**Belirtiler:**
- Log worker çalışıyor ama kuyruk boşalmıyor

**Çözümler:**

1. **Worker loglarında hata olup olmadığını kontrol edin:**
```bash
docker compose -f docker-compose.prod.yml logs --tail=100 log-worker
```

2. **Elasticsearch'ün yazma kabul ettiğini kontrol edin:**
```bash
curl -s -u elastic:$ELASTIC_PASSWORD 'http://localhost:9200/_cluster/health' | python3 -m json.tool
```

3. **Yazma alias'ının var olduğunu kontrol edin:**
```bash
curl -s -u elastic:$ELASTIC_PASSWORD 'http://localhost:9200/_alias/selenium-events'
```

---

## Kibana Sorunları

### Erişilemiyor

**Belirtiler:**
- `http://localhost:5601` açılamıyor
- Bağlantı reddedildi veya zaman aşımı

**Çözümler:**

1. **Kibana'nın çalıştığını kontrol edin:**
```bash
docker compose -f docker-compose.prod.yml ps kibana
```

2. **Kibana loglarını kontrol edin:**
```bash
docker compose -f docker-compose.prod.yml logs kibana
```

3. **Kibana'nın tamamen başlamasını bekleyin** (2-3 dakika sürebilir):
```bash
docker compose -f docker-compose.prod.yml logs -f kibana
# "Server running at http://0.0.0.0:5601" mesajını bekleyin
```

4. **Kibana sağlığını kontrol edin:**
```bash
curl -s http://localhost:5601/api/status | python3 -m json.tool
```

### Dashboard'larda Veri Yok

**Belirtiler:**
- Kibana yükleniyor ama dashboard'larda veri yok
- "No results found" mesajı

**Çözümler:**

1. **Elasticsearch'te veri var mı kontrol edin:**
```bash
curl -s -u elastic:$ELASTIC_PASSWORD 'http://localhost:9200/selenium-events-*/_count'
```

2. **Kibana'da zaman aralığını kontrol edin:**
   - Dashboard'lar varsayılan olarak "Son 15 dakika"yı gösterir
   - Zaman aralığını "Son 24 saat" veya "Son 7 gün" olarak genişletin

3. **Data view'ın var olduğunu doğrulayın:**
   - Stack Management > Data Views'a gidin
   - `selenium-events*` arayın

4. **Deployer'ın başarılı çalıştığını kontrol edin:**
```bash
docker compose -f docker-compose.prod.yml logs kibana-deployer | grep -i dashboard
```

---

## Kurtarma Prosedürleri

### Tam Sistem Sıfırlama

Tamamen sıfırlamak ve baştan başlamak için:

```bash
# Her şeyi durdurun ve volume'ları kaldırın
docker compose -f docker-compose.prod.yml down -v

# Yetim konteynerleri kaldırın
docker system prune -f

# Yeniden oluşturun ve başlatın
docker compose -f docker-compose.prod.yml up -d --build
```

### Tüm Servisleri Yeniden Başlat

```bash
docker compose -f docker-compose.prod.yml restart
```

### Belirli Servisi Yeniden Oluştur

```bash
# Tek bir servisi yeniden oluştur ve başlat
docker compose -f docker-compose.prod.yml up -d --build log-server
```

### Elasticsearch Hatasından Kurtarma

Elasticsearch verisi bozulduysa:

```bash
# 1. Tüm servisleri durdurun
docker compose -f docker-compose.prod.yml down

# 2. Elasticsearch volume'unu kaldırın (tüm veri silinir!)
docker volume rm tracker_es-data

# 3. Yeniden başlatın (deployer her şeyi yeniden oluşturacak)
docker compose -f docker-compose.prod.yml up -d --build
```

---

## Tanılama Komutları Özeti

```bash
# Genel durum
docker compose -f docker-compose.prod.yml ps

# Tüm servis logları
docker compose -f docker-compose.prod.yml logs

# Belirli servis logları
docker compose -f docker-compose.prod.yml logs -f log-worker

# Konteyner kaynak kullanımı
docker stats --no-stream

# Elasticsearch sağlığı
curl -s -u elastic:$ELASTIC_PASSWORD http://localhost:9200/_cluster/health?pretty

# Redis kuyruk uzunluğu
docker exec redis redis-cli LLEN selenium_logs

# Log sunucusu sağlığı
curl http://localhost:8084/health

# Kibana durumu
curl -s http://localhost:5601/api/status | python3 -c "import sys,json; print(json.load(sys.stdin)['status']['overall']['level'])"
```

---

## Yardım Alma

Bu çözümleri denedikten sonra sorunlar devam ederse:

1. Tanılama bilgilerini toplayın:
```bash
docker compose -f docker-compose.prod.yml ps > diag_ps.txt
docker compose -f docker-compose.prod.yml logs > diag_logs.txt 2>&1
```

2. Sistem kaynaklarını kontrol edin:
```bash
free -h > diag_memory.txt
df -h > diag_disk.txt
```

3. Loglardaki hata kalıplarını inceleyin

4. Ana dokümantasyona başvurun:
   - [README.md](../README.md)
   - [SYSADMIN_GUIDE_TR.md](SYSADMIN_GUIDE_TR.md)
