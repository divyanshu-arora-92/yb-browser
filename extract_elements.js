// mark_page.js
// Collect rich metadata for interactive/clickable elements.
// Does NOT create any DOM overlays.

(function () {
  // utility: escape XML text
  function xmlEscape(str) {
    if (str == null) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  // Create a simple CSS selector for element
  function makeCssSelector(el) {
    if (!el || el === document) return '';
    if (el.id) return '#' + el.id;
    var tag = el.tagName.toLowerCase();
    var cls = el.className ? ('.' + String(el.className).trim().replace(/\s+/g, '.')) : '';
    var name = el.getAttribute && el.getAttribute('name') ? '[name="' + el.getAttribute('name') + '"]' : '';
    // Limit length
    var sel = tag + cls + name;
    if (sel.length > 200) sel = tag;
    return sel;
  }

  // Compute XPath for an element (useful when CSS selector not unique)
  function makeXPath(el) {
    if (!el || el.nodeType !== 1) return '';
    var xpath = '';
    for (; el && el.nodeType === 1; el = el.parentNode) {
      var id = el.getAttribute('id');
      if (id) {
        xpath = '/*[@id="' + id + '"]' + xpath;
        break;
      } else {
        var sib = el, nth = 1;
        while (sib = sib.previousElementSibling) {
          if (sib.tagName === el.tagName) nth++;
        }
        xpath = '/' + el.tagName.toLowerCase() + '[' + nth + ']' + xpath;
      }
    }
    return xpath;
  }

  // Check if element is visible in the viewport (some heuristics)
  function isVisible(el) {
    try {
      var style = window.getComputedStyle(el);
      if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity || '1') === 0) return false;
      var rect = el.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) return false;
      // check if element is covered at its center by another element that is not itself or its descendant
      var cx = rect.left + rect.width / 2;
      var cy = rect.top + rect.height / 2;
      if (cx < 0 || cy < 0 || cx > (window.innerWidth || document.documentElement.clientWidth) || cy > (window.innerHeight || document.documentElement.clientHeight)) {
        // not visible in viewport currently
        return false;
      }
      var topEl = document.elementFromPoint(cx, cy);
      if (!topEl) return false;
      return (topEl === el || el.contains(topEl));
    } catch (e) {
      return true;
    }
  }

  // collect attributes that are useful
  function collectAttributes(el) {
    var attrs = {};
    try {
      var attrList = ['id', 'name', 'href', 'type', 'value', 'placeholder', 'title', 'role', 'tabindex', 'aria-label', 'aria-hidden', 'alt', 'src'];
      attrList.forEach(function (k) {
        var v = el.getAttribute && el.getAttribute(k);
        if (v != null) attrs[k] = v;
      });
    } catch (e) {
      // ignore
    }
    return attrs;
  }

  // Main function
  function markPage() {
    var vw = Math.max(document.documentElement.clientWidth || 0, window.innerWidth || 0);
    var vh = Math.max(document.documentElement.clientHeight || 0, window.innerHeight || 0);

    var elements = Array.prototype.slice.call(document.querySelectorAll('*'));

    var items = elements.map(function (element) {
      var textualContent = (element.textContent || '').trim().replace(/\s{2,}/g, ' ');
      var elementType = element.tagName ? element.tagName.toLowerCase() : '';
      var ariaLabel = element.getAttribute && (element.getAttribute('aria-label') || element.getAttribute('aria-labelledby')) || '';

      // get rects (some elements have many client rects)
      var rects = [];
      try {
        var clientRects = Array.prototype.slice.call(element.getClientRects() || []);
        clientRects.forEach(function (bb) {
          // clip to viewport bounds
          var left = Math.max(0, bb.left);
          var top = Math.max(0, bb.top);
          var right = Math.min(vw, bb.right);
          var bottom = Math.min(vh, bb.bottom);
          var width = Math.max(0, right - left);
          var height = Math.max(0, bottom - top);
          if (width > 0 && height > 0) {
            rects.push({
              left: Math.round(left),
              top: Math.round(top),
              right: Math.round(right),
              bottom: Math.round(bottom),
              width: Math.round(width),
              height: Math.round(height)
            });
          }
        });
      } catch (e) {
        // ignore rect errors
      }

      var area = rects.reduce(function (acc, r) { return acc + (r.width * r.height); }, 0);

      return {
        element: element,
        include:
          element.tagName === 'INPUT' ||
          element.tagName === 'TEXTAREA' ||
          element.tagName === 'SELECT' ||
          element.tagName === 'BUTTON' ||
          element.tagName === 'A' ||
          element.onclick != null ||
          window.getComputedStyle(element).cursor === 'pointer' ||
          element.tagName === 'IFRAME' ||
          element.tagName === 'VIDEO',
        area: area,
        rects: rects,
        text: textualContent,
        type: elementType,
        ariaLabel: ariaLabel,
        attributes: collectAttributes(element),
        cssSelector: makeCssSelector(element),
        xpath: makeXPath(element),
        visible: isVisible(element),
        computedCursor: (function () { try { return window.getComputedStyle(element).cursor; } catch (e) { return ''; } })()
      };
    });

    // keep only interactive & reasonably sized ones
    items = items.filter(function (item) {
      return item.include && item.area >= 20 && item.visible;
    });

    // Only keep inner clickable items (same behaviour as your previous script)
    items = items.filter(function (x) {
      return !items.some(function (y) {
        return x.element.contains(y.element) && x !== y;
      });
    });

    // Convert items to pure data (remove DOM references)
    var data = items.map(function (item, index) {
      var rects = (item.rects || []).map(function (r) {
        // center coordinate for each rect
        var cx = Math.round(r.left + r.width / 2);
        var cy = Math.round(r.top + r.height / 2);
        return {
          left: r.left,
          top: r.top,
          right: r.right,
          bottom: r.bottom,
          width: r.width,
          height: r.height,
          centerX: cx,
          centerY: cy
        };
      });

      // overall center (average of rect centers)
      var center = { x: null, y: null };
      if (rects.length > 0) {
        var sx = 0, sy = 0;
        rects.forEach(function (r) { sx += r.centerX; sy += r.centerY; });
        center.x = Math.round(sx / rects.length);
        center.y = Math.round(sy / rects.length);
      }

      return {
        index: index,
        type: item.type,
        text: item.text,
        ariaLabel: item.ariaLabel,
        attributes: item.attributes,
        cssSelector: item.cssSelector,
        xpath: item.xpath,
        visible: item.visible,
        computedCursor: item.computedCursor,
        area: item.area,
        rects: rects,
        center: center
      };
    });

    // also provide page context info
    var pageInfo = {
      url: window.location.href,
      title: document.title,
      timestamp: new Date().toISOString()
    };

    return { pageInfo: pageInfo, elements: data };
  }

  // expose function
  window.markPage = markPage;
})();
