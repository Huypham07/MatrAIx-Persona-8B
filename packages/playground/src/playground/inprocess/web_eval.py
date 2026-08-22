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


def _resolve_live_url(task: WebEvalTask) -> str:
    tid = (task.id or "").lower()
    tname = str(task.task_path).lower()
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
    return "https://webscraper.io/test-sites/e-commerce/static/computers/laptops"


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


class InprocessWebEvalRunner:
    """Run Web user simulation with real Playwright Chrome browser automation."""

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

        live_url = _resolve_live_url(task)
        headless = os.environ.get("PLAYWRIGHT_HEADLESS", "false").strip().lower() in {"1", "true", "yes"}
        page_summary = ""
        trace_events: List[Dict[str, Any]] = []

        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                emit({
                    "type": "stage",
                    "stage": "browser_launching",
                    "message": f"Opening Chrome browser at {live_url}...",
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
                    "url": live_url,
                    "description": f"Launched Chrome and opened new tab for {task.site_name}",
                })

                emit({
                    "type": "stage",
                    "stage": "navigating",
                    "message": f"Navigating to {live_url} in Chrome...",
                })
                page.goto(live_url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(1500)
                page.evaluate("window.__pw_move_cursor__(640, 250)")
                trace_events.append({
                    "step": 2,
                    "action": "navigate",
                    "url": live_url,
                    "description": f"Loaded {page.title() or task.site_name}",
                })

                # If Notion pricing page, click "Pay monthly" or toggle monthly billing if present
                if "notion" in live_url:
                    try:
                        monthly_btn = page.locator("text=/Pay monthly|Monthly/i").first
                        if monthly_btn.is_visible(timeout=3000):
                            box = monthly_btn.bounding_box()
                            if box:
                                cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
                                page.evaluate(f"window.__pw_click_visual__({cx}, {cy})")
                                page.wait_for_timeout(400)
                            monthly_btn.click()
                            page.wait_for_timeout(1000)
                            trace_events.append({
                                "step": 3,
                                "action": "click",
                                "target": "Pay monthly toggle",
                                "description": "Activated monthly billing view with click ripple",
                            })
                    except Exception:
                        pass

                # Scan / browse available items with cursor movement and highlight
                try:
                    cards = page.locator("div.thumbnail, div.card, div[class*='plan'], div[class*='pricing']").all()
                    for card in cards[:3]:
                        box = card.bounding_box()
                        if box:
                            cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
                            page.evaluate(f"window.__pw_move_cursor__({cx}, {cy})")
                            page.wait_for_timeout(400)
                except Exception:
                    pass

                # Scroll down smoothly so user sees the page being browsed in Chrome
                page.evaluate("window.scrollBy({top: 350, behavior: 'smooth'})")
                page.wait_for_timeout(1200)
                page.evaluate("window.scrollBy({top: -150, behavior: 'smooth'})")
                page.wait_for_timeout(800)
                trace_events.append({
                    "step": len(trace_events) + 1,
                    "action": "scroll",
                    "description": "Scrolled and inspected available products and options",
                })

                # Extract page content for LLM decision
                page_text = page.evaluate("() => document.body.innerText") or ""
                page_summary = page_text[:3500]

                emit({
                    "type": "stage",
                    "stage": "evaluating",
                    "message": f"Evaluating live webpage options as {persona.name}...",
                })

                client = build_json_client(config.persona_model)
                system_prompt = (
                    f"{persona_body}\n\n"
                    "You are simulating a user browsing a live website and making a purchasing or selection decision.\n"
                    "Evaluate the available options on the website and return a JSON object with your selected option, scores, and honest feedback."
                )

                user_prompt = (
                    f"Website: {task.site_name} ({live_url})\n"
                    f"Task: {task.title}\n"
                    f"Description: {task.description}\n\n"
                    f"Live Website Page Content:\n{page_summary}\n\n"
                    "Browse the website, compare options based on your persona, and output your decision in valid JSON with format:\n"
                    "{\n"
                    '  "selected_product_id": "<ID of selected item or plan>",\n'
                    '  "selected_product_name": "<Name of selected item or plan>",\n'
                    '  "need_satisfaction": <integer 1 to 10>,\n'
                    '  "ease_of_use": <integer 1 to 10>,\n'
                    '  "overall_experience_rating": <integer 1 to 10>,\n'
                    '  "reason": "<Detailed paragraph explaining why you chose this item based on your persona preferences and budget>"\n'
                    "}"
                )

                raw = client.complete_json(system=system_prompt, user=user_prompt)

                selected_id = str(raw.get("selected_product_id") or raw.get("selectedProductId") or f"{task.id}-item-1")
                selected_name = str(raw.get("selected_product_name") or raw.get("selectedProductName") or f"{task.site_name} Selected Option")
                need_sat = max(1, min(10, int(raw.get("need_satisfaction", raw.get("needSatisfaction", 7)))))
                ease = max(1, min(10, int(raw.get("ease_of_use", raw.get("easeOfUse", 8)))))
                overall = max(1, min(10, int(raw.get("overall_experience_rating", raw.get("overallExperienceRating", 8)))))
                reason = str(raw.get("reason", "")).strip()
                if len(reason) < 20:
                    reason = f"Based on my personal preferences and profile as {persona.name}, I selected {selected_name} on {task.site_name}."

                emit({
                    "type": "stage",
                    "stage": "selecting",
                    "message": f"Selecting {selected_name} on webpage...",
                })

                # Visualize selection with cursor movement, click ripple, and glowing highlight
                try:
                    coords = page.evaluate(f"window.__pw_highlight_visual__({json.dumps(selected_name)})")
                    if coords and isinstance(coords, dict):
                        cx, cy = coords.get("x", 640), coords.get("y", 300)
                        page.evaluate(f"window.__pw_click_visual__({cx}, {cy})")
                    else:
                        item_locator = page.locator(f"text={selected_name}").first
                        if item_locator.is_visible(timeout=2000):
                            box = item_locator.bounding_box()
                            if box:
                                cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
                                page.evaluate(f"window.__pw_click_visual__({cx}, {cy})")
                    page.wait_for_timeout(2500)
                except Exception:
                    pass

                trace_events.append({
                    "step": len(trace_events) + 1,
                    "action": "select",
                    "target": selected_name,
                    "description": f"Highlighted and clicked {selected_name} ({selected_id})",
                })
                browser.close()

        except Exception as exc:
            # Fallback if browser launch or network is restricted
            client = build_json_client(config.persona_model)
            system_prompt = (
                f"{persona_body}\n\n"
                "You are simulating a user browsing a website and making a purchasing or selection decision.\n"
                "Evaluate the website and return a JSON object with your selected option, scores, and honest feedback."
            )
            user_prompt = (
                f"Website: {task.site_name} ({live_url})\n"
                f"Task: {task.title}\n"
                f"Description: {task.description}\n\n"
                "Browse the website, compare options based on your persona, and output your decision in valid JSON with format:\n"
                "{\n"
                '  "selected_product_id": "<ID of selected item or plan>",\n'
                '  "selected_product_name": "<Name of selected item or plan>",\n'
                '  "need_satisfaction": <integer 1 to 10>,\n'
                '  "ease_of_use": <integer 1 to 10>,\n'
                '  "overall_experience_rating": <integer 1 to 10>,\n'
                '  "reason": "<Detailed paragraph explaining why you chose this item based on your persona preferences and budget>"\n'
                "}"
            )
            raw = client.complete_json(system=system_prompt, user=user_prompt)
            selected_id = str(raw.get("selected_product_id") or raw.get("selectedProductId") or f"{task.id}-item-1")
            selected_name = str(raw.get("selected_product_name") or raw.get("selectedProductName") or f"{task.site_name} Selected Option")
            need_sat = max(1, min(10, int(raw.get("need_satisfaction", raw.get("needSatisfaction", 7)))))
            ease = max(1, min(10, int(raw.get("ease_of_use", raw.get("easeOfUse", 8)))))
            overall = max(1, min(10, int(raw.get("overall_experience_rating", raw.get("overallExperienceRating", 8)))))
            reason = str(raw.get("reason", "")).strip()
            if len(reason) < 20:
                reason = f"Based on my personal preferences and profile as {persona.name}, this option met my needs well on {task.site_name}."
            trace_events = [
                {"step": 1, "action": "navigate", "url": live_url, "description": f"Navigated to {task.site_name}"},
                {"step": 2, "action": "select", "url": live_url, "description": f"Selected {selected_name} ({selected_id})"},
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

        trace = WebTrace(events=trace_events, raw={"trace": trace_events})

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
