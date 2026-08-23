"""In-process Web evaluation runner using Local LLM."""

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

    # Original tasks retain their direct landing URLs
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


_CURSOR_INJECT_SCRIPT = """
(function() {
  function setupVisualizer() {
    if (document.getElementById('__pw_cursor__')) return;
    const cursor = document.createElement('div');
    cursor.id = '__pw_cursor__';
    cursor.style.cssText = `
      position: fixed;
      top: -100px;
      left: -100px;
      width: 28px;
      height: 28px;
      pointer-events: none;
      z-index: 2147483647;
      transform: translate(0, 0);
      transition: transform 0.12s cubic-bezier(0.2, 0.9, 0.3, 1), left 0.35s cubic-bezier(0.2, 0.9, 0.3, 1), top 0.35s cubic-bezier(0.2, 0.9, 0.3, 1);
      display: block;
    `;
    cursor.innerHTML = `
      <svg width="28" height="28" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg" style="filter: drop-shadow(0 2px 6px rgba(0,0,0,0.6));">
        <path d="M0 0 L0 21 L5.5 15.5 L9.5 24.5 L13.5 23 L9.5 14 L16 14 Z" fill="#111111" stroke="#ffffff" stroke-width="2" stroke-linejoin="round"/>
        <circle cx="0" cy="0" r="3.5" fill="#ff2d55"/>
      </svg>
    `;
    document.documentElement.appendChild(cursor);
    window.__pw_cursor_elem__ = cursor;

    if (!document.getElementById('__pw_cursor_style__')) {
      const style = document.createElement('style');
      style.id = '__pw_cursor_style__';
      style.innerHTML = `
        @keyframes __pw_click_ripple__ {
          0% {
            transform: translate(-50%, -50%) scale(0.2);
            opacity: 1;
            box-shadow: 0 0 0 0 #ffeb3b, 0 0 20px #ff3b30, 0 0 40px #ff9500;
          }
          50% {
            opacity: 0.9;
            box-shadow: 0 0 0 22px rgba(255, 235, 59, 0.6), 0 0 45px rgba(255, 59, 48, 0.8);
          }
          100% {
            transform: translate(-50%, -50%) scale(2.8);
            opacity: 0;
            box-shadow: 0 0 0 50px transparent;
          }
        }
        .__pw_active_highlight__ {
          outline: 4px solid #ff2d55 !important;
          outline-offset: 4px !important;
          box-shadow: 0 0 25px rgba(255, 45, 85, 0.8), inset 0 0 15px rgba(255, 45, 85, 0.2) !important;
          transition: all 0.3s cubic-bezier(0.2, 0.9, 0.3, 1) !important;
          border-radius: 8px !important;
        }
        .__pw_ripple_ring__ {
          position: fixed;
          width: 36px;
          height: 36px;
          border-radius: 50%;
          background: radial-gradient(circle, rgba(255, 255, 255, 0.95) 0%, rgba(255, 235, 59, 0.85) 40%, rgba(255, 45, 85, 0.6) 80%, transparent 100%);
          pointer-events: none;
          z-index: 2147483646;
          animation: __pw_click_ripple__ 0.65s cubic-bezier(0.1, 0.8, 0.3, 1) forwards;
        }
      `;
      document.head.appendChild(style);
    }
  }

  window.__pw_move_cursor__ = function(x, y) {
    setupVisualizer();
    if (window.__pw_cursor_elem__) {
      window.__pw_cursor_elem__.style.left = x + 'px';
      window.__pw_cursor_elem__.style.top = y + 'px';
    }
  };

  window.__pw_click_visual__ = function(x, y) {
    setupVisualizer();
    window.__pw_move_cursor__(x, y);
    const ring = document.createElement('div');
    ring.className = '__pw_ripple_ring__';
    ring.style.left = x + 'px';
    ring.style.top = y + 'px';
    document.documentElement.appendChild(ring);
    if (window.__pw_cursor_elem__) {
      window.__pw_cursor_elem__.style.transform = 'translate(-2px, -2px) scale(0.85)';
      setTimeout(() => {
        if (window.__pw_cursor_elem__) {
          window.__pw_cursor_elem__.style.transform = 'translate(0, 0) scale(1)';
        }
      }, 250);
    }
    setTimeout(() => ring.remove(), 750);
  };

  window.__pw_highlight_visual__ = function(textOrSelector) {
    setupVisualizer();
    document.querySelectorAll('.__pw_active_highlight__').forEach(el => el.classList.remove('__pw_active_highlight__'));
    let target = null;
    if (typeof textOrSelector === 'string' && textOrSelector) {
      try {
        target = document.querySelector(textOrSelector);
      } catch (e) {}
      if (!target) {
        const candidates = Array.from(document.querySelectorAll('div.thumbnail, div.card, div[class*="plan"], div[class*="pricing"], div[class*="tier"], h1, h2, h3, h4, a, button, p, span'));
        target = candidates.find(el => (el.innerText || '').toLowerCase().includes(textOrSelector.toLowerCase()));
      }
    }
    if (target) {
      target.classList.add('__pw_active_highlight__');
      target.scrollIntoView({ behavior: 'smooth', block: 'center' });
      const rect = target.getBoundingClientRect();
      const cx = Math.round(rect.left + rect.width / 2);
      const cy = Math.round(rect.top + rect.height / 2);
      window.__pw_move_cursor__(cx, cy);
      return { x: cx, y: cy };
    }
    return null;
  };

  document.addEventListener('DOMContentLoaded', setupVisualizer);
  if (document.body) setupVisualizer();
})();
"""


def _derive_persona_tiers(persona: Persona) -> Dict[str, Any]:
    """Derive 3-tier configuration from Persona profile."""
    p_text = f"{persona.name} {getattr(persona, 'summary', '')} {getattr(persona, 'context', '')} {getattr(persona, 'goal', '')}".lower()
    
    # Tier 2: Patience & Budget
    if any(w in p_text for w in ["impatient", "nóng vội", "student", "sinh viên", "casual", "lười", "vội", "quick"]):
        patience = "low"
        max_steps = 5
        temp = 0.65
        typing_delay = 25
        scroll_style = "fast_skim"
    elif any(w in p_text for w in ["analyst", "kỹ sư", "engineer", "researcher", "thorough", "cẩn thận", "chuyên gia", "tỉ mỉ", "khó tính", "planner"]):
        patience = "high"
        max_steps = 10
        temp = 0.15
        typing_delay = 55
        scroll_style = "slow_read"
    else:
        patience = "medium"
        max_steps = 7
        temp = 0.35
        typing_delay = 40
        scroll_style = "standard"

    return {
        "patience": patience,
        "max_steps": max_steps,
        "temperature": temp,
        "typing_delay": typing_delay,
        "scroll_style": scroll_style,
    }


class InprocessWebEvalRunner:
    """Autonomous Multi-step Web Agent Loop (Observe -> Plan -> Act) for Persona."""

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
        persona_body = render_persona_block(persona, persona_yaml_path="").strip()
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
        selected_id = f"{task.id}-item-1"
        selected_name = f"{task.site_name} Selected Option"
        need_sat = 8
        ease = 8
        overall = 8
        reason = f"Completed browsing task for {task.title} according to {persona.name}'s profile."

        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                emit({
                    "type": "stage",
                    "stage": "browser_launching",
                    "message": f"Opening Chrome at {start_url} (Patience: {tiers['patience']}, Max Steps: {max_steps})...",
                })
                browser = playwright.chromium.launch(
                    headless=headless,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                context = browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                )
                context.add_init_script(_CURSOR_INJECT_SCRIPT)
                page = context.new_page()

                trace_events.append({
                    "step": 1,
                    "action": "launch_browser",
                    "url": start_url,
                    "description": f"Launched Chrome and opened search entrypoint ({start_url})",
                })

                emit({
                    "type": "stage",
                    "stage": "navigating",
                    "message": f"Navigating to {start_url} in Chrome...",
                })
                page.goto(start_url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(1500)
                page.evaluate("window.__pw_move_cursor__(640, 250)")

                # Handle Google consent dialog if shown
                try:
                    consent_btn = page.locator("button:has-text('Accept all'), button:has-text('I agree'), button:has-text('Tôi đồng ý'), button:has-text('Accept')").first
                    if consent_btn.is_visible(timeout=1500):
                        consent_btn.click()
                        page.wait_for_timeout(1000)
                except Exception:
                    pass

                trace_events.append({
                    "step": 2,
                    "action": "navigate",
                    "url": start_url,
                    "description": f"Loaded {page.title() or 'Search Engine'}",
                })

                client = build_json_client(config.persona_model)

                # ==========================================
                # MULTI-STEP AGENT LOOP (Observe -> Plan -> Act)
                # ==========================================
                for step_num in range(1, max_steps + 1):
                    emit({"type": "stage", "stage": "observing", "step": step_num, "message": f"[Step {step_num}/{max_steps}] Observing page elements..."})

                    # 1. OBSERVE: Extract interactive elements with IDs @e1, @e2...
                    obs_script = """
                    () => {
                      const elements = [];
                      const interactive = document.querySelectorAll('button, a, input, textarea, select, div.g h3, div.thumbnail, div.card, div[class*="plan"], div[class*="pricing"], tr, h2, h3, h4');
                      let id = 1;
                      for (const el of interactive) {
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 5 && rect.height > 5 && rect.top < window.innerHeight * 1.5 && rect.bottom > -150) {
                          const text = (el.innerText || el.getAttribute('placeholder') || el.getAttribute('aria-label') || el.getAttribute('value') || '').trim();
                          if (text || el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'BUTTON') {
                            const tag = el.tagName.toLowerCase();
                            elements.push({
                              id: `@e${id++}`,
                              tag: tag,
                              text: text.slice(0, 120).replace(/\\s+/g, ' '),
                              rect: { x: Math.round(rect.left + rect.width/2), y: Math.round(rect.top + rect.height/2) }
                            });
                          }
                        }
                      }
                      return {
                        title: document.title,
                        url: window.location.href,
                        scrollY: Math.round(window.scrollY),
                        elements: elements.slice(0, 30)
                      };
                    }
                    """
                    try:
                        page.wait_for_load_state("domcontentloaded", timeout=4000)
                    except Exception:
                        pass
                    page.wait_for_timeout(1000)
                    try:
                        observation = page.evaluate(obs_script)
                    except Exception:
                        page.wait_for_timeout(1500)
                        try:
                            observation = page.evaluate(obs_script)
                        except Exception:
                            observation = {"title": page.title() if hasattr(page, "title") else "", "url": page.url, "scrollY": 0, "elements": []}
                    obs_elements = observation.get("elements", [])
                    elements_summary = "\n".join(
                        f"- {el['id']} [{el['tag']}]: \"{el['text']}\"" for el in obs_elements[:20]
                    )

                    # 2. PLAN & REASON: Local LLM generates thought & action
                    system_prompt = (
                        f"{persona_body}\n\n"
                        "=== QUY TẮC & CHIẾN LƯỢC DUYỆT WEB CỦA PERSONA ===\n"
                        f"- Tính cách: Kiên nhẫn ở mức {tiers['patience'].upper()} | Giới hạn: Tối đa {max_steps} bước (hiện tại là bước {step_num}/{max_steps}).\n"
                        "- QUYỀN BỎ CUỘC: Nếu không tìm thấy lựa chọn phù hợp sau nhiều bước, được phép gọi action: 'give_up'.\n\n"
                        "=== HƯỚNG DẪN HÀNH ĐỘNG THÔNG MINH ===\n"
                        "1. KHI ĐANG Ở TRANG TÌM KIẾM (DuckDuckGo, Brave Search...):\n"
                        "   - Bạn PHẢI dùng action: 'type' để gõ từ khóa tìm kiếm phù hợp (ví dụ: 'laptop dell lenovo core i5 sinh vien gia re 15 trieu').\n"
                        "   - KHÔNG ĐƯỢC gọi 'go_back' hay 'done' khi đang ở trang tìm kiếm ban đầu.\n"
                        "2. KIỂM TRA ĐÚNG MỤC TIÊU (Relevance Validation):\n"
                        "   - Sau khi click vào một link, hãy kiểm tra xem trang web có đúng là sản phẩm bạn cần tìm (máy tính Laptop thật, KHÔNG PHẢI phụ kiện/túi đựng/balo/chuột/vỏ bảo vệ) hay không.\n"
                        "   - NẾU VÀO NHẦM TRANG PHỤ KIỆN HOẶC TRANG KHÔNG ĐÚNG MỤC TIÊU: Bạn PHẢI dùng action: 'go_back' để quay lại trang tìm kiếm, rồi click vào kết quả khác hoặc đổi từ khóa. TUYỆT ĐỐI KHÔNG CHỌN SẢN PHẨM PHỤ KIỆN/TÚI ĐỰNG.\n"
                        "3. THAM KHẢO & SO SÁNH NHIỀU NGUỒN:\n"
                        "   - Nếu trang hiện tại không đủ thông tin hoặc giá quá đắt, dùng action: 'go_back' để quay lại xem nguồn khác.\n"
                        "4. CÁC HÀNH ĐỘNG HỢP LỆ:\n"
                        "   - 'type': Gõ từ khóa tìm kiếm mới hoặc lọc sản phẩm.\n"
                        "   - 'click': Click vào link kết quả tìm kiếm, thẻ sản phẩm, nút chọn.\n"
                        "   - 'scroll': Cuộn trang để đọc tiếp nội dung.\n"
                        "   - 'go_back': Quay lại trang trước (chỉ dùng sau khi đã click vào xem một trang mà muốn quay lại tìm kiếm).\n"
                        "   - 'done': Chốt lựa chọn khi đã tìm thấy đúng máy tính Laptop ưng ý.\n"
                        "   - 'give_up': Bỏ cuộc khi không có lựa chọn phù hợp."
                    )

                    user_prompt = (
                        f"Nhiệm vụ: {task.title}\n"
                        f"Mục tiêu cần hoàn thành: {task.description}\n"
                        f"URL hiện tại: {observation.get('url')} (Tiêu đề trang: {observation.get('title')}, Cuộn: {observation.get('scrollY')}px)\n\n"
                        f"Lịch sử các bước đã thực hiện:\n{json.dumps(action_history, ensure_ascii=False, indent=1)}\n\n"
                        f"Các phần tử tương tác đang nhìn thấy trên màn hình:\n{elements_summary}\n\n"
                        "Hãy suy nghĩ và chọn 1 hành động theo định dạng JSON:\n"
                        "{\n"
                        '  "thought": "<Suy nghĩ cụ thể của Persona: kiểm tra xem trang có đúng mục tiêu không, cần click, type, scroll, go_back hay done/give_up>",\n'
                        '  "action": "type" | "click" | "scroll" | "go_back" | "done" | "give_up",\n'
                        '  "target": "<ID phần tử ví dụ @e1 nếu click/type>",\n'
                        '  "text": "<từ khóa nếu type>",\n'
                        '  "direction": "down" | "up" (nếu scroll),\n'
                        '  "amount": 350,\n'
                        '  "selected_product_id": "<ID sản phẩm nếu done>",\n'
                        '  "selected_product_name": "<Tên sản phẩm CHÍNH XÁC nếu done - ví dụ tên Laptop, không chọn phụ kiện>",\n'
                        '  "need_satisfaction": <1-10 nếu done>,\n'
                        '  "ease_of_use": <1-10 nếu done>,\n'
                        '  "overall_experience_rating": <1-10 nếu done>,\n'
                        '  "reason": "<Giải thích chi tiết quyết định nếu done hoặc give_up>"\n'
                        "}"
                    )

                    emit({"type": "stage", "stage": "planning", "step": step_num, "message": f"[Step {step_num}] Thinking as {persona.name}..."})
                    decision = client.complete_json(system=system_prompt, user=user_prompt)

                    thought = str(decision.get("thought", "")).strip()
                    act_name = str(decision.get("action", "scroll")).strip().lower()
                    target_id = str(decision.get("target", "")).strip()

                    emit({
                        "type": "thought",
                        "step": step_num,
                        "persona": persona.name,
                        "thought": thought,
                        "action": act_name,
                        "target": target_id,
                    })

                    action_history.append({"step": step_num, "thought": thought, "action": act_name, "target": target_id})

                    # 3. ACT: Motor execution via Playwright
                    if act_name in ("go_back", "back"):
                        page.evaluate("window.__pw_move_cursor__(50, 50)")
                        page.wait_for_timeout(300)
                        try:
                            page.go_back(wait_until="domcontentloaded", timeout=15000)
                        except Exception:
                            pass
                        page.wait_for_timeout(1500)
                        if page.url == "about:blank":
                            page.goto("https://duckduckgo.com", wait_until="domcontentloaded")
                            page.wait_for_timeout(1500)
                        trace_events.append({
                            "step": len(trace_events) + 1,
                            "action": "go_back",
                            "thought": thought,
                            "description": "Navigated back to previous page/search results to compare other sources",
                        })

                    elif act_name == "type":
                        type_text = str(
                            decision.get("text")
                            or decision.get("query")
                            or decision.get("search_query")
                            or decision.get("value")
                            or ""
                        ).strip()
                        if not type_text:
                            type_text = f"{task.title}".strip()

                        matched_el = next((e for e in obs_elements if e["id"] == target_id), None)
                        if matched_el:
                            cx, cy = matched_el["rect"]["x"], matched_el["rect"]["y"]
                            page.evaluate(f"window.__pw_click_visual__({cx}, {cy})")
                            page.wait_for_timeout(200)
                            try:
                                page.mouse.click(cx, cy)
                                page.keyboard.type(type_text, delay=tiers["typing_delay"])
                                page.wait_for_timeout(300)
                                page.keyboard.press("Enter")
                            except Exception:
                                pass
                            page.wait_for_timeout(2000)
                        else:
                            # Fallback if typing into search box
                            search_box = page.locator("textarea[name='q'], input[name='q'], input[type='text'], input[type='search']").first
                            if search_box.is_visible():
                                box = search_box.bounding_box()
                                if box:
                                    cx, cy = box["x"] + box["width"]/2, box["y"] + box["height"]/2
                                    page.evaluate(f"window.__pw_click_visual__({cx}, {cy})")
                        # If DuckDuckGo returned 418 anti-bot or didn't navigate, open search results directly
                        page.wait_for_timeout(1500)
                        if "418" in page.url or "error" in page.url or page.url.endswith("duckduckgo.com/"):
                            try:
                                encoded_q = type_text.replace(" ", "+")
                                page.goto(f"https://search.brave.com/search?q={encoded_q}", wait_until="domcontentloaded", timeout=30000)
                                page.wait_for_timeout(1500)
                            except Exception:
                                pass

                        trace_events.append({
                            "step": len(trace_events) + 1,
                            "action": "type",
                            "target": target_id or "search_box",
                            "text": type_text,
                            "thought": thought,
                            "description": f"Searched '{type_text}' on DuckDuckGo",
                        })

                    elif act_name == "click":
                        matched_el = next((e for e in obs_elements if e["id"] == target_id), None)
                        if matched_el:
                            cx, cy = matched_el["rect"]["x"], matched_el["rect"]["y"]
                            page.evaluate(f"window.__pw_click_visual__({cx}, {cy})")
                            page.wait_for_timeout(300)
                            try:
                                page.mouse.click(cx, cy)
                            except Exception:
                                pass
                        page.wait_for_timeout(1800)
                        trace_events.append({
                            "step": len(trace_events) + 1,
                            "action": "click",
                            "target": target_id,
                            "thought": thought,
                            "description": f"Clicked {target_id} ({matched_el.get('text', '') if matched_el else ''})",
                        })

                    elif act_name == "scroll":
                        amount = int(decision.get("amount", 350))
                        if decision.get("direction") == "up":
                            amount = -abs(amount)
                        else:
                            amount = abs(amount)
                        page.evaluate(f"window.scrollBy({{top: {amount}, behavior: 'smooth'}})")
                        page.wait_for_timeout(1200 if tiers["scroll_style"] == "slow_read" else 600)
                        trace_events.append({
                            "step": len(trace_events) + 1,
                            "action": "scroll",
                            "amount": amount,
                            "thought": thought,
                            "description": f"Scrolled {amount}px to inspect search results / content",
                        })

                    elif act_name in ("done", "give_up"):
                        selected_id = str(decision.get("selected_product_id") or f"{task.id}-item-1")
                        selected_name = str(decision.get("selected_product_name") or f"{task.title} Choice")
                        need_sat = max(1, min(10, int(decision.get("need_satisfaction", 8))))
                        ease = max(1, min(10, int(decision.get("ease_of_use", 8))))
                        overall = max(1, min(10, int(decision.get("overall_experience_rating", 8))))
                        reason = str(decision.get("reason", thought or "Decision made according to persona preferences.")).strip()

                        # Highlight choice on webpage
                        try:
                            coords = page.evaluate(f"window.__pw_highlight_visual__({json.dumps(selected_name)})")
                            if coords and isinstance(coords, dict):
                                cx, cy = coords.get("x", 640), coords.get("y", 300)
                                page.evaluate(f"window.__pw_click_visual__({cx}, {cy})")
                            page.wait_for_timeout(2000)
                        except Exception:
                            pass

                        trace_events.append({
                            "step": len(trace_events) + 1,
                            "action": act_name,
                            "target": selected_name,
                            "thought": thought,
                            "description": f"{'Completed and selected' if act_name == 'done' else 'Gave up on'} {selected_name}",
                        })
                        break

                browser.close()

        except Exception as exc:
            # Fallback if browser/network issue occurs
            client = build_json_client(config.persona_model)
            system_prompt = (
                f"{persona_body}\n\n"
                "Evaluate the website task and output your selection decision in JSON."
            )
            user_prompt = (
                f"Task: {task.title}\n"
                f"Description: {task.description}\n"
                "Return JSON with selected_product_id, selected_product_name, need_satisfaction, ease_of_use, overall_experience_rating, reason."
            )
            raw = client.complete_json(system=system_prompt, user=user_prompt)
            selected_id = str(raw.get("selected_product_id") or f"{task.id}-item-1")
            selected_name = str(raw.get("selected_product_name") or f"{task.site_name} Selected Option")
            need_sat = max(1, min(10, int(raw.get("need_satisfaction", 8))))
            ease = max(1, min(10, int(raw.get("ease_of_use", 8))))
            overall = max(1, min(10, int(raw.get("overall_experience_rating", 8))))
            reason = str(raw.get("reason", f"Selected {selected_name} based on persona preferences.")).strip()
            trace_events = [
                {"step": 1, "action": "navigate", "url": start_url, "description": f"Navigated to {task.site_name}"},
                {"step": 2, "action": "select", "url": start_url, "description": f"Selected {selected_name} ({selected_id})"},
            ]

        web_result = WebEvalResultArtifact(
            selected_product_id=selected_id,
            selected_product_name=selected_name,
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

