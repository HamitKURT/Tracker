import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def run_telemetry_test():
    print("🚀 Initializing Selenium Test for Tracker system...")
    
    # Configure Chrome options (headless or headed)
    options = webdriver.ChromeOptions()
    options.add_argument('--headless=new') # Run in headless mode for simplicity, remove to see the browser
    
    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 5)
    
    try:
        # 1. Page Load Event & WebDriver Detection
        print("1️⃣ Navigating to the page...")
        driver.get("http://localhost:8081")
        time.sleep(2)  
        
        # 2. Input Tracking (Generates 'interaction' and 'dom-query' events)
        print("2️⃣ Simulating user typing & standard clicks...")
        try:
            username_field = driver.find_element(By.ID, "username") 
            username_field.send_keys("test_bot")
        except: pass
        time.sleep(0.5)
        
        try:
            password_field = driver.find_element(By.CSS_SELECTOR, "input[type='password']") 
            password_field.send_keys("super_secret")
        except: pass
        time.sleep(0.5)

        # 3. Missing Selectors (Generates 'found: false' for dom-query)
        print("3️⃣ Executing invalid CSS and ID queries...")
        broken_css = [".missing-class", "div#fake_id", "span.broken-element"]
        for sel in broken_css:
            try: driver.find_element(By.CSS_SELECTOR, sel)
            except: pass
            
        broken_ids = ["nonexistent_id", "fake_button", "missing_link"]
        for i in broken_ids:
            try: driver.find_element(By.ID, i)
            except: pass
        time.sleep(1)

        # 4. Missing XPaths (Generates 'found: false' for xpath-query)
        print("4️⃣ Executing invalid XPath queries...")
        broken_xpaths = ["//div[@id='nonexistent']", "//span[text()='missing']", "//table/tr/td[99]", "//a[@class='phantom']"]
        for xp in broken_xpaths:
            try: driver.find_element(By.XPATH, xp)
            except: pass
        time.sleep(1)

        # 5. Suspicious Timing Alert & Multiple Element Interactions
        print("5️⃣ Generating rapid, bot-like clicks and interacting with various tags...")
        try:
            test_btn = driver.find_element(By.ID, "testButton")
            actions = ActionChains(driver)
            actions.click(test_btn).click(test_btn).click(test_btn).click(test_btn).perform() 
        except: pass
        
        # Click randomly on the body or header to generate interactions with different tags
        try: driver.find_element(By.TAG_NAME, "h1").click()
        except: pass
        try: driver.find_element(By.TAG_NAME, "p").click()
        except: pass
        try: driver.find_element(By.TAG_NAME, "div").click()
        except: pass
        time.sleep(1)
        
        # 6. Throwing Multiple JS Errors
        print("6️⃣ Triggering multiple unhandled JavaScript errors...")
        try:
            driver.find_element(By.CLASS_NAME, "error-btn").click()
        except: pass
        
        # Inject raw errors to ensure the dashboard gets detailed logs
        driver.execute_script("setTimeout(function() { fakeFunctionCall(); }, 10);")
        driver.execute_script("setTimeout(function() { window.someUndefinedObj.crash(); }, 20);")
        driver.execute_script("setTimeout(function() { throw new Error('Simulated Database Timeout Exception'); }, 30);")
        time.sleep(1)
        
        # 7. Navigation/Visibility Tests
        print("7️⃣ Triggering Page Navigation & testing page transition events...")
        try:
            driver.find_element(By.LINK_TEXT, "Navigate to Another Page").click()
        except: pass
        time.sleep(3) 
        
        print("\n✅ Test sequence complete!")
        print("🌐 Check your Kibana dashboard or LogWorker output terminal!")
        
    finally:
        driver.quit()

if __name__ == "__main__":
    run_telemetry_test()
