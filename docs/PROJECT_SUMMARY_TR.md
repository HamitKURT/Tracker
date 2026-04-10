# Selenium Tracker - Proje Özeti

## Genel Bakış

Web uygulamalarından enjekte edilmiş JavaScript tracker aracılığıyla olayları yakalayan, bir mesaj kuyruğu üzerinden yönlendiren, Elasticsearch'te indeksleyen ve Kibana dashboard'larında görselleştiren kapsamlı bir tarayıcı telemetrisi ve QA izleme pipeline'ı.

---

## Mimari

```
Tarayıcı (performance.js)
    | XHR POST /events (toplu JSON)
    v
Log Sunucusu (Flask, port 8084)
    | LPUSH Redis listesine
    v
Redis Kuyruğu ("selenium_logs")
    | BRPOP (engelleyici pop)
    v
Log Worker (Python)
    | elasticsearch-py ile bulk indeks
    v
Elasticsearch (port 9200, indeks: "selenium-events")
    |
    v
Kibana (port 5601, dashboard'lar kibana_deployer tarafından dağıtılır)
```

---

## Servisler

| Servis | Dizin | Port | Açıklama |
|--------|-------|------|----------|
| **web-app** | `web_app/` | 8081 | `performance.js` enjekte edilmiş Flask demo uygulaması |
| **log-server** | `log_server/` | 8084 | Olayları alan ve Redis'e kuyruğa alan Flask endpoint |
| **log-worker** | `log_worker/` | - | Redis kuyruğunu tüketen, Elasticsearch'e toplu indeksleyen |
| **kibana-deployer** | `kibana_deployer/` | - | ES mapping'lerini yapılandıran, Kibana data view'ları ve dashboard'ları oluşturan |
| **selenium-test** | `selenium_test/` | - | 25+ olay kategorisi üreten headless Chrome test paketi |
| **redis** | (image) | 6379 | Olay kuyruğu depolama |
| **elasticsearch** | (image) | 9200 | Arama ve depolama backend |
| **kibana** | (image) | 5601 | Görselleştirme arayüzü |

---

## Olay Türleri

### Otomasyon Tespiti
| Tür | Açıklama |
|-----|----------|
| `automation-detected` | Tarayıcı otomasyon işaretleri bulundu (navigator.webdriver, Selenium global'leri, headless UA) |

### Selector & XPath İzleme
| Tür | Açıklama |
|-----|----------|
| `selector-miss` | querySelector/getElementById/getElementsBy* sonuç döndürmedi |
| `selector-error` | CSS selector sözdizimi hatası |
| `selector-found` | Element başarıyla bulundu (opsiyonel, `ENV_TRACK_SUCCESS=true` ile) |
| `xpath-error` | Geçersiz XPath ifadesi |
| `element-inspection` | getBoundingClientRect/getComputedStyle/offset* erişildi (sadece otomasyon) |

### Değer Manipülasyonu
| Tür | Açıklama |
|-----|----------|
| `value-manipulation` | Input/textarea değeri programatik olarak ayarlandı (sadece otomasyon) |

### Ağ İzleme
| Tür | Açıklama |
|-----|----------|
| `xhr-success` / `fetch-success` | HTTP isteği başarılı (status < 400) |
| `xhr-error` / `fetch-error` | HTTP isteği başarısız (status >= 400 veya ağ hatası) |
| `xhr-slow` / `fetch-slow` | HTTP isteği 5000ms eşiğini aştı |

### Hata İzleme
| Tür | Açıklama |
|-----|----------|
| `js-error` | Yakalanmamış JavaScript hatası |
| `unhandled-rejection` | İşlenmemiş Promise rejection |
| `resource-error` | Başarısız script/link/img kaynak yüklemesi |
| `console-error` | `console.error()` çağrıldı |
| `console-warn` | `console.warn()` çağrıldı |

### Kullanıcı Etkileşimleri
| Tür | Açıklama |
|-----|----------|
| `user-click` | Kullanıcı bir elemente tıkladı |
| `programmatic-click` | `element.click()` programatik olarak çağrıldı (otomasyon) |
| `rapid-clicks` | 80ms aralıklarla 5+ veya 20+ tıklama |
| `click-on-disabled` | Devre dışı/aria-disabled elemente tıklama |

### Form İzleme
| Tür | Açıklama |
|-----|----------|
| `form-submission` | Form gönderildi |
| `form-validation-failure` | Form gönderimde `:invalid` alanlara sahip |

### Sayfa Yaşam Döngüsü
| Tür | Açıklama |
|-----|----------|
| `page-load` | Sayfa yüklemesi tamamlandı (zamanlama verileriyle) |
| `page-idle` | 30+ saniye kullanıcı aktivitesi yok |
| `hashchange` | URL hash değişti |
| `pushState` / `replaceState` | History API ile SPA navigasyonu |
| `connection` | Tarayıcı çevrimiçi/çevrimdışı oldu |

### DOM Mutasyonları
| Tür | Açıklama |
|-----|----------|
| `dom-mutations` | Bir batch'te 10+ düğüm eklendi/kaldırıldı |
| `dom-attribute-changes` | İlgili özellikler değişti (class, style, disabled, aria-*, data-*) |

### Güvenlik
| Tür | Açıklama |
|-----|----------|
| `csp-violation` | Content Security Policy bir kaynağı engelledi |
| `websocket-error` | WebSocket bağlantısı başarısız oldu |
| `websocket-unclean-close` | WebSocket anormal şekilde kapandı |
| `blocking-overlay-detected` | Viewport'un %30'undan fazlasını kaplayan sabit/mutlak overlay |

### Framework'e Özgü Hatalar
| Tür | Açıklama |
|-----|----------|
| `frameworks-detected` | React/Angular/Vue/jQuery/Svelte/vb. tespit edildi |
| `react-render-error` | React bileşen render hatası |
| `react-hydration-mismatch` | React SSR hydration uyumsuzluğu |
| `react-error-boundary-triggered` | React error boundary hata yakaladı |
| `angular-zone-error` | Zone.js hata yakaladı |
| `angular-framework-error` | Angular NG hata kodu |
| `vue-error` / `vue-warning` | Vue hata/uyarı handler tetiklendi |
| `jquery-ajax-error` | jQuery AJAX isteği başarısız |
| `nextjs-runtime-error` | Next.js runtime hatası |
| `nuxt-error` | Nuxt.js hatası |

---

## Yapılandırma

### Ortam Değişkenleri (.env)

| Değişken | Varsayılan | Açıklama |
|----------|------------|----------|
| `ELASTIC_PASSWORD` | `changeme` | Elasticsearch şifresi |
| `ELASTIC_USERNAME` | `elastic` | Elasticsearch kullanıcı adı |
| `KIBANA_SYSTEM_PASSWORD` | `changeme` | Kibana sistem kullanıcı şifresi |
| `ELASTIC_URL` | `http://elasticsearch:9200` | Elasticsearch URL |
| `KIBANA_URL` | `http://kibana:5601` | Kibana URL |
| `REDIS_HOST` | `redis` | Redis hostname |
| `REDIS_PORT` | `6379` | Redis portu |
| `REDIS_QUEUE_KEY` | `selenium_logs` | Olay kuyruğu için Redis liste anahtarı |
| `ELASTIC_INDEX` | `selenium-events` | Elasticsearch indeks adı |
| `BATCH_SIZE` | `50` | Bulk indeksleme için worker batch boyutu |
| `MAX_WAIT_TIME` | `2.0` | Batch boşaltmadan önce maksimum saniye |
| `LOGSERVER_EXTERNAL_URL` | `http://localhost:8084` | Tarayıcı için log sunucusu URL |
| `LOGSERVER_INTERNAL_URL` | `http://log-server:8084` | Otomasyon için log sunucusu URL (Docker ağı) |
| `DEBUG` | `false` | Ayrıntılı loglama etkinleştir |
| `ENV_TRACK_SUCCESS` | `false` | Başarılı selector eşleşmelerini izle |

### Frontend Yapılandırması (performance.js)

`performance.js` yüklenmeden önce `window.*` global'leri ile ayarlayın:

| Global | Açıklama |
|--------|----------|
| `window.ENV_LOGSERVER_URL` | Log sunucusu URL (normal tarama) |
| `window.ENV_LOGSERVER_INTERNAL_URL` | Log sunucusu URL (otomasyon, Docker internal) |
| `window.ENV_DEBUG` | Konsol debug çıktısı için `"true"` |
| `window.ENV_TRACK_SUCCESS` | Başarılı selector eşleşmelerini loglamak için `"true"` |
| `window.ENV_QA_SESSION_ID` | Session ID'yi override et |
| `window.ENV_PRIVACY_MODE` | Katı gizlilik modunu devre dışı bırakmak için `"relaxed"` |

---

## Gizlilik & Sanitizasyon

Tüm veriler iletilmeden önce tarayıcıda temizlenir:

- **Hassas alanlar gizlenir**: password, token, api_key, ssn, credit_card, vb. (50+ kalıp)
- **E-posta maskeleme**: `kullanici@example.com` -> `ku***@example.com`
- **Token tespiti**: 32+ karakterli hex string'ler ve 40+ karakterli Base64 string'ler `[token]` olarak maskelenir
- **URL parametre gizleme**: Hassas sorgu parametreleri `[REDACTED]` ile değiştirilir
- **Değer kesme**: String'ler yapılandırılabilir maksimum uzunlukta kesilir (varsayılan 100 karakter)

---

## Kibana Dashboard

`kibana_deployer` 12 bölümlü tek bir kapsamlı dashboard oluşturur:

1. **Özet KPI'lar** - Toplam olaylar, hatalar, oturumlar, URL'ler, yüksek/kritik önem sayıları
2. **Genel Zaman Çizelgeleri** - Zaman içinde tüm olaylar ve hata olayları
3. **Olay Dağılımı** - Türe ve öneme göre olaylar (pasta grafikleri + tablolar)
4. **JavaScript Hataları** - JS hataları, işlenmemiş rejection'lar, konsol hataları/uyarıları
5. **Ağ** - İstek zaman çizelgesi, hatalar, endpoint'e göre yavaş istekler
6. **Selector'lar & XPath** - CSS selector kaçırmaları, XPath hataları, hata analizi
7. **Kullanıcı Etkileşimleri** - Tıklama olayları, form gönderimleri, doğrulama hataları
8. **Navigasyon** - Zamanlama ile sayfa yüklemeleri, SPA navigasyonu, hash değişiklikleri
9. **DOM Mutasyonları** - Düğüm ekleme/kaldırma, özellik değişiklikleri
10. **Güvenlik** - CSP ihlalleri, WebSocket hataları, engelleyen overlay'ler
11. **Otomasyon Tespiti** - Otomasyon sinyalleri, programatik tıklamalar
12. **Framework Hataları** - React/Angular/Vue'ya özgü hatalar

---

## Dağıtım

### Geliştirme

```bash
cp .env.example .env
# .env dosyasını şifrelerinizle düzenleyin
docker-compose -f docker-compose.dev.yml up -d
```

### Production

```bash
cp .env.example .env
# .env dosyasında güçlü şifreler ayarlayın
docker-compose -f docker-compose.prod.yml up -d
```

### Servis Başlangıç Sırası

1. **Redis** ve **Elasticsearch** ilk başlar
2. **Kibana Deployer** ES cluster sağlığını bekler, `kibana_system` şifresini ayarlar, Kibana'yı bekler, sonra dashboard'ları dağıtır
3. **Log Server** ve **Log Worker** Redis ve ES'e bağlanır
4. **Web App** `performance.js` ile demo sayfayı sunar
5. **Selenium Test** kapsamlı test paketini çalıştırır

### Servislere Erişim

- **Web App**: `http://localhost:8081`
- **Kibana**: `http://localhost:5601` (giriş: `elastic` / şifreniz)
- **Elasticsearch**: `http://localhost:9200`
- **Log Server Sağlık**: `http://localhost:8084/health`

---

## Veri Akışı Detayları

### Tarayıcı -> Log Sunucusu
- Olaylar toplu halde (istek başına max 100) `Content-Type: text/plain` ile `POST /events` olarak gönderilir
- Payload formatı: `{ "events": [...] }`
- Üstel geri çekilme ile yeniden deneme (3 denemeye kadar)
- Sayfa unload'da: `fetch` ile `keepalive` veya `navigator.sendBeacon` kullanır

### Log Sunucusu -> Redis
- Her olay ayrı ayrı yapılandırılmış Redis liste anahtarına `LPUSH` edilir
- Dönüşüm uygulanmaz

### Log Worker -> Elasticsearch
- 1s timeout ile `BRPOP`, `BATCH_SIZE` olaya veya `MAX_WAIT_TIME` saniyeye kadar toplar
- `_ctx` context nesnesini üst düzey olay alanlarına birleştirir
- Timestamp alanlarını ISO 8601'e normalize eder
- Sunucu UTC zamanıyla `@timestamp` ekler
- Hata yönetimi ve başarısız belgeler için yeniden kuyruğa alma ile bulk indeksler

---

## Selenium Test Paketi

Test (`selenium_test/app/main.py`) 25+ kategori olay üretir:

- Eksik selector'lar (querySelector, getElementById, getElementsBy*, XPath)
- JavaScript hataları (ReferenceError, TypeError, SyntaxError, RangeError, vb.)
- Ağ hataları (XHR/fetch hataları, yavaş istekler, timeout'lar)
- Hızlı etkileşimler (25 hızlı tıklama, hızlı tuş girişleri)
- DOM mutasyon patlamaları (30 element ekleme/kaldırma)
- Form doğrulama hataları
- Konsol hataları ve uyarıları
- Engelleyen overlay tespiti
- WebSocket hataları
- Sayfa boşta tespiti (30s bekleme)
- Navigasyon olayları (hash, pushState, replaceState)
- Kaynak yükleme hataları (bozuk resimler, script'ler, stylesheet'ler)
