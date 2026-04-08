import time
import os
import random
import string
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import Select


def set_chrome_options() -> ChromeOptions:
    options = ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    return options


def random_text(length=10):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


def run_error_test_suite():
    print("=" * 70)
    print("COMPREHENSIVE SELENIUM ERROR & EDGE CASE TEST SUITE")
    print("Testing: Missing Objects, Errors, Failed Selectors, Network Issues")
    print("=" * 70)
    
    web_app_url = os.getenv("WEB_APP_URL", "http://web-app:8081")
    chromedriver_path = os.getenv("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")
    
    from selenium.webdriver.chrome.service import Service
    service = Service(executable_path=chromedriver_path)
    driver = webdriver.Chrome(service=service, options=set_chrome_options())

    
    try:
        # =========================================================================
        # SECTION 1: PAGE LOAD & AUTOMATION DETECTION
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 1: PAGE LOAD & AUTOMATION DETECTION")
        print("=" * 70)
        
        driver.get(web_app_url)
        time.sleep(2)
        print("[PASS] Page loaded successfully")
        
        # =========================================================================
        # SECTION 2: MISSING SELECTOR TESTS - Generate selector-not-found events
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 2: MISSING SELECTOR TESTS (selector-not-found)")
        print("=" * 70)
        
        # Non-existent IDs - repeated to trigger missCount thresholds
        for i in range(15):
            selector = f"#nonexistent-id-{random_text(8)}"
            driver.execute_script("document.querySelector(arguments[0]);", selector)
        print(f"[ERROR] querySelector with non-existent ID executed 15 times")
        
        for i in range(15):
            selector = f"missing-id-{random_text(8)}"
            driver.execute_script("document.getElementById(arguments[0]);", selector)
        print(f"[ERROR] getElementById with non-existent ID executed 15 times")
        
        # Non-existent classes
        for i in range(12):
            selector = f".fake-class-{random_text(6)}"
            driver.execute_script("document.querySelectorAll(arguments[0]);", selector)
        print(f"[ERROR] querySelectorAll with non-existent class executed 12 times")
        
        # Non-existent tags
        for i in range(10):
            selector = f"nonexistent-tag-{random_text(6)}"
            driver.execute_script("document.querySelectorAll(arguments[0]);", selector)
        print(f"[ERROR] querySelectorAll with non-existent tag executed 10 times")
        
        # Complex non-existent selectors
        complex_selectors = [
            "div.missing-class[data-missing]",
            "ul > li:nth-child(999)",
            "#parent .nested .deep .very-deep",
            '[aria-label="Does Not Exist"]',
            ".modal.is-visible",
            "input[type='checkbox'][checked]",
        ]
        for selector in complex_selectors:
            for _ in range(3):
                try:
                    driver.execute_script("document.querySelector(arguments[0]);", selector)
                except Exception:
                    print(f"[WARNING] Ignoring querySelector invalid selector error for {selector}")
        print(f"[ERROR] Complex non-existent selectors executed {len(complex_selectors)*3} times")
        
        # =========================================================================
        # SECTION 3: MISSING XPATH TESTS - Generate xpath-not-found events
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 3: MISSING XPATH TESTS (xpath-not-found)")
        print("=" * 70)
        
        xpath_queries = [
            "//div[@id='nonexistent-div-12345']",
            "//button[@class='missing-class']",
            "//input[@name='fake-input']",
            "//table[@id='missing-table']//tr",
            "//form[@id='ghost-form']//input",
            "//a[@href='/nonexistent-page']",
            "//span[contains(@class, 'notfound')]",
            "//div[contains(text(), 'Missing Text')]",
            "//*[contains(@aria-label, 'Ghost')]",
            "//section[@data-testid='fake-test-id']",
        ]
        
        for xpath in xpath_queries:
            for _ in range(5):
                driver.execute_script("""
                    var result = document.evaluate(
                        arguments[0], document, null, 
                        XPathResult.FIRST_ORDERED_NODE_TYPE, null
                    );
                    var node = result.singleNodeValue;
                """, xpath)
        print(f"[ERROR] Failed XPath queries executed {len(xpath_queries)*5} times")
        
        # XPath error scenarios
        xpath_errors = [
            "//div[contains(@attribute, 'value')]",  # Invalid attribute
            "/html/body/div[999]/span",  # Deep non-existent path
            "//*[@id='']",  # Empty id attribute
        ]
        for xpath in xpath_errors:
            try:
                driver.execute_script("document.evaluate(arguments[0], document, null, 0, null);", xpath)
            except Exception:
                pass
        print(f"[ERROR] Invalid XPath syntax executed {len(xpath_errors)} times")
        
        time.sleep(0.5)
        
        # =========================================================================
        # SECTION 4: MISSING getElementsBy TESTS
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 4: MISSING getElementsBy TESTS")
        print("=" * 70)
        
        # getElementsByClassName - failures
        for _ in range(8):
            driver.execute_script("document.getElementsByClassName('this-class-definitely-does-not-exist-xyz123');")
        print("[ERROR] getElementsByClassName with missing class: 8 times")
        
        # getElementsByTagName - non-existent tags
        for _ in range(6):
            driver.execute_script("document.getElementsByTagName('non-existent-html-tag');")
        print("[ERROR] getElementsByTagName with missing tag: 6 times")
        
        # getElementsByName - non-existent names
        for _ in range(8):
            driver.execute_script("document.getElementsByName('fake-form-field-name-xyz');")
        print("[ERROR] getElementsByName with missing name: 8 times")
        
        time.sleep(0.5)
        
        # =========================================================================
        # SECTION 5: JAVASCRIPT ERRORS
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 5: JAVASCRIPT ERRORS (js-error)")
        print("=" * 70)
        
        error_scripts = [
            ("ReferenceError: undefined variable", "undefinedVarXYZ123;"),
            ("TypeError: Cannot read property", "nullObj.prop;"),
            ("TypeError: undefined is not an object", "(void 0).anything;"),
            ("SyntaxError: invalid JSON", "JSON.parse('not valid json{{{');"),
            ("RangeError: Maximum call stack", "function recurse(){recurse()}; recurse();"),
            ("EvalError: disallowed", "eval('var x = 1');"),
            ("URIError: malformed URI", "decodeURIComponent('%');"),
            ("Custom Error", "throw new Error('Test error from Selenium');"),
        ]
        
        for name, script in error_scripts:
            try:
                driver.execute_script(script)
            except Exception:
                pass
            print(f"[ERROR] {name}")
        
        time.sleep(0.3)
        
        # Trigger error button
        try:
            driver.find_element(By.CLASS_NAME, "error-btn").click()
            print("[ERROR] Clicked error trigger button")
        except:
            print("[ERROR] Error button not found")
        
        time.sleep(0.5)
        
        # =========================================================================
        # SECTION 6: UNHANDLED PROMISE REJECTIONS
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 6: UNHANDLED PROMISE REJECTIONS (unhandled-promise-rejection)")
        print("=" * 70)
        
        driver.execute_script("Promise.reject(new Error('Unhandled rejection 1'))")
        print("[ERROR] Promise.reject with Error")
        
        driver.execute_script("Promise.reject('String rejection message')")
        print("[ERROR] Promise.reject with String")
        
        driver.execute_script("""
            Promise.reject({
                code: 'API_ERROR',
                message: 'Server returned 500',
                details: { field: 'value' }
            })
        """)
        print("[ERROR] Promise.reject with Object")
        
        driver.execute_script("""
            fetch('/api/nonexistent-endpoint')
                .then(r => r.json())
                .catch(() => Promise.reject(new Error('Network failed')));
        """)
        print("[ERROR] Promise.reject from failed fetch")
        
        time.sleep(0.5)
        
        # =========================================================================
        # SECTION 7: NETWORK ERRORS (XHR & Fetch)
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 7: NETWORK ERRORS (xhr-error, fetch-error)")
        print("=" * 70)
        
        # Failed XHR requests
        for i in range(5):
            driver.execute_script(f"""
                var xhr = new XMLHttpRequest();
                xhr.open('GET', '/api/endpoint-does-not-exist-{i}');
                xhr.send();
            """)
        print("[ERROR] Failed XHR requests: 5 times")
        
        # Failed fetch requests
        for i in range(5):
            driver.execute_script(f"""
                fetch('/api/fake-endpoint-{i}', {{ method: 'GET' }})
                    .catch(err => {{ console.error('Fetch failed:', err); }});
            """)
        print("[ERROR] Failed fetch requests: 5 times")
        
        # Slow XHR (will be tracked as slow — exceeds 5000ms threshold)
        driver.execute_script("""
            var xhr = new XMLHttpRequest();
            xhr.open('GET', '/api/slow-response');
            xhr.send();
        """)
        print("[WARNING] Slow XHR request initiated (6s endpoint)")

        # Slow Fetch (will be tracked as slow)
        driver.execute_script("""
            fetch('/api/slow-response').then(function(r) { return r.text(); });
        """)
        print("[WARNING] Slow Fetch request initiated (6s endpoint)")

        # XHR with timeout
        driver.execute_script("""
            var xhr = new XMLHttpRequest();
            xhr.open('GET', 'http://192.0.2.1/');  // TEST-NET, non-routable
            xhr.timeout = 2000;
            xhr.send();
        """)
        print("[ERROR] XHR timeout scenario")

        # Wait for slow responses to complete and be tracked
        time.sleep(8)
        
        # =========================================================================
        # SECTION 8: XHR ISSUE EVENTS (errors, slow responses)
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 8: XHR ISSUE EVENTS")
        print("=" * 70)
        
        # XHR with error status codes
        driver.execute_script("""
            var xhr = new XMLHttpRequest();
            xhr.open('POST', '/api/test-500');
            xhr.send();
        """)
        print("[ERROR] XHR with 500 status simulation")
        
        driver.execute_script("""
            var xhr = new XMLHttpRequest();
            xhr.open('GET', '/api/not-found');
            xhr.send();
        """)
        print("[ERROR] XHR with 404 status simulation")
        
        time.sleep(0.5)
        
        # =========================================================================
        # SECTION 9: RAPID INTERACTIONS - Timing Alerts
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 9: RAPID INTERACTIONS (rapid-clicks, timing-alert)")
        print("=" * 70)
        
        # Rapid clicks on button
        try:
            for _ in range(25):
                driver.execute_script("""
                    var btn = document.getElementById('testButton');
                    if (btn) btn.click();
                """)
            print("[WARNING] 25 rapid clicks executed")
        except Exception:
            print("[ERROR] Button not found for rapid clicks")
        
        time.sleep(0.3)
        
        # Extremely rapid inputs
        try:
            input_field = driver.find_element(By.ID, "username")
            for _ in range(15):
                input_field.send_keys("a")
        except:
            print("[ERROR] Input field not found")
        print("[WARNING] Rapid key inputs: 15 times")
        
        time.sleep(0.5)
        
        # =========================================================================
        # SECTION 10: CLICK ON MISSING/DISABLED ELEMENTS
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 10: CLICK ON MISSING/DISABLED ELEMENTS")
        print("=" * 70)
        
        # Click on elements that don't exist
        for i in range(10):
            try:
                driver.execute_script(f"""
                    var el = document.getElementById('ghost-element-{i}');
                    if (el) el.click();
                """)
            except:
                pass
        print("[ERROR] Attempted click on non-existent elements: 10 times")
        
        # Create and click disabled button
        driver.execute_script("""
            var btn = document.createElement('button');
            btn.id = 'dynamically-disabled-btn';
            btn.disabled = true;
            btn.textContent = 'Disabled Button';
            document.body.appendChild(btn);
        """)
        try:
            disabled_btn = driver.find_element(By.ID, "dynamically-disabled-btn")
            disabled_btn.click()
        except Exception:
            print("[ERROR] Click on disabled element attempted")
        
        # Click on hidden element
        driver.execute_script("""
            var hiddenDiv = document.createElement('div');
            hiddenDiv.id = 'hidden-click-target';
            hiddenDiv.style.display = 'none';
            hiddenDiv.textContent = 'Hidden';
            document.body.appendChild(hiddenDiv);
        """)
        try:
            hidden = driver.find_element(By.ID, "hidden-click-target")
            hidden.click()
        except Exception:
            print("[ERROR] Click on hidden element attempted")
        
        time.sleep(0.5)
        
        # =========================================================================
        # SECTION 11: DOM MUTATION BURSTS
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 11: DOM MUTATION BURSTS (dom-mutation-burst)")
        print("=" * 70)
        
        # Add many elements rapidly
        driver.execute_script("""
            for (var i = 0; i < 30; i++) {
                var div = document.createElement('div');
                div.className = 'mutation-burst-item';
                div.textContent = 'Added ' + i;
                div.setAttribute('data-id', i);
                document.body.appendChild(div);
            }
        """)
        print("[WARNING] 30 elements added in burst")
        
        time.sleep(0.4)
        
        # Remove many elements
        driver.execute_script("""
            var items = document.querySelectorAll('.mutation-burst-item');
            items.forEach(function(item) { item.remove(); });
        """)
        print("[WARNING] 30 elements removed in burst")
        
        time.sleep(0.4)
        
        # Attribute mutations on hidden/disabled elements
        driver.execute_script("""
            for (var i = 0; i < 10; i++) {
                var el = document.createElement('div');
                el.id = 'attr-mutation-' + i;
                el.style.display = 'none';
                el.setAttribute('aria-hidden', 'true');
                document.body.appendChild(el);
                
                // Modify attributes
                el.setAttribute('class', 'hidden-element-' + i);
                el.setAttribute('data-modified', 'true');
            }
        """)
        print("[WARNING] Attribute mutations on hidden elements: 10 times")
        
        time.sleep(0.5)
        
        # =========================================================================
        # SECTION 12: ELEMENT HIDDEN EVENTS
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 12: ELEMENT HIDDEN EVENTS (element-hidden)")
        print("=" * 70)
        
        # Hide elements via JavaScript
        driver.execute_script("""
            var h1 = document.querySelector('h1');
            if (h1) {
                h1.setAttribute('hidden', 'true');
                h1.style.display = 'none';
            }
        """)
        print("[WARNING] H1 element hidden via display:none")
        
        driver.execute_script("""
            var container = document.querySelector('.container');
            if (container) {
                container.style.visibility = 'hidden';
            }
        """)
        print("[WARNING] Container hidden via visibility:hidden")
        
        driver.execute_script("""
            var btn = document.getElementById('testButton');
            if (btn) {
                btn.setAttribute('aria-hidden', 'true');
            }
        """)
        print("[WARNING] Button hidden via aria-hidden")
        
        time.sleep(0.5)
        
        # =========================================================================
        # SECTION 13: FORM VALIDATION FAILURES
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 13: FORM VALIDATION FAILURES (form-validation-failure)")
        print("=" * 70)
        
        # Fill form with invalid data and try to submit
        try:
            driver.find_element(By.ID, "email").send_keys("not-an-email")
            driver.find_element(By.ID, "number").send_keys("999999999")
            driver.execute_script("""
                var form = document.getElementById('mainForm');
                if (form) {
                    form.dispatchEvent(new Event('submit', {bubbles: true, cancelable: true}));
                }
            """)
            print("[ERROR] Form validation failure triggered via #mainForm")
        except Exception:
            print("[ERROR] Form validation failure scenario")
        
        time.sleep(0.5)
        
        # =========================================================================
        # SECTION 14: PROGRAMMATIC INPUT DETECTION
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 14: PROGRAMMATIC INPUT (programmatic-input)")
        print("=" * 70)
        
        # Set input value via JavaScript (no isTrusted)
        driver.execute_script("""
            var input = document.getElementById('username');
            if (input) {
                var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                nativeInputValueSetter.call(input, 'Programmatic Value Set');
                var event = new Event('input', { bubbles: true });
                input.dispatchEvent(event);
            }
        """)
        print("[WARNING] Programmatic input value set via JavaScript")
        
        driver.execute_script("""
            var input = document.getElementById('password');
            if (input) {
                var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                nativeInputValueSetter.call(input, 'SecretPassword123');
                var event = new Event('input', { bubbles: true });
                input.dispatchEvent(event);
            }
        """)
        print("[WARNING] Programmatic password value set")
        
        time.sleep(0.5)
        
        # =========================================================================
        # SECTION 15: CONSOLE ERRORS & WARNINGS
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 15: CONSOLE ERRORS & WARNINGS (console-error, console-warn)")
        print("=" * 70)
        
        console_errors = [
            "Critical error: Database connection failed",
            "Warning: Deprecated API usage",
            "Error: Authentication failed",
            "TypeError: Cannot read property 'data' of undefined",
            "Failed to load resource: net::ERR_CONNECTION_REFUSED",
            "SecurityError: Blocked mixed content",
            "Error: Maximum update depth exceeded",
        ]
        
        for error in console_errors:
            driver.execute_script("console.error(arguments[0]);", error)
        
        for i in range(3):
            driver.execute_script("console.warn(arguments[0]);", f"Warning message {i}: Invalid configuration detected")
        
        driver.execute_script("""
            console.error('Error with', { detail: 'multiple', args: true, code: 500 });
            console.warn('Warning', 'with', 'multiple', 'arguments');
        """)
        
        print(f"[ERROR] Console errors logged: {len(console_errors) + 2}")
        print("[WARNING] Console warnings logged: 3 + 1")
        
        time.sleep(0.5)
        
        # =========================================================================
        # SECTION 16: BLOCKING OVERLAY DETECTION
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 16: BLOCKING OVERLAY DETECTION (blocking-overlay-detected)")
        print("=" * 70)
        
        # Create blocking overlay
        driver.execute_script("""
            var overlay = document.createElement('div');
            overlay.id = 'cookie-banner-overlay';
            overlay.style.cssText = `
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                z-index: 9999;
                background: rgba(0,0,0,0.7);
                display: flex;
                justify-content: center;
                align-items: center;
            `;
            overlay.innerHTML = '<div style="background:white;padding:20px;text-align:center;">Cookie Banner</div>';
            document.body.appendChild(overlay);
        """)
        print("[WARNING] Blocking overlay created (z-index: 9999)")
        
        time.sleep(1)
        
        # Remove overlay
        driver.execute_script("""
            var overlay = document.getElementById('cookie-banner-overlay');
            if (overlay) overlay.remove();
        """)
        
        time.sleep(0.5)
        
        # =========================================================================
        # SECTION 17: MEDIA LOAD ERRORS
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 17: MEDIA LOAD ERRORS (media-load-error)")
        print("=" * 70)
        
        # Create broken image
        driver.execute_script("""
            var img = document.createElement('img');
            img.src = '/nonexistent/image/path/broken.png';
            img.id = 'broken-image';
            document.body.appendChild(img);
        """)
        print("[ERROR] Broken image element created")
        
        # Create broken video
        driver.execute_script("""
            var video = document.createElement('video');
            video.src = '/nonexistent/video.mp4';
            video.id = 'broken-video';
            document.body.appendChild(video);
        """)
        print("[ERROR] Broken video element created")
        
        # Create broken iframe
        driver.execute_script("""
            var iframe = document.createElement('iframe');
            iframe.src = 'http://192.0.2.1/nonexistent';
            iframe.id = 'broken-iframe';
            document.body.appendChild(iframe);
        """)
        print("[ERROR] Broken iframe element created")
        
        time.sleep(1)
        
        # =========================================================================
        # SECTION 18: CSP VIOLATIONS
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 18: CSP VIOLATIONS (csp-violation)")
        print("=" * 70)
        
        # Load external font (blocked by font-src 'none' CSP)
        driver.execute_script("""
            var link = document.createElement('link');
            link.rel = 'stylesheet';
            link.href = 'https://fonts.googleapis.com/css?family=Roboto';
            document.head.appendChild(link);
        """)
        print("[WARNING] External font load attempted (CSP font-src 'none' blocks it)")

        # Load iframe (blocked by frame-src 'none' CSP)
        driver.execute_script("""
            var iframe = document.createElement('iframe');
            iframe.src = 'https://example.com';
            document.body.appendChild(iframe);
        """)
        print("[WARNING] External iframe load attempted (CSP frame-src 'none' blocks it)")

        # Load external script (blocked by script-src CSP)
        driver.execute_script("""
            var script = document.createElement('script');
            script.src = 'https://cdn.example.com/malicious.js';
            document.head.appendChild(script);
        """)
        print("[WARNING] External script load attempted (CSP blocks it)")

        time.sleep(1)
        
        # =========================================================================
        # SECTION 19: WEBSOCKET ERRORS
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 19: WEBSOCKET ERRORS (websocket-error, websocket-unclean-close)")
        print("=" * 70)
        
        # Create failing WebSocket
        driver.execute_script("""
            try {
                var ws = new WebSocket('ws://192.0.2.1:8080/nonexistent');
                ws.onerror = function() {
                    console.log('WebSocket error occurred');
                };
                ws.onclose = function(e) {
                    console.log('WebSocket closed:', e.code, e.reason);
                };
            } catch(e) {
                console.error('WebSocket creation failed:', e);
            }
        """)
        print("[ERROR] WebSocket connection attempted to non-routable IP")
        
        time.sleep(1)
        
        # =========================================================================
        # SECTION 20: EXCESSIVE TIMERS DETECTION
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 20: EXCESSIVE TIMERS (excessive-timers)")
        print("=" * 70)
        
        # Create many setTimeout calls
        driver.execute_script("""
            for (var i = 0; i < 100; i++) {
                setTimeout(function() {}, Math.random() * 10000);
            }
        """)
        print("[WARNING] 100 setTimeout calls created")
        
        # Create many setInterval calls
        driver.execute_script("""
            for (var i = 0; i < 60; i++) {
                setInterval(function() {}, 1000000 + i);
            }
        """)
        print("[WARNING] 60 setInterval calls created")
        
        time.sleep(1)
        
        # =========================================================================
        # SECTION 21: PAGE IDLE DETECTION
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 21: PAGE IDLE (page-idle)")
        print("=" * 70)
        
        # Wait for idle detection (30 seconds)
        print("[INFO] Waiting for page idle detection (30 seconds)...")
        time.sleep(32)
        print("[WARNING] Page marked as idle")
        
        # =========================================================================
        # SECTION 22: RESOURCE LOAD FAILURES
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 22: RESOURCE LOAD FAILURES (resource-load-error)")
        print("=" * 70)
        
        # Create broken link
        driver.execute_script("""
            var link = document.createElement('link');
            link.rel = 'stylesheet';
            link.href = '/nonexistent/styles.css';
            document.head.appendChild(link);
        """)
        print("[ERROR] Broken CSS link created")
        
        # Create broken script
        driver.execute_script("""
            var script = document.createElement('script');
            script.src = '/nonexistent/app.js';
            script.id = 'missing-script';
            document.head.appendChild(script);
        """)
        print("[ERROR] Broken script tag created")
        
        time.sleep(1)
        
        # =========================================================================
        # SECTION 23: SCROLL INTO VIEW EVENTS
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 23: SCROLL INTO VIEW (scroll-into-view)")
        print("=" * 70)
        
        # Create elements and scroll to them
        driver.execute_script("""
            for (var i = 0; i < 5; i++) {
                var div = document.createElement('div');
                div.id = 'scroll-target-' + i;
                div.textContent = 'Scroll target ' + i;
                div.style.height = '500px';
                document.body.appendChild(div);
            }
        """)
        
        for i in range(5):
            driver.execute_script(f"""
                var el = document.getElementById('scroll-target-{i}');
                if (el) el.scrollIntoView();
            """)
            time.sleep(0.2)
        
        print("[INFO] scrollIntoView called 5 times")
        
        # =========================================================================
        # SECTION 24: DIALOG EVENTS
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 24: DIALOG EVENTS (dialog-alert, dialog-confirm, dialog-prompt)")
        print("=" * 70)
        
        # Trigger alert dialogs
        driver.execute_script("window.alert('Automation test alert message');")
        try:
            alert = driver.switch_to.alert
            alert.accept()
        except Exception:
            pass
        print("[INFO] Alert dialog triggered")
        
        time.sleep(0.3)
        
        # Dismiss confirm dialog (returns false)
        driver.execute_script("window.confirm('Are you sure you want to proceed?');")
        try:
            alert = driver.switch_to.alert
            alert.dismiss()
        except Exception:
            pass
        print("[INFO] Confirm dialog triggered")
        
        time.sleep(0.3)
        
        # Trigger prompt dialog
        driver.execute_script("window.prompt('Enter your name:', 'Default Name');")
        try:
            alert = driver.switch_to.alert
            alert.accept()
        except Exception:
            pass
        print("[INFO] Prompt dialog triggered")
        
        time.sleep(0.5)
        
        # =========================================================================
        # SECTION 25: NAVIGATION ERRORS
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 25: NAVIGATION ERRORS")
        print("=" * 70)
        
        # Hash navigation
        driver.execute_script("window.location.hash = '#test-section';")
        print("[INFO] Hash navigation")
        
        time.sleep(0.3)
        
        # PushState navigation
        driver.execute_script("history.pushState({}, 'Test', '/test-page-1');")
        print("[INFO] pushState navigation")
        
        time.sleep(0.3)
        
        # ReplaceState navigation
        driver.execute_script("history.replaceState({}, 'Test', '/test-page-2');")
        print("[INFO] replaceState navigation")
        
        time.sleep(0.5)
        
        # Navigate to non-existent page
        try:
            driver.get(web_app_url + "/nonexistent-page")
            time.sleep(1)
        except Exception:
            pass
        print("[ERROR] Navigation to non-existent page")
        
        time.sleep(0.5)
        
        # =========================================================================
        # SECTION 26: HEALTH SNAPSHOT
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 26: HEALTH SNAPSHOT (health-snapshot)")
        print("=" * 70)
        
        # Health snapshots are sent automatically every 30s during automation
        print("[INFO] Waiting for automatic health snapshots...")
        time.sleep(5)
        
        # =========================================================================
        # SECTION 27: REPEATED SELECTOR FAILURES - Trigger high severity
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 27: REPEATED SELECTOR FAILURES (HIGH SEVERITY)")
        print("=" * 70)
        
        # Same selector queried repeatedly (polling pattern)
        same_selector = "div.missing-polling-class"
        for i in range(12):
            driver.execute_script("document.querySelector(arguments[0]);", same_selector)
        
        print(f"[ERROR] Same selector queried 12 times: {same_selector}")
        
        # XPath polling pattern
        same_xpath = "//div[@id='polling-xpath-missing']"
        for i in range(12):
            driver.execute_script("""
                document.evaluate(arguments[0], document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
            """, same_xpath)
        
        print(f"[ERROR] Same XPath queried 12 times: {same_xpath}")
        
        time.sleep(0.5)
        
        # =========================================================================
        # SECTION 28: PERFORMANCE DEGRADATION
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 28: PERFORMANCE DEGRADATION")
        print("=" * 70)
        
        # Create performance-heavy operations
        driver.execute_script("""
            // Memory-intensive operation
            var arr = [];
            for (var i = 0; i < 100000; i++) {
                arr.push({
                    id: i,
                    data: new Array(100).fill('x')
                });
            }
            console.log('Created large array');
        """)
        print("[WARNING] Memory-intensive operation executed")
        
        time.sleep(0.5)
        
        # Trigger page unload
        print("\n" + "=" * 70)
        print("SECTION 29: PAGE UNLOAD EVENTS")
        print("=" * 70)
        
        driver.get(web_app_url + "/dashboard")
        time.sleep(1)
        print("[INFO] Navigated for page unload test")

        # Navigate back for remaining tests
        driver.get(web_app_url)
        time.sleep(2)

        # =========================================================================
        # SECTION 30: KEYBOARD ACTIONS
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 30: KEYBOARD ACTIONS (keyboard-action)")
        print("=" * 70)

        # Special keys on input field
        try:
            username_field = driver.find_element(By.ID, "username")
            username_field.clear()
            username_field.send_keys("test")
            username_field.send_keys(Keys.TAB)
            username_field.send_keys(Keys.BACKSPACE)
            username_field.send_keys(Keys.DELETE)
            username_field.send_keys(Keys.ESCAPE)
            username_field.send_keys(Keys.ENTER)
            print("[INFO] Special keys sent: TAB, BACKSPACE, DELETE, ESCAPE, ENTER")
        except Exception:
            print("[ERROR] Failed to send special keys to username field")

        # Arrow keys and navigation keys
        try:
            search_field = driver.find_element(By.ID, "search")
            search_field.click()
            search_field.send_keys(Keys.ARROW_DOWN)
            search_field.send_keys(Keys.ARROW_UP)
            search_field.send_keys(Keys.ARROW_LEFT)
            search_field.send_keys(Keys.ARROW_RIGHT)
            search_field.send_keys(Keys.HOME)
            search_field.send_keys(Keys.END)
            search_field.send_keys(Keys.PAGE_UP)
            search_field.send_keys(Keys.PAGE_DOWN)
            print("[INFO] Navigation keys sent: Arrows, Home, End, PageUp, PageDown")
        except Exception:
            print("[ERROR] Failed to send navigation keys")

        # Function keys
        try:
            actions = ActionChains(driver)
            actions.send_keys(Keys.F1)
            actions.send_keys(Keys.F2)
            actions.send_keys(Keys.F3)
            actions.send_keys(Keys.F5)
            actions.perform()
            print("[INFO] Function keys sent: F1, F2, F3, F5")
        except Exception:
            print("[ERROR] Failed to send function keys")

        # Modifier combos
        try:
            username_field = driver.find_element(By.ID, "username")
            username_field.click()
            username_field.send_keys("hello")
            actions = ActionChains(driver)
            actions.key_down(Keys.CONTROL).send_keys('a').key_up(Keys.CONTROL).perform()
            actions = ActionChains(driver)
            actions.key_down(Keys.CONTROL).send_keys('c').key_up(Keys.CONTROL).perform()
            actions = ActionChains(driver)
            actions.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
            actions = ActionChains(driver)
            actions.key_down(Keys.SHIFT).send_keys(Keys.TAB).key_up(Keys.SHIFT).perform()
            print("[INFO] Modifier combos sent: Ctrl+A, Ctrl+C, Ctrl+V, Shift+Tab")
        except Exception:
            print("[ERROR] Failed to send modifier combos")

        time.sleep(0.5)

        # =========================================================================
        # SECTION 31: PROGRAMMATIC CLICK
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 31: PROGRAMMATIC CLICK (programmatic-click)")
        print("=" * 70)

        # Call .click() via JS on existing buttons
        driver.execute_script("document.getElementById('testButton').click();")
        print("[INFO] Programmatic click on #testButton")

        driver.execute_script("document.getElementById('multiClickBtn').click();")
        print("[INFO] Programmatic click on #multiClickBtn")

        driver.execute_script("document.getElementById('register').click();")
        print("[INFO] Programmatic click on #register")

        driver.execute_script("document.getElementById('cancel').click();")
        print("[INFO] Programmatic click on #cancel")

        driver.execute_script("document.getElementById('reset').click();")
        print("[INFO] Programmatic click on #reset")

        # Click on tab buttons
        driver.execute_script("document.querySelectorAll('.tab-button')[1].click();")
        print("[INFO] Programmatic click on tab button 2")

        time.sleep(0.5)

        # =========================================================================
        # SECTION 32: CLICK ON ARIA-DISABLED ELEMENTS
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 32: CLICK ON ARIA-DISABLED (click-on-disabled)")
        print("=" * 70)

        # Set aria-disabled on existing button and click
        driver.execute_script("""
            var btn = document.getElementById('cancel');
            btn.setAttribute('aria-disabled', 'true');
        """)
        try:
            driver.find_element(By.ID, "cancel").click()
            print("[WARNING] Clicked aria-disabled cancel button")
        except Exception:
            print("[ERROR] Could not click aria-disabled cancel button")

        # Set disabled attribute on register and click
        driver.execute_script("""
            var btn = document.getElementById('register');
            btn.disabled = true;
        """)
        try:
            driver.find_element(By.ID, "register").click()
            print("[WARNING] Clicked disabled register button")
        except Exception:
            print("[ERROR] Could not click disabled register button (expected)")

        # Clean up
        driver.execute_script("""
            document.getElementById('cancel').removeAttribute('aria-disabled');
            document.getElementById('register').disabled = false;
        """)

        time.sleep(0.5)

        # =========================================================================
        # SECTION 33: VALUE MANIPULATION (textarea, select, innerText)
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 33: VALUE MANIPULATION (value-manipulation)")
        print("=" * 70)

        # Textarea value via native setter
        driver.execute_script("""
            var setter = Object.getOwnPropertyDescriptor(
                window.HTMLTextAreaElement.prototype, 'value'
            ).set;
            var textarea = document.getElementById('comments');
            if (textarea && setter) {
                setter.call(textarea, 'Programmatic textarea content set via native setter');
                textarea.dispatchEvent(new Event('input', { bubbles: true }));
            }
        """)
        print("[INFO] Textarea value set via native setter")

        time.sleep(0.6)

        # Select value via native setter
        driver.execute_script("""
            var setter = Object.getOwnPropertyDescriptor(
                window.HTMLSelectElement.prototype, 'value'
            ).set;
            var select = document.getElementById('country');
            if (select && setter) {
                setter.call(select, 'de');
                select.dispatchEvent(new Event('change', { bubbles: true }));
            }
        """)
        print("[INFO] Select value set to 'de' via native setter")

        time.sleep(0.6)

        # Select selectedIndex via native setter
        driver.execute_script("""
            var setter = Object.getOwnPropertyDescriptor(
                window.HTMLSelectElement.prototype, 'selectedIndex'
            ).set;
            var select = document.getElementById('country');
            if (select && setter) {
                setter.call(select, 4);
                select.dispatchEvent(new Event('change', { bubbles: true }));
            }
        """)
        print("[INFO] Select selectedIndex set to 4 via native setter")

        time.sleep(0.6)

        # innerText via native setter
        driver.execute_script("""
            var setter = Object.getOwnPropertyDescriptor(
                window.HTMLElement.prototype, 'innerText'
            ).set;
            var btn = document.getElementById('testButton');
            if (btn && setter) {
                setter.call(btn, 'Modified Button Text');
            }
        """)
        print("[INFO] innerText set on #testButton via native setter")

        time.sleep(0.5)

        # =========================================================================
        # SECTION 34: ELEMENT INSPECTION
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 34: ELEMENT INSPECTION (element-inspection)")
        print("=" * 70)

        # getBoundingClientRect
        driver.execute_script("document.getElementById('username').getBoundingClientRect();")
        print("[INFO] getBoundingClientRect on #username")

        # getComputedStyle
        driver.execute_script("window.getComputedStyle(document.getElementById('login'));")
        print("[INFO] getComputedStyle on #login")

        # offsetWidth / offsetHeight on different elements
        driver.execute_script("var w = document.getElementById('testButton').offsetWidth;")
        print("[INFO] offsetWidth on #testButton")

        driver.execute_script("var h = document.getElementById('email').offsetHeight;")
        print("[INFO] offsetHeight on #email")

        # clientWidth / clientHeight
        driver.execute_script("var w = document.getElementById('dataTable').clientWidth;")
        print("[INFO] clientWidth on #dataTable")

        # scrollWidth / scrollHeight
        driver.execute_script("var h = document.getElementById('itemList').scrollHeight;")
        print("[INFO] scrollHeight on #itemList")

        driver.execute_script("var w = document.getElementById('comments').scrollWidth;")
        print("[INFO] scrollWidth on #comments")

        time.sleep(0.5)

        # =========================================================================
        # SECTION 35: DOM ATTRIBUTE CHANGES
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 35: DOM ATTRIBUTE CHANGES (dom-attribute-changes)")
        print("=" * 70)

        # Modify class attribute
        driver.execute_script("""
            document.getElementById('testButton').setAttribute('class', 'modified-class-test');
        """)
        print("[INFO] Changed class on #testButton")

        # Modify style attribute
        driver.execute_script("""
            document.getElementById('login').style.backgroundColor = 'red';
        """)
        print("[INFO] Changed style on #login")

        # Toggle disabled
        driver.execute_script("""
            document.getElementById('register').disabled = true;
        """)
        time.sleep(0.1)
        driver.execute_script("""
            document.getElementById('register').disabled = false;
        """)
        print("[INFO] Toggled disabled on #register")

        # Set aria-expanded
        driver.execute_script("""
            document.getElementById('testModal').setAttribute('aria-expanded', 'true');
        """)
        print("[INFO] Set aria-expanded on #testModal")

        # Set aria-selected
        driver.execute_script("""
            document.getElementById('tab1').setAttribute('aria-selected', 'true');
        """)
        print("[INFO] Set aria-selected on #tab1")

        # Set data-testid
        driver.execute_script("""
            document.getElementById('username').setAttribute('data-testid', 'user-input-field');
        """)
        print("[INFO] Set data-testid on #username")

        # Set data-state
        driver.execute_script("""
            document.getElementById('country').setAttribute('data-state', 'modified');
        """)
        print("[INFO] Set data-state on #country")

        # Set hidden attribute
        driver.execute_script("""
            document.getElementById('warningBtn').setAttribute('hidden', 'true');
        """)
        time.sleep(0.1)
        driver.execute_script("""
            document.getElementById('warningBtn').removeAttribute('hidden');
        """)
        print("[INFO] Toggled hidden on #warningBtn")

        time.sleep(0.7)

        # =========================================================================
        # SECTION 36: SELECTOR ERROR (invalid CSS syntax)
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 36: SELECTOR ERROR (selector-error)")
        print("=" * 70)

        invalid_selectors = [
            "[",
            "##double-hash",
            ":not(",
            "div[attr=",
            ">>>invalid",
        ]
        for sel in invalid_selectors:
            try:
                driver.execute_script("""
                    try {
                        document.querySelector(arguments[0]);
                    } catch(e) {
                        // Error caught - tracker already enqueued selector-error
                    }
                """, sel)
                print(f"[ERROR] Invalid selector tested: {sel}")
            except Exception:
                print(f"[ERROR] Invalid selector caused WebDriver error: {sel}")

        time.sleep(0.5)

        # =========================================================================
        # SECTION 37: XHR/FETCH SUCCESS
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 37: XHR/FETCH SUCCESS (xhr-success, fetch-success)")
        print("=" * 70)

        # XHR GET to / (returns 200)
        driver.execute_script("""
            var xhr = new XMLHttpRequest();
            xhr.open('GET', '/');
            xhr.send();
        """)
        print("[INFO] XHR GET / (expect 200)")

        # XHR GET to /dashboard (returns 200)
        driver.execute_script("""
            var xhr = new XMLHttpRequest();
            xhr.open('GET', '/dashboard');
            xhr.send();
        """)
        print("[INFO] XHR GET /dashboard (expect 200)")

        # Fetch GET to /
        driver.execute_script("""
            fetch('/').then(function(r) { return r.text(); });
        """)
        print("[INFO] Fetch GET / (expect 200)")

        # Fetch GET to /dashboard
        driver.execute_script("""
            fetch('/dashboard').then(function(r) { return r.text(); });
        """)
        print("[INFO] Fetch GET /dashboard (expect 200)")

        # Fetch POST to /dashboard
        driver.execute_script("""
            fetch('/dashboard', { method: 'POST', body: 'test=data' })
                .then(function(r) { return r.text(); })
                .catch(function(e) {});
        """)
        print("[INFO] Fetch POST /dashboard")

        time.sleep(1)

        # =========================================================================
        # SECTION 38: CONNECTION ONLINE/OFFLINE
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 38: CONNECTION ONLINE/OFFLINE (connection)")
        print("=" * 70)

        driver.execute_script("window.dispatchEvent(new Event('offline'));")
        print("[WARNING] Dispatched offline event")

        time.sleep(0.3)

        driver.execute_script("window.dispatchEvent(new Event('online'));")
        print("[INFO] Dispatched online event")

        time.sleep(0.5)

        # =========================================================================
        # SECTION 39: CHECKBOX, RADIO, SELECT INTERACTIONS
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 39: CHECKBOX, RADIO, SELECT INTERACTIONS")
        print("=" * 70)

        # Click checkboxes
        try:
            driver.find_element(By.ID, "check1").click()
            driver.find_element(By.ID, "check2").click()
            driver.find_element(By.ID, "check3").click()
            print("[INFO] Clicked checkboxes: check1, check2, check3")
        except Exception:
            print("[ERROR] Failed to click checkboxes")

        # Click radio buttons
        try:
            driver.find_element(By.ID, "radio1").click()
            time.sleep(0.2)
            driver.find_element(By.ID, "radio2").click()
            time.sleep(0.2)
            driver.find_element(By.ID, "radio3").click()
            print("[INFO] Clicked radios: radio1, radio2, radio3")
        except Exception:
            print("[ERROR] Failed to click radio buttons")

        # Select dropdown interaction
        try:
            select_el = Select(driver.find_element(By.ID, "country"))
            select_el.select_by_value("us")
            time.sleep(0.2)
            select_el.select_by_value("uk")
            time.sleep(0.2)
            select_el.select_by_visible_text("Germany")
            time.sleep(0.2)
            select_el.select_by_visible_text("France")
            time.sleep(0.2)
            select_el.select_by_value("tr")
            print("[INFO] Selected dropdown options: US, UK, Germany, France, Turkey")
        except Exception:
            print("[ERROR] Failed to interact with select dropdown")

        time.sleep(0.5)

        # =========================================================================
        # SECTION 40: TAB SWITCHING
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 40: TAB SWITCHING (dom-attribute-changes, programmatic-click)")
        print("=" * 70)

        # Switch through all tabs
        driver.execute_script("document.querySelectorAll('.tab-button')[1].click();")
        time.sleep(0.5)
        print("[INFO] Switched to Tab 2")

        driver.execute_script("document.querySelectorAll('.tab-button')[2].click();")
        time.sleep(0.5)
        print("[INFO] Switched to Tab 3")

        driver.execute_script("document.querySelectorAll('.tab-button')[0].click();")
        time.sleep(0.5)
        print("[INFO] Switched back to Tab 1")

        # Type in tab inputs
        try:
            driver.execute_script("document.querySelectorAll('.tab-button')[1].click();")
            time.sleep(0.3)
            tab2_input = driver.find_element(By.CSS_SELECTOR, "#tab2 input")
            tab2_input.send_keys("Tab 2 test input")
            print("[INFO] Typed in Tab 2 input field")
        except Exception:
            print("[ERROR] Failed to type in tab input")

        time.sleep(0.5)

        # =========================================================================
        # SECTION 41: MODAL OPEN/CLOSE
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 41: MODAL OPEN/CLOSE (dom-attribute-changes)")
        print("=" * 70)

        # Open modal
        driver.execute_script("toggleModal();")
        time.sleep(0.5)
        print("[INFO] Modal opened")

        # Close modal
        driver.execute_script("toggleModal();")
        time.sleep(0.7)
        print("[INFO] Modal closed")

        # Open and close again
        driver.execute_script("toggleModal();")
        time.sleep(0.3)
        driver.execute_script("toggleModal();")
        time.sleep(0.5)
        print("[INFO] Modal opened and closed again")

        # =========================================================================
        # SECTION 42: TABLE & LIST OPERATIONS
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 42: TABLE & LIST OPERATIONS (dom-mutations)")
        print("=" * 70)

        # Add 12 table rows (crosses threshold of >= 10)
        driver.execute_script("""
            for (var i = 0; i < 12; i++) { addTableRow(); }
        """)
        time.sleep(0.5)
        print("[INFO] Added 12 table rows")

        # Remove 6 rows (crosses threshold of >= 5 removed)
        driver.execute_script("""
            for (var i = 0; i < 6; i++) { removeTableRow(); }
        """)
        time.sleep(0.5)
        print("[INFO] Removed 6 table rows")

        # Add 12 list items
        driver.execute_script("""
            for (var i = 0; i < 12; i++) { addListItem(); }
        """)
        time.sleep(0.5)
        print("[INFO] Added 12 list items")

        # Remove 6 list items
        driver.execute_script("""
            for (var i = 0; i < 6; i++) { removeListItem(); }
        """)
        time.sleep(0.5)
        print("[INFO] Removed 6 list items")

        # =========================================================================
        # SECTION 43: PROGRESS BAR
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 43: PROGRESS BAR (dom-attribute-changes)")
        print("=" * 70)

        driver.execute_script("updateProgress();")
        time.sleep(1.5)
        print("[INFO] Progress bar updated (0% -> 100%)")

        # =========================================================================
        # SECTION 44: FORM SUBMISSION SUCCESS
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 44: FORM SUBMISSION SUCCESS (form-submission)")
        print("=" * 70)

        # Create a valid form dynamically, prevent navigation, submit
        driver.execute_script("""
            var form = document.createElement('form');
            form.id = 'test-dynamic-form';
            form.action = '/dashboard';
            form.method = 'get';

            var input = document.createElement('input');
            input.type = 'text';
            input.name = 'testField';
            input.value = 'valid-data';
            form.appendChild(input);

            document.body.appendChild(form);

            // Prevent actual navigation
            form.addEventListener('submit', function(e) { e.preventDefault(); });

            // Dispatch submit event
            form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
        """)
        print("[INFO] Dynamic form submitted successfully (no invalid fields)")

        time.sleep(0.3)

        # Also submit the mainForm with valid data
        driver.execute_script("""
            var form = document.getElementById('mainForm');
            if (form) {
                // Clear invalid data from earlier tests
                var email = document.getElementById('email');
                if (email) email.value = 'valid@example.com';
                var number = document.getElementById('number');
                if (number) number.value = '42';

                form.addEventListener('submit', function(e) { e.preventDefault(); });
                form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
            }
        """)
        print("[INFO] mainForm submitted with valid data")

        time.sleep(0.5)

        # =========================================================================
        # SECTION 45: SUCCESSFUL SELECTOR QUERIES (selector-found)
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 45: SUCCESSFUL SELECTOR QUERIES (selector-found)")
        print("=" * 70)

        # Reload page with TRACK_SUCCESS_SELECTORS enabled
        driver.execute_script("window.ENV_TRACK_SUCCESS = 'true';")
        driver.get(web_app_url)
        time.sleep(2)
        print("[INFO] Page reloaded with TRACK_SUCCESS_SELECTORS enabled")

        # Perform successful queries
        driver.execute_script("document.querySelector('#username');")
        print("[INFO] Successful querySelector for #username")

        driver.execute_script("document.getElementById('login');")
        print("[INFO] Successful getElementById for login")

        driver.execute_script("document.querySelectorAll('button');")
        print("[INFO] Successful querySelectorAll for button")

        driver.execute_script("document.getElementsByClassName('card');")
        print("[INFO] Successful getElementsByClassName for card")

        driver.execute_script("document.getElementsByTagName('input');")
        print("[INFO] Successful getElementsByTagName for input")

        driver.execute_script("document.querySelector('.tab-button');")
        print("[INFO] Successful querySelector for .tab-button")

        time.sleep(1)

        # =========================================================================
        # SECTION 46: FRAMEWORK ERROR SIMULATION (React / Angular / Vue)
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 46: FRAMEWORK ERROR SIMULATION")
        print("=" * 70)

        # Inject fake framework globals before page reload so performance.js
        # detects them and activates framework-specific error hooks
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': """
                // Fake React DevTools hook with renderers so detection triggers
                window.__REACT_DEVTOOLS_GLOBAL_HOOK__ = {
                    renderers: new Map([[1, { version: '18.2.0-test' }]]),
                    onCommitFiberRoot: function() {},
                    onCommitFiberUnmount: function() {},
                    supportsFiber: true
                };

                // Fake Angular ng global so detection triggers
                window.ng = { getComponent: function() { return null; } };

                // Fake Vue 3 global so detection triggers
                window.__VUE__ = {
                    createApp: function(opts) {
                        return {
                            config: { errorHandler: null, warnHandler: null },
                            mount: function() {},
                            use: function() { return this; }
                        };
                    }
                };
            """
        })
        print("[INFO] Injected fake framework globals for detection")

        # Reload page so performance.js detects frameworks on init
        driver.get(web_app_url)
        time.sleep(3)
        print("[INFO] Page reloaded with framework globals — detection should fire")

        # --- React errors: trigger via console.error with React-specific patterns ---
        driver.execute_script("""
            console.error('The above error occurred in the <UserProfile> component');
        """)
        print("[ERROR] React render error simulated via console.error pattern")
        time.sleep(0.3)

        driver.execute_script("""
            console.error('Hydration failed because the initial UI does not match what was rendered on the server. Content did not match.');
        """)
        print("[ERROR] React hydration mismatch simulated")
        time.sleep(0.3)

        driver.execute_script("""
            console.error('Each child in a list should have a unique "key" prop.');
        """)
        print("[WARNING] React key warning simulated")
        time.sleep(0.3)

        # --- Angular errors: trigger via console.error with NG error codes ---
        driver.execute_script("""
            console.error('NG0100: ExpressionChangedAfterItHasBeenCheckedError: Expression has changed after it was checked.');
        """)
        print("[ERROR] Angular framework error (NG0100) simulated")
        time.sleep(0.3)

        driver.execute_script("""
            console.error('NG0200: Circular dependency in DI detected for InjectionToken.');
        """)
        print("[ERROR] Angular framework error (NG0200) simulated")
        time.sleep(0.3)

        driver.execute_script("""
            console.error('ExpressionChangedAfterItHasBeenCheckedError: Previous value was true, current value is false.');
        """)
        print("[ERROR] Angular change detection error simulated")
        time.sleep(0.3)

        # --- Vue errors: trigger via the Vue error/warn handlers if hooked ---
        # Vue hooks are set on createApp().config — since we faked createApp,
        # we call it and trigger the error handler
        driver.execute_script("""
            try {
                if (window.__VUE__ && window.__VUE__.createApp) {
                    var app = window.__VUE__.createApp({});
                    if (app.config && app.config.errorHandler) {
                        app.config.errorHandler(
                            new Error('Vue test render error in computed property'),
                            { $: { type: { __name: 'TestComponent' } } },
                            'render function'
                        );
                    }
                    if (app.config && app.config.warnHandler) {
                        app.config.warnHandler(
                            'Component is missing template or render function',
                            { $: { type: { __name: 'BrokenWidget' } } },
                            'Component render'
                        );
                    }
                }
            } catch(e) { console.log('Vue error simulation fallback:', e); }
        """)
        print("[ERROR] Vue error and warning simulated via hooked handlers")

        time.sleep(1)

        # =========================================================================
        # SECTION 47: QUEUE OVERFLOW (queue-overflow)
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 47: QUEUE OVERFLOW (queue-overflow)")
        print("=" * 70)

        # Generate 600+ events rapidly to exceed MAX_QUEUE_SIZE (500)
        # console.error calls will each generate a console-error event
        driver.execute_script("""
            for (var i = 0; i < 620; i++) {
                console.error('Overflow stress test event #' + i);
            }
        """)
        print("[WARNING] Fired 620 rapid console.error calls to trigger queue overflow")
        time.sleep(3)

        # =========================================================================
        # SECTION 48: SESSION END (session-end)
        # =========================================================================
        print("\n" + "=" * 70)
        print("SECTION 48: SESSION END (session-end)")
        print("=" * 70)

        # Dispatch pagehide event to trigger session-end
        driver.execute_script("""
            window.dispatchEvent(new Event('pagehide'));
        """)
        print("[INFO] Dispatched pagehide event to trigger session-end")
        time.sleep(1)

        # Navigate away to also trigger beforeunload/pagehide naturally
        driver.get("about:blank")
        time.sleep(1)
        print("[INFO] Navigated to about:blank — session ended")

        # Navigate back for final flush
        driver.get(web_app_url)
        time.sleep(2)
        print("[INFO] Navigated back for final event flush")

        # =========================================================================
        # FINAL SUMMARY
        # =========================================================================
        print("\n" + "=" * 70)
        print("TEST SUITE COMPLETE")
        print("=" * 70)
        print("\nERROR & EVENT TYPES GENERATED:")
        print("  - selector-miss: ~150+ queries")
        print("  - selector-found: 6 successful queries")
        print("  - selector-error: 5 invalid CSS syntax errors")
        print("  - xpath-not-found: ~50+ queries")
        print("  - xpath-error: 3 invalid XPath attempts")
        print("  - js-error: 8 different JavaScript error types")
        print("  - unhandled-rejection: 4 rejections")
        print("  - xhr-error: 5 failed XHR requests")
        print("  - xhr-success: 2 successful XHR requests")
        print("  - xhr-slow: 1 slow XHR request (6s endpoint)")
        print("  - fetch-error: 5 failed fetch requests")
        print("  - fetch-success: 3 successful fetch requests")
        print("  - fetch-slow: 1 slow fetch request (6s endpoint)")
        print("  - rapid-clicks: 25 rapid clicks")
        print("  - dom-mutations: 60+ element mutations (table/list ops)")
        print("  - dom-attribute-changes: 10+ attribute modifications")
        print("  - element-inspection: 7 inspection method calls")
        print("  - value-manipulation: textarea, select, selectedIndex, innerText")
        print("  - form-validation-failure: 1 validation failure")
        print("  - form-submission: 2 successful form submissions")
        print("  - programmatic-click: 6 programmatic clicks")
        print("  - click-on-disabled: 2 (disabled + aria-disabled)")
        print("  - keyboard-action: 20+ special keys and modifier combos")
        print("  - user-click: checkbox, radio, select, button clicks")
        print("  - programmatic-input: 2 programmatic inputs")
        print("  - console-error: 9+ console errors")
        print("  - console-warn: 3+ console warnings")
        print("  - blocking-overlay-detected: 1 overlay created")
        print("  - media-load-error: 3 broken media elements")
        print("  - resource-error: 2 broken resources (CSS, JS)")
        print("  - websocket-error: 1 failed WebSocket")
        print("  - connection: 1 offline + 1 online event")
        print("  - dialog-opened: 3 dialogs (alert/confirm/prompt)")
        print("  - page-idle: 1 idle event")
        print("  - page-load: automatic on each page load")
        print("  - hashchange/pushState/replaceState: navigation events")
        print("  - automation-detected: automatic on page load")
        print("  - csp-violation: 3 CSP violations (font, iframe, script)")
        print("  - react-render-error: 1 simulated via console pattern")
        print("  - react-hydration-mismatch: 1 simulated via console pattern")
        print("  - react-key-warning: 1 simulated via console pattern")
        print("  - angular-framework-error: 2 simulated (NG0100, NG0200)")
        print("  - angular-change-detection-error: 1 simulated")
        print("  - vue-error: 1 simulated via hooked handler")
        print("  - vue-warning: 1 simulated via hooked handler")
        print("  - queue-overflow: 1 triggered via 620 rapid events")
        print("  - session-end: 1 via pagehide + navigation")
        print("\nCheck Kibana QA Monitor Dashboard for all events!")
        print("=" * 70)
        
    finally:
        print("\n[INFO] Closing browser...")
        driver.quit()


if __name__ == "__main__":
    run_error_test_suite()
