import time
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def set_chrome_options() -> ChromeOptions:
    options = ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    return options

def run_telemetry_test():
    print("Initializing Selenium Test for Tracker system...")
    
    web_app_url = os.getenv("WEB_APP_URL", "http://web-app:8081")
    chromedriver_path = os.getenv("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")
    
    from selenium.webdriver.chrome.service import Service
    service = Service(executable_path=chromedriver_path)
    driver = webdriver.Chrome(service=service, options=set_chrome_options())
    wait = WebDriverWait(driver, 5)
    
    try:
        print("1. Navigating to the page...")
        driver.get(web_app_url)
        time.sleep(2)  
        
        print("2. Simulating user typing & standard clicks...")
        try:
            username_field = driver.find_element(By.ID, "username") 
            username_field.send_keys("test_bot")
        except Exception: pass
        time.sleep(0.5)
        
        try:
            password_field = driver.find_element(By.CSS_SELECTOR, "input[type='password']") 
            password_field.send_keys("super_secret")
        except Exception: pass
        time.sleep(0.5)

        print("3. Executing invalid CSS and ID queries...")
        broken_css = [".missing-class", "div#fake_id", "span.broken-element"]
        for sel in broken_css:
            try: driver.find_element(By.CSS_SELECTOR, sel)
            except Exception: pass
            
        broken_ids = ["nonexistent_id", "fake_button", "missing_link"]
        for i in broken_ids:
            try: driver.find_element(By.ID, i)
            except Exception: pass
        time.sleep(1)

        print("4. Executing invalid XPath queries...")
        broken_xpaths = ["//div[@id='nonexistent']", "//span[text()='missing']", "//table/tr/td[99]", "//a[@class='phantom']"]
        for xp in broken_xpaths:
            try: driver.find_element(By.XPATH, xp)
            except Exception: pass
        time.sleep(1)

        print("5. Generating rapid, bot-like clicks and interacting with various tags...")
        try:
            test_btn = driver.find_element(By.ID, "testButton")
            actions = ActionChains(driver)
            actions.click(test_btn).click(test_btn).click(test_btn).click(test_btn).perform() 
        except Exception: pass
        
        try: driver.find_element(By.TAG_NAME, "h1").click()
        except Exception: pass
        try: driver.find_element(By.TAG_NAME, "p").click()
        except Exception: pass
        try: driver.find_element(By.TAG_NAME, "div").click()
        except Exception: pass
        time.sleep(1)
        
        print("6. Triggering multiple unhandled JavaScript errors...")
        try:
            driver.find_element(By.CLASS_NAME, "error-btn").click()
        except Exception: pass
        
        driver.execute_script("setTimeout(function() { fakeFunctionCall(); }, 10);")
        driver.execute_script("setTimeout(function() { window.someUndefinedObj.crash(); }, 20);")
        driver.execute_script("setTimeout(function() { throw new Error('Simulated Database Timeout Exception'); }, 30);")
        time.sleep(1)
        
        print("7. Scrolling the page to trigger scroll-depth events...")
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)

        print("8. Triggering right-click (context menu) events...")
        try:
            elem = driver.find_element(By.TAG_NAME, "h1")
            actions = ActionChains(driver)
            actions.context_click(elem).perform()
        except Exception: pass
        time.sleep(0.5)

        print("9. Triggering window resize events...")
        driver.set_window_size(800, 600)
        time.sleep(1)
        driver.set_window_size(1920, 1080)
        time.sleep(0.5)

        print("10. Triggering console errors and promise rejections...")
        driver.execute_script("console.error('Test console error from Selenium');")
        driver.execute_script("console.warn('Test console warning from Selenium');")
        driver.execute_script("Promise.reject('Simulated unhandled rejection');")
        time.sleep(1)

        print("11. Triggering Page Navigation & testing page transition events...")
        try:
            driver.find_element(By.LINK_TEXT, "Navigate to Another Page").click()
        except Exception: pass
        time.sleep(3)

        print("\nTest sequence complete!")
        print("Check your Kibana dashboard or LogWorker output terminal!")
        
    finally:
        driver.quit()

if __name__ == "__main__":
    run_telemetry_test()
