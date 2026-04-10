# Selenium Tracker Script Karşılaştırması

## script.js vs performance.js (observe.js)

---

## Genel Bakış

| Özellik | script.js | performance.js (observe.js) |
|---------|-----------|----------------------------|
| **Dosya Boyutu** | ~55 KB (1.314 satır) | ~104 KB (2.493 satır) |
| **Mimari** | Düz, monolitik IIFE | Modüler, numaralı bölümler (27 modül) |
| **Olay İletimi** | Ateşle ve unut (olay başına anında gönderim) | Yeniden deneme + geri çekilme ile toplu kuyruk |
| **Gizlilik / Sanitizasyon** | Yok | Tam PII gizleme, URL sanitizasyonu, e-posta maskeleme, token maskeleme |
| **Framework Desteği** | Yok | React, Angular, Vue, Svelte, jQuery, Next.js, Nuxt, Ember |
| **Yapılandırma** | Sadece env değişkenleriyle hardcoded `data-logserver` | `<script>` etiketinde `data-logserver` attribute + env değişkenleri + 60+ yapılandırma anahtarı |
| **Correlation ID'ler** | Yok | Tam correlation zinciri (session, page, event, parent) |
| **Olay Özetleri** | Yok | Her olayda insan tarafından okunabilir `summary` alanı |
| **Önem Seviyeleri** | Yok | Her olayda `low` / `medium` / `high` / `critical` |

---

## Özellik Bazlı Karşılaştırma

### 1. Otomasyon Tespiti

| Özellik | script.js | performance.js |
|---------|-----------|----------------|
| `navigator.webdriver` | Evet | Evet |
| Selenium global değişkenleri | Evet (14 global) | Evet (30+ global, Playwright, Cypress, Puppeteer, PhantomJS dahil) |
| Sıfır dış boyutlar | Evet | Evet |
| Headless ekran konumu | Evet | Hayır (UA kontrolü ile kapsanıyor) |
| Sıfır canvas boyutu | Evet | Hayır |
| User-Agent sniffing (HeadlessChrome, PhantomJS, Electron) | Hayır | Evet |
| WebGL yazılım renderer tespiti | Hayır | Evet |
| Sıfır eklenti tespiti | Hayır | Evet |
| Chrome runtime anomalisi | Hayır | Evet |
| ChromeDriver `$cdc_` tespiti | Hayır | Evet |

**Kazanan: performance.js** - 2 kat daha fazla otomasyon framework'ü ve sinyal tespit eder.

---

### 2. DOM Sorgu Yakalama (Selector İzleme)

| Özellik | script.js | performance.js |
|---------|-----------|----------------|
| `querySelector` | Evet | Evet |
| `querySelectorAll` | Evet | Evet |
| `getElementById` | Evet | Evet |
| `getElementsByClassName` | Evet | Evet |
| `getElementsByTagName` | Evet | Evet |
| `getElementsByName` | Evet | Evet |
| `document.evaluate` (XPath) | Evet | Evet (iterator sarma ile geliştirilmiş) |
| Element kapsamlı `querySelector/All` | Evet | Evet |
| **Shadow DOM** sorgu izleme | Hayır | Evet |
| Selector kaçırma izleme (benzersiz ID, sayı, ilk/son deneme) | Hayır | Evet |
| Selector kaçırma önem yükseltme | Hayır | Evet (kaçırma sayısına göre low -> medium -> high) |
| Selector ayrıştırma & analiz | Hayır | Evet (tag, id, class'lar, attribute'lar, pseudo-class'lar, combinator'lar) |
| Olası sorun teşhisi | Hayır | Evet ("dinamik CSS class değişmiş olabilir" gibi akıllı ipuçları) |
| Kaçırmada parent bağlamı | Hayır | Evet (parent yolu, tag, id, class'lar) |
| Başarılı selector izleme | Hayır | Evet (`data-track-success` ile yapılandırılabilir) |
| Kısıtlanmış kaçırma loglama | Hayır | Evet (200ms aralık) |

**Kazanan: performance.js** - Sadece sorguları izlemekle kalmaz, hatalar için eyleme dönüştürülebilir debug bağlamı sağlar.

---

### 3. Element İnceleme İzleme

| Özellik | script.js | performance.js |
|---------|-----------|----------------|
| `getBoundingClientRect` | Evet (her çağrı) | Evet (kısıtlanmış, sadece otomasyon) |
| `getComputedStyle` | Evet (her çağrı) | Evet (kısıtlanmış, sadece otomasyon) |
| Layout özellikleri (offsetWidth, vb.) | 12 özellik, her erişim | 6 temel özellik, kısıtlanmış |
| `Element.matches()` | Evet | Hayır (gerekli değil - selector izleme ile kapsanıyor) |
| `Element.closest()` | Evet | Hayır |
| `getAttribute` | Evet (her çağrı) | Hayır (gizlilik endişesi) |
| `hasAttribute` | Evet (her çağrı) | Hayır |
| Kısıtlama | Yok | Element+metod başına 1000ms |
| Sadece otomasyon kapısı | Hayır (her zaman tetiklenir) | Evet (sadece `IS_AUTOMATED` olduğunda) |

**Kazanan: production için performance.js** - script.js daha fazla metod izler ama sıfır kısıtlama ile her erişimde tetiklenir, bu da devasa olay hacmine neden olur.

---

### 4. Değer Manipülasyonu İzleme

| Özellik | script.js | performance.js |
|---------|-----------|----------------|
| `HTMLInputElement.value` | Evet | Evet |
| `HTMLTextAreaElement.value` | Evet | Evet |
| `HTMLSelectElement.value` | Hayır | Evet |
| `HTMLSelectElement.selectedIndex` | Hayır | Evet |
| `HTMLInputElement.checked` | Evet | Hayır |
| `innerText` (get + set) | Evet (ikisi de) | Evet (sadece set, sadece otomasyon) |
| `textContent` (get + set) | Evet (ikisi de) | Hayır (çok gürültülü) |
| Stack trace analizi (`is_suspicious_stack`) | Evet | Hayır (gereksiz overhead) |
| Hassas alan gizleme | Hayır | Evet (password, token, API key alanları otomatik gizlenir) |
| Kısıtlama | Yok | Element+metod başına 500ms |
| Sadece otomasyon kapısı | Hayır | Evet |

**Kazanan: Berabere** - script.js daha fazla getter kapsar ama hassas veriyi açığa çıkarır. performance.js gizlilik güvenli ve production'a hazır.

---

### 5. Ağ İzleme

| Özellik | script.js | performance.js |
|---------|-----------|----------------|
| Fetch yakalama | Evet | Evet |
| XHR yakalama | Evet | Evet |
| Log endpoint hariç tutma | Evet | Evet |
| Yavaş istek tespiti | Hayır | Evet (5000ms eşik) |
| Ayrı hata/yavaş/başarı olay türleri | Hayır (tek `network-request` türü) | Evet (`xhr-error`, `xhr-slow`, `xhr-success`, `fetch-*`) |
| URL sanitizasyonu | Hayır | Evet (sorgu parametresi gizleme) |
| Önem atama | Hayır | Evet |

**Kazanan: performance.js** - İstekleri önemle birlikte hata/yavaş/başarı olarak sınıflandırır.

---

### 6. Hata İzleme

| Özellik | script.js | performance.js |
|---------|-----------|----------------|
| `window.onerror` | Evet | Evet |
| `unhandledrejection` | Evet | Evet |
| Kaynak yükleme hataları (script, img, css) | Hayır | Evet |
| `console.error` | Evet | Evet |
| `console.warn` | Evet | Evet |
| Stack trace yakalama | Evet (ham, 1000 karaktere kadar) | Evet (sanitize edilmiş) |
| CSP ihlalleri | Hayır | Evet |
| WebSocket hataları | Hayır | Evet |

**Kazanan: performance.js** - Kaynak hataları, CSP ihlalleri ve WebSocket hatalarını kapsar.

---

### 7. Kullanıcı Etkileşimi İzleme

| Özellik | script.js | performance.js |
|---------|-----------|----------------|
| Tıklama olayları | Evet | Evet |
| `isTrusted` tespiti | Evet | Evet |
| Hızlı tıklama tespiti | Evet (tıklama başına aralık kontrolü) | Evet (sayı tabanlı: 5 ve 20 eşikleri) |
| Programatik `.click()` | Evet | Evet (sadece otomasyon) |
| Devre dışı elementlere tıklama | Hayır | Evet |
| Klavye olayları | Evet (ham `keydown`) | Evet (özel tuşlar + modifier kombinasyonları, sadece otomasyon) |
| Input olayları | Evet | Hayır (değer manipülasyonu ile kapsanıyor) |
| Focus olayları | Evet | Hayır |
| Change olayları | Evet | Hayır |
| Form gönderimi | Evet | Evet (doğrulama hatası izleme ile) |
| Form doğrulama hatası (`:invalid` alanlar) | Hayır | Evet |
| Pano (copy/cut/paste) | Evet | Hayır |
| Context menu | Evet | Hayır |
| Metin seçimi | Evet | Hayır |
| Dialog yakalama (alert/confirm/prompt) | Hayır | Evet |

**Kazanan: Berabere** - script.js daha fazla ham etkileşim türü yakalar. performance.js daha eyleme dönüştürülebilir olaylar yakalar (devre dışı tıklamalar, form doğrulama, dialoglar).

---

### 8. Sayfa & Navigasyon İzleme

| Özellik | script.js | performance.js |
|---------|-----------|----------------|
| Sayfa yükleme | Evet | Evet (HTTP status koduyla) |
| Performans zamanlaması | Evet (detaylı: FP, FCP, DOM interactive, transfer boyutu) | Evet (yükleme süresi + yavaş flag) |
| Sayfa unload | Evet | Evet (parçalanmış, çoklu transport) |
| Görünürlük değişimi | Evet | Evet (kuyruk boşaltmayı tetikler) |
| Hash değişimi | Hayır | Evet |
| SPA navigasyonu (`pushState`/`replaceState`) | Hayır | Evet |
| Pencere yeniden boyutlandırma | Evet | Hayır |
| Bağlantı çevrimiçi/çevrimdışı | Evet | Evet |

**Kazanan: performance.js** - SPA navigasyon izleme modern uygulamalar için kritik.

---

### 9. Gelişmiş Özellikler (sadece performance.js)

| Özellik | Mevcut |
|---------|--------|
| **Toplu olay kuyruğu** (batch başına max 100, kuyruk max 500) | Evet |
| **Üstel geri çekilme ile yeniden deneme** (3 deneme, 1s taban) | Evet |
| **Düşürülen batch kurtarma** (sessionStorage kalıcılığı) | Evet |
| **Kuyruk taşması tespiti** | Evet |
| **Unload parçalama** (tarayıcı 64KB limiti altında 50KB parçalar) | Evet |
| **Correlation ID'ler** (session -> page -> event zinciri) | Evet |
| **Olay özetleri** (olay başına insan tarafından okunabilir) | Evet |
| **Önem sınıflandırması** (low/medium/high/critical) | Evet |
| **Gizlilik/PII sanitizasyonu** (e-postalar, token'lar, hassas alanlar) | Evet |
| **URL parametre gizleme** | Evet |
| **Framework tespiti** (React, Angular, Vue, Svelte, jQuery, Ember, Next.js, Nuxt, SvelteKit) | Evet |
| **React error boundary tespiti** (fiber tree yürüme) | Evet |
| **React hydration uyumsuzluğu tespiti** | Evet |
| **Angular Zone.js hata sarma** | Evet |
| **Angular stabilite izleme** | Evet |
| **Vue hata/uyarı handler kancalama** (v2 + v3) | Evet |
| **jQuery AJAX hata + Deferred hata izleme** | Evet |
| **Next.js runtime hata tespiti** | Evet |
| **Nuxt hata olayı izleme** | Evet |
| **DOM mutasyon izleme** (debounce edilmiş, kaldırılan element selector'larıyla) | Evet |
| **DOM attribute değişikliği izleme** (otomasyon odaklı) | Evet |
| **Overlay/modal tespiti** (>%30 kapsama ile engelleyen overlay'ler) | Evet |
| **Boşta/takılmış sayfa tespiti** (30s eşik) | Evet |
| **Throttle map temizliği** (uzun oturumlarda bellek sızıntısını önler) | Evet |
| **`data-logserver` script attribute** yapılandırması | Evet |
| **`pagehide` olayı** işleme (iOS/Safari) | Evet |
| **Periyodik kuyruk boşaltma** (her 5s) | Evet |

---

## Performans Etkisi Karşılaştırması

| Metrik | script.js | performance.js |
|--------|-----------|----------------|
| **Sayfa yüklemesi başına olaylar** (tipik) | Çok Yüksek (yüzlerce-binlerce) | Orta (onlarca-yüzlerce) |
| **Ağ istekleri** | Olay başına 1 XHR (toplu yok) | Batch başına 1 XHR (100 olaya kadar) |
| **DOM okumalarında CPU overhead** | Yüksek (her `getAttribute`, `innerText` get, `textContent` get, 12 layout özelliği yakalar) | Düşük (kısıtlanmış, otomasyon kapılı) |
| **Bellek kullanımı** | Düşük (kuyruk yok) ama yüksek ağ | Sınırlı (500 olay kuyruğu, throttle map temizliği) |
| **Otomatik olmayan kullanıcılar üzerindeki etki** | Otomatik ile aynı (her zaman yakalar) | Minimal (çoğu izleme otomasyon kapılı) |
| **Uzun oturum stabilitesi** | Bellek sızıntısı riski (temizlik yok) | Stabil (periyodik throttle map temizliği) |
| **Unload güvenilirliği** | sendBeacon veya fetch | sendBeacon -> fetch fallback, parçalanmış, `pagehide` + `visibilitychange` |

---

## Production Hazırlık Karşılaştırması

| Kriter | script.js | performance.js |
|--------|-----------|----------------|
| **PII Koruması** | :x: Yok - ham değerler, e-postalar, token'lar açık | :white_check_mark: Tam gizleme (50+ hassas anahtar, e-posta maskeleme, token maskeleme) |
| **GDPR/Gizlilik Uyumu** | :x: Ham metin içeriği, attribute değerleri, pano verisi yakalar | :white_check_mark: Gizlilik modu, yapılandırılabilir gizleme |
| **Ağ Verimliliği** | :x: Olay başına 1 istek | :white_check_mark: Toplu (batch başına 100'e kadar) yeniden deneme ile |
| **Hata Kurtarma** | :x: Ağ hatasında olaylar kaybolur | :white_check_mark: Yeniden deneme + sessionStorage kurtarma |
| **CPU Etkisi** | :x: Yüksek frekanslı yakalamalarda kısıtlama yok | :white_check_mark: Kısıtlanmış, otomasyon kapılı |
| **Bellek Güvenliği** | :x: Temizlik mekanizması yok | :white_check_mark: Sınırlı kuyruk, throttle map temizliği |
| **Olay Hacmi Kontrolü** | :x: Tekilleştirme veya kısıtlama yok | :white_check_mark: Kısıtlanmış loglama, debounce edilmiş mutasyonlar |
| **Hata Yönetimi** | :warning: Sessiz catch blokları | :white_check_mark: Sessiz catch + kuyruk taşması uyarıları |
| **Yapılandırma** | :x: Sadece env değişkenleri | :white_check_mark: Script attribute + env değişkenleri + 60+ yapılandırma anahtarı |
| **Debug Desteği** | :warning: Sadece ham olaylar | :white_check_mark: Özetler, önem, correlation ID'ler, olası sorun ipuçları |

---

## Her Script Ne Zaman Kullanılmalı

### script.js Kullanın:
- **Hızlı prototip** veya kavram kanıtı gerektiğinde
- Ortam **tamamen kontrollü** olduğunda (dahili QA lab, gerçek kullanıcı verisi yok)
- **Maksimum ham veri yakalama** istediğinizde (pano, metin seçimi, context menu, her attribute erişimi)
- Ağ bant genişliği endişe olmadığında
- Hedef sayfa düşük DOM aktivitesiyle basit olduğunda
- PII açığa çıkmasını önemsemediğinizde (gerçek kullanıcı verisi yok)

### performance.js Kullanın:
- Selenium/otomasyon testlerinin **production izlemesi**
- **CI/CD pipeline'ları** - performans önemli
- Hedef uygulama **modern framework'ler** kullanıyorsa (React, Angular, Vue)
- **Gizlilik uyumu** gerekli (GDPR, SOC2, vb.)
- **Eyleme dönüştürülebilir debug verisi** gerektiğinde (sadece ham olaylar değil)
- Testler **uzun oturumlar** çalıştırıyorsa (bellek güvenliği önemli)
- **Ağ güvenilirliği** belirsiz olduğunda (yeniden deneme + kurtarma gerekli)
- **Engelleyen overlay'ler, takılmış sayfalar veya form doğrulama sorunları** tespit etmeniz gerektiğinde
- İstemci tarafı yönlendirmeli **SPA uygulamaları**

---

## Nihai Değerlendirme

| Kullanım Durumu | Önerilen Script | Neden |
|-----------------|-----------------|-------|
| **Production CI/CD** | **performance.js** | Toplu işleme, kısıtlama, gizlilik, bellek güvenliği |
| **Gerçek kullanıcılarla production** | **performance.js** | PII gizleme, otomatik olmayan trafikte minimal CPU etkisi |
| **Hızlı yerel debug** | script.js | Daha fazla ham veri, anlaması daha basit |
| **React/Angular/Vue uygulamaları** | **performance.js** | Framework'e özgü hata izleme |
| **SPA uygulamaları** | **performance.js** | pushState/replaceState izleme |
| **Yüksek trafikli sayfalar** | **performance.js** | Toplu iletim, sınırlı kuyruk, kısıtlama |
| **Güvenlik denetimi (ham yakalama)** | script.js | Pano, seçim, ham attribute'lar dahil her şeyi yakalar |
| **Uzun süren test paketleri** | **performance.js** | Bellek sızıntısı önleme, boşta tespiti |
| **Tutarsız test araştırması** | **performance.js** | Selector kaçırma analizi, olası sorun ipuçları, correlation ID'ler |
| **Genel öneri** | **performance.js** | 10 kategorinin 9'unda üstün |

---

## Geçiş Notları (script.js -> performance.js)

script.js'den performance.js'e geçiş yapıyorsanız, **script.js'de olup performance.js'de OLMAYAN** şu özelliklere dikkat edin:
1. Pano olayı izleme (copy/cut/paste)
2. Context menu izleme
3. Metin seçimi izleme
4. Pencere yeniden boyutlandırma izleme
5. `textContent` getter yakalama
6. `getAttribute` / `hasAttribute` yakalama
7. `Element.matches()` / `Element.closest()` yakalama
8. `HTMLInputElement.checked` izleme
9. Detaylı performans paint metrikleri (FP, FCP, DOM interactive, transfer boyutu)
10. `MutationObserver` constructor sarma (performance.js bunun yerine kendi observer'ını kullanır)

Bunlar kasıtlı ihmallerdir - production'da minimum debug değeriyle aşırı gürültü üretirler.
