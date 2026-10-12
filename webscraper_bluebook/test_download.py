import os
import json
import time
import requests
from selenium.webdriver.common.by import By
from scraper import make_driver, goto_results_for_section, set_popover_filter, safe_click

# site's radio-button label  ->  filename we save it under
OPTIONS = {
    "No correct answers or explanations":    "questions_only.pdf",
    "With correct answers and explanations": "with_answers.pdf",
    "Without answers or headers":            "no_headers.pdf",
}

# JavaScript that records the answer of the site's pdf-download call.
# Installed once per page load; each call resets the list of captures.
CAPTURE_JS = """
if (!window.__capInstalled) {
  window.__capInstalled = true;
  const origOpen = XMLHttpRequest.prototype.open;
  const origSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (m, u) {
    this.__u = u;
    return origOpen.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function (body) {
    this.addEventListener('load', function () {
      if ((this.__u || '').includes('pdf-download')) {
        let txt = '';
        try { txt = this.responseText; } catch (e) {}
        window.__cap.push({request: String(body), status: this.status, response: txt});
      }
    });
    return origSend.apply(this, arguments);
  };
}
window.__cap = [];
"""


def open_export_popover(driver):
    """Return the export popover, opening it only if it is not already open
    (the Export button toggles, so a blind click could close it)."""
    for p in driver.find_elements(By.CSS_SELECTOR, ".export-popover"):
        if p.is_displayed():
            return p
    safe_click(driver, driver.find_element(By.ID, "export-button"))
    for _ in range(10):
        time.sleep(0.5)
        for p in driver.find_elements(By.CSS_SELECTOR, ".export-popover"):
            if p.is_displayed():
                return p
    raise RuntimeError("Export popover did not open")


def request_pdf_link(driver, label_text, timeout=90):
    """Choose one export option, click Export PDF, return (downloadUrl, question_count)."""
    driver.execute_script(CAPTURE_JS)

    popover = open_export_popover(driver)
    safe_click(driver, popover.find_element(By.XPATH, f".//label[normalize-space()='{label_text}']"))
    time.sleep(1)
    btn = popover.find_element(By.XPATH, ".//button[normalize-space()='Export PDF']")
    btn.click()

    end = time.time() + timeout
    while time.time() < end:
        caps = driver.execute_script("return window.__cap;") or []
        if caps:
            cap = caps[-1]
            if cap["status"] != 200:
                raise RuntimeError(f"Server answered {cap['status']}: {cap['response'][:200]}")
            answer = json.loads(cap["response"])
            if answer.get("status") != "COMPLETED" or not answer.get("downloadUrl"):
                raise RuntimeError(f"Unexpected answer: {answer}")
            n_questions = len(json.loads(cap["request"]).get("questions", []))
            return answer["downloadUrl"], n_questions
        time.sleep(1)
    raise TimeoutError("No pdf-download answer within the time limit")


def download_pdf(driver, url, dest):
    """Download the link with requests, reusing the browser's cookies."""
    session = requests.Session()
    for c in driver.get_cookies():
        session.cookies.set(c["name"], c["value"])
    session.headers["User-Agent"] = driver.execute_script("return navigator.userAgent;")
    r = session.get(url, timeout=60)
    r.raise_for_status()
    if not r.content.startswith(b"%PDF"):
        raise RuntimeError(f"Not a PDF. First bytes: {r.content[:40]!r}")
    with open(dest, "wb") as f:
        f.write(r.content)
    return len(r.content)


# ------------------------------ the test ------------------------------
test_dir = os.path.abspath("test_download")
os.makedirs(test_dir, exist_ok=True)

driver = make_driver()
try:
    # A skill/difficulty with 41 questions, so it spans several pages
    goto_results_for_section(driver, "Reading and Writing")
    set_popover_filter(driver, "skill-filter", "Central Ideas and Details")
    set_popover_filter(driver, "difficulty-filter", "Easy")

    safe_click(driver, driver.find_element(By.CSS_SELECTOR, "button.cb-dropdown-toggle"))
    time.sleep(1)
    safe_click(driver, driver.find_element(By.XPATH, "//a[normalize-space()='Select Entire Set']"))
    time.sleep(2)

    for label_text, filename in OPTIONS.items():
        print(f"\n--- {label_text} ---")
        url, n_questions = request_pdf_link(driver, label_text)
        print("questions sent to the server:", n_questions)
        print("link:", url)
        size = download_pdf(driver, url, os.path.join(test_dir, filename))
        print(f"saved {filename} ({size:,} bytes)")
        time.sleep(2)   # small pause between exports

    print("\nFiles:", os.listdir(test_dir))
finally:
    input("\nPress Enter to close the browser...")
    driver.quit()