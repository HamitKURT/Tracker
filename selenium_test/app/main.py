import time
import os
import random
import string
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def set_chrome_options() -> ChromeOptions:
    options = ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    return options

def random_text(length=10):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def run_telemetry_test():
    print("=" * 60)
    print("Starting Comprehensive Selenium Telemetry Test")
    print("=" * 60)
    
    web_app_url = os.getenv("WEB_APP_URL", "http://web-app:8081")
    chromedriver_path = os.getenv("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")
    
    from selenium.webdriver.chrome.service import Service
    service = Service(executable_path=chromedriver_path)
    driver = webdriver.Chrome(service=service, options=set_chrome_options())
    wait = WebDriverWait(driver, 10)
    
    try:
        # =========================================================================
        # TEST 1: Page Load Events (page-load, navigation, automation-detected)
        # =========================================================================
        print("\n[TEST 1] Page Load Events")
        print("-" * 40)
        driver.get(web_app_url)
        time.sleep(2)
        print("  -> Page loaded, waiting for initial events...")
        
        # =========================================================================
        # TEST 2: DOM Query Events (dom-query)
        # =========================================================================
        print("\n[TEST 2] DOM Query Events")
        print("-" * 40)
        
        # querySelector - success
        driver.execute_script("document.querySelector('#username');")
        print("  -> querySelector (success)")
        
        # querySelector - failure
        driver.execute_script("document.querySelector('.nonexistent-class');")
        print("  -> querySelector (failure)")
        
        # getElementById - success
        driver.execute_script("document.getElementById('username');")
        print("  -> getElementById (success)")
        
        # getElementById - failure
        driver.execute_script("document.getElementById('nonexistent-id-12345');")
        print("  -> getElementById (failure)")
        
        # getElementsByClassName - success
        driver.execute_script("document.getElementsByClassName('form-group');")
        print("  -> getElementsByClassName (success)")
        
        # getElementsByClassName - failure
        driver.execute_script("document.getElementsByClassName('no-such-class');")
        print("  -> getElementsByClassName (failure)")
        
        # getElementsByTagName - success
        driver.execute_script("document.getElementsByTagName('button');")
        print("  -> getElementsByTagName (success)")
        
        # getElementsByTagName - failure
        driver.execute_script("document.getElementsByTagName('nonexistent-tag');")
        print("  -> getElementsByTagName (failure)")
        
        # getElementsByName - success
        driver.execute_script("document.getElementsByName('username');")
        print("  -> getElementsByName (success)")
        
        # getElementsByName - failure
        driver.execute_script("document.getElementsByName('fake-name-xyz');")
        print("  -> getElementsByName (failure)")
        
        # XPath queries - use ORDERED_NODE_ITERATOR_TYPE to get snapshotLength
        driver.execute_script("""
            var result = document.evaluate('//button[@id="testButton"]', document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
            var count = result.snapshotLength;
        """)
        print("  -> XPath query (success)")
        
        driver.execute_script("""
            var result = document.evaluate('//div[@id="nonexistent-xyz"]', document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
            var count = result.snapshotLength;
        """)
        print("  -> XPath query (failure)")
        
        time.sleep(0.5)
        
        # =========================================================================
        # TEST 3: Element Inspection Events (element-inspection)
        # =========================================================================
        print("\n[TEST 3] Element Inspection Events")
        print("-" * 40)
        
        # getBoundingClientRect
        driver.execute_script("""
            var el = document.getElementById('testButton');
            if (el) el.getBoundingClientRect();
        """)
        print("  -> getBoundingClientRect")
        
        # getComputedStyle
        driver.execute_script("""
            var el = document.getElementById('username');
            if (el) window.getComputedStyle(el);
        """)
        print("  -> getComputedStyle")
        
        # offset properties
        driver.execute_script("""
            var el = document.getElementById('testButton');
            if (el) { el.offsetWidth; el.offsetHeight; el.offsetTop; el.offsetLeft; }
        """)
        print("  -> offsetWidth/Height/Top/Left")
        
        # client properties
        driver.execute_script("""
            var el = document.getElementById('testButton');
            if (el) { el.clientWidth; el.clientHeight; el.clientTop; el.clientLeft; }
        """)
        print("  -> clientWidth/Height/Top/Left")
        
        # scroll properties
        driver.execute_script("""
            var el = document.getElementById('testButton');
            if (el) { el.scrollWidth; el.scrollHeight; el.scrollTop; el.scrollLeft; }
        """)
        print("  -> scrollWidth/Height/Top/Left")
        
        # querySelectorAll on element
        driver.execute_script("""
            var el = document.querySelector('.container');
            if (el) el.querySelectorAll('button');
        """)
        print("  -> Element.querySelectorAll")
        
        # querySelector on element
        driver.execute_script("""
            var el = document.querySelector('.container');
            if (el) el.querySelector('button');
        """)
        print("  -> Element.querySelector")
        
        # matches
        driver.execute_script("""
            var el = document.getElementById('testButton');
            if (el) el.matches('button');
        """)
        print("  -> Element.matches")
        
        # closest
        driver.execute_script("""
            var el = document.getElementById('testButton');
            if (el && el.closest) el.closest('.container');
        """)
        print("  -> Element.closest")
        
        time.sleep(0.5)
        
        # =========================================================================
        # TEST 4: Data Extraction Events (data-extraction)
        # =========================================================================
        print("\n[TEST 4] Data Extraction Events")
        print("-" * 40)
        
        # getAttribute - success
        driver.execute_script("""
            var el = document.getElementById('testButton');
            if (el) el.getAttribute('id');
        """)
        print("  -> getAttribute (success)")
        
        # getAttribute - failure
        driver.execute_script("""
            var el = document.getElementById('testButton');
            if (el) el.getAttribute('data-nonexistent');
        """)
        print("  -> getAttribute (null)")
        
        # hasAttribute
        driver.execute_script("""
            var el = document.getElementById('testButton');
            if (el) { el.hasAttribute('id'); el.hasAttribute('data-nonexistent'); }
        """)
        print("  -> hasAttribute")
        
        # innerText (get)
        driver.execute_script("""
            var el = document.querySelector('h1');
            if (el) el.innerText;
        """)
        print("  -> innerText (get)")
        
        # textContent (get)
        driver.execute_script("""
            var el = document.querySelector('h1');
            if (el) el.textContent;
        """)
        print("  -> textContent (get)")
        
        time.sleep(0.5)
        
        # =========================================================================
        # TEST 5: Value Manipulation Events (value-manipulation)
        # =========================================================================
        print("\n[TEST 5] Value Manipulation Events")
        print("-" * 40)
        
        # innerText (set)
        driver.execute_script("""
            var el = document.querySelector('h1');
            if (el) el.innerText = 'Modified by Automation';
        """)
        print("  -> innerText (set)")
        
        # textContent (set)
        driver.execute_script("""
            var el = document.querySelector('p');
            if (el) el.textContent = 'Modified text content';
        """)
        print("  -> textContent (set)")
        
        # Input value (set)
        username_field = driver.find_element(By.ID, "username")
        username_field.clear()
        username_field.send_keys("automation_user")
        print("  -> input.value (set)")
        
        # Textarea value (set)
        driver.execute_script("""
            var textarea = document.createElement('textarea');
            textarea.value = 'Test textarea value';
            document.body.appendChild(textarea);
        """)
        print("  -> textarea.value (set)")
        
        # checkbox checked (set)
        driver.execute_script("""
            var checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.checked = true;
            document.body.appendChild(checkbox);
        """)
        print("  -> checkbox.checked (set)")
        
        time.sleep(0.5)
        
        # =========================================================================
        # TEST 6: Interaction Events (interaction)
        # =========================================================================
        print("\n[TEST 6] Interaction Events")
        print("-" * 40)
        
        # Click events
        try:
            test_btn = driver.find_element(By.ID, "testButton")
            test_btn.click()
            print("  -> button click")
        except Exception as e:
            print(f"  -> button click (failed: {e})")
        
        # Focus events
        driver.execute_script("document.getElementById('username').focus();")
        print("  -> focus event")
        
        # Input/focus events with typing
        try:
            input_field = driver.find_element(By.ID, "username")
            input_field.clear()
            input_field.send_keys("testuser123")
            print("  -> input event")
        except Exception as e:
            print(f"  -> input event (failed: {e})")
        
        # Keydown events
        try:
            input_field = driver.find_element(By.ID, "username")
            input_field.send_keys("a")
            print("  -> keydown event")
        except Exception as e:
            print(f"  -> keydown event (failed: {e})")
        
        # Change events (blur to trigger)
        try:
            input_field = driver.find_element(By.ID, "username")
            input_field.send_keys(Keys.TAB)
            print("  -> change event")
        except Exception as e:
            print(f"  -> change event (failed: {e})")
        
        time.sleep(0.5)
        
        # =========================================================================
        # TEST 7: Rapid Clicks - Timing Alert
        # =========================================================================
        print("\n[TEST 7] Rapid Clicks (Timing Alert)")
        print("-" * 40)
        
        try:
            test_btn = driver.find_element(By.ID, "testButton")
            actions = ActionChains(driver)
            for i in range(10):
                actions.click(test_btn)
            actions.perform()
            print("  -> 10 rapid clicks executed")
        except Exception as e:
            print(f"  -> Rapid clicks (failed: {e})")
        
        time.sleep(0.5)
        
        # =========================================================================
        # TEST 8: Element Action Events (element-action)
        # =========================================================================
        print("\n[TEST 8] Element Action Events (click)")
        print("-" * 40)
        
        # Various element clicks
        try:
            driver.find_element(By.ID, "testButton").click()
            print("  -> button.click()")
        except: pass
        
        try:
            driver.find_element(By.TAG_NAME, "h1").click()
            print("  -> h1.click()")
        except: pass
        
        try:
            driver.find_element(By.TAG_NAME, "a").click()
            print("  -> link.click()")
        except: pass
        
        time.sleep(0.5)
        
        # =========================================================================
        # TEST 9: Network Request Events (network-request)
        # =========================================================================
        print("\n[TEST 9] Network Request Events")
        print("-" * 40)
        
        # Fetch request
        driver.execute_script("""
            fetch('/events', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ test: 'fetch-request' })
            });
        """)
        print("  -> fetch() request")
        
        # XHR request
        driver.execute_script("""
            var xhr = new XMLHttpRequest();
            xhr.open('GET', 'https://httpbin.org/get');
            xhr.send();
        """)
        print("  -> XMLHttpRequest")
        
        time.sleep(1)
        
        # =========================================================================
        # TEST 10: Form Submit Events (form-submit)
        # =========================================================================
        print("\n[TEST 10] Form Submit Events")
        print("-" * 40)
        
        # Create and submit a form
        driver.execute_script("""
            var form = document.createElement('form');
            form.action = '/test-submit';
            form.method = 'POST';
            var input = document.createElement('input');
            input.name = 'testfield';
            input.value = 'testvalue';
            form.appendChild(input);
            document.body.appendChild(form);
            form.submit();
        """)
        print("  -> form.submit()")
        
        time.sleep(2)
        
        # Go back to main page
        driver.back()
        time.sleep(1)
        
        # =========================================================================
        # TEST 11: Clipboard Events (clipboard)
        # =========================================================================
        print("\n[TEST 11] Clipboard Events")
        print("-" * 40)
        
        # Copy event
        driver.execute_script("""
            var el = document.querySelector('h1');
            if (el) {
                var range = document.createRange();
                range.selectNodeContents(el);
                var selection = window.getSelection();
                selection.removeAllRanges();
                selection.addRange(range);
                document.execCommand('copy');
            }
        """)
        print("  -> copy event")
        
        # Paste event
        try:
            input_field = driver.find_element(By.ID, "username")
            input_field.click()
            input_field.send_keys(Keys.CONTROL, "v")
            print("  -> paste event")
        except: pass
        
        # Cut event
        driver.execute_script("""
            var el = document.querySelector('h1');
            if (el) {
                var range = document.createRange();
                range.selectNodeContents(el);
                var selection = window.getSelection();
                selection.removeAllRanges();
                selection.addRange(range);
                document.execCommand('cut');
            }
        """)
        print("  -> cut event")
        
        time.sleep(0.5)
        
        # =========================================================================
        # TEST 12: Context Menu Events (context-menu)
        # =========================================================================
        print("\n[TEST 12] Context Menu Events")
        print("-" * 40)
        
        try:
            elem = driver.find_element(By.ID, "testButton")
            actions = ActionChains(driver)
            actions.context_click(elem).perform()
            print("  -> contextmenu (right-click)")
        except Exception as e:
            print(f"  -> contextmenu (failed: {e})")
        
        time.sleep(0.5)
        
        # =========================================================================
        # TEST 13: Selection Events (selection)
        # =========================================================================
        print("\n[TEST 13] Selection Events")
        print("-" * 40)
        
        # Text selection
        driver.execute_script("""
            var el = document.querySelector('p');
            if (el) {
                var range = document.createRange();
                range.selectNodeContents(el);
                var selection = window.getSelection();
                selection.removeAllRanges();
                selection.addRange(range);
            }
        """)
        print("  -> text selection")
        
        time.sleep(1)
        
        # =========================================================================
        # TEST 14: Resize Events (resize)
        # =========================================================================
        print("\n[TEST 14] Resize Events")
        print("-" * 40)
        
        driver.set_window_size(1024, 768)
        print("  -> window resize to 1024x768")
        time.sleep(0.3)
        
        driver.set_window_size(800, 600)
        print("  -> window resize to 800x600")
        time.sleep(0.3)
        
        driver.set_window_size(1920, 1080)
        print("  -> window resize to 1920x1080")
        
        time.sleep(0.5)
        
        # =========================================================================
        # TEST 15: Visibility Events (visibility)
        # =========================================================================
        print("\n[TEST 15] Visibility Events")
        print("-" * 40)
        
        # Switch tabs (triggers visibility change)
        driver.execute_script("window.open('about:blank', '_blank');")
        time.sleep(0.5)
        
        # Switch back
        windows = driver.window_handles
        if len(windows) > 1:
            driver.switch_to.window(windows[0])
            print("  -> visibility change (tab switch)")
        
        time.sleep(0.5)
        
        # =========================================================================
        # TEST 16: Connection Events (connection)
        # =========================================================================
        print("\n[TEST 16] Connection Events")
        print("-" * 40)
        
        # Go offline
        driver.execute_script("window.dispatchEvent(new Event('offline'));")
        print("  -> offline event")
        
        time.sleep(0.3)
        
        # Go online
        driver.execute_script("window.dispatchEvent(new Event('online'));")
        print("  -> online event")
        
        time.sleep(0.5)
        
        # =========================================================================
        # TEST 17: Mutation Observer Events (mutation-observer)
        # =========================================================================
        print("\n[TEST 17] Mutation Observer Events")
        print("-" * 40)
        
        # Trigger DOM mutations
        driver.execute_script("""
            // Create new elements
            for (var i = 0; i < 5; i++) {
                var div = document.createElement('div');
                div.className = 'mutation-test';
                div.textContent = 'Mutated element ' + i;
                document.body.appendChild(div);
            }
            
            // Modify existing element
            var h1 = document.querySelector('h1');
            if (h1) h1.textContent = 'Mutated Title';
            
            // Remove elements
            var toRemove = document.querySelectorAll('.mutation-test');
            toRemove.forEach(function(el) { el.remove(); });
        """)
        print("  -> DOM mutations (add/modify/remove)")
        
        time.sleep(1)
        
        # =========================================================================
        # TEST 18: JavaScript Error Events (js-error)
        # =========================================================================
        print("\n[TEST 18] JavaScript Error Events")
        print("-" * 40)
        
        # Wrap JS errors in try-catch to prevent Selenium from throwing
        def execute_js_with_error(driver, script, description):
            try:
                driver.execute_script(script)
            except Exception:
                pass
            print(f"  -> {description}")
        
        # ReferenceError
        execute_js_with_error(driver, "undefinedFunctionXYZ123();", "ReferenceError")
        time.sleep(0.2)
        
        # TypeError
        execute_js_with_error(driver, "nullObject.property;", "TypeError")
        time.sleep(0.2)
        
        # SyntaxError (in a setTimeout to catch parse errors)
        execute_js_with_error(driver, "setTimeout(function() { JSON.parse('invalid json {{{'); }, 10);", "SyntaxError")
        time.sleep(0.5)
        
        # Click the error button
        try:
            error_btn = driver.find_element(By.CLASS_NAME, "error-btn")
            error_btn.click()
            print("  -> error-btn click")
        except: pass
        
        time.sleep(0.5)
        
        # =========================================================================
        # TEST 19: Promise Rejection Events (promise-rejection)
        # =========================================================================
        print("\n[TEST 19] Promise Rejection Events")
        print("-" * 40)
        
        # Promise.reject needs a handler to not cause unhandledrejection
        driver.execute_script("Promise.reject(new Error('Test rejection 1')).catch(function(){});")
        print("  -> Promise.reject(Error)")
        
        time.sleep(0.2)
        
        driver.execute_script("Promise.reject('String rejection').catch(function(){});")
        print("  -> Promise.reject(String)")
        
        time.sleep(0.2)
        
        driver.execute_script("""
            new Promise(function(resolve, reject) {
                reject({ code: 'CUSTOM_ERROR', message: 'Custom error object' });
            }).catch(function(){});
        """)
        print("  -> Promise.reject(Object)")
        
        time.sleep(0.5)
        
        # =========================================================================
        # TEST 20: Console Error/Warn Events (console-error)
        # =========================================================================
        print("\n[TEST 20] Console Error/Warn Events")
        print("-" * 40)
        
        driver.execute_script("console.error('Selenium Test Error Message');")
        print("  -> console.error()")
        
        time.sleep(0.2)
        
        driver.execute_script("console.warn('Selenium Test Warning Message');")
        print("  -> console.warn()")
        
        time.sleep(0.2)
        
        driver.execute_script("console.error('Error with', { detail: 'multiple', args: true });")
        print("  -> console.error(multiple args)")
        
        time.sleep(0.5)
        
        # =========================================================================
        # TEST 21: Performance Events (performance)
        # =========================================================================
        print("\n[TEST 21] Performance Events")
        print("-" * 40)
        
        # Performance API calls
        driver.execute_script("""
            // Navigation timing
            performance.getEntriesByType('navigation');
            
            // Resource timing
            performance.getEntriesByType('resource');
            
            // Paint timing
            performance.getEntriesByType('paint');
        """)
        print("  -> Performance API calls")
        
        time.sleep(1)
        
        # =========================================================================
        # TEST 22: Scroll Events (via resize/scroll)
        # =========================================================================
        print("\n[TEST 22] Scroll Events")
        print("-" * 40)
        
        driver.execute_script("window.scrollTo(0, 500);")
        print("  -> window.scrollTo()")
        
        time.sleep(0.3)
        
        driver.execute_script("window.scrollBy(0, 200);")
        print("  -> window.scrollBy()")
        
        time.sleep(0.3)
        
        driver.execute_script("window.scrollTo(0, 0);")
        print("  -> scroll to top")
        
        time.sleep(0.5)
        
        # =========================================================================
        # TEST 23: Page Navigation Events (navigation, page-unload)
        # =========================================================================
        print("\n[TEST 23] Page Navigation Events")
        print("-" * 40)
        
        try:
            link = driver.find_element(By.LINK_TEXT, "Navigate to Another Page")
            link.click()
            print("  -> Link navigation")
            time.sleep(2)
        except Exception as e:
            print(f"  -> Navigation (failed: {e})")
            driver.get(web_app_url)
            time.sleep(1)
        
        # Navigate back
        driver.back()
        print("  -> Back navigation")
        time.sleep(1)
        
        # Navigate forward
        driver.forward()
        print("  -> Forward navigation")
        time.sleep(1)
        
        # Go to a new URL
        driver.get(web_app_url + "/dashboard")
        print("  -> Direct URL navigation")
        time.sleep(2)
        
        # =========================================================================
        # TEST 24: Multiple Rapid Interactions (automation-alert simulation)
        # =========================================================================
        print("\n[TEST 24] Synthetic Event Simulation")
        print("-" * 40)
        
        # Dispatch synthetic events (these should trigger automation-alert)
        driver.execute_script("""
            var event = new MouseEvent('click', {
                bubbles: true,
                cancelable: true,
                view: window,
                isTrusted: false
            });
            var btn = document.getElementById('testButton');
            if (btn) btn.dispatchEvent(event);
        """)
        print("  -> Synthetic click (isTrusted: false)")
        
        time.sleep(0.3)
        
        driver.execute_script("""
            var event = new Event('input', {
                bubbles: true,
                cancelable: true,
                isTrusted: false
            });
            var input = document.getElementById('username');
            if (input) input.dispatchEvent(event);
        """)
        print("  -> Synthetic input (isTrusted: false)")
        
        time.sleep(0.5)
        
        # =========================================================================
        # TEST 25: Comprehensive Element Inspection
        # =========================================================================
        print("\n[TEST 25] Comprehensive Element Inspection")
        print("-" * 40)
        
        driver.execute_script("""
            var elements = document.querySelectorAll('.container, button, input, a, div');
            elements.forEach(function(el) {
                try {
                    el.getBoundingClientRect();
                    el.getAttribute('class');
                    el.matches('button');
                    el.offsetWidth;
                    el.clientHeight;
                } catch(e) {}
            });
        """)
        print("  -> Bulk element inspections")
        
        time.sleep(0.5)
        
        # =========================================================================
        # TEST 26: Batch DOM Operations
        # =========================================================================
        print("\n[TEST 26] Batch DOM Operations")
        print("-" * 40)
        
        driver.execute_script("""
            // Create a lot of elements
            var fragment = document.createDocumentFragment();
            for (var i = 0; i < 20; i++) {
                var div = document.createElement('div');
                div.id = 'batch-test-' + i;
                div.className = 'batch-item';
                div.textContent = 'Item ' + i;
                div.setAttribute('data-index', i);
                fragment.appendChild(div);
            }
            document.body.appendChild(fragment);
        """)
        print("  -> Batch DOM creation")
        
        time.sleep(0.5)
        
        # Query all created elements
        driver.execute_script("""
            var items = document.querySelectorAll('.batch-item');
            items.forEach(function(item) {
                item.getAttribute('data-index');
                item.innerText;
                item.getBoundingClientRect();
            });
        """)
        print("  -> Batch DOM queries")
        
        time.sleep(0.5)
        
        # Remove created elements
        driver.execute_script("""
            var items = document.querySelectorAll('.batch-item');
            items.forEach(function(item) { item.remove(); });
        """)
        print("  -> Batch DOM removal")
        
        time.sleep(0.5)
        
        # =========================================================================
        # FINAL: Summary
        # =========================================================================
        print("\n" + "=" * 60)
        print("TEST COMPLETE - All Event Types Triggered")
        print("=" * 60)
        print("\nEvent types tested:")
        print("  1. page-load, navigation, automation-detected")
        print("  2. dom-query (querySelector, getElementById, etc.)")
        print("  3. xpath-query (document.evaluate)")
        print("  4. element-inspection (getBoundingClientRect, etc.)")
        print("  5. data-extraction (getAttribute, innerText, etc.)")
        print("  6. value-manipulation (innerText, input.value, etc.)")
        print("  7. interaction (click, input, focus, change, keydown)")
        print("  8. timing-alert (rapid clicks)")
        print("  9. element-action (element.click())")
        print(" 10. network-request (fetch, XHR)")
        print(" 11. form-submit")
        print(" 12. clipboard (copy, cut, paste)")
        print(" 13. context-menu (right-click)")
        print(" 14. selection (text selection)")
        print(" 15. resize (window resize)")
        print(" 16. visibility (tab switch)")
        print(" 17. connection (online/offline)")
        print(" 18. mutation-observer (DOM mutations)")
        print(" 19. js-error (JavaScript errors)")
        print(" 20. promise-rejection (unhandled rejections)")
        print(" 21. console-error (console.error/warn)")
        print(" 22. performance (performance API)")
        print(" 23. automation-alert (synthetic events)")
        print(" 24. page-unload (navigation)")
        print("\nCheck Kibana dashboard for all events!")
        print("=" * 60)
        
    finally:
        print("\nClosing browser...")
        driver.quit()

if __name__ == "__main__":
    run_telemetry_test()
