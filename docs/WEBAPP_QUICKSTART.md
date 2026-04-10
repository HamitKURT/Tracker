# Web App Integration - Quick Start

A simple guide for integrating browser telemetry into your web application.

---

## Before You Start

You will need:
- [ ] The **log server IP address** from your system administrator
- [ ] Access to your web application's HTML files
- [ ] The `performance.js` script file

---

## Integration Checklist

- [ ] Get log server IP from system administrator
- [ ] Copy `performance.js` to your static assets folder
- [ ] Add the script tag to ALL pages
- [ ] Test the integration

---

## Step 1: Get the Script

Copy the `performance.js` file to your web application's static assets folder (e.g., `/static/`, `/js/`, `/assets/`).

Your system administrator will provide this file, or you can find it in the project repository.

---

## Step 2: Add to Your HTML

Add the following script tag to **every HTML page** you want to monitor. Place it just before the closing `</body>` tag:

```html
<script src="/performance.js" data-logserver="http://[IP_ADDRESS]:8084"></script>
```

**Important:**
- Replace `[IP_ADDRESS]` with the IP address provided by your system administrator
- The `data-logserver` attribute tells the script where to send telemetry data
- Make sure the path to `performance.js` matches your folder structure

### Examples

If your assets are in `/static/js/`:
```html
<script src="/static/js/performance.js" data-logserver="http://[IP_ADDRESS]:8084"></script>
```

If your assets are in `/assets/`:
```html
<script src="/assets/performance.js" data-logserver="http://[IP_ADDRESS]:8084"></script>
```

---

## Step 3: Verify the Integration

1. Open your web application in a browser
2. Open the browser Developer Tools (F12 or Cmd+Option+I)
3. Go to the **Network** tab
4. Filter by "events" or look for requests to port 8084
5. You should see POST requests to `http://[IP_ADDRESS]:8084/events`

If you see these requests with status 200, the integration is working.

---

## Optional Configuration

### Enable Debug Mode

To see detailed logging in the browser console, add this before the script tag:

```html
<script>
  window.ENV_DEBUG = "true";
</script>
<script src="/performance.js" data-logserver="http://[IP_ADDRESS]:8084"></script>
```

### Track Successful Selectors

By default, only selector misses are tracked. To also track successful selector matches:

```html
<script src="/performance.js" data-logserver="http://[IP_ADDRESS]:8084" data-track-success="true"></script>
```

---

## What Gets Tracked

The script automatically captures:
- JavaScript errors and warnings
- Network request failures and slow requests
- Page load performance
- User interactions (clicks, form submissions)
- DOM selector issues (missing elements)
- And more...

All data is sanitized before transmission - sensitive information like passwords and tokens are automatically redacted.

---



## Need Help?

- **Script not working?** See [WEBAPP_TROUBLESHOOTING.md](WEBAPP_TROUBLESHOOTING.md)
- **Need the IP address?** Contact your system administrator
- **Have questions about the data?** Ask your system administrator to show you the Kibana dashboards
