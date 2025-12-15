import json
import random
import time
import os
from dotenv import load_dotenv
import uuid
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from openai import OpenAI

import logging

# Configure logger
logging.basicConfig(
    level=logging.INFO,  # Change to DEBUG for more verbose logs
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


class GoogleFormAutomation:
    def __init__(self, openai_api_key, form_url):
        self.client = OpenAI(api_key=openai_api_key)
        self.form_url = form_url
        self.driver = None
        self.collected_answers = {}
        self.first_page_answers = {}
        self.seed = random.choice([3,4,5,6,7,8,9,10,12,14])
    def setup_driver(self):
        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")  # Required for Docker
        options.add_argument("--disable-dev-shm-usage")  # Overcome limited resource problems
        options.add_argument("--disable-gpu")  # Disable GPU hardware acceleration
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--disable-extensions")
        
        # Specify chromium binary path (from Docker env)
        options.binary_location = "/usr/bin/chromium"
        
        # Use the system chromedriver
        self.driver = webdriver.Chrome(options=options)

    def extract_questions(self):
        """Extract all questions + metadata for a single page."""
        questions = []

        items = self.driver.find_elements(By.CSS_SELECTOR, '[role="listitem"]')

        for qid, item in enumerate(items, 1):
            qtext = ""
            is_required = False
            
            try:
                qtext = item.find_element(By.CSS_SELECTOR, '[role="heading"]').text.strip()
                # Check if question is required (has asterisk)
                is_required = '*' in qtext or bool(item.find_elements(By.CSS_SELECTOR, '.freebirdFormviewerComponentsQuestionBaseRequiredAsterisk'))
            except:
                continue

            qtype = "text"  # default
            option_labels = []

            # short text
            if item.find_elements(By.CSS_SELECTOR, 'input[type="text"]'):
                qtype = "short_text"

            # paragraph
            if item.find_elements(By.CSS_SELECTOR, 'textarea'):
                qtype = "long_text"

            # multiple choice
            radio = item.find_elements(By.CSS_SELECTOR, '[role="radio"]')
            if radio:
                qtype = "mcq"
                option_labels = [r.get_attribute("aria-label") for r in radio]

            # checkbox
            checks = item.find_elements(By.CSS_SELECTOR, '[role="checkbox"]')
            if checks:
                qtype = "checkbox"
                option_labels = [c.get_attribute("aria-label") for c in checks]

            # linear scale (Google forms typically show numbers 1–5)
            numbers = item.find_elements(By.CSS_SELECTOR, ".Od2TWd")
            if numbers and len(numbers) >= 5:
                qtype = "scale_1_5"

            questions.append({
                "id": qid,
                "text": qtext,
                "type": qtype,
                "options": option_labels,
                "required": is_required
            })

        return questions

    def get_ai_answers_batch(self, question_list):
        """Single API call with all questions."""
        qstring = ""
        for q in question_list:
            req_marker = " [REQUIRED]" if q.get('required') else ""
            qstring += f"{q['id']}. {q['text']}{req_marker} (type: {q['type']}, options: {q['options']})\n"
        
        
        
       
        strict_prompt = f"""
        

You are filling out a Google Form. Return ONLY a JSON object with question IDs as keys and answers as values.

You are simulating a realistic Indian respondent (age 18–25). 
Names MUST be realistically Indian but **not overly common**.  
You MUST NOT reuse names such as “Anjali Sharma”, “Rahul Kumar”, or similar stereotypical pairs.  
Use names from diverse Indian regions (North, South, East, West) and vary caste/community patterns.

CRITICAL RULES:
RANDOMNESS SEED: {self.seed}
        Use the seed to randomize gender and name selection.
        If the seed ends in an EVEN digit → choose MALE.
        If the seed ends in an ODD digit → choose FEMALE.
1. For MCQ: Choose EXACTLY ONE option from the provided list.
2. For checkbox: Choose one or more options, comma-separated.
3. For scale_1_5: Choose a number from 1–5.
4. For short_text/long_text: Provide realistic, concise answers suitable for a psychology survey.
5. REQUIRED fields MUST be answered.
6. If any question asks for **Name**, **Full Name**, or anything equivalent:
   - Generate a unique, realistic Indian name.
   - Avoid all of these common names: 
     ["Anjali Sharma", "Anjali Singh", "Rahul Sharma", "Rahul Kumar", "Neha Singh", "Amit Kumar"].
   - Use a different name each time this API is called.
7. If any question asks “Do you agree to participate in this survey?”, ALWAYS answer "YES".
8. Return ONLY a clean JSON object. No markdown, no commentary, no code blocks.

Questions:
{qstring}

Return format example:
{{"1": "answer1", "2": "answer2"}}

Your JSON response:
"""


        response = self.client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[
                {"role": "system", "content": "You are a form-filling assistant. Return ONLY valid JSON. No markdown, no code blocks, no explanations."},
                {"role": "user", "content": strict_prompt}
            ],
            max_tokens=500,
            temperature=0.8
        )

        content = response.choices[0].message.content.strip()

        # Aggressive markdown stripping
        # Remove ```json, ```JSON, or just ```
        if "```" in content:
            # Find the first { and last }
            start = content.find("{")
            end = content.rfind("}") + 1
            if start != -1 and end > start:
                content = content[start:end]
        
        content = content.strip()

        try:
            parsed = json.loads(content)
            logger.info(f"✓ Successfully parsed {len(parsed)} answers")
            return parsed
        except Exception as e:
            logger.info("\n⚠️ GPT returned invalid JSON.")
            logger.info("Raw response:")
            logger.info(repr(content))
            logger.info(f"\nError: {e}")
            raise

    def fill_page(self, questions, answers):
        """Fill all questions using GPT answers."""
        items = self.driver.find_elements(By.CSS_SELECTOR, '[role="listitem"]')

        for q in questions:
            ans = answers.get(str(q["id"]), "")
            
            if not ans and q.get('required'):
                logger.info(f"⚠️ Warning: Required question {q['id']} has no answer!")
                continue
                
            item = items[q["id"] - 1]  # same indexing order

            if q["type"] in ["short_text", "long_text"]:
                try:
                    el = item.find_element(By.CSS_SELECTOR, 'input[type="text"], textarea')
                    el.clear()
                    el.send_keys(str(ans))
                    logger.info(f"✓ Filled Q{q['id']}: {str(ans)[:50]}")
                except Exception as e:
                    logger.info(f"✗ Failed to fill Q{q['id']}: {e}")

            elif q["type"] == "mcq":
                options = item.find_elements(By.CSS_SELECTOR, '[role="radio"]')
                filled = False
                ans_lower = str(ans).lower().strip()
                
                # Try exact match first
                for opt in options:
                    label = opt.get_attribute("aria-label")
                    if label and label.lower().strip() == ans_lower:
                        opt.click()
                        logger.info(f"✓ Selected Q{q['id']}: {label}")
                        filled = True
                        break
                
                # Try partial match if exact didn't work
                if not filled:
                    for opt in options:
                        label = opt.get_attribute("aria-label")
                        if label and ans_lower in label.lower():
                            opt.click()
                            logger.info(f"✓ Selected Q{q['id']}: {label} (partial match)")
                            filled = True
                            break
                
                if not filled:
                    logger.info(f"✗ Could not match answer '{ans}' for Q{q['id']}")
                    logger.info(f"  Available options: {[opt.get_attribute('aria-label') for opt in options]}")

            elif q["type"] == "checkbox":
                # Handle comma-separated answers
                chosen = [x.strip().lower() for x in str(ans).split(",")]
                options = item.find_elements(By.CSS_SELECTOR, '[role="checkbox"]')
                
                for opt in options:
                    label = opt.get_attribute("aria-label")
                    if not label:
                        continue
                    
                    label_lower = label.lower().strip()
                    
                    # Check if this option should be selected
                    should_select = False
                    for choice in chosen:
                        if choice == label_lower or choice in label_lower or label_lower in choice:
                            should_select = True
                            break
                    
                    if should_select:
                        # Only click if not already checked
                        is_checked = opt.get_attribute("aria-checked") == "true"
                        if not is_checked:
                            opt.click()
                            logger.info(f"✓ Checked Q{q['id']}: {label}")

            elif q["type"] == "scale_1_5":
                try:
                    # Extract just the number if it's in a string
                    scale_value = str(ans).strip()
                    # Try to find by aria-label with the number
                    target = item.find_element(By.XPATH, f".//div[@aria-label='{scale_value}']")
                    target.click()
                    logger.info(f"✓ Selected scale Q{q['id']}: {scale_value}")
                except Exception as e:
                    logger.info(f"✗ Failed to select scale Q{q['id']}: {e}")
                    logger.info(f"  Tried to select: {ans}")

    def check_validation_errors(self):
        """Check for validation errors on the page."""
        try:
            error_elements = self.driver.find_elements(By.CSS_SELECTOR, '[role="alert"], .freebirdFormviewerViewItemsItemErrorMessage')
            if error_elements:
                errors = [err.text for err in error_elements if err.text]
                if errors:
                    logger.info("\n⚠️ Validation errors found:")
                    for err in errors:
                        logger.info(f"  - {err}")
                    return True
        except:
            pass
        return False

    def fill_form(self):
        self.setup_driver()
        self.driver.get(self.form_url)
        WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '[role="listitem"]'))
        )

        page_num = 1

        while True:
            logger.info(f"\n{'='*50}")
            logger.info(f"Processing Page {page_num}")
            logger.info(f"{'='*50}")
            
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '[role="listitem"]'))
            )

            # 1. Extract all questions on the page
            questions = self.extract_questions()
            logger.info(f"\nFound {len(questions)} questions on this page")

            # 2. Get ALL answers with ONE GPT call
            logger.info("\nGetting AI answers...")
            answers = self.get_ai_answers_batch(questions)
            # ✅ store ALL answers (internal use)
            self.collected_answers.update(answers)

            # ✅ store ONLY first page answers (for UI)
            if page_num == 1:
                self.first_page_answers = answers

            # 3. Fill the page
            logger.info("\nFilling form...")
            self.fill_page(questions, answers)

            # Add a small delay after filling
            time.sleep(0.5)

            # 4. Check for validation errors BEFORE clicking next/submit
            self.check_validation_errors()

            # 5. Try Next button
            try:
                next_btn = self.driver.find_element(By.XPATH, "//span[text()='Next']/..")
                logger.info("\n→ Clicking 'Next' button...")
                next_btn.click()
                WebDriverWait(self.driver, 10).until(
    EC.staleness_of(
        self.driver.find_elements(By.CSS_SELECTOR, '[role="listitem"]')[0]
    )
)
                page_num += 1
                continue
            except:
                logger.info("\n→ No 'Next' button found, looking for 'Submit'...")
                pass

            # 6. Try Submit button with better handling
            try:
                # Find the submit button
                submit_btn = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((
                        By.XPATH,
                        "//span[contains(text(), 'Submit')]"
                    ))
                )

                # Scroll into view
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", submit_btn)
                time.sleep(0.5)

                # Get the current URL before clicking
                url_before = self.driver.current_url
                logger.info(f"\nURL before submit: {url_before}")

                # Click using JavaScript as backup
                logger.info("→ Clicking 'Submit' button...")
                try:
                    submit_btn.click()
                except:
                    logger.info("  (using JavaScript click)")
                    self.driver.execute_script("arguments[0].click();", submit_btn)

                WebDriverWait(self.driver, 10).until(
    lambda d: d.current_url != url_before or "formResponse" in d.current_url
)


                # Check if URL changed (more reliable than text search)
                url_after = self.driver.current_url
                logger.info(f"URL after submit: {url_after}")
                
                if url_after != url_before or "formResponse" in url_after:
                    logger.info("\n" + "="*50)
                    logger.info("✓ FORM SUBMITTED SUCCESSFULLY")
                    logger.info("="*50)
                    logger.info(f"Response URL: {url_after}")
                    break
                else:
                    # Check for validation errors again
                    logger.info("\n" + "="*50)
                    logger.info("❌ SUBMISSION FAILED")
                    logger.info("="*50)
                    
                    has_errors = self.check_validation_errors()
                    
                    if not has_errors:
                        logger.info("No validation errors found - unknown issue")
                        logger.info(f"Current URL: {self.driver.current_url}")
                    
                    # Save screenshot for debugging
                    screenshot_name = "submit_error.png"
                    self.driver.save_screenshot(screenshot_name)
                    logger.info(f"\nScreenshot saved as '{screenshot_name}'")
                    break

            except Exception as e:
                logger.info("\n" + "="*50)
                logger.info("❌ SUBMIT BUTTON ERROR")
                logger.info("="*50)
                logger.info(f"Error: {e}")
                self.driver.save_screenshot("submit_error.png")
                logger.info("Screenshot saved as 'submit_error.png'")
                break

        self.driver.quit()
        return self.first_page_answers


# Run
if __name__ == "__main__":
    load_dotenv()

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLScCVnuD58jymr9CLaCPKNtYbpYY5Erz28VMK6eETixwHJh7_A/viewform"

    bot = GoogleFormAutomation(OPENAI_API_KEY, FORM_URL)
    bot.fill_form()
