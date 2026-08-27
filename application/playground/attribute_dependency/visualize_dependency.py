"""Interactive HTML Visualizer for Survey Attribute Dependencies on Persona Taxonomy Tree."""

from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

from .constants import REPO_ROOT

DEFAULT_TAXONOMY_TREE = REPO_ROOT / "persona" / "schema" / "persona_taxonomy_tree.json"
DEFAULT_TASK_DEPENDENCIES = (
    REPO_ROOT
    / "application"
    / "tasks"
    / "survey_price-sensitivity-hasbro-gaming-candy-land"
    / "input"
    / "attribute_dependencies.json"
)


def load_json(path: Path) -> Dict[str, Any]:
    """Load JSON from path."""
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found at: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_visualization_html(
    taxonomy_tree: Dict[str, Any],
    dependencies_data: Dict[str, Any],
) -> str:
    """Generate self-contained HTML page containing the interactive D3 tree visualizer."""
    taxonomy_json_str = json.dumps(taxonomy_tree, ensure_ascii=False)
    deps_json_str = json.dumps(dependencies_data, ensure_ascii=False)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>MatrAIx Persona — Attribute Dependency Tree Visualizer</title>
  <!-- D3.js CDN -->
  <script src="https://d3js.org/d3.v7.min.js"></script>
  <style>
    :root {{
      --bg-primary: #0f172a;
      --bg-secondary: #1e293b;
      --bg-tertiary: #334155;
      --border-color: #475569;
      --text-primary: #f8fafc;
      --text-secondary: #94a3b8;
      --text-muted: #64748b;
      
      --accent-primary: #38bdf8;
      --accent-hover: #0ea5e9;
      --high-relevance: #10b981;
      --high-relevance-bg: rgba(16, 185, 129, 0.15);
      --high-relevance-border: #059669;
      
      --med-relevance: #f59e0b;
      --med-relevance-bg: rgba(245, 158, 11, 0.15);
      --med-relevance-border: #d97706;

      --l1-background: #3b82f6;
      --l1-psychology: #a855f7;
      --l1-behavior: #10b981;
      --l1-lifestyle: #f59e0b;
      --l1-social: #ec4899;
    }}

    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}

    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background-color: var(--bg-primary);
      color: var(--text-primary);
      height: 100vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }}

    /* Top Navigation Bar */
    header {{
      background-color: var(--bg-secondary);
      border-bottom: 1px solid var(--border-color);
      padding: 12px 24px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      z-index: 10;
      flex-shrink: 0;
    }}

    .header-left {{
      display: flex;
      align-items: center;
      gap: 16px;
    }}

    .logo-badge {{
      background: linear-gradient(135deg, #38bdf8, #818cf8);
      color: #0f172a;
      font-weight: 800;
      font-size: 13px;
      padding: 4px 10px;
      border-radius: 6px;
      letter-spacing: 0.5px;
    }}

    .header-title {{
      font-size: 17px;
      font-weight: 700;
      color: var(--text-primary);
    }}

    .header-subtitle {{
      font-size: 13px;
      color: var(--text-secondary);
    }}

    .header-actions {{
      display: flex;
      align-items: center;
      gap: 10px;
    }}

    .btn {{
      background-color: var(--bg-tertiary);
      color: var(--text-primary);
      border: 1px solid var(--border-color);
      padding: 6px 14px;
      border-radius: 6px;
      font-size: 13px;
      font-weight: 500;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.15s ease;
    }}

    .btn:hover {{
      background-color: var(--border-color);
      border-color: #64748b;
    }}

    .btn-primary {{
      background-color: #0284c7;
      border-color: #0369a1;
      color: #fff;
    }}

    .btn-primary:hover {{
      background-color: #0369a1;
    }}

    /* Main Container Layout */
    .app-body {{
      flex: 1;
      display: grid;
      grid-template-columns: 360px 1fr 340px;
      min-height: 0;
      overflow: hidden;
    }}

    /* Left Sidebar: Questions & Meta */
    .left-sidebar {{
      background-color: var(--bg-secondary);
      border-right: 1px solid var(--border-color);
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }}

    .sidebar-section-title {{
      padding: 14px 16px 8px;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.8px;
      color: var(--text-muted);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}

    .question-tabs {{
      flex: 1;
      overflow-y: auto;
      padding: 8px 12px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }}

    .question-tab-item {{
      background-color: rgba(51, 65, 85, 0.4);
      border: 1px solid transparent;
      border-radius: 8px;
      padding: 12px 14px;
      cursor: pointer;
      transition: all 0.2s ease;
      position: relative;
    }}

    .question-tab-item:hover {{
      background-color: rgba(51, 65, 85, 0.8);
      border-color: var(--border-color);
    }}

    .question-tab-item.active {{
      background-color: rgba(56, 189, 248, 0.12);
      border-color: #38bdf8;
      box-shadow: 0 0 12px rgba(56, 189, 248, 0.2);
    }}

    .tab-header-row {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 6px;
    }}

    .tab-id {{
      font-size: 12px;
      font-weight: 700;
      color: #38bdf8;
    }}

    .tab-badge {{
      font-size: 11px;
      font-weight: 600;
      padding: 2px 7px;
      border-radius: 12px;
      background-color: var(--bg-tertiary);
      color: var(--text-secondary);
    }}

    .question-tab-item.active .tab-badge {{
      background-color: #38bdf8;
      color: #0f172a;
    }}

    .tab-prompt {{
      font-size: 13px;
      color: var(--text-primary);
      line-height: 1.4;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }}

    /* Selected Question Detail Card */
    .question-info-card {{
      background-color: #0f172a;
      border-top: 1px solid var(--border-color);
      padding: 14px 16px;
      max-height: 250px;
      overflow-y: auto;
      font-size: 12px;
    }}

    .info-tag {{
      display: inline-block;
      padding: 2px 6px;
      border-radius: 4px;
      background: var(--bg-tertiary);
      color: var(--text-secondary);
      font-size: 11px;
      margin-right: 4px;
      margin-bottom: 4px;
    }}

    /* Center Visualizer Workspace */
    .canvas-container {{
      position: relative;
      background-color: var(--bg-primary);
      overflow: hidden;
      display: flex;
      flex-direction: column;
    }}

    .canvas-toolbar {{
      position: absolute;
      top: 16px;
      left: 16px;
      z-index: 5;
      background-color: rgba(30, 41, 59, 0.85);
      backdrop-filter: blur(8px);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 6px 10px;
      display: flex;
      align-items: center;
      gap: 12px;
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
    }}

    .view-toggle {{
      display: flex;
      background-color: var(--bg-primary);
      border-radius: 6px;
      padding: 2px;
      border: 1px solid var(--border-color);
    }}

    .toggle-btn {{
      padding: 4px 10px;
      font-size: 12px;
      font-weight: 500;
      color: var(--text-secondary);
      background: transparent;
      border: none;
      border-radius: 4px;
      cursor: pointer;
      transition: all 0.15s;
    }}

    .toggle-btn.active {{
      background-color: #38bdf8;
      color: #0f172a;
      font-weight: 700;
    }}

    .search-box {{
      position: relative;
      display: flex;
      align-items: center;
    }}

    .search-input {{
      background-color: var(--bg-primary);
      border: 1px solid var(--border-color);
      color: var(--text-primary);
      padding: 5px 10px 5px 28px;
      border-radius: 6px;
      font-size: 12px;
      width: 180px;
      outline: none;
      transition: width 0.2s;
    }}

    .search-input:focus {{
      border-color: #38bdf8;
      width: 240px;
    }}

    .search-icon {{
      position: absolute;
      left: 8px;
      width: 14px;
      height: 14px;
      color: var(--text-muted);
      pointer-events: none;
    }}

    .zoom-controls {{
      display: flex;
      gap: 4px;
    }}

    .btn-icon {{
      width: 28px;
      height: 28px;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 0;
    }}

    /* SVG Canvas */
    #tree-svg {{
      width: 100%;
      height: 100%;
      cursor: grab;
    }}

    #tree-svg:active {{
      cursor: grabbing;
    }}

    /* D3 Tree Node & Link Styling */
    .tree-link {{
      fill: none;
      stroke: #334155;
      stroke-width: 1.2px;
      transition: stroke 0.3s, stroke-width 0.3s, opacity 0.3s;
    }}

    .tree-link.active {{
      stroke: #38bdf8;
      stroke-width: 2.5px;
      opacity: 1 !important;
      filter: drop-shadow(0 0 4px rgba(56, 189, 248, 0.6));
    }}

    .tree-link.active-high {{
      stroke: #10b981;
      stroke-width: 2.8px;
      opacity: 1 !important;
      filter: drop-shadow(0 0 5px rgba(16, 185, 129, 0.7));
    }}

    .tree-link.active-med {{
      stroke: #f59e0b;
      stroke-width: 2.5px;
      opacity: 1 !important;
      filter: drop-shadow(0 0 4px rgba(245, 158, 11, 0.6));
    }}

    .tree-link.dimmed {{
      opacity: 0.15;
    }}

    .tree-node {{
      cursor: pointer;
    }}

    .tree-node circle {{
      fill: #1e293b;
      stroke: #64748b;
      stroke-width: 1.5px;
      transition: all 0.25s ease;
    }}

    .tree-node:hover circle {{
      stroke: #f8fafc;
      stroke-width: 2.5px;
    }}

    .tree-node.active-leaf circle {{
      stroke-width: 3px;
      r: 7px;
    }}

    .tree-node.active-high circle {{
      fill: #10b981;
      stroke: #ecfdf5;
      filter: drop-shadow(0 0 8px rgba(16, 185, 129, 0.9));
    }}

    .tree-node.active-med circle {{
      fill: #f59e0b;
      stroke: #fffbeb;
      filter: drop-shadow(0 0 8px rgba(245, 158, 11, 0.9));
    }}

    .tree-node.has-active-children circle {{
      stroke: #38bdf8;
      stroke-width: 2.5px;
    }}

    .tree-node.dimmed {{
      opacity: 0.25;
    }}

    .node-text {{
      font-size: 11px;
      fill: #cbd5e1;
      font-family: inherit;
      transition: fill 0.2s, font-weight 0.2s;
      pointer-events: none;
      text-shadow: 0 1px 3px rgba(0,0,0,0.8);
    }}

    .node-text.active {{
      fill: #ffffff;
      font-weight: 700;
      font-size: 12px;
    }}

    .node-count-badge {{
      font-size: 9px;
      fill: #38bdf8;
      font-weight: bold;
    }}

    /* Right Sidebar: Node Detail & Attributes Inspector */
    .right-sidebar {{
      background-color: var(--bg-secondary);
      border-left: 1px solid var(--border-color);
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }}

    .detail-panel-content {{
      flex: 1;
      overflow-y: auto;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }}

    .detail-header-card {{
      background-color: var(--bg-primary);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 14px;
    }}

    .detail-type-badge {{
      display: inline-block;
      font-size: 10px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      padding: 2px 8px;
      border-radius: 4px;
      margin-bottom: 8px;
    }}

    .badge-layer {{ background-color: #334155; color: #94a3b8; }}
    .badge-high {{ background-color: var(--high-relevance-bg); color: #34d399; border: 1px solid var(--high-relevance-border); }}
    .badge-med {{ background-color: var(--med-relevance-bg); color: #fbbf24; border: 1px solid var(--med-relevance-border); }}
    .badge-inactive {{ background-color: #334155; color: #94a3b8; }}

    .detail-title {{
      font-size: 16px;
      font-weight: 700;
      color: var(--text-primary);
      margin-bottom: 4px;
    }}

    .detail-path {{
      font-size: 11px;
      color: var(--text-secondary);
      line-height: 1.4;
      word-break: break-word;
    }}

    .reason-box {{
      background-color: rgba(56, 189, 248, 0.08);
      border-left: 3px solid #38bdf8;
      padding: 10px 12px;
      border-radius: 0 6px 6px 0;
      font-size: 12px;
      line-height: 1.5;
      color: #e2e8f0;
    }}

    .reason-box.high {{
      background-color: var(--high-relevance-bg);
      border-left-color: #10b981;
    }}

    .reason-box.med {{
      background-color: var(--med-relevance-bg);
      border-left-color: #f59e0b;
    }}

    .values-container {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 6px;
    }}

    .value-pill {{
      background-color: var(--bg-tertiary);
      border: 1px solid var(--border-color);
      color: #e2e8f0;
      font-size: 11px;
      padding: 3px 8px;
      border-radius: 12px;
    }}

    /* Attribute Quick Pick List */
    .active-attributes-list {{
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}

    .attr-chip-item {{
      background-color: var(--bg-primary);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      padding: 8px 10px;
      font-size: 12px;
      cursor: pointer;
      display: flex;
      justify-content: space-between;
      align-items: center;
      transition: all 0.15s;
    }}

    .attr-chip-item:hover {{
      border-color: #38bdf8;
      background-color: rgba(56, 189, 248, 0.08);
    }}

    .attr-chip-name {{
      font-weight: 600;
      color: var(--text-primary);
    }}

    /* Floating Tooltip */
    .tree-tooltip {{
      position: absolute;
      pointer-events: none;
      background-color: rgba(15, 23, 42, 0.95);
      border: 1px solid #38bdf8;
      border-radius: 8px;
      padding: 10px 14px;
      font-size: 12px;
      color: #f8fafc;
      box-shadow: 0 8px 24px rgba(0,0,0,0.5);
      backdrop-filter: blur(6px);
      z-index: 100;
      max-width: 320px;
      display: none;
      line-height: 1.4;
    }}

    /* Legend */
    .legend-box {{
      position: absolute;
      bottom: 16px;
      left: 16px;
      background-color: rgba(30, 41, 59, 0.85);
      backdrop-filter: blur(8px);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 8px 12px;
      display: flex;
      gap: 14px;
      font-size: 11px;
      color: var(--text-secondary);
      z-index: 5;
    }}

    .legend-item {{
      display: flex;
      align-items: center;
      gap: 6px;
    }}

    .legend-dot {{
      width: 10px;
      height: 10px;
      border-radius: 50%;
    }}
  </style>
</head>
<body>

  <!-- Top Header -->
  <header>
    <div class="header-left">
      <div class="logo-badge">MatrAIx</div>
      <div>
        <div class="header-title" id="survey-title-display">Attribute Dependency Tree Visualizer</div>
        <div class="header-subtitle" id="survey-task-display">Task: Loading...</div>
      </div>
    </div>
    <div class="header-actions">
      <button class="btn" id="btn-fit-tree" title="Fit tree to canvas">⛶ Fit Screen</button>
      <button class="btn" id="btn-expand-active" title="Expand active paths">🔍 Focus Active</button>
      <button class="btn" id="btn-expand-all" title="Expand entire tree">➕ Expand All</button>
      <button class="btn" id="btn-collapse-all" title="Collapse all">➖ Collapse All</button>
      <button class="btn btn-primary" id="btn-load-json" onclick="document.getElementById('file-input').click()">📁 Load JSON</button>
      <input type="file" id="file-input" style="display:none" accept=".json" onchange="handleFileUpload(event)">
    </div>
  </header>

  <!-- Main Grid Layout -->
  <div class="app-body">
    
    <!-- Left Column: Survey Questions -->
    <div class="left-sidebar">
      <div class="sidebar-section-title">
        <span>Survey Questions</span>
        <span id="question-count-badge" class="info-tag">0 Questions</span>
      </div>
      
      <div class="question-tabs" id="question-tabs-container">
        <!-- Injected via JavaScript -->
      </div>

      <div class="question-info-card" id="selected-question-card">
        <div style="font-weight: 700; color: #38bdf8; margin-bottom: 4px;">Selected Question Info</div>
        <div id="q-detail-prompt" style="color: #f1f5f9; margin-bottom: 8px; line-height: 1.4;">Select a question above to inspect dependencies.</div>
        <div id="q-detail-tags"></div>
      </div>
    </div>

    <!-- Center Column: Interactive Tree Canvas -->
    <div class="canvas-container" id="canvas-wrapper">
      
      <!-- Floating Canvas Toolbar -->
      <div class="canvas-toolbar">
        <div class="view-toggle">
          <button class="toggle-btn active" id="btn-mode-pruned" onclick="setViewMode('pruned')">Active Focus</button>
          <button class="toggle-btn" id="btn-mode-full" onclick="setViewMode('full')">Full Tree</button>
        </div>

        <div class="search-box">
          <svg class="search-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>
          </svg>
          <input type="text" class="search-input" id="search-input" placeholder="Search attribute or group..." oninput="handleSearch(this.value)">
        </div>

        <div class="zoom-controls">
          <button class="btn btn-icon" onclick="zoomIn()" title="Zoom In">+</button>
          <button class="btn btn-icon" onclick="zoomOut()" title="Zoom Out">-</button>
          <button class="btn btn-icon" onclick="resetZoom()" title="Reset Zoom">↺</button>
        </div>
      </div>

      <!-- Main SVG Canvas -->
      <svg id="tree-svg">
        <g id="tree-root-group"></g>
      </svg>

      <!-- Bottom Canvas Legend -->
      <div class="legend-box">
        <div class="legend-item">
          <span class="legend-dot" style="background-color: var(--high-relevance); box-shadow: 0 0 6px var(--high-relevance);"></span>
          <span>High Relevance</span>
        </div>
        <div class="legend-item">
          <span class="legend-dot" style="background-color: var(--med-relevance); box-shadow: 0 0 6px var(--med-relevance);"></span>
          <span>Medium Relevance</span>
        </div>
        <div class="legend-item">
          <span class="legend-dot" style="background-color: #64748b;"></span>
          <span>Inactive Dimension</span>
        </div>
        <div class="legend-item">
          <span class="legend-dot" style="background-color: #38bdf8;"></span>
          <span>Parent Group with Active Children</span>
        </div>
      </div>

      <!-- Floating Tooltip -->
      <div class="tree-tooltip" id="tooltip"></div>
    </div>

    <!-- Right Column: Detail & Attribute Inspector -->
    <div class="right-sidebar">
      <div class="sidebar-section-title">
        <span id="detail-panel-title">Attribute Inspector</span>
        <span id="active-count-badge" class="info-tag">0 Active</span>
      </div>

      <div class="detail-panel-content" id="detail-content-area">
        
        <!-- Active Node Detail Card -->
        <div class="detail-header-card" id="node-inspector-card">
          <div id="inspect-type-badge" class="detail-type-badge badge-layer">Root Node</div>
          <div class="detail-title" id="inspect-title">Persona Taxonomy Root</div>
          <div class="detail-path" id="inspect-path">Hover or click on any node to view details</div>
        </div>

        <!-- Reasoning Box (for active attributes) -->
        <div id="inspect-reason-section" style="display: none;">
          <div style="font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; margin-bottom: 6px;">Why This Matters (Causal Reasoning)</div>
          <div class="reason-box" id="inspect-reason-text">...</div>
        </div>

        <!-- Values Box (for leaf attributes) -->
        <div id="inspect-values-section" style="display: none;">
          <div style="font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; margin-bottom: 4px;">Possible Persona Values (<span id="inspect-values-count">0</span>)</div>
          <div class="values-container" id="inspect-values-list"></div>
        </div>

        <!-- Active Attributes List for current question -->
        <div style="margin-top: 8px;">
          <div style="font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; margin-bottom: 8px;">Dependent Attributes for Current View</div>
          <div class="active-attributes-list" id="active-attributes-chips">
            <!-- Injected via JavaScript -->
          </div>
        </div>

      </div>
    </div>

  </div>

  <!-- Embedded Data & Interactive D3 Visualization Logic -->
  <script>
    // 1. Injected Data
    let taxonomyData = {taxonomy_json_str};
    let dependencyData = {deps_json_str};

    // State variables
    let currentSelectedQuestionId = "ALL"; // "ALL" or question_id
    let viewMode = "pruned"; // "pruned" or "full"
    let currentActiveAttrMap = new Map(); // attribute_id -> depObj
    let activePathNodeIds = new Set(); // Set of node ids on active path
    let rootNodeD3 = null;
    let svg, gRoot, treeLayout, zoomBehavior;
    let nodeWidth = 260;
    let nodeHeight = 34;

    // Initialize UI on Load
    window.addEventListener("DOMContentLoaded", () => {{
      initHeader();
      initQuestionTabs();
      initD3Tree();
      selectQuestion("ALL");
    }});

    function initHeader() {{
      if (dependencyData) {{
        document.getElementById("survey-title-display").textContent = dependencyData.survey_title || "Survey Attribute Dependencies";
        document.getElementById("survey-task-display").textContent = `Task: ${{dependencyData.task_name || 'N/A'}} | Total Questions: ${{dependencyData.total_questions || 0}} | Total Unique Traits: ${{dependencyData.total_unique_attributes || 0}}`;
      }}
    }}

    function initQuestionTabs() {{
      const container = document.getElementById("question-tabs-container");
      container.innerHTML = "";

      const questions = dependencyData.questions || [];
      document.getElementById("question-count-badge").textContent = `${{questions.length}} Questions`;

      // 1. Overview Tab
      const allTab = document.createElement("div");
      allTab.className = "question-tab-item active";
      allTab.id = "tab-ALL";
      allTab.onclick = () => selectQuestion("ALL");
      allTab.innerHTML = `
        <div class="tab-header-row">
          <span class="tab-id">🌐 GLOBAL OVERVIEW</span>
          <span class="tab-badge">${{dependencyData.total_unique_attributes || 0}} attrs</span>
        </div>
        <div class="tab-prompt">All unique attributes across all survey questions aggregated.</div>
      `;
      container.appendChild(allTab);

      // 2. Individual Question Tabs
      questions.forEach((q, idx) => {{
        const tab = document.createElement("div");
        tab.className = "question-tab-item";
        tab.id = `tab-${{q.question_id}}`;
        tab.onclick = () => selectQuestion(q.question_id);
        
        const depCount = q.dependencies ? q.dependencies.length : 0;
        tab.innerHTML = `
          <div class="tab-header-row">
            <span class="tab-id">[Q${{idx + 1}}] ${{q.question_id}}</span>
            <span class="tab-badge">${{depCount}} attrs</span>
          </div>
          <div class="tab-prompt">${{q.prompt}}</div>
        `;
        container.appendChild(tab);
      }});
    }}

    function selectQuestion(questionId) {{
      currentSelectedQuestionId = questionId;

      // Update Tab Styles
      document.querySelectorAll(".question-tab-item").forEach(el => el.classList.remove("active"));
      const activeTab = document.getElementById(`tab-${{questionId}}`);
      if (activeTab) activeTab.classList.add("active");

      // Compute active attribute map
      currentActiveAttrMap.clear();
      activePathNodeIds.clear();

      if (questionId === "ALL") {{
        // Aggregated mode: collect all dependencies across questions
        const questions = dependencyData.questions || [];
        questions.forEach(q => {{
          (q.dependencies || []).forEach(dep => {{
            if (!currentActiveAttrMap.has(dep.attribute_id)) {{
              currentActiveAttrMap.set(dep.attribute_id, dep);
            }}
          }});
        }});

        document.getElementById("q-detail-prompt").textContent = dependencyData.survey_description || dependencyData.survey_title;
        document.getElementById("q-detail-tags").innerHTML = `
          <span class="info-tag">Overview Mode</span>
          <span class="info-tag">${{currentActiveAttrMap.size}} Unique Persona Attributes</span>
        `;
      }} else {{
        // Specific Question mode
        const qObj = (dependencyData.questions || []).find(q => q.question_id === questionId);
        if (qObj) {{
          (qObj.dependencies || []).forEach(dep => {{
            currentActiveAttrMap.set(dep.attribute_id, dep);
          }});

          document.getElementById("q-detail-prompt").textContent = qObj.prompt;
          document.getElementById("q-detail-tags").innerHTML = `
            <span class="info-tag">ID: ${{qObj.question_id}}</span>
            <span class="info-tag">Construct: ${{qObj.construct || 'N/A'}}</span>
            <span class="info-tag">Type: ${{qObj.type || 'N/A'}}</span>
            <span class="info-tag">${{currentActiveAttrMap.size}} Dependencies</span>
          `;
        }}
      }}

      // Compute path from root to all active leaves
      markActivePaths(rootNodeD3);

      // Update right sidebar active chips
      renderActiveAttributesChips();

      // Expand/Collapse tree to focus on active nodes
      if (viewMode === "pruned") {{
        expandActivePathsOnly(rootNodeD3);
      }}

      updateTreeVisualization();
      resetZoom();
    }}

    function markActivePaths(d3Node) {{
      if (!d3Node) return false;

      let hasActive = false;
      if (d3Node.data.node_type === "dimension" || !d3Node.data.children || d3Node.data.children.length === 0) {{
        if (currentActiveAttrMap.has(d3Node.data.id)) {{
          hasActive = true;
          activePathNodeIds.add(d3Node.data.id);
        }}
      }}

      // Recurse on all original children
      const allChildren = d3Node.children || d3Node._children || [];
      allChildren.forEach(child => {{
        if (markActivePaths(child)) {{
          hasActive = true;
        }}
      }});

      if (hasActive) {{
        activePathNodeIds.add(d3Node.data.id);
      }}

      d3Node._hasActiveDescendant = hasActive;
      return hasActive;
    }}

    function expandActivePathsOnly(d3Node) {{
      if (!d3Node) return;

      if (d3Node._hasActiveDescendant) {{
        if (d3Node._children) {{
          d3Node.children = d3Node._children;
          d3Node._children = null;
        }}
      }} else {{
        if (d3Node.children && d3Node.depth > 1) {{
          d3Node._children = d3Node.children;
          d3Node.children = null;
        }}
      }}

      const children = d3Node.children || [];
      children.forEach(child => expandActivePathsOnly(child));
    }}

    function initD3Tree() {{
      const wrapper = document.getElementById("canvas-wrapper");
      svg = d3.select("#tree-svg");
      gRoot = d3.select("#tree-root-group");

      zoomBehavior = d3.zoom()
        .scaleExtent([0.15, 3.0])
        .on("zoom", (event) => {{
          gRoot.attr("transform", event.transform);
        }});

      svg.call(zoomBehavior).on("dblclick.zoom", null);

      // Build hierarchy
      rootNodeD3 = d3.hierarchy(taxonomyData, d => d.children);
      rootNodeD3.x0 = wrapper.clientHeight / 2;
      rootNodeD3.y0 = 60;

      // Collapse non-essential nodes by default
      function collapseAll(d) {{
        if (d.children) {{
          d._children = d.children;
          d._children.forEach(collapseAll);
          d.children = null;
        }}
      }}
      if (rootNodeD3.children) {{
        rootNodeD3.children.forEach(collapseAll);
      }}

      // Event listeners for top controls
      document.getElementById("btn-fit-tree").onclick = resetZoom;
      document.getElementById("btn-expand-active").onclick = () => {{
        expandActivePathsOnly(rootNodeD3);
        updateTreeVisualization();
        resetZoom();
      }};
      document.getElementById("btn-expand-all").onclick = () => {{
        function expand(d) {{
          if (d._children) {{
            d.children = d._children;
            d._children = null;
          }}
          if (d.children) d.children.forEach(expand);
        }}
        expand(rootNodeD3);
        updateTreeVisualization();
        resetZoom();
      }};
      document.getElementById("btn-collapse-all").onclick = () => {{
        function collapse(d) {{
          if (d.children && d.depth > 0) {{
            d._children = d.children;
            d.children = null;
          }}
          if (d._children) d._children.forEach(collapse);
        }}
        collapse(rootNodeD3);
        updateTreeVisualization();
        resetZoom();
      }};
    }}

    function updateTreeVisualization() {{
      const treeLayout = d3.tree().nodeSize([nodeHeight, nodeWidth]);
      const treeData = treeLayout(rootNodeD3);

      const nodes = treeData.descendants();
      const links = treeData.links();

      // Normalize depth spacing
      nodes.forEach(d => {{
        d.y = d.depth * 280 + 80;
      }});

      // -------------------------------------------------------------
      // 1. Render Links
      // -------------------------------------------------------------
      const linkSelection = gRoot.selectAll(".tree-link")
        .data(links, d => d.target.data.id);

      const linkEnter = linkSelection.enter()
        .append("path")
        .attr("class", "tree-link")
        .attr("d", d => {{
          const o = {{ x: rootNodeD3.x0, y: rootNodeD3.y0 }};
          return diagonal(o, o);
        }});

      const linkUpdate = linkEnter.merge(linkSelection);

      linkUpdate.transition().duration(350)
        .attr("d", d => diagonal(d.source, d.target))
        .attr("class", d => {{
          const isTargetActive = activePathNodeIds.has(d.target.data.id);
          if (isTargetActive) {{
            const dep = currentActiveAttrMap.get(d.target.data.id);
            if (dep && dep.relevance === "high") return "tree-link active-high";
            if (dep && dep.relevance === "medium") return "tree-link active-med";
            return "tree-link active";
          }}
          return viewMode === "pruned" && !isTargetActive ? "tree-link dimmed" : "tree-link";
        }});

      linkSelection.exit().transition().duration(250)
        .attr("d", d => {{
          const o = {{ x: rootNodeD3.x0, y: rootNodeD3.y0 }};
          return diagonal(o, o);
        }})
        .remove();

      // -------------------------------------------------------------
      // 2. Render Nodes
      // -------------------------------------------------------------
      const nodeSelection = gRoot.selectAll(".tree-node")
        .data(nodes, d => d.data.id);

      const nodeEnter = nodeSelection.enter()
        .append("g")
        .attr("class", "tree-node")
        .attr("transform", d => `translate(${{rootNodeD3.y0}},${{rootNodeD3.x0}})`)
        .on("click", (event, d) => {{
          // Toggle children on click
          if (d.children) {{
            d._children = d.children;
            d.children = null;
          }} else if (d._children) {{
            d.children = d._children;
            d._children = null;
          }}
          inspectNode(d);
          updateTreeVisualization();
        }})
        .on("mouseenter", (event, d) => {{
          inspectNode(d);
          showTooltip(event, d);
        }})
        .on("mouseleave", hideTooltip);

      // Node Circle
      nodeEnter.append("circle")
        .attr("r", d => d.depth === 0 ? 9 : (d.data.node_type === "dimension" ? 5 : 7));

      // Node Label
      nodeEnter.append("text")
        .attr("class", "node-text")
        .attr("dy", "0.32em")
        .attr("x", d => d.children || d._children ? -12 : 12)
        .attr("text-anchor", d => d.children || d._children ? "end" : "start")
        .text(d => d.data.label || d.data.id);

      // Node count badge for non-leaf
      nodeEnter.append("text")
        .attr("class", "node-count-badge")
        .attr("dy", "-0.7em")
        .attr("text-anchor", "middle")
        .text("");

      // Merge & Update
      const nodeUpdate = nodeEnter.merge(nodeSelection);

      nodeUpdate.transition().duration(350)
        .attr("transform", d => `translate(${{d.y}},${{d.x}})`)
        .attr("class", d => {{
          let cls = "tree-node";
          const isLeaf = d.data.node_type === "dimension" || (!d.children && !d._children);
          const isDep = currentActiveAttrMap.has(d.data.id);

          if (isDep) {{
            const dep = currentActiveAttrMap.get(d.data.id);
            cls += " active-leaf";
            cls += dep.relevance === "high" ? " active-high" : " active-med";
          }} else if (d._hasActiveDescendant) {{
            cls += " has-active-children";
          }} else if (viewMode === "pruned" && !activePathNodeIds.has(d.data.id)) {{
            cls += " dimmed";
          }}
          return cls;
        }});

      nodeUpdate.select("circle")
        .attr("r", d => {{
          if (currentActiveAttrMap.has(d.data.id)) return 8;
          if (d.depth === 0) return 9;
          if (d.data.node_type === "layer_1") return 8;
          return d.data.node_type === "dimension" ? 5 : 6.5;
        }})
        .style("fill", d => {{
          if (d.depth === 0) return "#38bdf8";
          if (currentActiveAttrMap.has(d.data.id)) {{
            const dep = currentActiveAttrMap.get(d.data.id);
            return dep.relevance === "high" ? "#10b981" : "#f59e0b";
          }}
          if (d._children) return "#475569"; // collapsed indicator
          return "#1e293b";
        }});

      nodeUpdate.select(".node-text")
        .attr("x", d => d.children || d._children ? -12 : 12)
        .attr("text-anchor", d => d.children || d._children ? "end" : "start")
        .attr("class", d => {{
          const isDep = currentActiveAttrMap.has(d.data.id);
          return isDep ? "node-text active" : "node-text";
        }})
        .text(d => {{
          let label = d.data.label || d.data.id;
          if (d._children && d._children.length > 0) {{
            label += ` (${{d._children.length}})`;
          }}
          return label;
        }});

      nodeSelection.exit().transition().duration(250)
        .attr("transform", d => `translate(${{rootNodeD3.y0}},${{rootNodeD3.x0}})`)
        .remove();

      // Cache positions for animations
      nodes.forEach(d => {{
        d.x0 = d.x;
        d.y0 = d.y;
      }});
    }}

    // Curved Bezier Link Path Generator
    function diagonal(s, d) {{
      return `M ${{s.y}} ${{s.x}}
              C ${{(s.y + d.y) / 2}} ${{s.x}},
                ${{(s.y + d.y) / 2}} ${{d.x}},
                ${{d.y}} ${{d.x}}`;
    }}

    // Inspector details
    function inspectNode(d) {{
      const data = d.data;
      const isLeaf = data.node_type === "dimension" || (!data.children && !data._children);
      const isDep = currentActiveAttrMap.has(data.id);
      const dep = currentActiveAttrMap.get(data.id);

      const typeBadge = document.getElementById("inspect-type-badge");
      const title = document.getElementById("inspect-title");
      const pathEl = document.getElementById("inspect-path");
      const reasonSec = document.getElementById("inspect-reason-section");
      const reasonText = document.getElementById("inspect-reason-text");
      const valuesSec = document.getElementById("inspect-values-section");
      const valuesList = document.getElementById("inspect-values-list");
      const valuesCount = document.getElementById("inspect-values-count");

      title.textContent = data.label || data.id;

      // Compute full ancestral path
      let ancestors = [];
      let curr = d;
      while (curr) {{
        ancestors.unshift(curr.data.label || curr.data.id);
        curr = curr.parent;
      }}
      pathEl.textContent = ancestors.join(" > ");

      if (isDep) {{
        typeBadge.textContent = `${{dep.relevance.toUpperCase()}} RELEVANCE ATTRIBUTE`;
        typeBadge.className = dep.relevance === "high" ? "detail-type-badge badge-high" : "detail-type-badge badge-med";
        
        reasonSec.style.display = "block";
        reasonText.textContent = dep.reason || "Influences question outcome.";
        reasonText.className = dep.relevance === "high" ? "reason-box high" : "reason-box med";
      }} else {{
        typeBadge.textContent = data.node_type ? data.node_type.toUpperCase() : "TAXONOMY NODE";
        typeBadge.className = "detail-type-badge badge-layer";
        reasonSec.style.display = "none";
      }}

      // Values display
      const vals = data.values || (dep ? dep.values : []);
      if (vals && vals.length > 0) {{
        valuesSec.style.display = "block";
        valuesCount.textContent = vals.length;
        valuesList.innerHTML = vals.map(v => `<span class="value-pill">${{v}}</span>`).join("");
      }} else {{
        valuesSec.style.display = "none";
      }}
    }}

    // Tooltip
    function showTooltip(event, d) {{
      const tooltip = document.getElementById("tooltip");
      const wrapper = document.getElementById("canvas-wrapper");
      const wrapperRect = wrapper.getBoundingClientRect();
      const targetEl = event.currentTarget;
      const nodeRect = targetEl.getBoundingClientRect();

      const data = d.data;
      const isDep = currentActiveAttrMap.has(data.id);
      const dep = currentActiveAttrMap.get(data.id);

      let html = `<div style="font-weight:700; color:#38bdf8; font-size:13px; margin-bottom:4px;">${{data.label || data.id}}</div>`;
      if (data.category) {{
        html += `<div style="color:#94a3b8; font-size:11px; margin-bottom:6px;">Category: ${{data.category}}</div>`;
      }}

      if (isDep) {{
        const relColor = dep.relevance === "high" ? "#10b981" : "#f59e0b";
        html += `<div style="color:${{relColor}}; font-weight:700; margin-bottom:4px;">● ${{dep.relevance.toUpperCase()}} RELEVANCE</div>`;
        html += `<div style="font-size:11px; color:#e2e8f0; line-height:1.4; border-top:1px solid #334155; padding-top:6px; margin-top:4px;">${{dep.reason}}</div>`;
      }}

      const vals = data.values || (dep ? dep.values : []);
      if (vals && vals.length > 0) {{
        html += `<div style="margin-top:6px; font-size:11px; color:#94a3b8;"><strong>Values (${{vals.length}}):</strong> ${{vals.slice(0, 5).join(", ")}}${{vals.length > 5 ? '...' : ''}}</div>`;
      }}

      tooltip.innerHTML = html;
      tooltip.style.display = "block";

      // Position tooltip right next to the node (adjacent horizontally)
      const tooltipWidth = 320;
      let left = (nodeRect.right - wrapperRect.left) + 12;
      let top = (nodeRect.top - wrapperRect.top) - 10;

      // If tooltip exceeds right edge of canvas, show on the left of node
      if (left + tooltipWidth > wrapperRect.width - 20) {{
        left = (nodeRect.left - wrapperRect.left) - tooltipWidth - 12;
      }}

      // Keep tooltip within vertical canvas boundaries
      if (top < 10) top = 10;
      if (top + 160 > wrapperRect.height) {{
        top = Math.max(10, wrapperRect.height - 180);
      }}

      tooltip.style.left = `${{Math.max(10, Math.round(left))}}px`;
      tooltip.style.top = `${{Math.max(10, Math.round(top))}}px`;
    }}

    function hideTooltip() {{
      document.getElementById("tooltip").style.display = "none";
    }}

    // Right Sidebar Active Attribute Chips
    function renderActiveAttributesChips() {{
      const container = document.getElementById("active-attributes-chips");
      const badge = document.getElementById("active-count-badge");
      container.innerHTML = "";

      const entries = Array.from(currentActiveAttrMap.entries());
      badge.textContent = `${{entries.length}} Active`;

      if (entries.length === 0) {{
        container.innerHTML = `<div style="color: var(--text-muted); font-size: 12px; font-style: italic;">No attributes selected for this question.</div>`;
        return;
      }}

      entries.forEach(([attrId, dep]) => {{
        const item = document.createElement("div");
        item.className = "attr-chip-item";
        item.onclick = () => focusOnAttributeId(attrId);

        const relBadgeColor = dep.relevance === "high" ? "var(--high-relevance)" : "var(--med-relevance)";
        item.innerHTML = `
          <div>
            <div class="attr-chip-name">${{dep.attribute_label || attrId}}</div>
            <div style="font-size: 10px; color: var(--text-muted);">${{dep.category || 'Dimension'}}</div>
          </div>
          <span style="color: ${{relBadgeColor}}; font-weight: 700; font-size: 10px;">${{dep.relevance.toUpperCase()}}</span>
        `;
        container.appendChild(item);
      }});
    }}

    // Focus on specific attribute
    function focusOnAttributeId(attrId) {{
      function findAndExpand(d) {{
        if (d.data.id === attrId) return true;
        let found = false;
        const all = d.children || d._children || [];
        all.forEach(c => {{
          if (findAndExpand(c)) {{
            found = true;
          }}
        }});
        if (found && d._children) {{
          d.children = d._children;
          d._children = null;
        }}
        return found;
      }}

      findAndExpand(rootNodeD3);
      updateTreeVisualization();

      // Find the D3 node and zoom to it
      const target = rootNodeD3.descendants().find(d => d.data.id === attrId);
      if (target) {{
        inspectNode(target);
        const wrapper = document.getElementById("canvas-wrapper");
        const scale = 1.2;
        const x = -target.y * scale + wrapper.clientWidth / 2;
        const y = -target.x * scale + wrapper.clientHeight / 2;

        svg.transition().duration(600).call(
          zoomBehavior.transform,
          d3.zoomIdentity.translate(x, y).scale(scale)
        );
      }}
    }}

    // Search Box Handler
    function handleSearch(query) {{
      query = (query || "").trim().toLowerCase();
      if (!query) {{
        updateTreeVisualization();
        return;
      }}

      // Expand nodes matching search
      function searchExpand(d) {{
        const label = (d.data.label || "").toLowerCase();
        const id = (d.data.id || "").toLowerCase();
        let match = label.includes(query) || id.includes(query);

        const all = d.children || d._children || [];
        all.forEach(c => {{
          if (searchExpand(c)) match = true;
        }});

        if (match && d._children) {{
          d.children = d._children;
          d._children = null;
        }}
        return match;
      }}

      searchExpand(rootNodeD3);
      updateTreeVisualization();
    }}

    // View Mode Toggle
    function setViewMode(mode) {{
      viewMode = mode;
      document.getElementById("btn-mode-pruned").classList.toggle("active", mode === "pruned");
      document.getElementById("btn-mode-full").classList.toggle("active", mode === "full");
      
      if (mode === "pruned") {{
        expandActivePathsOnly(rootNodeD3);
      }}
      updateTreeVisualization();
      resetZoom();
    }}

    // Zoom Controls
    function zoomIn() {{
      svg.transition().duration(250).call(zoomBehavior.scaleBy, 1.3);
    }}

    function zoomOut() {{
      svg.transition().duration(250).call(zoomBehavior.scaleBy, 0.77);
    }}

    function resetZoom() {{
      const wrapper = document.getElementById("canvas-wrapper");
      const bounds = gRoot.node().getBBox();
      if (!bounds || bounds.width === 0 || bounds.height === 0) return;

      const fullWidth = wrapper.clientWidth;
      const fullHeight = wrapper.clientHeight;
      const width = bounds.width;
      const height = bounds.height;
      const midX = bounds.x + width / 2;
      const midY = bounds.y + height / 2;

      const scale = Math.min(fullWidth / (width + 120), fullHeight / (height + 120), 1.0);
      const translate = [fullWidth / 2 - scale * midX, fullHeight / 2 - scale * midY];

      svg.transition().duration(500).call(
        zoomBehavior.transform,
        d3.zoomIdentity.translate(translate[0], translate[1]).scale(scale)
      );
    }}

    // File Upload Handler (for dragging/dropping other task JSONs)
    function handleFileUpload(event) {{
      const file = event.target.files[0];
      if (!file) return;

      const reader = new FileReader();
      reader.onload = (e) => {{
        try {{
          const uploadedData = JSON.parse(e.target.result);
          if (uploadedData.questions || uploadedData.unique_attributes) {{
            dependencyData = uploadedData;
            initHeader();
            initQuestionTabs();
            selectQuestion("ALL");
          }} else {{
            alert("Uploaded file does not appear to be a valid attribute_dependencies.json file.");
          }}
        }} catch (err) {{
          alert("Error parsing JSON: " + err.message);
        }}
      }};
      reader.readAsText(file);
    }}
  </script>
</body>
</html>
"""
    return html_content


def generate_visualizer_file(
    dependencies_path: Path,
    taxonomy_path: Path = DEFAULT_TAXONOMY_TREE,
    output_path: Optional[Path] = None,
    open_browser: bool = False,
) -> Path:
    """Generate interactive visualizer HTML file."""
    deps_data = load_json(dependencies_path)
    taxonomy_data = load_json(taxonomy_path)

    if output_path is None:
        # Default output next to attribute_dependencies.json
        output_path = dependencies_path.parent / "attribute_dependencies_visualizer.html"

    html_content = build_visualization_html(taxonomy_data, deps_data)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"[Visualizer] HTML Dashboard created successfully:\n  -> {output_path}")

    if open_browser:
        webbrowser.open(output_path.as_uri())

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Generate interactive HTML visualization for survey attribute dependencies."
    )
    parser.add_argument(
        "dependencies",
        nargs="?",
        default=str(DEFAULT_TASK_DEPENDENCIES),
        help=f"Path to attribute_dependencies.json (default: {DEFAULT_TASK_DEPENDENCIES})",
    )
    parser.add_argument(
        "--taxonomy",
        default=str(DEFAULT_TAXONOMY_TREE),
        help=f"Path to persona_taxonomy_tree.json (default: {DEFAULT_TAXONOMY_TREE})",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Custom output HTML file path.",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Automatically open the generated HTML in default browser.",
    )

    args = parser.parse_args()
    deps_path = Path(args.dependencies).resolve()
    tax_path = Path(args.taxonomy).resolve()
    out_path = Path(args.output).resolve() if args.output else None

    generate_visualizer_file(
        dependencies_path=deps_path,
        taxonomy_path=tax_path,
        output_path=out_path,
        open_browser=args.open,
    )


if __name__ == "__main__":
    main()

