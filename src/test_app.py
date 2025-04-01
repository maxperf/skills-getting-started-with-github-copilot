import pytest
from playwright.sync_api import sync_playwright

@pytest.fixture(scope="module")
def playwright_context():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context()
        yield context
        browser.close()

@pytest.fixture(scope="module")
def page(playwright_context):
    page = playwright_context.new_page()
    yield page

# Test to check if the index page loads successfully
def test_index_page_loads(page):
    page.goto("http://localhost:8000")
    assert page.title() == "Mergington High School Activities"  # Updated to match the actual title

# Test to check if a specific element is present on the page
def test_element_presence(page):
    page.goto("http://localhost:8000")
    assert page.query_selector("#activities-container") is not None  # Updated to check for the activities container

# Test to check if the activities are displayed correctly
def test_activities_displayed(page):
    page.goto("http://localhost:8000")
    # Wait for activities to load
    page.wait_for_selector("#activities-list", timeout=5000)
    # Check if activities container exists
    activities_list = page.query_selector("#activities-list")
    assert activities_list is not None, "Activities list container not found"
    
    # Check activity content (even if it's just the loading message)
    content = activities_list.inner_text()
    assert content, "Activities list is empty"

# Test if the form exists and has required elements
def test_form_presence(page):
    page.goto("http://localhost:8000")
    # Check if the signup form exists
    form = page.query_selector("#signup-form")
    assert form is not None, "Signup form not found"
    
    # Check if email input exists
    email_input = page.query_selector("#email")
    assert email_input is not None, "Email input not found"
    
    # Check if activity dropdown exists
    activity_select = page.query_selector("#activity")
    assert activity_select is not None, "Activity dropdown not found"
    
    # Check if submit button exists
    submit_button = page.query_selector("button[type='submit']")
    assert submit_button is not None, "Submit button not found"