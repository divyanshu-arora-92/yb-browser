from typing import TypedDict, List, Literal, Optional, Any, Dict, Tuple
import random
import time
import asyncio
import platform
import xml.etree.ElementTree as ET
from playwright.async_api import async_playwright, Browser, Playwright, Page

EXTRACT_ELEMENTS_JS_PATH = "./extract_elements.js"
class BrowserManager:
    def __init__(self):
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self._extract_elements_script: Optional[str] = None

        try:
            with open(EXTRACT_ELEMENTS_JS_PATH, "r", encoding="utf-8") as f:
                self._extract_elements_script = f.read()
        except FileNotFoundError:
            self._extract_elements_script = "" # page_id → Playwright Page

    async def start(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=False)
        self.context = await self.browser.new_context()

        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=False, args=["--start-maximized"])
        self.context = await self.browser.new_context(no_viewport=True)

        # Open a default tab
        await self.context.new_page()

    async def stop(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def get_page_summaries(self) -> List[Dict[str, Any]]:
        return_data = []

        for _page in self.context.pages:
            elements = await _page.query_selector_all("button, a, input, h1, h2, h3")
            summary = []

            for el in elements[:30]:  # limit element count
                tag = await el.evaluate("(element) => element.tagName.toLowerCase()")
                text = await el.evaluate(
                    "(element) => element.innerText || element.placeholder || ''"
                )
                text = text.strip()

                if text:
                    summary.append({"tag": tag, "text": text[:100]})

            try:
                _url = _page.url.split("/")[2]
            except:
                _url = ""

            return_data.append({
                "url": _page.url,
                "title": await _page.title(),
                "domain": _url,
                "elements_summary": summary
            })

        return return_data


    async def take_snapshot(self, page: Page) -> Tuple[bytes, str]:
        await asyncio.sleep(3)
        def _safe_text(parent, tag, value):
            """Helper: add a child with text (handle None)."""
            child = ET.SubElement(parent, tag)
            if value is None:
                child.text = ""
            else:
                # Convert non-string to string safely
                child.text = str(value)
            return child
        
        def _add_attributes(parent, attributes):
            attrs_node = ET.SubElement(parent, "attributes")
            if not attributes:
                return attrs_node
            for k, v in attributes.items():
                # attribute value might be None
                child = ET.SubElement(attrs_node, "attr", attrib={"name": str(k)})
                child.text = "" if v is None else str(v)
            return attrs_node

        # Inject script (defines window.markPage)
        await page.evaluate(self._extract_elements_script)

        result = await page.evaluate("markPage()")

        elements = result.get("elements", [])

        # Save a clean screenshot (NO overlays)
        screenshot_bytes: bytes = await page.screenshot(full_page=False)

        elements_node = ET.Element("elements")

        for el in (elements or []):
            el_node = ET.SubElement(elements_node, "element", attrib={"index": str(el.get("index", ""))})
            _safe_text(el_node, "type", el.get("type"))
            _safe_text(el_node, "text", el.get("text"))
            _safe_text(el_node, "ariaLabel", el.get("ariaLabel"))
            _safe_text(el_node, "cssSelector", el.get("cssSelector"))
            _safe_text(el_node, "computedCursor", el.get("computedCursor"))
            _add_attributes(el_node, el.get("attributes"))
            center = el.get("center", {})
            center_node = ET.SubElement(el_node, "center")
            _safe_text(center_node, "x", center.get("x"))
            _safe_text(center_node, "y", center.get("y"))

        # indent for readability (Python 3.9+)
        try:
            import xml.dom.minidom as minidom
            rough_string = ET.tostring(elements_node, 'utf-8')
            reparsed = minidom.parseString(rough_string)
            pretty_xml_string = reparsed.toprettyxml(indent="  ")
            return screenshot_bytes, pretty_xml_string.decode('utf-8')
        except Exception:
            # Fallback for older Python or if minidom fails
            pretty_xml_string = ET.tostring(elements_node, encoding="utf-8", xml_declaration=True).decode('utf-8')
            return screenshot_bytes, pretty_xml_string

    async def take_screenshot(self, page: Page, full_page: Optional[bool] = True) -> Tuple[bytes, List[dict[str, Any]]]:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1)
        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(1)
        screenshot_bytes: bytes = await page.screenshot(full_page=full_page)
        return(screenshot_bytes)
    
    async def goto(self, page: Page, url: str):
        await page.goto(url)
        await asyncio.sleep(1)  

    async def action_click(self, page: Page, x: int, y:int):
        await page.mouse.click(x, y)
        await asyncio.sleep(0.5)
        
    async def action_typetext(self, page: Page, x:int, y:int, text: str):
        """
        Clicks the center of the bounding box to focus the element, 
        clears existing text, and types the new text content.
        """

        # 1. Click to focus the input field
        await page.mouse.click(x, y)
        
        # 2. Select all existing text
        select_all = "Meta+A" if platform.system() == "Darwin" else "Control+A"
        await page.keyboard.press(select_all)
        
        # 3. Delete the selection
        await page.keyboard.press("Backspace")
        
        # 4. Type the new text content with a human-like delay
        for char in text:
            await page.keyboard.press(char)
            # Use random delay for less robotic interaction
            await asyncio.sleep(random.uniform(0.08, 0.15))
            
        # 5. Press Enter to submit/confirm
        await page.keyboard.press("Enter")
        await asyncio.sleep(0.5)

    async def action_scroll(self, page: Page, direction, whole_page=True, x=None, y=None):   
        if whole_page:
            # Not sure the best value for this:
            scroll_amount = 500
            scroll_direction = (-scroll_amount if direction.lower() == "up" else scroll_amount)
            await page.evaluate(f"window.scrollBy(0, {scroll_direction})")
        else:
            # Scrolling within a specific element
            scroll_amount = 200
            scroll_direction = (-scroll_amount if direction.lower() == "up" else scroll_amount)
            await page.mouse.move(x, y)
            await page.mouse.wheel(0, scroll_direction)

        return f"Scrolled {direction} in whole page {whole_page} or x={x}, y={y}"
    
    async def back(self, page: Page):
        await page.go_back()
        await asyncio.sleep(0.5)

