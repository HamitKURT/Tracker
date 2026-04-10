# Web Uygulaması Entegrasyonu - Sorun Giderme

Telemetri script'i entegrasyonunda sık karşılaşılan sorunlar ve çözümler.

---

## Olaylar Gönderilmiyor

### Belirtiler
- Network sekmesinde `/events` adresine POST istekleri yok
- Dashboard'larda veri görünmüyor

### Çözümler

**1. Script etiketinin mevcut olduğunu kontrol edin**
```html
<!-- </body> kapanış etiketinden önce olmalı -->
<script src="/performance.js" data-logserver="http://[IP_ADDRESS]:8084"></script>
```

**2. `data-logserver` özelliğini doğrulayın**
- Tam URL içermeli, `http://` ile başlamalı
- Port numarası dahil olmalı: `:8084`
- IP adresi doğru olmalı (sistem yöneticisinden alın)

**3. IP erişilebilirliğini test edin**

Tarayıcınızı açın ve şu adrese gidin:
```
http://[IP_ADDRESS]:8084/health
```

Şöyle bir JSON yanıt görmelisiniz:
```json
{"status": "healthy", "redis": "connected"}
```

Bu çalışmıyorsa:
- Log sunucusu çalışmıyor olabilir
- Bağlantıyı engelleyen bir güvenlik duvarı olabilir
- Sistem yöneticinizle iletişime geçin

---

## Script Yüklenmiyor (404 Hatası)

### Belirtiler
- Tarayıcı konsolu şunu gösteriyor: `GET /performance.js 404 (Not Found)`
- Telemetri verisi gönderilmiyor

### Çözümler

**1. Dosya yolunu kontrol edin**

`performance.js` dosyasının statik dosyalar klasörünüzde var olduğunu doğrulayın:
```bash
ls -la /yol/sizin/static/klasorunuz/performance.js
```

**2. Statik dosyaların sunulduğunu doğrulayın**

Web sunucunuzun statik dosyaları doğru dizinden sunacak şekilde yapılandırıldığından emin olun.

**3. Script src yolunu kontrol edin**

HTML'deki yol, dosyanın bulunduğu konumla eşleşmeli:
```html
<!-- Dosya /static/js/performance.js konumundaysa -->
<script src="/static/js/performance.js" data-logserver="http://[IP_ADDRESS]:8084"></script>

<!-- Dosya /assets/performance.js konumundaysa -->
<script src="/assets/performance.js" data-logserver="http://[IP_ADDRESS]:8084"></script>
```

---

## CORS Hataları

### Belirtiler
Tarayıcı konsolunda şöyle hatalar görünüyor:
```
Access to XMLHttpRequest at 'http://[IP]:8084/events' from origin 'http://siteniz.com'
has been blocked by CORS policy
```

### Çözüm

**Sistem yöneticinizle iletişime geçin.** Log sunucusunu sizin alan adınızdan gelen isteklere izin verecek şekilde yapılandırmaları gerekiyor.

Onlara şunları sağlayın:
- Web uygulamanızın alan adı (örn: `https://uygulamam.example.com`)
- Standart dışı port kullanıyorsanız port numarası (örn: geliştirme için `http://localhost:3000`)

---

## performance.js'den Kaynaklanan Konsol Hataları

### Belirtiler
Konsolda `performance.js` ile ilgili JavaScript hataları görünüyor

### Çözümler

**1. Tarayıcı uyumluluğunu kontrol edin**

Script modern bir tarayıcı gerektirir:
- Chrome 70+
- Firefox 65+
- Safari 12+
- Edge 79+

**2. Diğer script'lerle çakışma olup olmadığını kontrol edin**

`performance.js`'i diğer tüm script'lerden sonra yüklemeyi deneyin:
```html
<!-- Önce diğer script'ler -->
<script src="/app.js"></script>
<script src="/vendor.js"></script>

<!-- performance.js en son -->
<script src="/performance.js" data-logserver="http://[IP_ADDRESS]:8084"></script>
</body>
```

---

## Debug Modu

Script'in ne yaptığı hakkında detaylı bilgi görmek için debug modunu etkinleştirin:

```html
<script>
  window.ENV_DEBUG = "true";
</script>
<script src="/performance.js" data-logserver="http://[IP_ADDRESS]:8084"></script>
```

Ardından tarayıcı konsolunda şöyle mesajları kontrol edin:
- `[Tracker] Initialized with endpoint: http://...`
- `[Tracker] Sending batch of X events`
- `[Tracker] Batch sent successfully`

---

## Olaylar Gönderiliyor Ama Dashboard'larda Görünmüyor

### Belirtiler
- Network sekmesi başarılı POST isteklerini gösteriyor (durum 200)
- Ancak Kibana dashboard'larında veri görünmüyor

### Çözüm

**Sistem yöneticinizle iletişime geçin.** Sorun muhtemelen sunucu tarafındadır:
- Log worker çalışmıyor olabilir
- Elasticsearch'te sorun olabilir
- İşleme gecikmesi olabilir

---

## Yüksek Bellek Kullanımı veya Yavaş Sayfa

### Belirtiler
- Uzun süreli kullanımdan sonra sayfa yavaşlıyor
- Tarayıcı bellek kullanımı zamanla artıyor

### Olası Nedenler

Bu nadir bir durumdur ama şu sayfalarda olabilir:
- Aşırı yüksek DOM aktivitesi (binlerce değişiklik)
- Hızlı ardışık hatalar (olay kuyruğunu dolduran)

### Çözümler

**1. JavaScript hata döngülerini kontrol edin**

Uygulamanızda sürekli tetiklenen bir JavaScript hatası varsa, olay kuyruğunu doldurabilir. Asıl hatayı düzeltin.

**2. Yoğun sayfalarda izlemeyi sınırlayın**

Aşırı DOM aktivitesi olan sayfalar için belirli izleme özelliklerini devre dışı bırakabilirsiniz. Rehberlik için sistem yöneticinizle iletişime geçin.

---

## Hızlı Kontrol Listesi

Bir şey çalışmıyorsa, bu kontrol listesini gözden geçirin:

1. [ ] `performance.js` erişilebilir mi? (tarayıcı Network sekmesinde 200 durumunu kontrol edin)
2. [ ] `data-logserver` özelliği mevcut ve doğru mu?
3. [ ] IP adresi doğru mu? (sistem yöneticisinden alın)
4. [ ] URL'de 8084 portu var mı?
5. [ ] `http://[IP]:8084/health` adresine doğrudan erişebiliyor musunuz?
6. [ ] Konsolda CORS hatası var mı?
7. [ ] Konsolda JavaScript hatası var mı?

---

## Yardım Alma

Yukarıdakilerin hepsini denediyseniz ve hâlâ sorun yaşıyorsanız:

1. Debug modunu etkinleştirin ve konsol çıktısını kaydedin
2. Network sekmesinin ekran görüntüsünü alın
3. Hata mesajlarını not edin
4. Bu bilgilerle sistem yöneticinizle iletişime geçin
