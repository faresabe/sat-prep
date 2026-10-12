"""
Selenium fallback — scrapes the Math questions that have no external_id.
Handles both MCQ and SPR (student-produced response) formats.

Set TEST_LIMIT = 5 for a test run, or None for the full 402.
"""

import os
import json
import time
import base64
import re
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException


TEST_LIMIT = None
API_ROOT = "https://qbank-api.collegeboard.org/msreportingquestionbank-prod/questionbank/digital"
ASMT = 99
OUTPUT_ROOT = "SAT_Downloads"
QB_SEARCH = "https://satsuiteeducatorquestionbank.collegeboard.org/digital/search"
DIFF_MAP = {"E": "Easy", "M": "Medium", "H": "Hard"}
MATH_DOMAIN_STRINGS = ["H,P,Q,G", "A,P,Q,G", "H,AM,PSDA,GT"]


def make_folder_name(section, domain, skill, difficulty):
    prefix = "RW" if section == "Reading and Writing" else "Math"
    name = "_".join([prefix, domain, skill, difficulty])
    for ch in ['/', '\\', ':', '*', '?', '"', '<', '>', '|', ',']:
        name = name.replace(ch, '')
    while "__" in name:
        name = name.replace("__", "_")
    return name.strip("_")[:150]


def fetch_missing():
    seen = set()
    missing = []
    for dstr in MATH_DOMAIN_STRINGS:
        r = requests.post(f"{API_ROOT}/get-questions",
                          json={"asmtEventId": ASMT, "test": 2, "domain": dstr},
                          timeout=30)
        if r.status_code != 200:
            continue
        for q in r.json():
            qid = q.get("questionId")
            if not qid or qid in seen:
                continue
            seen.add(qid)
            if q.get("external_id"):
                continue
            missing.append({
                "questionId": qid,
                "section": "Math",
                "domain": q.get("primary_class_cd_desc") or "Unknown",
                "skill": q.get("skill_desc") or "Unknown",
                "difficulty": DIFF_MAP.get(q.get("difficulty") or "E", "Easy"),
            })
    return missing


def make_driver():
    opts = Options()
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    d = webdriver.Chrome(options=opts)
    d.set_window_size(1400, 1000)
    return d


def dismiss_cookies(driver):
    for sel in ["#onetrust-accept-btn-handler", "#accept-recommended-btn-handler"]:
        try:
            b = driver.find_element(By.CSS_SELECTOR, sel)
            if b.is_displayed():
                b.click()
                time.sleep(1)
                return
        except Exception:
            pass
    try:
        driver.execute_script(
            "const el=document.getElementById('onetrust-consent-sdk');"
            "if(el)el.remove();document.body.style.overflow='';")
        time.sleep(0.3)
    except Exception:
        pass


def goto_math_results(driver):
    driver.get(QB_SEARCH)
    time.sleep(3)
    dismiss_cookies(driver)
    a = Select(WebDriverWait(driver, 20).until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, 'select[aria-label="Select Assessment"]'))))
    a.select_by_value("99")
    time.sleep(1)
    s = Select(WebDriverWait(driver, 20).until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, 'select[aria-label="Choose Section"]'))))
    s.select_by_value("2")
    time.sleep(1)
    for cb in driver.find_elements(By.CSS_SELECTOR, '.content-domain input[type="checkbox"]'):
        if not cb.is_selected():
            try:
                cb.click()
            except Exception:
                driver.execute_script("arguments[0].click();", cb)
    time.sleep(1)
    for b in driver.find_elements(By.CSS_SELECTOR, "button.cb-btn-yellow"):
        if b.is_enabled() and "Search" in (b.text or ""):
            b.click()
            break
    time.sleep(5)
    dismiss_cookies(driver)


# ---------------------------------------------------------------------------
# Math extraction helpers
# ---------------------------------------------------------------------------
def element_inner_html_and_math(el):
    """
    Given a WebElement (e.g. stem_paragraph), return:
      - text: the readable text with math replaced by its alt description
      - images: list of (index, base64_data_url) for each math image found
    """
    # Get HTML and swap <img alt="..."> for the alt text
    html = el.get_attribute("outerHTML")
    # replace every <img ... alt="DESC" ...> with [DESC]  (or just DESC)
    def _img_sub(m):
        attrs = m.group(0)
        alt = re.search(r'alt="([^"]*)"', attrs)
        return f" ⟦{alt.group(1)}⟧ " if alt else " ⟦math⟧ "
    text = re.sub(r'<img[^>]*>', _img_sub, html)
    # strip all remaining tags
    text = re.sub(r'<[^>]+>', '', text)
    # collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    images = []
    imgs = el.find_elements(By.TAG_NAME, "img")
    for i, img in enumerate(imgs):
        src = img.get_attribute("src") or ""
        alt = img.get_attribute("alt") or ""
        images.append({"index": i, "alt": alt, "src": src})
    return text, images


def save_math_images(images, folder, qid):
    """Save every base64 data URL to a PNG file. Return list of filenames."""
    saved = []
    for i, im in enumerate(images):
        src = im.get("src", "")
        if not src.startswith("data:image"):
            continue
        try:
            header, data = src.split(",", 1)
            raw = base64.b64decode(data)
            fn = f"q{qid}_math{i}.png"
            with open(os.path.join(folder, fn), "wb") as f:
                f.write(raw)
            saved.append({"file": fn, "alt": im.get("alt", "")})
        except Exception as e:
            print(f"      img save failed: {e}")
    return saved


# ---------------------------------------------------------------------------
# Modal scraper (handles MCQ + SPR)
# ---------------------------------------------------------------------------
def scrape_modal(driver, question_id):
    try:
        btn = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, f'button.view-question-button[id="{question_id}"]'))
        )
    except TimeoutException:
        return None

    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
    try:
        btn.click()
    except Exception:
        driver.execute_script("arguments[0].click();", btn)

    try:
        modal = WebDriverWait(driver, 15).until(
            EC.visibility_of_element_located(
                (By.CSS_SELECTOR, ".cb-modal.cb-dialog-modal.cb-open"))
        )
    except TimeoutException:
        return None

    time.sleep(1)
    data = {"questionId": question_id, "_source": "selenium"}

    # ---- metadata ----
    try:
        cells = modal.find_elements(By.CSS_SELECTOR, ".question-banner tbody tr td")
        texts = [c.text.strip() for c in cells]
        if len(texts) >= 5:
            data["_section"] = texts[1]
            data["_domain"] = texts[2]
            data["_skill"] = texts[3]
            data["_difficulty"] = texts[4]
    except Exception:
        pass

    # ---- stimulus_reference (given equations/figures) ----
    all_math_images = []
    try:
        refs = modal.find_elements(
            By.CSS_SELECTOR, ".question-content .stimulus_reference")
        ref_texts = []
        for r in refs:
            txt, imgs = element_inner_html_and_math(r)
            if txt:
                ref_texts.append(txt)
            all_math_images.extend(imgs)
        if ref_texts:
            data["stimulus_reference"] = "\n".join(ref_texts)
    except Exception:
        pass

    # ---- stimulus (reading passage, if any) ----
    try:
        p = modal.find_element(By.CSS_SELECTOR, ".question-content .prompt")
        txt, imgs = element_inner_html_and_math(p)
        if txt:
            data["stimulus"] = txt
            all_math_images.extend(imgs)
    except Exception:
        pass

    # ---- stem ----
    try:
        stem_paras = modal.find_elements(
            By.CSS_SELECTOR, ".question-content .question p.stem_paragraph")
        parts = []
        for p in stem_paras:
            txt, imgs = element_inner_html_and_math(p)
            if txt:
                parts.append(txt)
            all_math_images.extend(imgs)
        if parts:
            data["stem"] = "\n".join(parts)
    except Exception:
        pass

    # ---- choices (empty for SPR) ----
    try:
        lis = modal.find_elements(By.CSS_SELECTOR, ".answer-choices ul li")
        labels = ["A", "B", "C", "D", "E"]
        options = []
        correct = []
        for i, li in enumerate(lis):
            letter = labels[i] if i < len(labels) else str(i)
            txt, imgs = element_inner_html_and_math(li)
            all_math_images.extend(imgs)
            is_correct = "correct" in (li.get_attribute("class") or "")
            options.append({"label": letter, "content": txt})
            if is_correct:
                correct.append(letter)
        data["answerOptions"] = options
        if correct:
            data["correct_answer"] = correct
        data["_question_type"] = "MCQ" if options else "SPR"
    except Exception:
        data["_question_type"] = "SPR"

    # ---- save math images ----
    if all_math_images:
        folder = make_folder_name(
            data.get("_section") or "Math",
            data.get("_domain") or "Unknown",
            data.get("_skill") or "Unknown",
            data.get("_difficulty") or "Easy",
        )
        path = os.path.join(OUTPUT_ROOT, folder)
        os.makedirs(path, exist_ok=True)
        data["math_images"] = save_math_images(all_math_images, path, question_id)

    # ---- fallback: full modal HTML ----
    try:
        data["_modal_html"] = modal.get_attribute("outerHTML")
    except Exception:
        pass

    # ---- close ----
    try:
        driver.find_element(By.TAG_NAME, "body").send_keys("\ue00c")
    except Exception:
        pass
    time.sleep(0.5)
    try:
        if modal.is_displayed():
            close = modal.find_element(
                By.CSS_SELECTOR, '[data-cb-modal-close="true"], .cb-btn-close')
            driver.execute_script("arguments[0].click();", close)
    except Exception:
        pass
    time.sleep(1)

    return data


def find_and_scrape(driver, question_id, max_pages=40):
    data = scrape_modal(driver, question_id)
    if data:
        return data
    for _ in range(max_pages):
        try:
            nxt = driver.find_element(By.CSS_SELECTOR, '[id$="_next"]')
        except NoSuchElementException:
            return None
        if nxt.get_attribute("aria-disabled") == "true":
            return None
        try:
            driver.execute_script("arguments[0].click();", nxt)
        except Exception:
            return None
        time.sleep(1.5)
        data = scrape_modal(driver, question_id)
        if data:
            return data
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    os.makedirs(OUTPUT_ROOT, exist_ok=True)
    print("[1] Finding Math questions with no external_id...")
    missing = fetch_missing()
    print(f"    found {len(missing)} Selenium-only questions")

    todo = []
    for m in missing:
        folder = make_folder_name(m["section"], m["domain"], m["skill"], m["difficulty"])
        path = os.path.join(OUTPUT_ROOT, folder, f"q{m['questionId']}.json")
        if os.path.exists(path):
            continue
        todo.append(m)
    print(f"    {len(todo)} still missing on disk")

    if TEST_LIMIT:
        todo = todo[:TEST_LIMIT]
        print(f"    TEST_LIMIT active → only running {len(todo)} this time")
    if not todo:
        print("Nothing to do.")
        return

    print("[2] Opening Chrome...")
    driver = make_driver()
    try:
        goto_math_results(driver)
        done = failed = 0
        for i, m in enumerate(todo, 1):
            qid = m["questionId"]
            print(f"  [{i}/{len(todo)}] {qid} — "
                  f"{m['domain']} / {m['skill']} / {m['difficulty']}")
            data = find_and_scrape(driver, qid)
            if not data:
                failed += 1
                print("      ✗ not found")
                continue

            folder = make_folder_name(
                data.get("_section") or m["section"],
                data.get("_domain") or m["domain"],
                data.get("_skill") or m["skill"],
                data.get("_difficulty") or m["difficulty"],
            )
            path = os.path.join(OUTPUT_ROOT, folder)
            os.makedirs(path, exist_ok=True)
            out = os.path.join(path, f"q{qid}.json")
            with open(out, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            qtype = data.get("_question_type", "?")
            n_choices = len(data.get("answerOptions", []))
            n_imgs = len(data.get("math_images", []))
            status = "OK" if (data.get("stem") or data.get("stimulus_reference")) else "EMPTY"
            print(f"      saved ({status}) type={qtype} "
                  f"choices={n_choices} correct={data.get('correct_answer')} "
                  f"images={n_imgs}")
            done += 1

        print(f"\nDONE — scraped {done}, failed {failed}")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()