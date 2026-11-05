from selenium.webdriver.common.by import By
from scraper import make_driver, goto_results_for_section, set_popover_filter

def dump(title):
    print(f"\n===== {title} =====")
    for el in driver.find_elements(By.CSS_SELECTOR, "button, input, label, a, select"):
        try:
            if el.is_displayed():
                text = (el.text or "").replace("\n", " ")[:40]
                print(el.tag_name, "| id =", el.get_attribute("id"),
                      "| class =", el.get_attribute("class"), "| text =", text)
        except Exception:
            pass

driver = make_driver()
goto_results_for_section(driver, "Reading and Writing")
set_popover_filter(driver, "skill-filter", "Inferences")
set_popover_filter(driver, "difficulty-filter", "Easy")

dump("RESULTS PAGE")
input("In the browser: click select-all (if there is one), then click Export. "
      "When the export dialog is open, press Enter here...")
dump("EXPORT DIALOG")

input("Press Enter to close the browser...")
driver.quit()