# Web App Integration - Troubleshooting

Common issues and solutions when integrating the telemetry script.

---

## Events Not Being Sent

### Symptoms
- No POST requests to `/events` in the Network tab
- No data appearing in dashboards

### Solutions

**1. Check the script tag is present**
```html
<!-- Should be before </body> -->
<script src="/performance.js" data-logserver="http://[IP_ADDRESS]:8084"></script>
```

**2. Verify the `data-logserver` attribute**
- Must include the full URL with `http://`
- Must include the port `:8084`
- IP address must be correct (get from system administrator)

**3. Test IP reachability**

Open your browser and navigate to:
```
http://[IP_ADDRESS]:8084/health
```

You should see a JSON response like:
```json
{"status": "healthy", "redis": "connected"}
```

If this doesn't work:
- The log server may not be running
- There may be a firewall blocking the connection
- Contact your system administrator

---

## Script Not Loading (404 Error)

### Symptoms
- Browser console shows: `GET /performance.js 404 (Not Found)`
- No telemetry data being sent

### Solutions

**1. Check the file path**

Verify `performance.js` exists in your static assets folder:
```bash
ls -la /path/to/your/static/folder/performance.js
```

**2. Verify static files are being served**

Make sure your web server is configured to serve static files from the correct directory.

**3. Check the script src path**

The path in your HTML must match where the file is located:
```html
<!-- If file is at /static/js/performance.js -->
<script src="/static/js/performance.js" data-logserver="http://[IP_ADDRESS]:8084"></script>

<!-- If file is at /assets/performance.js -->
<script src="/assets/performance.js" data-logserver="http://[IP_ADDRESS]:8084"></script>
```

---

## CORS Errors

### Symptoms
Browser console shows errors like:
```
Access to XMLHttpRequest at 'http://[IP]:8084/events' from origin 'http://yoursite.com'
has been blocked by CORS policy
```

### Solution

**Contact your system administrator.** They need to configure the log server to allow requests from your domain.

Provide them with:
- Your web application's domain (e.g., `https://myapp.example.com`)
- The port if non-standard (e.g., `http://localhost:3000` for development)

---

## Console Errors from performance.js

### Symptoms
JavaScript errors appearing in the console related to `performance.js`

### Solutions

**1. Check browser compatibility**

The script requires a modern browser:
- Chrome 70+
- Firefox 65+
- Safari 12+
- Edge 79+

**2. Check for conflicts with other scripts**

Try loading `performance.js` after all other scripts:
```html
<!-- Other scripts first -->
<script src="/app.js"></script>
<script src="/vendor.js"></script>

<!-- performance.js last -->
<script src="/performance.js" data-logserver="http://[IP_ADDRESS]:8084"></script>
</body>
```

---

## Debug Mode

To see detailed information about what the script is doing, enable debug mode:

```html
<script>
  window.ENV_DEBUG = "true";
</script>
<script src="/performance.js" data-logserver="http://[IP_ADDRESS]:8084"></script>
```

Then check the browser console for messages like:
- `[Tracker] Initialized with endpoint: http://...`
- `[Tracker] Sending batch of X events`
- `[Tracker] Batch sent successfully`

---

## Events Sent but Not Appearing in Dashboards

### Symptoms
- Network tab shows successful POST requests (status 200)
- But no data appears in Kibana dashboards

### Solution

**Contact your system administrator.** The issue is likely on the server side:
- The log worker may not be running
- Elasticsearch may have issues
- There may be a processing delay

---

## High Memory Usage or Slow Page

### Symptoms
- Page becomes slow after extended use
- Browser memory usage increases over time

### Possible Causes

This is rare but can happen on pages with:
- Extremely high DOM activity (thousands of mutations)
- Rapid consecutive errors (flooding the event queue)

### Solutions

**1. Check for JavaScript error loops**

If your application has a JavaScript error that fires repeatedly, it can flood the event queue. Fix the underlying error.

**2. Limit tracking on heavy pages**

For pages with extreme DOM activity, you can disable certain tracking features. Contact your system administrator for guidance.

---

## Quick Checklist

If something isn't working, go through this checklist:

1. [ ] Is `performance.js` accessible? (check browser Network tab for 200 status)
2. [ ] Is `data-logserver` attribute present and correct?
3. [ ] Is the IP address correct? (get from system administrator)
4. [ ] Is the port 8084 included in the URL?
5. [ ] Can you access `http://[IP]:8084/health` directly?
6. [ ] Are there any CORS errors in the console?
7. [ ] Are there any JavaScript errors in the console?

---

## Getting Help

If you've tried everything above and still have issues:

1. Enable debug mode and capture the console output
2. Take a screenshot of the Network tab
3. Note any error messages
4. Contact your system administrator with this information
