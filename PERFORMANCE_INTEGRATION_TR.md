# performance.js Entegrasyon Rehberi

Herhangi bir web uygulamasını otomatik olarak izleyen, bağımlılığı olmayan bir tarayıcı telemetri scripti. DOM etkileşimlerini, ağ isteklerini, JS hatalarını, framework'e özgü sorunları ve daha fazlasını yakalar — ardından olayları analiz için log sunucusuna gönderir.

---

## Hızlı Başlangıç

HTML'inize tek bir script etiketi ekleyin:

```html
<script src="/performance.js" data-logserver="http://log-sunucunuz:8084"></script>
```

Hepsi bu kadar. Script kendini başlatır ve olayları anında yakalamaya başlar.

### Script'i Sunma

`performance.js` dosyasını statik varlıklar dizininize kopyalayın ve diğer JS dosyaları gibi sunun. Derleme adımı, bağımlılık veya modül sistemi gerektirmez.

```
uygulamaniz/
├── static/
│   └── performance.js    ← bu dosyayı kopyalayın
├── templates/
│   └── index.html         ← script etiketini buraya ekleyin
```

---

## Yapılandırma

### Script Etiketi Özellikleri

| Özellik | Açıklama | Örnek |
|---------|----------|-------|
| `data-logserver` | Log sunucusu temel URL'i | `http://sunucum:8084` |
| `data-track-success` | Başarılı seçici aramalarını logla (ayrıntılı) | `"true"` |

### Global Değişkenler (`window.*`)

Varsayılanları geçersiz kılmak için script yüklenmeden **önce** bunları ayarlayın:

| Değişken | Açıklama | Varsayılan |
|----------|----------|------------|
| `ENV_LOGSERVER_URL` | Log sunucusu URL'i (tüm tarayıcılar) | `http://mainlogserver.local:8084` |
| `ENV_LOGSERVER_INTERNAL_URL` | Yalnızca otomatik/Selenium oturumlarında kullanılan dahili URL | — |
| `ENV_QA_SESSION_ID` | Otomatik oluşturulan oturum kimliğini geçersiz kıl | Otomatik oluşturulur |
| `ENV_DEBUG` | Tarayıcı konsolunda hata ayıklama loglamasını etkinleştir | `'false'` |
| `ENV_PRIVACY_MODE` | Sıkı URL token temizlemeyi devre dışı bırakmak için `'relaxed'` olarak ayarlayın | strict |
| `ENV_TRACK_SUCCESS` | Başarılı seçici eşleşmelerini global olarak logla | `'false'` |

**Global değişkenlerle örnek:**

```html
<script>
  window.ENV_LOGSERVER_URL = 'http://sunucum:8084';
  window.ENV_DEBUG = 'true';
  window.ENV_QA_SESSION_ID = 'test-calistirmasi-42';
</script>
<script src="/performance.js"></script>
```

### URL Çözümleme Önceliği

Script, log sunucusu URL'ini bağlama göre farklı şekilde çözümler:

**Otomatik oturumlar** (Selenium, Playwright, Puppeteer, vb.):
```
ENV_LOGSERVER_INTERNAL_URL → ENV_LOGSERVER_URL → data-logserver → varsayılan
```

**Manuel tarama:**
```
ENV_LOGSERVER_URL → data-logserver → varsayılan
```

Bu, otomatik testler için dahili Docker/ağ URL'lerini kullanırken manuel test için genel URL kullanmanıza olanak tanır.

---

## Log Sunucusu Gereksinimleri

Script, olayları HTTP POST aracılığıyla `{logserver}/events` adresine gönderir.

### Endpoint Spesifikasyonu

| Özellik | Değer |
|---------|-------|
| **Yol** | `/events` |
| **Metod** | `POST` |
| **Content-Type** | `text/plain` |
| **Yük** | JSON dizesi: `{ "events": [ ... ] }` |

### Yük Formatı

```json
{
  "events": [
    {
      "type": "page-load",
      "url": "https://ornek.com/panel",
      "loadTime": 1234,
      "severity": "low",
      "eventId": "a1b2-c3d4",
      "sessionId": "e5f6-g7h8",
      "correlationId": "corr-1712567890123-1",
      "summary": "Sayfa 1234ms'de yüklendi (OK)",
      "_ctx": {
        "sessionId": "e5f6-g7h8",
        "pageId": "i9j0-k1l2",
        "url": "https://ornek.com/panel",
        "timestamp": "2026-04-08T12:00:00.000Z",
        "uptime": 5000,
        "isAutomated": false,
        "userAgent": "Mozilla/5.0 ..."
      }
    }
  ]
}
```

### CORS

Log sunucusu uygulamanızdan farklı bir origin'de çalışıyorsa, CORS başlıkları döndürmesi **gerekir**:

```
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: POST, OPTIONS
Access-Control-Allow-Headers: Content-Type
```

### Sayfa Kapatılırken Teslimat

Sayfa kapanırken (kapatma, başka sayfaya gitme), script kalan olayları teslim etmek için `navigator.sendBeacon()` veya `fetch({ keepalive: true })` kullanır. Bu yöntemlerin ~64KB tarayıcı limiti vardır, bu yüzden script yükleri otomatik olarak 50KB altında parçalar.

### Beklenen Sunucu Yanıtı

Script yanıt gövdesini incelemez. Herhangi bir `2xx` durumu başarı olarak kabul edilir. Başarısızlık durumunda, üstel geri çekilme ile 3 kez yeniden dener (1s, 2s, 3s). Yeniden denemeler tükendikten sonra, düşürülen olaylar `sessionStorage`'a kaydedilir ve bir sonraki sayfa yüklemesinde kurtarılır.

---

## Olay Türleri Referansı

Her olay şu ortak alanları içerir:

| Alan | Açıklama |
|------|----------|
| `type` | Olay türü tanımlayıcısı |
| `severity` | `low`, `medium`, `high` veya `critical` |
| `eventId` | Benzersiz olay kimliği |
| `sessionId` | Oturum tanımlayıcısı |
| `correlationId` | İlgili olayları zincirler halinde gruplar |
| `summary` | İnsan tarafından okunabilir tek satırlık açıklama |
| `_ctx` | Sayfa bağlamı (URL, zaman damgası, çalışma süresi, userAgent) |
| `isAutomationDetected` | Otomasyon tespit edilip edilmediği |
| `pageUrl` | Mevcut sayfa URL'i |
| `app` | Uygulama origin'i |

### Sayfa ve Navigasyon

| Tür | Önem | Açıklama |
|-----|------|----------|
| `page-load` | low–high | Sayfa yükleme zamanlaması, varsa HTTP durumunu içerir |
| `hashchange` | low | URL hash'i değişti |
| `pushState` | low | `history.pushState` ile SPA navigasyonu |
| `replaceState` | low | `history.replaceState` ile SPA navigasyonu |
| `page-idle` | high | 30 saniye kullanıcı aktivitesi yok (yapılandırılabilir) — test takılmış olabilir |
| `connection` | low–medium | Tarayıcı çevrimiçi/çevrimdışı oldu |

### Seçici ve Element Takibi

| Tür | Önem | Açıklama |
|-----|------|----------|
| `selector-miss` | low–high | DOM sorgusu sonuç döndürmedi (tekrar sayısıyla artar) |
| `selector-found` | low | DOM sorgusu başarılı (`data-track-success="true"` olduğunda) |
| `selector-error` | high | Geçersiz CSS seçici istisna fırlattı |
| `xpath-error` | high | Geçersiz XPath ifadesi istisna fırlattı |
| `element-inspection` | low | Otomasyon element boyutlarını/stilini okudu (kısıtlı) |
| `value-manipulation` | low | Otomasyon input/textarea/select değerini ayarladı |

### Ağ

| Tür | Önem | Açıklama |
|-----|------|----------|
| `xhr-success` | low | XHR başarıyla tamamlandı |
| `xhr-error` | high | XHR başarısız oldu (durum 0 veya >= 400) |
| `xhr-slow` | medium | XHR > 5000ms sürdü |
| `fetch-success` | low | Fetch başarıyla tamamlandı |
| `fetch-error` | high | Fetch başarısız oldu |
| `fetch-slow` | medium | Fetch > 5000ms sürdü |
| `websocket-error` | high | WebSocket bağlantı hatası |
| `websocket-unclean-close` | medium | WebSocket anormal şekilde kapandı |

### JavaScript Hataları

| Tür | Önem | Açıklama |
|-----|------|----------|
| `js-error` | high | Yakalanmamış JavaScript hatası |
| `unhandled-rejection` | high | İşlenmemiş promise reddi |
| `resource-error` | medium–high | Script, stylesheet veya resim yüklenemedi |
| `console-error` | high | `console.error()` çağrısı yakalandı |
| `console-warn` | medium | `console.warn()` çağrısı yakalandı |
| `csp-violation` | high | Content Security Policy ihlali |

### Kullanıcı Etkileşimi

| Tür | Önem | Açıklama |
|-----|------|----------|
| `user-click` | low | Kullanıcı bir elemente tıkladı |
| `programmatic-click` | low | Otomasyon `.click()` tetikledi |
| `rapid-clicks` | medium | < 80ms aralıklarla 5+ tıklama |
| `click-on-disabled` | medium | Devre dışı elemente tıklama |
| `keyboard-action` | low | Otomasyon sırasında özel tuşa basıldı (Tab, Enter, oklar, vb.) |
| `form-submission` | low | Form gönderildi |
| `form-validation-failure` | medium | Geçersiz alanlarla form gönderimi |
| `dialog-opened` | high | `alert()`, `confirm()` veya `prompt()` yakalandı |

### DOM Mutasyonları

| Tür | Önem | Açıklama |
|-----|------|----------|
| `dom-mutations` | low–high | Eklenen/kaldırılan DOM düğümlerinin toplu işlemi (eşik: 10+ değişiklik) |
| `dom-attribute-changes` | low–medium | Otomasyon sırasında ilgili özellik değişiklikleri |
| `blocking-overlay-detected` | high | Viewport'un %30'undan fazlasını kaplayan modal/overlay tespit edildi |

### Framework'e Özgü

| Tür | Önem | Framework |
|-----|------|-----------|
| `frameworks-detected` | low | Hepsi — tespit edilen framework'leri ve sürümlerini listeler |
| `react-render-error` | critical | React |
| `react-hydration-mismatch` | high | React |
| `react-key-warning` | medium | React |
| `react-error-boundary-triggered` | high | React |
| `react-root-render-crash` | critical | React |
| `angular-zone-error` | high | Angular |
| `angular-framework-error` | high | Angular (NG hata kodları) |
| `angular-change-detection-error` | high | Angular |
| `angular-zone-unstable` | high | Angular |
| `vue-error` | high | Vue 2/3 |
| `vue-warning` | medium | Vue 2/3 |
| `jquery-ajax-error` | medium–high | jQuery |
| `jquery-deferred-error` | high | jQuery |
| `nextjs-runtime-error` | critical | Next.js |
| `nuxt-error` | high | Nuxt |

### Sistem / Dahili

| Tür | Önem | Açıklama |
|-----|------|----------|
| `automation-detected` | medium–high | Otomasyon sinyalleri bulundu (Selenium, Playwright, vb.) |
| `queue-overflow` | critical | Olay kuyruğu 500'ü aştı — en eski olaylar düşürüldü |
| `batch-dropped` | critical | 3 yeniden denemeden sonra toplu iş kalıcı olarak kaybedildi |
| `session-end` | low | Sayfa kapanıyor — oturumdaki son olay |

---

## Framework Desteği

Script, **yapılandırma gerektirmeden** bu framework'leri otomatik olarak tespit eder ve bağlanır:

| Framework | Tespit Yöntemi | Yakaladıkları |
|-----------|---------------|---------------|
| **React** | DevTools hook, Fiber ağacı, DOM inceleme | Render hataları, hidrasyon uyumsuzlukları, key uyarıları, error boundary'ler |
| **Angular** (2+) | `ng` global, `ng-version` özelliği | Zone hataları, NG hata kodları, change detection hataları, kararlılık |
| **AngularJS** (1.x) | `angular.version` global | Temel hata takibi |
| **Vue 2** | `Vue.config` global | Bileşen hataları ve uyarıları |
| **Vue 3** | `__VUE__` global, `data-v-app` özelliği | App error/warn handler'ları aracılığıyla bileşen hataları ve uyarıları |
| **Next.js** | `__NEXT_DATA__` global | Runtime hataları |
| **Nuxt** | `$nuxt` global | Uygulama hataları |
| **Svelte** | `svelte-` CSS sınıfları, `__svelte` global | Yalnızca tespit |
| **SvelteKit** | `data-sveltekit` özelliği | Yalnızca tespit |
| **jQuery** | `jQuery`/`$` global | AJAX hataları, Deferred istisnaları |
| **Ember** | `Ember` global | Yalnızca tespit |

Framework tespiti `DOMContentLoaded` sonrasında (500ms gecikme) ve `window.load` üzerinde tekrar (2s gecikme) çalışarak geç yüklenen framework'leri yakalar.

---

## Gizlilik ve Güvenlik

Script varsayılan olarak agresif temizleme uygular.

### Sansürlenen Alanlar

Bu anahtarlarla ilişkili herhangi bir değer `[REDACTED]` ile değiştirilir:

`password`, `token`, `access_token`, `refresh_token`, `api_key`, `secret`, `session`, `csrf`, `credential`, `ssn`, `credit_card`, `cvv`, `pin`, `otp`, `mfa`, `encryption_key`, `birth`, `dob`, `phone`, `address` ve daha fazlası (50+ anahtar).

### URL Parametre Sansürü

Bu URL parametreleri otomatik olarak temizlenir veya sansürlenir:

`token`, `access_token`, `refresh_token`, `api_key`, `secret`, `password`, `sessionid`, `csrf`, `Authorization`, `credential`, `key`, `sig`, `signature`

### Ek Korumalar

- **E-posta maskeleme:** E-postalar `ab***@domain.com` şeklinde kısaltılır
- **Token maskeleme:** Hex dizeleri (32+ karakter) ve Base64 dizeleri (40+ karakter) `[token]` ile değiştirilir
- **Değer kısaltma:** Dize değerleri 100 karakterle sınırlandırılır
- **Şifre girişleri:** `<input type="password">` değerleri her zaman `[REDACTED]` olur
- **Gizlilik modu (varsayılan: strict):** URL sorgu dizeleri tamamen temizlenir

URL sorgu dizelerini korumak için `window.ENV_PRIVACY_MODE = 'relaxed'` ayarlayın (hassas parametreler yine de ayrı ayrı sansürlenir).

---

## Üretim Ortamı Hususları

### Kısıtlama ve Hız Sınırlama

Script, performans etkisini minimize etmek için yüksek frekanslı olayları kısıtlar:

| Mekanizma | Aralık | Amaç |
|-----------|--------|------|
| Element inceleme kısıtlaması | Element başına 1000ms | `getBoundingClientRect`, `getComputedStyle`, boyut özelliklerinden taşmayı önler |
| Değer değişikliği kısıtlaması | Element başına 500ms | Input/textarea/select değer ayarlama takibini sınırlar |
| Seçici kaçırma kısıtlaması | Seçici başına 200ms | Yoklama seçicilerinden log spam'ini önler |
| Seçici başarı kısıtlaması | Seçici başına 5000ms | Başarılı arama loglamasını sınırlar |
| Mutasyon debounce | 300ms | Hızlı DOM değişikliklerini toplar |
| Özellik değişikliği debounce | 500ms | Hızlı özellik değişikliklerini toplar |

### Kuyruk ve Toplu İşleme

| Ayar | Değer |
|------|-------|
| Maksimum toplu iş boyutu | HTTP isteği başına 100 olay |
| Maksimum kuyruk boyutu | 500 olay (taşmada en eskiler düşürülür) |
| Yeniden deneme sayısı | Üstel geri çekilme ile 3 (1s, 2s, 3s) |
| Periyodik flush | Her 5 saniyede |
| XHR zaman aşımı | 5 saniye |
| Kapanış parça boyutu | Maksimum 50KB (64KB tarayıcı limitinin altında) |

### Bellek Sızıntısı Önleme

Kısıtlama haritaları (element inceleme, değer değişiklikleri, seçici başarıları) her 60 saniyede temizlenir. Harita 500 girişi aştığında 30 saniyeden eski girdiler kaldırılır. Seçici kaçırma önbelleği 200 benzersiz seçiciyle sınırlandırılmıştır.

### Kendi Kendini Hariç Tutma

Script, sonsuz geri bildirim döngülerini önlemek için kendi `/events` isteklerini ağ izlemesinden otomatik olarak hariç tutar.

### Boşta Kalma Tespiti

30 saniye boyunca tıklama veya tuş basışı olmazsa, `page-idle` olayı tetiklenir. Bu, takılan otomatik testleri belirlemeye yardımcı olur. Aktivite zamanlayıcıyı sıfırlar.

### Overlay Tespiti

Periyodik kontrol (her 15 saniyede, `requestIdleCallback` aracılığıyla zamanlanmış) viewport'un %30'undan fazlasını kaplayan modaller, açılır pencereler ve overlay'ler için tarar. Tespit edilen overlay'ler `blocking-overlay-detected` olayı yayar.

---

## Otomasyon Tespiti

Script, birden fazla sinyal aracılığıyla otomatik tarayıcıları tanımlar:

- `navigator.webdriver` bayrağı
- Selenium/Playwright/Puppeteer/Cypress/PhantomJS global'leri
- ChromeDriver artifact'leri (`$cdc_asdjflasutopfhvcZLmcfl_`)
- HeadlessChrome / PhantomJS user-agent dizeleri
- Sıfır eklenti, sıfır dış boyut
- Yazılım WebGL renderer'ları (SwiftShader, Mesa, LLVMpipe)
- Extension ID olmadan Chrome runtime

Otomasyon tespit edildiğinde ek izleme etkinleşir:
- Element inceleme loglama (boyutlar, hesaplanmış stiller)
- Değer manipülasyonu takibi (input/textarea/select değişiklikleri)
- Klavye özel tuş takibi
- Özellik değişikliği izleme
- Programatik tıklama takibi

---

## Minimal Log Sunucusu Örneği

Henüz bir log sunucunuz yoksa, işte minimal bir Node.js implementasyonu:

```javascript
const http = require('http');

const server = http.createServer((req, res) => {
  // CORS başlıkları
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    return res.end();
  }

  if (req.method === 'POST' && req.url === '/events') {
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', () => {
      try {
        const data = JSON.parse(body);
        const events = data.events || [data];
        events.forEach(evt => {
          console.log(`[${evt.severity}] ${evt.type}: ${evt.summary || ''}`);
        });
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end('{"status":"ok"}');
      } catch (e) {
        res.writeHead(400);
        res.end('{"error":"gecersiz json"}');
      }
    });
  } else {
    res.writeHead(404);
    res.end();
  }
});

server.listen(8084, () => console.log('Log sunucusu :8084 portunda'));
```

Veya Python/Flask ile (bu projenin log sunucusuyla eşleşir):

```python
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.route('/events', methods=['POST', 'OPTIONS'])
def events():
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify(error='gecersiz json'), 400

    events = data.get('events', [data] if isinstance(data, dict) else data)
    for evt in events:
        print(f"[{evt.get('severity', '?')}] {evt.get('type')}: {evt.get('summary', '')}")

    return jsonify(status='kuyrukta'), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8084)
```

---

## Sorun Giderme

| Belirti | Neden | Çözüm |
|---------|-------|-------|
| Olay gelmiyor | Yanlış `data-logserver` URL'i | `ENV_DEBUG='true'` ile tarayıcı konsolunu kontrol edin |
| Konsolda CORS hataları | Log sunucusunda CORS başlıkları eksik | Sunucuya `Access-Control-Allow-Origin: *` ekleyin |
| Olaylar gönderildi ama Kibana'da boş | Yük formatı uyumsuzluğu | Sunucunun `{ "events": [...] }` formatını ayrıştırdığından emin olun |
| Çok fazla `selector-miss` olayı | Yoklama seçicisi bulunamadı | Elementin var olup olmadığını kontrol edin; seçiciyi ayarlayın |
| `queue-overflow` olayları | Log sunucusu erişilemez veya çok yavaş | Sunucu sağlığını kontrol edin; kuyruk boyutunu artırın |
| Uzun oturumlarda yüksek bellek kullanımı | Kısıtlama haritaları büyüyor | Script her 60s'de otomatik temizler; aşırı ise oturum süresini azaltın |
