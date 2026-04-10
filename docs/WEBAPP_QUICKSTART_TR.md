# Web Uygulaması Entegrasyonu - Hızlı Başlangıç

Web uygulamanıza tarayıcı telemetrisi eklemek için basit bir kılavuz.

---

## Başlamadan Önce

İhtiyacınız olacaklar:
- [ ] Sistem yöneticinizden **log sunucusu IP adresi**
- [ ] Web uygulamanızın HTML dosyalarına erişim
- [ ] `performance.js` script dosyası

---

## Entegrasyon Kontrol Listesi

- [ ] Sistem yöneticisinden log sunucusu IP adresini alın
- [ ] `performance.js` dosyasını statik dosyalar klasörünüze kopyalayın
- [ ] Script etiketini TÜM sayfalara ekleyin
- [ ] Entegrasyonu test edin

---

## Adım 1: Script'i Alın

`performance.js` dosyasını web uygulamanızın statik dosyalar klasörüne kopyalayın (örn: `/static/`, `/js/`, `/assets/`).

Sistem yöneticiniz bu dosyayı sağlayacaktır veya proje deposunda bulabilirsiniz.

---

## Adım 2: HTML'e Ekleyin

Aşağıdaki script etiketini izlemek istediğiniz **her HTML sayfasına** ekleyin. Kapanış `</body>` etiketinin hemen öncesine yerleştirin:

```html
<script src="/performance.js" data-logserver="http://[IP_ADDRESS]:8084"></script>
```

**Önemli:**
- `[IP_ADDRESS]` kısmını sistem yöneticinizin verdiği IP adresiyle değiştirin
- `data-logserver` özelliği script'e telemetri verilerini nereye göndereceğini söyler
- `performance.js` yolunun klasör yapınızla eşleştiğinden emin olun

### Örnekler

Dosyalarınız `/static/js/` klasöründeyse:
```html
<script src="/static/js/performance.js" data-logserver="http://[IP_ADDRESS]:8084"></script>
```

Dosyalarınız `/assets/` klasöründeyse:
```html
<script src="/assets/performance.js" data-logserver="http://[IP_ADDRESS]:8084"></script>
```

---

## Adım 3: Entegrasyonu Doğrulayın

1. Web uygulamanızı tarayıcıda açın
2. Tarayıcı Geliştirici Araçlarını açın (F12 veya Cmd+Option+I)
3. **Network** (Ağ) sekmesine gidin
4. "events" ile filtreleyin veya 8084 portuna giden istekleri arayın
5. `http://[IP_ADDRESS]:8084/events` adresine POST istekleri görmelisiniz

Bu istekleri 200 durumuyla görüyorsanız, entegrasyon çalışıyor demektir.

---

## İsteğe Bağlı Yapılandırma

### Debug Modunu Etkinleştirin

Tarayıcı konsolunda detaylı log görmek için, script etiketinden önce şunu ekleyin:

```html
<script>
  window.ENV_DEBUG = "true";
</script>
<script src="/performance.js" data-logserver="http://[IP_ADDRESS]:8084"></script>
```

### Başarılı Seçicileri Takip Edin

Varsayılan olarak sadece seçici hataları takip edilir. Başarılı seçici eşleşmelerini de takip etmek için:

```html
<script src="/performance.js" data-logserver="http://[IP_ADDRESS]:8084" data-track-success="true"></script>
```

---

## Neler Takip Edilir

Script otomatik olarak şunları yakalar:
- JavaScript hataları ve uyarıları
- Ağ isteği hataları ve yavaş istekler
- Sayfa yükleme performansı
- Kullanıcı etkileşimleri (tıklamalar, form gönderimleri)
- DOM seçici sorunları (eksik elementler)
- Ve daha fazlası...

Tüm veriler gönderilmeden önce temizlenir - şifreler ve token'lar gibi hassas bilgiler otomatik olarak gizlenir.


---

## Yardım mı Gerekiyor?

- **Script çalışmıyor mu?** Bakın: [WEBAPP_TROUBLESHOOTING_TR.md](WEBAPP_TROUBLESHOOTING_TR.md)
- **IP adresi mi gerekiyor?** Sistem yöneticinizle iletişime geçin
- **Veriler hakkında sorularınız mı var?** Sistem yöneticinizden Kibana dashboard'larını göstermesini isteyin
