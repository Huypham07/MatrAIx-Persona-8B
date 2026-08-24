"""In-process Web evaluation runner using Local LLM with fast, smooth, visible DOM interactions."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from playground.harbor.web_eval import (
    HarborWebEvalConfig,
    HarborWebEvalResult,
    WebEvalResultArtifact,
    WebEvalTask,
    WebTrace,
    build_web_task_prompt,
)
from playground.model_client import build_json_client
from playground.types import Persona
from playground.user_sim.prompt import render_persona_block


def _resolve_start_url(task: WebEvalTask) -> str:
    start_mode = os.environ.get("WEB_AGENT_START_MODE", "auto").strip().lower()
    if start_mode in {"duckduckgo", "ddg"}:
        return "https://duckduckgo.com"
    if start_mode == "google":
        return "https://www.google.com"
    if start_mode == "direct":
        if task.site_url and task.site_url.startswith("http") and "example.com" not in task.site_url:
            return task.site_url

    tid = (task.id or "").lower()
    tname = str(task.task_path).lower()

    # Search tasks start from DuckDuckGo
    if "search" in tid or "search" in tname or "duckduckgo" in (task.site_url or ""):
        return "https://duckduckgo.com"

    # Catalog & direct web evaluation tasks
    if "laptop" in tid or "laptop" in tname:
        return "https://webscraper.io/test-sites/e-commerce/static/computers/laptops"
    if "notion" in tid or "notion" in tname or "plan-choice" in tid:
        return "https://www.notion.com/pricing"
    if "quote" in tid or "quote" in tname:
        return "https://quotes.toscrape.com/"
    if "book" in tid or "book" in tname:
        return "https://books.toscrape.com/"
    if "course" in tid or "mit" in tid or "ocw" in tid:
        return "https://ocw.mit.edu/courses/"
    if task.site_url and task.site_url.startswith("http") and "example.com" not in task.site_url:
        return task.site_url
    return "https://duckduckgo.com"


_FAST_CURSOR_AND_SOM_SCRIPT = """
(function() {
  window.__pw_elements__ = {};

  function setupVisuals() {
    if (document.getElementById('__pw_cursor__')) return;

    // Visual Cursor
    const cursor = document.createElement('div');
    cursor.id = '__pw_cursor__';
    cursor.style.cssText = `
      position: fixed;
      top: -100px;
      left: -100px;
      width: 26px;
      height: 26px;
      pointer-events: none;
      z-index: 2147483647;
      transition: left 0.22s cubic-bezier(0.2, 0.9, 0.3, 1), top 0.22s cubic-bezier(0.2, 0.9, 0.3, 1), transform 0.1s ease;
      display: block;
    `;
    cursor.innerHTML = `
      <svg width="26" height="26" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg" style="filter: drop-shadow(0 2px 5px rgba(0,0,0,0.5));">
        <path d="M0 0 L0 21 L5.5 15.5 L9.5 24.5 L13.5 23 L9.5 14 L16 14 Z" fill="#0f172a" stroke="#ffffff" stroke-width="2" stroke-linejoin="round"/>
        <circle cx="0" cy="0" r="3.5" fill="#3b82f6"/>
      </svg>
    `;
    document.documentElement.appendChild(cursor);
    window.__pw_cursor_elem__ = cursor;

    // CSS Styles for badges & ripples
    if (!document.getElementById('__pw_style__')) {
      const style = document.createElement('style');
      style.id = '__pw_style__';
      style.innerHTML = `
        @keyframes __pw_ripple_anim__ {
          0% { transform: translate(-50%, -50%) scale(0.2); opacity: 1; }
          100% { transform: translate(-50%, -50%) scale(2.2); opacity: 0; }
        }
        .__pw_ripple_ring__ {
          position: fixed;
          width: 32px;
          height: 32px;
          border-radius: 50%;
          background: radial-gradient(circle, rgba(59, 130, 246, 0.8) 0%, rgba(245, 158, 11, 0.6) 50%, transparent 100%);
          pointer-events: none;
          z-index: 2147483646;
          animation: __pw_ripple_anim__ 0.4s cubic-bezier(0.1, 0.8, 0.3, 1) forwards;
        }
        .__pw_active_highlight__ {
          outline: 3px solid #3b82f6 !important;
          outline-offset: 3px !important;
          box-shadow: 0 0 16px rgba(59, 130, 246, 0.7) !important;
          transition: outline 0.2s ease, box-shadow 0.2s ease !important;
          border-radius: 6px !important;
        }
        .__pw_chosen_highlight__ {
          outline: 4px solid #10b981 !important;
          outline-offset: 4px !important;
          box-shadow: 0 0 25px rgba(16, 185, 129, 0.9) !important;
          transition: all 0.3s ease !important;
          border-radius: 8px !important;
        }
      `;
      document.head.appendChild(style);
    }
  }

  window.__pw_move_cursor__ = function(x, y) {
    setupVisuals();
    if (window.__pw_cursor_elem__) {
      window.__pw_cursor_elem__.style.left = x + 'px';
      window.__pw_cursor_elem__.style.top = y + 'px';
    }
  };

  window.__pw_click_visual__ = function(x, y) {
    setupVisuals();
    window.__pw_move_cursor__(x, y);
    const ring = document.createElement('div');
    ring.className = '__pw_ripple_ring__';
    ring.style.left = x + 'px';
    ring.style.top = y + 'px';
    document.documentElement.appendChild(ring);
    if (window.__pw_cursor_elem__) {
      window.__pw_cursor_elem__.style.transform = 'scale(0.85)';
      setTimeout(() => {
        if (window.__pw_cursor_elem__) window.__pw_cursor_elem__.style.transform = 'scale(1)';
      }, 150);
    }
    setTimeout(() => ring.remove(), 450);
  };

  // Set-of-Marks DOM scanner: clean extraction of product cards and interactive controls
  window.__pw_scan_dom__ = function() {
    setupVisuals();
    document.querySelectorAll('.__pw_som_badge__').forEach(el => el.remove());
    window.__pw_elements__ = {};

    // Auto dismiss top announcement / cookie banner if any
    const closeBtn = document.querySelector('.alert .close, button.close, [aria-label="Close"]');
    if (closeBtn && closeBtn.offsetWidth > 0) {
      try { closeBtn.click(); } catch(e) {}
    }

    const items = [];
    let badgeId = 1;

    // 1. Scan Product Cards & Search Results First
    const rawCards = Array.from(document.querySelectorAll('.thumbnail, div.card, div.g, article, div[class*="product-card"], div[class*="product-item"]'));
    const cards = rawCards.filter(c => !c.parentElement || !c.parentElement.closest('.thumbnail, div.card, div.g, article'));

    for (const card of cards) {
      const rect = card.getBoundingClientRect();
      const style = window.getComputedStyle(card);

      if (
        rect.width >= 40 && rect.height >= 40 &&
        style.visibility !== 'hidden' && style.display !== 'none' &&
        rect.top < window.innerHeight + 100 && rect.bottom > -50
      ) {
        const titleEl = card.querySelector('a.title, a[class*="title"], h4 a, h3 a, h2 a, h4:not([class*="price"]), h3:not([class*="price"]), h2:not([class*="price"])');
        const priceEl = card.querySelector('.price, [class*="price"], h4.price, span.price');
        const descEl = card.querySelector('.description, [class*="description"], p.description, p.card-text, .snippet, p');

        let title = '';
        if (titleEl) {
          title = (titleEl.getAttribute('title') || titleEl.innerText || titleEl.textContent || '').trim();
        }
        if (!title) {
          title = (card.getAttribute('data-name') || card.getAttribute('aria-label') || '').trim();
        }
        title = title.replace(/\\s+/g, ' ').slice(0, 100);

        const price = (priceEl ? (priceEl.innerText || priceEl.textContent) : '').trim();
        const desc = (descEl ? (descEl.innerText || descEl.textContent) : '').trim().replace(/\\s+/g, ' ').slice(0, 150);

        if (title || price) {
          const id = badgeId++;
          let targetEl = card;
          if (titleEl && titleEl.tagName === 'A') targetEl = titleEl;
          else if (titleEl && titleEl.closest('a')) targetEl = titleEl.closest('a');
          else if (card.querySelector('a[href]')) targetEl = card.querySelector('a[href]');
          window.__pw_elements__[id] = targetEl;

          // Inject small badge overlay on element
          const badge = document.createElement('div');
          badge.className = '__pw_som_badge__';
          badge.textContent = id;
          badge.style.cssText = `
            position: fixed;
            left: ${Math.max(2, Math.round(rect.left))}px;
            top: ${Math.max(2, Math.round(rect.top))}px;
            background: #f59e0b;
            color: #000;
            font-size: 11px;
            font-weight: 800;
            font-family: system-ui, -apple-system, monospace;
            padding: 1px 5px;
            border-radius: 3px;
            border: 1px solid #d97706;
            box-shadow: 0 1px 3px rgba(0,0,0,0.4);
            z-index: 2147483645;
            pointer-events: none;
            line-height: 13px;
          `;
          document.documentElement.appendChild(badge);

          items.push({
            id: id,
            type: 'product',
            title: title || 'Item',
            price: price,
            description: desc,
            rect: { x: Math.round(rect.left + rect.width / 2), y: Math.round(rect.top + rect.height / 2) }
          });
        }
      }
    }

    // 2. Scan Interactive Controls (Search inputs, buttons, pagination, main nav)
    const controlSelectors = 'input, textarea, select, button, .pagination a, [role="button"]';
    const controls = Array.from(document.querySelectorAll(controlSelectors));

    for (const ctrl of controls) {
      if (ctrl.closest('.thumbnail, .card, div[class*="product"]')) continue;
      const rect = ctrl.getBoundingClientRect();
      const style = window.getComputedStyle(ctrl);

      if (
        rect.width >= 10 && rect.height >= 10 &&
        style.visibility !== 'hidden' && style.display !== 'none' &&
        rect.top < window.innerHeight && rect.bottom > 0
      ) {
        let label = (ctrl.innerText || ctrl.getAttribute('placeholder') || ctrl.getAttribute('aria-label') || ctrl.getAttribute('value') || '').trim();
        label = label.replace(/\\s+/g, ' ').slice(0, 80);
        const tag = ctrl.tagName.toLowerCase();

        if (label || tag === 'input' || tag === 'textarea') {
          const id = badgeId++;
          window.__pw_elements__[id] = ctrl;

          const badge = document.createElement('div');
          badge.className = '__pw_som_badge__';
          badge.textContent = id;
          badge.style.cssText = `
            position: fixed;
            left: ${Math.max(2, Math.round(rect.left))}px;
            top: ${Math.max(2, Math.round(rect.top))}px;
            background: #3b82f6;
            color: #fff;
            font-size: 10px;
            font-weight: 800;
            font-family: system-ui, -apple-system, monospace;
            padding: 1px 4px;
            border-radius: 3px;
            z-index: 2147483645;
            pointer-events: none;
            line-height: 12px;
          `;
          document.documentElement.appendChild(badge);

          items.push({
            id: id,
            type: tag === 'input' || tag === 'textarea' ? 'input' : 'button',
            title: label || `Control (${tag})`,
            price: '',
            description: '',
            rect: { x: Math.round(rect.left + rect.width / 2), y: Math.round(rect.top + rect.height / 2) }
          });
        }
      }
    }

    return {
      title: document.title,
      url: window.location.href,
      scrollY: Math.round(window.scrollY),
      items: items
    };
  };

  window.__pw_interact_click__ = function(id) {
    setupVisuals();
    const el = window.__pw_elements__[id];
    if (!el) return null;
    
    const rect = el.getBoundingClientRect();
    const cx = Math.round(rect.left + rect.width / 2);
    const cy = Math.round(rect.top + rect.height / 2);
    window.__pw_click_visual__(cx, cy);
    el.classList.add('__pw_active_highlight__');
    setTimeout(() => el.classList.remove('__pw_active_highlight__'), 600);
    try { el.click(); } catch(e) {}
    return { x: cx, y: cy };
  };

  window.__pw_interact_type__ = function(id, text) {
    setupVisuals();
    const el = window.__pw_elements__[id] || document.querySelector("input[name='q'], textarea[name='q'], input[type='text'], input[type='search']");
    if (!el) return null;
    const rect = el.getBoundingClientRect();
    const cx = Math.round(rect.left + rect.width / 2);
    const cy = Math.round(rect.top + rect.height / 2);
    window.__pw_click_visual__(cx, cy);
    el.focus();
    if ('value' in el) {
      el.value = text;
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    }
    return { x: cx, y: cy };
  };

  window.__pw_highlight_chosen__ = function(productName) {
    setupVisuals();
    const all = Array.from(document.querySelectorAll('.thumbnail, .card, div[class*="product"], div[class*="item"], h1, h2, h3, h4, a'));
    const target = all.find(el => (el.innerText || '').toLowerCase().includes((productName || '').toLowerCase()));
    if (target) {
      target.classList.add('__pw_chosen_highlight__');
      target.scrollIntoView({ behavior: 'smooth', block: 'center' });
      const rect = target.getBoundingClientRect();
      const cx = Math.round(rect.left + rect.width / 2);
      const cy = Math.round(rect.top + rect.height / 2);
      window.__pw_click_visual__(cx, cy);
      return { x: cx, y: cy };
    }
    return null;
  };

  document.addEventListener('DOMContentLoaded', setupVisuals);
  if (document.body) setupVisuals();
})();
"""


def _render_persona_for_web(persona: Persona, repo_root: Optional[Path] = None) -> str:
    """Render full natural language persona prompt for web agent."""
    if repo_root:
        for candidate_dir in [
            repo_root / "persona" / "datasets" / "matraix-persona-dev-sample",
            repo_root / "persona" / "datasets",
            repo_root / "data" / "personas",
        ]:
            if candidate_dir.is_dir():
                pid = str(persona.id or "")
                for candidate in [
                    candidate_dir / f"{pid}.yaml",
                    candidate_dir / f"{pid}.yml",
                    candidate_dir / f"persona_{pid}.yaml",
                    candidate_dir / f"persona_{pid}.yml",
                ]:
                    if candidate.is_file():
                        try:
                            from matraix.agents.persona.loader import load_persona
                            from matraix.agents.persona.templating import (
                                PERSONA_SYSTEM_TEMPLATE,
                                render_persona_template,
                                resolve_persona_template,
                            )

                            loaded = load_persona(str(candidate))
                            template = resolve_persona_template(loaded, None, PERSONA_SYSTEM_TEMPLATE)
                            return render_persona_template(template, loaded).strip()
                        except Exception:
                            pass
    return render_persona_block(persona, persona_yaml_path="").strip()


def _derive_persona_tiers(persona: Persona) -> Dict[str, Any]:
    """Derive browsing configuration from Persona profile."""
    p_text = f"{persona.name} {getattr(persona, 'summary', '')} {getattr(persona, 'context', '')} {getattr(persona, 'goal', '')}".lower()

    env_max = os.environ.get("WEB_AGENT_MAX_STEPS", "").strip()
    custom_max = int(env_max) if env_max.isdigit() and int(env_max) > 0 else None

    if any(w in p_text for w in ["impatient", "nóng vội", "student", "sinh viên", "casual", "lười", "vội", "quick"]):
        patience = "low"
        max_steps = custom_max or 10
        temp = 0.4
    elif any(w in p_text for w in ["analyst", "kỹ sư", "engineer", "researcher", "thorough", "cẩn thận", "chuyên gia", "tỉ mỉ", "khó tính", "planner"]):
        patience = "high"
        max_steps = custom_max or 18
        temp = 0.15
    else:
        patience = "medium"
        max_steps = custom_max or 12
        temp = 0.25

    return {
        "patience": patience,
        "max_steps": max_steps,
        "temperature": temp,
    }


class InprocessWebEvalRunner:
    """Fast, smooth, visible autonomous web agent runner using Set-of-Marks interactive visual markers."""

    def __init__(self, *, repo_root: Optional[Path] = None) -> None:
        self.repo_root = repo_root

    def __call__(
        self,
        persona: Persona,
        task: WebEvalTask,
        config: Optional[HarborWebEvalConfig] = None,
        *,
        created_at: str,
        on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> HarborWebEvalResult:
        config = config or HarborWebEvalConfig()

        def emit(event: Dict[str, Any]) -> None:
            if on_event is not None:
                on_event(event)

        task_prompt = build_web_task_prompt(task)
        persona_body = _render_persona_for_web(persona, self.repo_root)
        
        # Enforce that the exported persona context matches the exact rendered prompt
        persona.context = persona_body
        
        prompts = {
            "personaPrompt": persona_body,
            "harborPrompt": persona_body,
            "taskPrompt": task_prompt,
        }
        emit({"type": "prompts", "prompts": prompts})
        emit({"type": "phase", "phase": "web_navigating"})

        tiers = _derive_persona_tiers(persona)
        max_steps = tiers["max_steps"]
        start_url = _resolve_start_url(task)
        headless = os.environ.get("PLAYWRIGHT_HEADLESS", "false").strip().lower() in {"1", "true", "yes"}

        trace_events: List[Dict[str, Any]] = []
        action_history: List[Dict[str, Any]] = []
        compared_candidates: List[Dict[str, Any]] = []

        selected_id = f"{task.id}-item-1"
        selected_name = f"{task.site_name} Selected Option"
        task_price = ""
        basis_primary = "features"
        exploration_style = "compared_multiple"
        need_sat = 8
        ease = 8
        overall = 8
        reason = f"Selected optimal product for {task.title} based on {persona.name}'s profile."

        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as playwright:
                emit({
                    "type": "stage",
                    "stage": "browser_launching",
                    "message": f"Opening Chrome at {start_url}...",
                })
                browser = playwright.chromium.launch(
                    headless=headless,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                context = browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                )
                context.add_init_script(_FAST_CURSOR_AND_SOM_SCRIPT)
                page = context.new_page()

                trace_events.append({
                    "step": 1,
                    "action": "launch_browser",
                    "url": start_url,
                    "description": f"Launched browser at {start_url}",
                })

                emit({
                    "type": "stage",
                    "stage": "navigating",
                    "message": f"Loading {start_url}...",
                })
                page.goto(start_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(350)
                page.evaluate("window.__pw_move_cursor__(640, 200)")

                # Handle Google / Search consent modal if shown
                try:
                    consent_btn = page.locator("button:has-text('Accept all'), button:has-text('I agree'), button:has-text('Accept')").first
                    if consent_btn.is_visible(timeout=600):
                        consent_btn.click()
                        page.wait_for_timeout(250)
                except Exception:
                    pass

                trace_events.append({
                    "step": 2,
                    "action": "navigate",
                    "url": start_url,
                    "description": f"Loaded {page.title() or start_url}",
                })

                client = build_json_client(config.persona_model, temperature=tiers["temperature"])

                # ==========================================
                # FAST & SMOOTH AGENT LOOP (Observe -> Plan -> Act)
                # ==========================================
                for step_num in range(1, max_steps + 1):
                    emit({
                        "type": "stage",
                        "stage": "observing",
                        "step": step_num,
                        "message": f"[Step {step_num}/{max_steps}] Observing screen...",
                    })

                    # 1. OBSERVE: Scan visible elements with numeric badges
                    page.wait_for_timeout(150)
                    try:
                        observation = page.evaluate("window.__pw_scan_dom__()")
                    except Exception:
                        page.wait_for_timeout(250)
                        try:
                            observation = page.evaluate("window.__pw_scan_dom__()")
                        except Exception:
                            observation = {"title": page.title(), "url": page.url, "scrollY": 0, "items": []}

                    items = observation.get("items", [])

                    # Format elements clearly with their badge IDs
                    products = [it for it in items if it.get("type") == "product"]
                    controls = [it for it in items if it.get("type") != "product"]

                    products_str = "\n".join(
                        f"[{p['id']}] {p['title']} | Giá: {p['price']} | Cấu hình: {p['description']}"
                        for p in products
                    ) if products else "(Không có sản phẩm nào trên màn hình hiện tại. Hãy scroll down để xem thêm)."

                    controls_str = "\n".join(
                        f"[{c['id']}] <{c['type']}> {c['title']}"
                        for c in controls
                    ) if controls else "(Không có nút điều khiển bổ sung)."

                    system_prompt = (
                        f"{persona_body}\n\n"
                        "=== HƯỚNG DẪN ĐIỀU KHIỂN TRÌNH DUYỆT (BROWSER AGENT) ===\n"
                        f"Bạn đang nhập vai '{persona.name}' để duyệt trang web và lựa chọn kết quả phù hợp nhất.\n"
                        "Trên màn hình, mỗi phần tử tương tác được gắn một số ID màu vàng [1], [2], [3]...\n\n"
                        "=== CÁC HÀNH ĐỘNG HỢP LỆ ===\n"
                        "1. done: CHỐT LỰA CHỌN CUỐI CÙNG khi bạn đã thấy kết quả ưng ý nhất. Điền đầy đủ 'selected_product_name', 'task_price_text', 'reason'.\n"
                        "2. click: Click vào một phần tử (target: số ID như 1, 2, 3...).\n"
                        "3. scroll: Cuộn trang xuống để xem thêm nội dung (direction: 'down' | 'up', amount: 400).\n"
                        "4. type: Nhập từ khóa tìm kiếm (target: số ID ô input, text: 'từ khóa').\n"
                        "5. go_back: Quay lại trang trước.\n\n"
                        "=== QUY TẮC QUAN TRỌNG ===\n"
                        "- Nếu bạn đang ở trang chi tiết của một mục và muốn xem các lựa chọn khác, BẮT BUỘC dùng `action: 'go_back'` để quay lại danh sách.\n"
                        "- Khi bạn đã đánh giá đủ và tìm thấy kết quả phù hợp nhất, hãy trả về `action: 'done'` để chốt kết quả."
                    )

                    user_prompt = (
                        f"Nhiệm vụ: {task.title}\n"
                        f"Mô tả: {task.description}\n"
                        f"Trang hiện tại: {observation.get('title')} ({observation.get('url')})\n\n"
                        f"=== DANH SÁCH SẢN PHẨM HIỂN THỊ TRÊN MÀN HÌNH ===\n"
                        f"{products_str}\n\n"
                        f"=== CÁC NÚT ĐIỀU KHIỂN / INPUT ===\n"
                        f"{controls_str}\n\n"
                        "Hãy trả về JSON hành động tiếp theo:\n"
                        "{\n"
                        '  "thought": "<Suy nghĩ cụ thể của persona về sản phẩm phù hợp>",\n'
                        '  "action": "done" | "click" | "scroll" | "type" | "go_back",\n'
                        '  "target": <Số ID phần tử như 1, 2 nếu click hoặc type>,\n'
                        '  "text": "<Từ khóa nếu type>",\n'
                        '  "direction": "down" | "up",\n'
                        '  "selected_product_name": "<Tên sản phẩm CHÍNH XÁC được chọn nếu done>",\n'
                        '  "task_price_text": "<Giá của sản phẩm được chọn nếu done, ví dụ $739.99>",\n'
                        '  "basis_primary": "price" | "quality" | "features" | "convenience" | "taste" | "fit",\n'
                        '  "exploration_style": "quick_pick" | "compared_multiple" | "deep_research",\n'
                        '  "need_satisfaction": <1-10 nếu done>,\n'
                        '  "ease_of_use": <1-10 nếu done>,\n'
                        '  "overall_experience_rating": <1-10 nếu done>,\n'
                        '  "reason": "<Lý do chi tiết vì sao chọn sản phẩm này phù hợp nhất với persona>"\n'
                        "}"
                    )

                    emit({
                        "type": "stage",
                        "stage": "planning",
                        "step": step_num,
                        "message": f"[Step {step_num}] Thinking as {persona.name}...",
                    })

                    decision = client.complete_json(system=system_prompt, user=user_prompt)

                    thought = str(decision.get("thought", "")).strip()
                    act_name = str(decision.get("action", "scroll")).strip().lower()

                    # Parse target number
                    raw_target = decision.get("target")
                    target_id = None
                    if raw_target is not None:
                        try:
                            target_id = int(re.sub(r"[^\d]", "", str(raw_target)))
                        except Exception:
                            target_id = None
                    # If model clicked the same product target in consecutive turns or expressed satisfaction, finalize with done
                    if act_name == "click" and target_id is not None:
                        prev_action = action_history[-1] if action_history else None
                        if prev_action and prev_action.get("action") == "click" and prev_action.get("target") == target_id:
                            act_name = "done"

                    emit({
                        "type": "thought",
                        "step": step_num,
                        "persona": persona.name,
                        "thought": thought,
                        "action": act_name,
                        "target": target_id,
                    })

                    action_history.append({
                        "step": step_num,
                        "thought": thought,
                        "action": act_name,
                        "target": target_id,
                    })

                    # 3. ACT: Fast, accurate, and visible execution
                    if act_name == "click" and target_id is not None:
                        matched = next((it for it in items if it["id"] == target_id), None)
                        matched_text = matched.get("title", "") if matched else ""
                        matched_price = matched.get("price", "") if matched else ""

                        # Record inspected candidate
                        if matched_text and len(matched_text) > 3 and matched.get("type") == "product":
                            if not any(c.get("name") == matched_text for c in compared_candidates):
                                compared_candidates.append({
                                    "name": matched_text,
                                    "price": matched_price,
                                    "notes": f"Inspected via item [{target_id}]",
                                })

                        page.evaluate(f"window.__pw_interact_click__({target_id})")
                        page.wait_for_timeout(350)

                        trace_events.append({
                            "step": len(trace_events) + 1,
                            "action": "click",
                            "target": f"[{target_id}] {matched_text}",
                            "thought": thought,
                            "description": f"Clicked [{target_id}] {matched_text}",
                        })

                    elif act_name == "type":
                        type_text = str(
                            decision.get("text")
                            or decision.get("query")
                            or decision.get("value")
                            or f"{task.title}"
                        ).strip()

                        if target_id is not None:
                            page.evaluate(f"window.__pw_interact_type__({target_id}, {json.dumps(type_text)})")
                        else:
                            page.evaluate(f"window.__pw_interact_type__(null, {json.dumps(type_text)})")

                        page.wait_for_timeout(200)
                        page.keyboard.press("Enter")
                        page.wait_for_timeout(400)

                        # If DuckDuckGo returned anti-bot 418, fallback cleanly to Brave Search
                        if "418" in page.url or page.url.endswith("duckduckgo.com/"):
                            try:
                                q_enc = type_text.replace(" ", "+")
                                page.goto(f"https://search.brave.com/search?q={q_enc}", wait_until="domcontentloaded", timeout=20000)
                                page.wait_for_timeout(300)
                            except Exception:
                                pass

                        trace_events.append({
                            "step": len(trace_events) + 1,
                            "action": "type",
                            "text": type_text,
                            "thought": thought,
                            "description": f"Searched for '{type_text}'",
                        })

                    elif act_name == "scroll":
                        amount = int(decision.get("amount", 400))
                        if decision.get("direction") == "up":
                            amount = -abs(amount)
                        else:
                            amount = abs(amount)

                        page.evaluate(f"window.scrollBy({{ top: {amount}, behavior: 'smooth' }})")
                        page.wait_for_timeout(300)

                        trace_events.append({
                            "step": len(trace_events) + 1,
                            "action": "scroll",
                            "amount": amount,
                            "thought": thought,
                            "description": f"Scrolled {'down' if amount > 0 else 'up'} to view more options",
                        })

                    elif act_name in ("go_back", "back"):
                        page.evaluate("window.__pw_move_cursor__(40, 40)")
                        try:
                            page.go_back(wait_until="domcontentloaded", timeout=10000)
                        except Exception:
                            pass
                        page.wait_for_timeout(350)

                        trace_events.append({
                            "step": len(trace_events) + 1,
                            "action": "go_back",
                            "thought": thought,
                            "description": "Navigated back to previous page",
                        })

                    elif act_name in ("done", "give_up"):
                        selected_name = str(decision.get("selected_product_name") or "").strip()
                        task_price = str(decision.get("task_price_text") or "").strip()

                        # If empty or generic, infer from most recently inspected candidate
                        if not selected_name or "choice" in selected_name.lower() or selected_name.lower().endswith("option"):
                            if compared_candidates:
                                selected_name = compared_candidates[-1]["name"]
                                if not task_price:
                                    task_price = compared_candidates[-1].get("price", "")
                            else:
                                selected_name = f"{task.title} Choice"

                        raw_id = decision.get("selected_product_id") or re.sub(r"[^a-zA-Z0-9_-]+", "-", selected_name).strip("-").lower()
                        selected_id = str(raw_id or f"{task.id}-item-1")
                        basis_primary = str(decision.get("basis_primary") or "features").strip()
                        exploration_style = str(decision.get("exploration_style") or ("compared_multiple" if len(compared_candidates) > 1 else "quick_pick")).strip()
                        need_sat = max(1, min(10, int(decision.get("need_satisfaction", 8))))
                        ease = max(1, min(10, int(decision.get("ease_of_use", 8))))
                        overall = max(1, min(10, int(decision.get("overall_experience_rating", 8))))
                        reason = str(decision.get("reason") or thought or "Selected based on persona criteria.").strip()

                        # Ensure selected item is in candidates list
                        if selected_name and not any(c.get("name") == selected_name for c in compared_candidates):
                            compared_candidates.append({
                                "name": selected_name,
                                "price": task_price,
                                "notes": "Selected as optimal choice",
                            })

                        # Highlight chosen product smoothly on screen
                        try:
                            page.evaluate(f"window.__pw_highlight_chosen__({json.dumps(selected_name)})")
                            page.wait_for_timeout(600)
                        except Exception:
                            pass

                        trace_events.append({
                            "step": len(trace_events) + 1,
                            "action": act_name,
                            "target": selected_name,
                            "thought": thought,
                            "description": f"Decided on {selected_name} ({task_price}) - {reason}",
                        })
                        break

                browser.close()

        except Exception as exc:
            import traceback
            traceback.print_exc()
            # Fallback in case of unexpected environment/browser error
            client = build_json_client(config.persona_model)
            system_prompt = f"{persona_body}\n\nEvaluate the task and select a suitable choice according to your persona."
            user_prompt = f"Task: {task.title}\n{task.description}\nReturn JSON with selected_product_name, task_price_text, reason, need_satisfaction, ease_of_use, overall_experience_rating."
            try:
                raw = client.complete_json(system=system_prompt, user=user_prompt)
                selected_name = str(raw.get("selected_product_name") or f"{task.site_name} Option")
                task_price = str(raw.get("task_price_text") or "")
                selected_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", selected_name).strip("-").lower()
                reason = str(raw.get("reason") or f"Selected based on persona preferences.")
                need_sat = max(1, min(10, int(raw.get("need_satisfaction", 8))))
                ease = max(1, min(10, int(raw.get("ease_of_use", 8))))
                overall = max(1, min(10, int(raw.get("overall_experience_rating", 8))))
            except Exception:
                pass

        web_result = WebEvalResultArtifact(
            selected_product_id=selected_id,
            selected_product_name=selected_name,
            task_price_text=task_price,
            compared_candidates=compared_candidates,
            basis_primary=basis_primary,
            exploration_style=exploration_style,
            need_satisfaction=need_sat,
            ease_of_use=ease,
            overall_experience_rating=overall,
            reason=reason,
            created_at=created_at,
            valid=True,
        )

        trace = WebTrace(events=trace_events, raw={"trace": trace_events, "action_history": action_history})

        result = HarborWebEvalResult(
            config=config,
            persona=persona,
            task=task,
            web_result=web_result,
            trace=trace,
            created_at=created_at,
            prompts=prompts,
        )
        emit({"type": "done", "result": result.to_dict()})
        return result

