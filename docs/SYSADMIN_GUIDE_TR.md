# Sistem Yöneticisi Kılavuzu

Selenium Tracker log sunucusu altyapısı için kapsamlı kurulum ve yapılandırma kılavuzu.

---

## Ön Gereksinimler

### Sistem Gereksinimleri

| Kaynak | Minimum | Önerilen |
|--------|---------|----------|
| RAM | 4 GB | 8 GB+ |
| CPU | 2 çekirdek | 4 çekirdek |
| Disk | 20 GB | 50 GB+ |
| Docker | 24.0+ | En son |
| Docker Compose | 2.20+ | En son |

### Gerekli Portlar

| Port | Servis | Açıklama |
|------|--------|----------|
| 6379 | Redis | Mesaj kuyruğu |
| 8084 | Log Sunucusu | Tarayıcı olaylarını alır |
| 9200 | Elasticsearch | Arama ve depolama |
| 5601 | Kibana | Görselleştirme arayüzü |

Bu portların kullanılmadığından ve web uygulama sunucularından erişilebilir olduğundan emin olun.

---

## Hızlı Başlangıç

### Adım 1: Klonla ve Yapılandır

```bash
cd /yol/seleniumtracker/Workarea/Tracker
cp .env.example .env
```

### Adım 2: Ortam Değişkenlerini Düzenle

`.env` dosyasını açın ve en azından şunları yapılandırın:

```dotenv
# GEREKLİ: Varsayılan değerleri değiştirin
ELASTIC_PASSWORD=GuvenliSifre123!
KIBANA_SYSTEM_PASSWORD=KibanaSifre456!

# Sunucu RAM'inize göre ayarlayın (sistem RAM'inin %50'si, max 30GB)
ES_JAVA_OPTS=-Xms1g -Xmx4g
```

### Adım 3: Stack'i Başlat

**Production modu** (kalıcı veri):
```bash
docker compose -f docker-compose.prod.yml up -d --build
```

**Development modu** (geçici veri):
```bash
docker compose -f docker-compose.dev.yml up -d --build
```

### Adım 4: Başlangıcı İzle

```bash
docker compose -f docker-compose.prod.yml logs -f kibana-deployer log-worker
```

Şu mesajları bekleyin:
```
DEPLOYER - INFO - [Kibana] All dashboards deployed successfully!
WORKER   - INFO - Write alias 'selenium-events' is available.
WORKER   - INFO - Starting log consumption from queue 'selenium_logs'
```

### Adım 5: Sağlığı Doğrula

```bash
docker compose -f docker-compose.prod.yml ps
```

Tüm servisler `healthy` veya `running` durumunda olmalı.

---

## Servis Başlangıç Sırası

Servisler otomatik olarak bağımlılık sırasına göre başlar:

```
1. Redis + Elasticsearch        (altyapı)
2. Kibana Deployer              (ES ve Kibana'yı yapılandırır)
3. Kibana                       (deployer'ı bekler)
4. Log Server                   (Redis'i bekler)
5. Log Worker                   (ES + Redis + Kibana'yı bekler)
```

Servisleri manuel olarak başlatmanız gerekmez.

---

## Yapılandırma Referansı

### Güvenlik Ayarları

| Değişken | Varsayılan | Açıklama |
|----------|------------|----------|
| `ELASTIC_PASSWORD` | `changeme` | Elasticsearch şifresi - **MUTLAKA DEĞİŞTİRİN** |
| `KIBANA_SYSTEM_PASSWORD` | `changeme` | Kibana sistem şifresi - **MUTLAKA DEĞİŞTİRİN** |

### Performans Ayarlama

| Değişken | Varsayılan | Açıklama |
|----------|------------|----------|
| `ES_JAVA_OPTS` | `-Xms1g -Xmx4g` | Elasticsearch heap (RAM'ın %50'si, max 30GB) |
| `BATCH_SIZE` | `50` | Toplu indeks başına olay sayısı |
| `MAX_WAIT_TIME` | `2.0` | Batch boşaltmadan önce max saniye |

Ayarlama önerileri:
- **4 GB sunucu**: `-Xms512m -Xmx2g`
- **8 GB sunucu**: `-Xms1g -Xmx4g`
- **16 GB sunucu**: `-Xms2g -Xmx8g`
- **32 GB sunucu**: `-Xms4g -Xmx16g`

### ILM (Index Lifecycle Management)

| Değişken | Varsayılan | Açıklama |
|----------|------------|----------|
| `ILM_MAX_SIZE` | `1gb` | Bu boyuta ulaşınca rollover |
| `ILM_MAX_AGE` | `7d` | Bu yaşa ulaşınca rollover |
| `ILM_MAX_DOCS` | `5000000` | Bu belge sayısında rollover |
| `ILM_DELETE_AFTER` | `30d` | Bundan eski indeksleri otomatik sil |

### CORS Yapılandırması

| Değişken | Varsayılan | Açıklama |
|----------|------------|----------|
| `CORS_ALLOWED_ORIGINS` | `*` | Cross-domain istekler için izin verilen kaynaklar |

Örnekler:
```dotenv
# Tüm kaynaklara izin ver (geliştirme)
CORS_ALLOWED_ORIGINS=*

# Tek kaynak
CORS_ALLOWED_ORIGINS=https://uygulama.example.com

# Birden fazla kaynak
CORS_ALLOWED_ORIGINS=https://uygulama1.example.com,https://uygulama2.example.com,http://localhost:3000
```

### Port Yapılandırması

| Değişken | Varsayılan | Açıklama |
|----------|------------|----------|
| `REDIS_PORT` | `6379` | Redis portu |
| `ELASTICSEARCH_PORT` | `9200` | Elasticsearch portu |
| `KIBANA_PORT` | `5601` | Kibana portu |
| `LOG_SERVER_PORT` | `8084` | Log sunucusu portu |

---

## Web Geliştiricilere Bilgi Sağlama

Dağıtımdan sonra, web geliştiricilerine şunları sağlayın:

1. **Log Sunucusu IP Adresi**: Sunucunuzun IP adresi
2. **Port**: 8084 (veya değiştirdiyseniz özel port)
3. **Entegrasyon Kodu**:

```html
<script src="/performance.js" data-logserver="http://[SUNUCU_IP]:8084"></script>
```

Gerçek IP ile örnek:
```html
<script src="/performance.js" data-logserver="http://10.0.0.50:8084"></script>
```

4. **`performance.js` dosyası**: Proje kök dizininde bulunur

Ayrıca şunları da sağlayın:
- [WEBAPP_QUICKSTART_TR.md](WEBAPP_QUICKSTART_TR.md) - Entegrasyon kılavuzu
- [WEBAPP_TROUBLESHOOTING_TR.md](WEBAPP_TROUBLESHOOTING_TR.md) - Sorun giderme kılavuzu

---

## Servis Yönetimi

### Servisleri Başlatma

```bash
docker compose -f docker-compose.prod.yml up -d
```

### Servisleri Durdurma

```bash
docker compose -f docker-compose.prod.yml down
```

### Tüm Servisleri Yeniden Başlatma

```bash
docker compose -f docker-compose.prod.yml restart
```

### Belirli Bir Servisi Yeniden Başlatma

```bash
docker compose -f docker-compose.prod.yml restart log-server
```

### Logları Görüntüleme

```bash
# Tüm servisler
docker compose -f docker-compose.prod.yml logs -f

# Belirli servis
docker compose -f docker-compose.prod.yml logs -f log-worker

# Son 100 satır
docker compose -f docker-compose.prod.yml logs --tail=100 elasticsearch
```

### Servis Durumunu Kontrol Etme

```bash
docker compose -f docker-compose.prod.yml ps
```

---

## İzleme

### Sağlık Endpoint'leri

| Endpoint | Beklenen Yanıt |
|----------|----------------|
| `http://localhost:8084/health` | `{"status": "healthy", "redis": "connected"}` |
| `http://localhost:9200/_cluster/health` | `{"status": "green"}` veya `{"status": "yellow"}` |
| `http://localhost:5601/api/status` | `{"status": {"overall": {"level": "available"}}}` |

### Elasticsearch İzleme

```bash
# Cluster sağlığı
curl -s -u elastic:$ELASTIC_PASSWORD http://localhost:9200/_cluster/health?pretty

# İndeks durumu
curl -s -u elastic:$ELASTIC_PASSWORD 'http://localhost:9200/_cat/indices/selenium-events-*?v&s=index'

# Belge sayısı
curl -s -u elastic:$ELASTIC_PASSWORD 'http://localhost:9200/selenium-events-*/_count'

# ILM durumu
curl -s -u elastic:$ELASTIC_PASSWORD 'http://localhost:9200/selenium-events-*/_ilm/explain' | python3 -m json.tool
```

### Redis İzleme

```bash
# Kuyruk uzunluğu
docker exec redis redis-cli LLEN selenium_logs

# Kuyruk bilgisi
docker exec redis redis-cli INFO
```

---

## Kibana'ya Erişim

1. `http://[SUNUCU_IP]:5601` adresini açın
2. Giriş yapın:
   - Kullanıcı adı: `elastic`
   - Şifre: `ELASTIC_PASSWORD` değeriniz
3. **Analytics** > **Dashboard** menüsüne gidin
4. **Selenium Monitoring Dashboard**'u seçin

---

## Tam Sıfırlama

Sistemi tamamen sıfırlamak ve baştan başlamak için:

```bash
# Tüm konteynerleri, volume'ları ve verileri durdur ve kaldır
docker compose -f docker-compose.prod.yml down -v

# Yeniden oluştur ve başlat
docker compose -f docker-compose.prod.yml up -d --build
```

**Uyarı**: Bu, Elasticsearch indeksleri dahil TÜM verileri siler.

---

## Yedekleme ve Geri Yükleme

Aşağıdaki konularda detaylı talimatlar için [README.md](../README.md) belgesinin "Backup and Restore — Complete Workflow" bölümüne bakın:
- Elasticsearch snapshot alma
- Verileri NDJSON dosyalarına aktarma
- Başka bir sunucuda veri geri yükleme

---

## İleri Okuma

- [README.md](../README.md) - Tam proje dokümantasyonu
- [SYSADMIN_TROUBLESHOOTING_TR.md](SYSADMIN_TROUBLESHOOTING_TR.md) - Sunucu sorun giderme
- [ANALYSIS_GUIDE_TR.md](../ANALYSIS_GUIDE_TR.md) - Elasticsearch alan referansı ve KQL sorguları
