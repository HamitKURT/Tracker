# Selenium İzleme — Olay Analiz Kılavuzu

`performance.js` tarafından desteklenen tarayıcı telemetri pipeline'ı için kapsamlı alan referansı.

---

## Mimari

```
Tarayıcı (performance.js)
    │  POST /events (toplu JSON, Content-Type: text/plain)
    ▼
Log Sunucusu (Flask :8084)
    │  Her olay için LPUSH
    ▼
Redis Kuyruğu ("events_main")
    │  BRPOP (50'lik batch, 2s pencere)
    ▼
Log Worker (Python)
    │  elasticsearch-py ile bulk indeks
    ▼
Elasticsearch (:9200, indeks: "selenium-events")
    │
    ▼
Kibana (:5601) — 15 bölümlü kapsamlı dashboard
```

---

## Ortak Alanlar (TÜM Olaylarda Mevcut)

Bu alanlar `enqueue()` fonksiyonu ve log worker'ın `_ctx` birleştirmesi tarafından enjekte edilir:

| Alan | ES Tipi | Kaynak | Açıklama |
|------|---------|--------|----------|
| `@timestamp` | date | log_worker | Sunucu tarafı UTC timestamp (yetkili) |
| `timestamp` | date | _ctx | İstemci tarafı ISO 8601 timestamp |
| `type` | keyword | event | Olay türü tanımlayıcı (aşağıya bakın) |
| `severity` | keyword | event | `low` / `medium` / `high` / `critical` |
| `sessionId` | keyword | enqueue | Tarayıcı oturum ID'si (sayfa yüklemeleri arasında kalır) |
| `pageId` | keyword | _ctx | Sayfa yüklemesi başına benzersiz ID |
| `correlationId` | keyword | enqueue | Bir zincirdeki ilgili olayları bağlar |
| `eventId` | keyword | enqueue | Olay başına benzersiz ID |
| `url` | keyword | _ctx | Temizlenmiş mevcut sayfa URL'i |
| `pageUrl` | keyword | enqueue | `url`'in kopyası (Kibana uyumluluğu) |
| `uptime` | long | _ctx | Sayfa yüklemesinin başlangıcından bu yana milisaniye |
| `isAutomated` | boolean | _ctx | Otomasyon sinyalleri tespit edildiyse `true` |
| `isAutomationDetected` | boolean | enqueue | `isAutomated` ile aynı |
| `userAgent` | text | _ctx | Tarayıcı user agent string'i |
| `summary` | keyword | enqueue | İnsan tarafından okunabilir olay özeti |
| `parentId` | keyword | enqueue | Opsiyonel parent correlation ID |
| `_ctx` | object (devre dışı) | enqueue | Ham context nesnesi (aranamaz) |

---

## Olay Türü Referansı

### 1. Otomasyon Tespiti

#### `automation-detected`
**Önem:** `high` (3+ sinyal) veya `medium`

Otomasyon işaretleri bulunduğunda sayfa yüklemesinde bir kez tetiklenir.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `signals` | keyword[] | Tespit sinyalleri (örn. `navigator.webdriver`, `window.Cypress`, `headless-chrome-ua`) |

**Dashboard:** Bölüm 11 — Otomasyon Tespiti

---

### 2. Selector & XPath Olayları

#### `selector-miss`
**Önem:** `high` (5+ kaçırma), `medium` (2+), `low` (ilk)

CSS selector veya XPath sorgusu sonuç döndürmedi.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `uniqueId` | keyword | `method:selector` bileşik anahtar |
| `method` | keyword | `querySelector`, `querySelectorAll`, `getElementById`, `getElementsByClassName`, `getElementsByTagName`, `getElementsByName`, `xpath`, `xpath-iterator` |
| `selector` | keyword | CSS selector veya XPath ifadesi |
| `selectorPath` | keyword | Basitleştirilmiş insan tarafından okunabilir selector |
| `xpath` | keyword | XPath ifadesi (sadece XPath sorguları) |
| `missCount` | integer | Bu selector için kümülatif kaçırma sayısı |
| `firstAttempt` | long | İlk kaçırmanın timestamp'i |
| `lastAttempt` | long | En son kaçırmanın timestamp'i |
| `timeSinceFirst` | long | İlk ve son deneme arasındaki ms |
| `isRepeatedFailure` | boolean | `missCount > 1` ise `true` |
| `selectorDetails` | object | Ayrıştırılmış selector: `raw`, `tagName`, `id`, `classes`, `attributes`, `pseudoClasses`, `combinators` |
| `xpathAnalysis` | object | XPath analizi: `containsText`, `containsAttribute`, `containsDescendant`, `containsAxis` |
| `parentPath` | keyword | Parent element CSS yolu |
| `parentTagName` | keyword | Parent element tag'i |
| `parentId` | keyword | Parent element ID'si |
| `parentClasses` | keyword[] | Parent element class'ları |
| `likelyIssue` | keyword | Tanılama ipucu |

**Dashboard:** Bölüm 6 — Selector'lar & XPath

#### `selector-found`
**Önem:** `low`

Element başarıyla bulundu (opsiyonel, `data-track-success="true"` veya `ENV_TRACK_SUCCESS` ile).

| Alan | Tip | Açıklama |
|------|-----|----------|
| `uniqueId` | keyword | `method:selector` bileşik anahtar |
| `method` | keyword | Kullanılan sorgu metodu |
| `selector` | keyword | CSS selector |
| `selectorPath` | keyword | Basitleştirilmiş selector |
| `matchCount` | integer | Eşleşen element sayısı |

**Dashboard:** Bölüm 6 — Selector'lar & XPath

#### `selector-error`
**Önem:** `high`

CSS selector sözdizimi hatası exception fırlattı.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `method` | keyword | Başarısız olan sorgu metodu |
| `selector` | keyword | Geçersiz selector |
| `message` | text | Hata mesajı |

**Dashboard:** Bölüm 6 — Selector'lar & XPath

#### `xpath-error`
**Önem:** `high`

Geçersiz XPath ifadesi exception fırlattı.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `xpath` | keyword | XPath ifadesi |
| `expression` | keyword | `xpath` ile aynı |
| `message` | text | Hata mesajı |

**Dashboard:** Bölüm 6 — Selector'lar & XPath

#### `element-inspection`
**Önem:** ayarlanmamış (bilgilendirme)

Otomasyon framework'ü element boyutlarına veya stillerine erişti (element başına saniyede 1 olay ile kısıtlanmış).

| Alan | Tip | Açıklama |
|------|-----|----------|
| `method` | keyword | `getBoundingClientRect`, `getComputedStyle`, `offsetWidth`, `offsetHeight`, `clientWidth`, `clientHeight`, `scrollWidth`, `scrollHeight` |
| `xpath` | keyword | Element tanımlayıcı anahtar |
| `success` | boolean | Çağrının başarılı olup olmadığı |
| `details` | object | Metoda özel: `{width, height}`, `{pseudo}`, veya `{value}` |

**Dashboard:** Bölüm 14 — Element İnceleme & Sayfa Sağlığı

---

### 3. Değer Manipülasyonu

#### `value-manipulation`
**Önem:** ayarlanmamış (bilgilendirme)

Otomasyon sırasında Input/textarea/select değeri programatik olarak değiştirildi (element başına 500ms ile kısıtlanmış).

| Alan | Tip | Açıklama |
|------|-----|----------|
| `method` | keyword | `input-value`, `textarea-value`, `select-value`, `select-selectedIndex`, `innerText` |
| `xpath` | keyword | Element tanımlayıcı anahtar |
| `details` | object | `{input_type, value_length, value_preview}` veya `{selectedIndex}` |

**Dashboard:** Bölüm 15 — Taşıma Sağlığı & Oturum Yaşam Döngüsü (Değer Manipülasyonları tablosu)

---

### 4. Ağ Olayları

#### `xhr-success` / `fetch-success`
**Önem:** `low`

HTTP isteği başarıyla tamamlandı (status < 400).

#### `xhr-error` / `fetch-error`
**Önem:** `high`

HTTP isteği başarısız oldu (status >= 400 veya ağ hatası).

#### `xhr-slow` / `fetch-slow`
**Önem:** `medium`

HTTP isteği 5000ms eşiğini aştı.

**Tüm ağ olayları için ortak alanlar:**

| Alan | Tip | Açıklama |
|------|-----|----------|
| `method` | keyword | HTTP verb (GET, POST, vb.) |
| `url` | keyword | Temizlenmiş istek URL'i |
| `status` | keyword | HTTP status kodu |
| `duration` | long | Milisaniye cinsinden istek süresi |
| `message` | text | Hata mesajı (sadece hatalar) |

**Dashboard:** Bölüm 5 — Ağ

---

### 5. JavaScript Hataları

#### `js-error`
**Önem:** `high`

Yakalanmamış JavaScript hatası (window.onerror).

| Alan | Tip | Açıklama |
|------|-----|----------|
| `message` | text | Hata mesajı |
| `filename` | keyword | Kaynak dosya URL'i |
| `lineno` | integer | Satır numarası |
| `colno` | integer | Sütun numarası |

**Dashboard:** Bölüm 4 — JavaScript Hataları

#### `resource-error`
**Önem:** `high` (script'ler), `medium` (diğerleri)

Harici kaynak yüklenemedi.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `tagName` | keyword | `SCRIPT`, `LINK`, `IMG` |
| `src` | keyword | Kaynak URL'i |
| `status` | keyword | Her zaman `0` |
| `message` | text | `"Failed to load resource"` |

**Dashboard:** Bölüm 5 — Ağ (Başarısız Ağ İstekleri)

#### `console-error`
**Önem:** `high`

`console.error()` çağrıldı.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `args` | text | Temizlenmiş konsol argümanları |
| `message` | text | Birleştirilmiş argümanlar |

**Dashboard:** Bölüm 4 — Konsol Hataları

#### `console-warn`
**Önem:** `medium`

`console.warn()` çağrıldı.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `args` | text | Temizlenmiş konsol argümanları |
| `message` | text | Birleştirilmiş argümanlar |

**Dashboard:** Bölüm 4 — Konsol Uyarıları

#### `unhandled-rejection`
**Önem:** `high`

İşlenmemiş Promise rejection.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `message` | text | Rejection nedeni |

**Dashboard:** Bölüm 4 — İşlenmemiş Promise Rejection'ları

---

### 6. Kullanıcı Etkileşimleri

#### `user-click`
**Önem:** `low`

Kullanıcı bir elemente tıkladı (isTrusted=true).

| Alan | Tip | Açıklama |
|------|-----|----------|
| `selector` | keyword | `#id` veya `tagname` |
| `tagName` | keyword | Element tag'i |
| `textContent` | text | Kesilmiş element metni |
| `isTrusted` | boolean | Gerçek tıklamalar için her zaman `true` |

#### `programmatic-click`
**Önem:** `low`

`element.click()` otomasyon yoluyla çağrıldı.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `selector` | keyword | Tıklanan elementin XPath'i |
| `tagName` | keyword | Element tag'i |

#### `rapid-clicks`
**Önem:** `medium`

80ms aralıklarla 5+ veya 20+ tıklama.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `count` | integer | Hızlı tıklama sayısı |
| `interval` | long | Tıklamalar arası süre (ms) |

#### `click-on-disabled`
**Önem:** `medium`

Devre dışı veya `aria-disabled="true"` elemente tıklama.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `selector` | keyword | Element selector'ı |

**Dashboard:** Bölüm 7 — Kullanıcı Etkileşimleri & Formlar

---

### 7. Dialog Olayları

#### `dialog-opened`
**Önem:** `high`

Tarayıcı dialogu yakalandı (alert, confirm veya prompt).

| Alan | Tip | Açıklama |
|------|-----|----------|
| `dialogType` | keyword | `alert`, `confirm` veya `prompt` |
| `message` | text | Dialog mesaj metni |
| `result` | boolean | Kullanıcının confirm yanıtı (sadece confirm) |
| `hasResult` | boolean | Kullanıcının girdi sağlayıp sağlamadığı (sadece prompt) |

**Dashboard:** Bölüm 13 — Dialoglar & Klavye Aksiyonları

---

### 8. Klavye Olayları

#### `keyboard-action`
**Önem:** `low`

Otomasyon sırasında özel tuş veya modifier kombinasyonu basıldı.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `key` | keyword | Tuş adı (`Tab`, `Enter`, `Escape`, vb.) |
| `keyCode` | keyword | Tuş kodu (`KeyA`, `Enter`, vb.) |
| `modifiers` | keyword[] | `Ctrl`, `Alt`, `Shift`, `Meta` |
| `targetElement` | keyword | Element tanımlayıcı |
| `targetTagName` | keyword | Hedef element tag'i |
| `isTrusted` | boolean | Olayın kullanıcı tarafından başlatılıp başlatılmadığı |

**Dashboard:** Bölüm 13 — Dialoglar & Klavye Aksiyonları

---

### 9. Form Olayları

#### `form-submission`
**Önem:** `low`

Form başarıyla gönderildi.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `formAction` | keyword | Temizlenmiş form action URL'i |
| `method` | keyword | Form metodu (GET/POST) |

#### `form-validation-failure`
**Önem:** `medium`

Form gönderimde `:invalid` alanlara sahip.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `formAction` | keyword | Temizlenmiş form action URL'i |
| `invalidFields` | object[] | `[{name, type}, ...]` (10'a kadar) |

**Dashboard:** Bölüm 7 — Kullanıcı Etkileşimleri & Formlar

---

### 10. Sayfa Yaşam Döngüsü

#### `page-load`
**Önem:** `high` (HTTP 400+ veya >10s), `medium` (>5s), `low`

Performans zamanlaması ile sayfa yüklemesi tamamlandı.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `loadTime` | long | Toplam yükleme süresi (ms) |
| `httpStatus` | integer | HTTP yanıt durumu (Chrome 109+) |
| `slow` | boolean | `loadTime > 5000ms` ise `true` |

#### `page-idle`
**Önem:** `high`

30+ saniye kullanıcı aktivitesi yok — test takılmış olabilir.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `idleMs` | long | Boşta kalma süresi milisaniye |

#### `hashchange`
**Önem:** `low`

URL hash değişti.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `from` | keyword | Önceki URL |
| `to` | keyword | Yeni URL |

#### `pushState` / `replaceState`
**Önem:** `low`

History API ile SPA navigasyonu.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `url` | keyword | Yeni URL |

#### `connection`
**Önem:** `medium` (çevrimdışı), `low` (çevrimiçi)

Tarayıcı çevrimiçi veya çevrimdışı oldu.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `status` | keyword | `online` veya `offline` |

**Dashboard:** Bölüm 8 — Navigasyon & Sayfa Yüklemeleri, Bölüm 14 (boşta), Bölüm 15 (bağlantı)

---

### 11. DOM Mutasyonları

#### `dom-mutations`
**Önem:** `high` (>20 değişiklik), `medium` (>5), `low`

Önemli DOM düğüm ekleme/kaldırma (eşik: 10+ düğüm).

| Alan | Tip | Açıklama |
|------|-----|----------|
| `nodesAdded` | integer | Eklenen düğümler |
| `nodesRemoved` | integer | Kaldırılan düğümler |
| `removedElements` | keyword[] | Kaldırılan elementlerin selector'ları (10'a kadar) |
| `totalRemoved` | integer | Toplam kaldırılan sayısı |
| `warning` | keyword | Büyük değişiklikler hakkında uyarı |

#### `dom-attribute-changes`
**Önem:** `medium` (>10 değişiklik), `low`

Otomasyon sırasında ilgili DOM özellikleri değişti.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `changes` | object[] | `[{attribute, target, oldValue, newValue, timestamp}]` (30'a kadar) |
| `totalChanges` | integer | Toplam özellik değişiklikleri |
| `automationContext` | boolean | Otomasyonda olup olmadığı |

**Dashboard:** Bölüm 9 — DOM Mutasyonları

---

### 12. Güvenlik Olayları

#### `csp-violation`
**Önem:** `high`

Content Security Policy ihlali.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `blockedURI` | keyword | Engellenen kaynak URI'si |
| `violatedDirective` | keyword | İhlal edilen CSP direktifi |
| `originalPolicy` | keyword | Tam CSP politikası (kesilmiş) |

#### `websocket-error`
**Önem:** `high`

WebSocket bağlantısı başarısız oldu.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `url` | keyword | WebSocket URL'i |

#### `websocket-unclean-close`
**Önem:** `medium`

WebSocket anormal şekilde kapandı.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `url` | keyword | WebSocket URL'i |
| `code` | integer | Kapatma kodu |
| `reason` | text | Kapatma nedeni |

#### `blocking-overlay-detected`
**Önem:** `high`

Viewport'un %30'undan fazlasını kaplayan sabit/mutlak overlay (z-index >= 900).

| Alan | Tip | Açıklama |
|------|-----|----------|
| `overlay` | object | `{selector, position, zIndex, coverage, text}` |

**Dashboard:** Bölüm 10 — Güvenlik Olayları

---

### 13. Framework Tespiti

#### `frameworks-detected`
**Önem:** `low`

Sayfa yüklemesinde frontend framework'leri tespit edildi.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `frameworks` | object[] | `[{name, version, source}]` |

Tespit edilen framework'ler: React, Next.js, Angular, AngularJS, Zone.js, Vue 2/3, Nuxt, Svelte, SvelteKit, jQuery, Ember, React Native Web.

**Dashboard:** Bölüm 12 — Framework Hataları

---

### 14. React Hataları

#### `react-error-boundary-triggered`
**Önem:** `high`

React error boundary bir hata yakaladı.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `componentName` | keyword | Bileşen adı |
| `componentStack` | keyword | Bileşen hiyerarşisi |

#### `react-render-error`
**Önem:** `critical`

Konsol üzerinden tespit edilen React render hatası.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `message` | text | Hata mesajı |

#### `react-hydration-mismatch`
**Önem:** `high`

Hydration sırasında sunucu/istemci HTML uyumsuzluğu.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `message` | text | Uyumsuzluk detayları |

#### `react-key-warning`
**Önem:** `medium`

Liste render'ında eksik benzersiz key.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `message` | text | Uyarı mesajı |

#### `react-function-component-warning`
**Önem:** `low`

Function component kullanım uyarısı.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `message` | text | Uyarı mesajı |

#### `react-root-render-crash`
**Önem:** `critical`

ReactDOM.createRoot().render() hata fırlattı.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `message` | text | Hata mesajı |
| `stack` | text | Stack trace |

**Dashboard:** Bölüm 12 — React Hataları tablosu

---

### 15. Angular Hataları

#### `angular-zone-error`
**Önem:** `high`

Angular Zone içinde hata.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `zoneName` | keyword | Zone adı |
| `source` | keyword | Hata kaynağı |
| `message` | text | Hata mesajı |
| `stack` | text | Stack trace |

#### `angular-framework-error`
**Önem:** `high`

NG hata koduyla Angular hatası.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `errorCode` | keyword | örn. `NG0300`, `NG0100` |
| `message` | text | Hata mesajı |

#### `angular-change-detection-error`
**Önem:** `high`

`ExpressionChangedAfterItHasBeenChecked` hatası.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `message` | text | Hata mesajı |

#### `angular-zone-unstable`
**Önem:** `high`

Angular zone stabil değil (bekleyen async işlemler).

| Alan | Tip | Açıklama |
|------|-----|----------|
| `pendingRequests` | integer | Bekleyen istek sayısı |

**Dashboard:** Bölüm 12 — Angular Hataları tablosu

---

### 16. Vue Hataları

#### `vue-error`
**Önem:** `high`

Vue bileşen hatası (Vue 2 veya 3).

| Alan | Tip | Açıklama |
|------|-----|----------|
| `message` | text | Hata mesajı |
| `stack` | text | Stack trace |
| `info` | keyword | Hata bağlam bilgisi |
| `componentName` | keyword | Bileşen adı |

#### `vue-warning`
**Önem:** `medium`

Vue uyarısı.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `message` | text | Uyarı mesajı |
| `componentName` | keyword | Bileşen adı |
| `trace` | keyword | Stack trace |

**Dashboard:** Bölüm 12 — Vue Hataları & Uyarıları tablosu

---

### 17. jQuery Hataları

#### `jquery-ajax-error`
**Önem:** `high` (5xx), `medium` (diğer)

jQuery `$.ajax()` isteği başarısız oldu.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `url` | keyword | İstek URL'i |
| `method` | keyword | HTTP metodu |
| `status` | keyword | HTTP status |
| `errorThrown` | keyword | Hata string'i |

#### `jquery-deferred-error`
**Önem:** `high`

jQuery Deferred exception.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `message` | text | Hata mesajı |
| `stack` | text | Stack trace |

**Dashboard:** Bölüm 12 — Framework Olayları

---

### 18. Meta Framework Hataları

#### `nextjs-runtime-error`
**Önem:** `critical`

Next.js işlenmemiş runtime hatası.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `message` | text | Hata mesajı |

#### `nuxt-error`
**Önem:** `high`

Nuxt uygulama hatası.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `message` | text | Hata mesajı |
| `statusCode` | integer | HTTP status kodu |

**Dashboard:** Bölüm 12 — Framework Olayları

---

### 19. Taşıma & Kuyruk Olayları

#### `queue-overflow`
**Önem:** `critical`

Olay kuyruğu maksimum boyutu aştı; olaylar düşürüldü.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `droppedCount` | integer | Düşürülen olaylar |
| `queueSize` | integer | Maksimum kuyruk boyutu |

#### `batch-dropped`
**Önem:** `critical`

Yeniden deneme tükenmesinden sonra olay batch'i kalıcı olarak kayboldu.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `droppedCount` | integer | Batch'teki olaylar |
| `retryAttempts` | integer | Denenen yeniden denemeler |

#### `session-end`
**Önem:** `low`

Tarayıcı oturumu sonlanıyor (sayfa unload).

| Alan | Tip | Açıklama |
|------|-----|----------|
| `reason` | text | Tetikleyici olay (`beforeunload`, `pagehide`, `visibilitychange`) |
| `totalEventsInQueue` | integer | Hâlâ kuyrukta olan olaylar |

**Dashboard:** Bölüm 15 — Taşıma Sağlığı & Oturum Yaşam Döngüsü

---

## Önem Kılavuzu

| Önem | Anlam | Örnekler |
|------|-------|----------|
| `critical` | Veri kaybı veya uygulama çökmesi | `queue-overflow`, `react-render-error`, `react-root-render-crash`, `nextjs-runtime-error`, `batch-dropped` |
| `high` | Fonksiyonel başarısızlık veya hata | `js-error`, `xhr-error`, `selector-error`, `csp-violation`, `page-idle`, `dialog-opened` |
| `medium` | Uyarı veya düşük performans | `console-warn`, `xhr-slow`, `rapid-clicks`, `form-validation-failure`, `websocket-unclean-close` |
| `low` | Bilgilendirme / normal aktivite | `user-click`, `page-load` (hızlı), `form-submission`, `selector-found`, `frameworks-detected` |

---

## Kibana Dashboard Bölümleri

| # | Bölüm | Olay Türleri |
|---|-------|-------------|
| 1 | Özet KPI'lar | Tüm olaylar, hatalar, oturumlar, URL'ler, yüksek/kritik önem |
| 2 | Genel Zaman Çizelgeleri | Zaman içinde tüm olaylar + hata olayları |
| 3 | Olay & Önem Dağılımı | Türe göre (pasta), öneme göre (donut), üst olaylar tablosu, üst URL'ler |
| 4 | JavaScript Hataları | `js-error`, `unhandled-rejection`, `console-error`, `console-warn` |
| 5 | Ağ | `xhr-*`, `fetch-*`, `resource-error` |
| 6 | Selector'lar & XPath | `selector-miss`, `selector-found`, `selector-error`, `xpath-error` |
| 7 | Kullanıcı Etkileşimleri & Formlar | `user-click`, `programmatic-click`, `rapid-clicks`, `click-on-disabled`, `form-submission`, `form-validation-failure`, `value-manipulation` |
| 8 | Navigasyon & Sayfa Yüklemeleri | `page-load`, `hashchange`, `pushState`, `replaceState` |
| 9 | DOM Mutasyonları | `dom-mutations`, `dom-attribute-changes` |
| 10 | Güvenlik | `csp-violation`, `websocket-error`, `websocket-unclean-close`, `blocking-overlay-detected` |
| 11 | Otomasyon Tespiti | `automation-detected`, `programmatic-click`, `rapid-clicks` |
| 12 | Framework Hataları | `frameworks-detected`, `react-*`, `angular-*`, `vue-*`, `jquery-*`, `nextjs-*`, `nuxt-*` |
| 13 | Dialoglar & Klavye | `dialog-opened`, `keyboard-action` |
| 14 | Element İnceleme & Sayfa Sağlığı | `element-inspection`, `page-idle` |
| 15 | Taşıma & Oturumlar | `queue-overflow`, `batch-dropped`, `session-end`, `connection` |

---

## KQL Sorgu Örnekleri

### Tüm yüksek önemli hataları bul
```
severity: "high" OR severity: "critical"
```

### Belirli bir dosyadaki JS hataları
```
type: "js-error" AND filename: *login*
```

### Belirli bir sayfa için başarısız selector'lar
```
type: "selector-miss" AND url: *dashboard*
```

### Endpoint'e göre ağ hataları
```
(type: "xhr-error" OR type: "fetch-error") AND url: */api/*
```

### Belirli bir oturum için tüm olaylar
```
sessionId: "abcd-1234"
```

### Sadece otomasyon tespit edilen oturumlar
```
isAutomated: true
```

### Yavaş sayfa yüklemeleri
```
type: "page-load" AND slow: true
```

### Bileşene göre React hataları
```
type: "react-error-boundary-triggered" AND componentName: *
```

### CSP ihlalleri
```
type: "csp-violation" AND violatedDirective: *script*
```

### Takılmış testler (sayfa boşta)
```
type: "page-idle" AND idleMs > 60000
```

### Veri kaybı olayları
```
type: "queue-overflow" OR type: "batch-dropped"
```

### Dialog etkileşimleri
```
type: "dialog-opened" AND dialogType: "confirm"
```

### Form doğrulama hataları
```
type: "form-validation-failure"
```

### Framework tespiti
```
type: "frameworks-detected"
```

### DOM mutasyon fırtınaları
```
type: "dom-mutations" AND nodesRemoved > 20
```
