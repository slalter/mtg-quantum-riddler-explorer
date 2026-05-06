(function () {
  cytoscape.use(cytoscapeDagre);

  const ROLE_LABEL = {
    ld: "Land destruction",
    removal: "Removal / burn",
    counter: "Counterspells",
    blink: "Blink (combo glue)",
    finisher: "Finisher",
    engine: "Card-advantage engine",
    lock: "Mana lock",
    mana: "Mana fixing",
    land: "Lands",
    hate: "Sideboard hate",
  };
  const ROLE_COLOR = {
    ld: "#d68352",
    removal: "#e07b5b",
    counter: "#6da7d8",
    blink: "#f5e9c8",
    finisher: "#c4a3e4",
    engine: "#79b483",
    lock: "#8c7ba0",
    mana: "#b9b3c4",
    land: "#8a7a5d",
    hate: "#d4a843",
  };

  let cy = null;
  let activeDeckId = null;
  const hiddenRoles = new Set(["land"]); // hide lands from graph by default

  // --- Tabs ---
  const tabs = document.getElementById("variant-tabs");
  Object.values(DECKS).forEach((d) => {
    const btn = document.createElement("button");
    btn.className = "tab" + (d.isReference ? " tab-ref" : "");
    btn.dataset.id = d.id;
    const refBadge = d.isReference ? '<span class="ref-badge">REFERENCE</span>' : "";
    btn.innerHTML = `<span class="name">${refBadge}${d.name}</span><span class="sub">${d.subtitle}</span>`;
    btn.addEventListener("click", () => loadDeck(d.id));
    tabs.appendChild(btn);
  });

  // --- Render deck ---
  function loadDeck(id) {
    activeDeckId = id;
    const deck = DECKS[id];
    document.querySelectorAll(".tab").forEach((t) =>
      t.classList.toggle("active", t.dataset.id === id)
    );

    document.getElementById("deck-title").textContent = deck.name;
    document.getElementById("deck-subtitle").textContent = deck.subtitle;
    document.getElementById("deck-colors").textContent = `Colors: ${deck.colors}`;
    document.getElementById("deck-arch").textContent = deck.archetype;

    const mainCount = deck.mainboard.reduce((s, [, q]) => s + q, 0);
    const sideCount = deck.sideboard.reduce((s, [, q]) => s + q, 0);
    document.getElementById("deck-count").textContent = `${mainCount} + ${sideCount}`;
    document.getElementById("main-count").textContent = `(${mainCount})`;
    document.getElementById("side-count").textContent = `(${sideCount})`;

    renderCardList("mainboard-list", deck.mainboard);
    renderCardList("sideboard-list", deck.sideboard);

    document.getElementById("pitch").textContent = deck.pitch;
    const gp = document.getElementById("gameplan");
    gp.innerHTML = "";
    deck.gameplan.forEach((step) => {
      const li = document.createElement("li");
      li.textContent = step;
      gp.appendChild(li);
    });

    const combo = document.getElementById("combo");
    combo.innerHTML = `<div class="name">${deck.keyCombo.name}</div><div class="desc">${deck.keyCombo.desc}</div><div class="cards">${deck.keyCombo.cards.join(" + ")}</div>`;

    renderCurve(deck.mainboard);
    renderStats(id);
    renderGraph(deck);
    hideCardDetail();
  }

  // Conditional metrics: P(can cast | card in hand at target turn).
  // The miss rate (1 - P) is the "dead card in hand" risk.
  const STAT_METRICS = [
    ["erode_T1",         "Cast Erode T1 ({W})"],
    ["path_T1",          "Cast Path to Exile T1 ({W})"],
    ["galvanic_T1",      "Cast Galvanic Discharge T1 ({R})"],
    ["phantom_T2",       "Cast Phantom T2 ({W}{W})"],
    ["phantom_T3",       "Cast Phantom T3 ({W}{W})"],
    ["phelia_T2",        "Cast Phelia T2 ({1}{W}) — flash"],
    ["phelia_T3",        "Cast Phelia T3 ({1}{W})"],
    ["wildfire_T2",      "Cast Cleansing Wildfire T2"],
    ["pof_T2",           "Cast Price of Freedom T2"],
    ["phlage_T3_removal","Phlage T3 as removal — Helix-eq + yard"],
    ["warp_qr_T2",       "Warp QR T2 ({1}{U})"],
    ["warp_qr_T3",       "Warp QR T3 ({1}{U})"],
    ["hardcast_qr_T5",   "Hardcast QR T5 ({3}{U}{U})"],
    ["hardcast_qr_T6",   "Hardcast QR T6 ({3}{U}{U})"],
    ["wos_T4",           "Cast Wrath of the Skies T4"],
    ["roku_T4",          "Cast The Legend of Roku T4"],
    ["phlage_escape_T6", "Escape Phlage T6 (yard ≥ 5 + RRWW)"],
    ["phlage_escape_T7", "Escape Phlage T7"],
  ];

  const MISC_METRICS = [
    ["keep_open_2to4_lands_pct",      "Keep opening 7 (2-4 lands)",       "good_high"],
    ["mana_for_phlage_escape_T5_pct", "Phlage escape mana T5 ({R}{R}{W}{W})", "good_mid"],
    ["mana_for_phlage_escape_T6_pct", "Phlage escape mana T6 ({R}{R}{W}{W})", "good_mid"],
    ["qr_flood_2plus_pct",            "Risk: ≥2 QR in hand at once",      "flood"],
  ];

  function renderStats(deckId) {
    const el = document.getElementById("stats");
    el.innerHTML = "";
    const stats = (typeof STATS !== "undefined") ? STATS[deckId] : null;
    if (!stats) {
      el.innerHTML = '<div class="muted" style="font-size:11px;padding:4px 0">No simulation data.</div>';
      return;
    }

    // === Compare table FIRST (top-priority view) ===
    const compareHeader = document.createElement("div");
    compareHeader.className = "muted";
    compareHeader.style.cssText = "font-size:10px;padding:0 0 4px;letter-spacing:1.5px;text-transform:uppercase;font-weight:700;color:var(--accent)";
    compareHeader.textContent = "Compare across decks (sim with mana-fix)";
    el.appendChild(compareHeader);
    renderCompareTable(deckId);

    // === Per-deck details below ===
    const sectionHeader = document.createElement("div");
    sectionHeader.className = "muted";
    sectionHeader.style.cssText = "font-size:10px;padding:14px 0 4px;letter-spacing:1.5px;text-transform:uppercase";
    sectionHeader.textContent = "This deck — castability detail";
    el.appendChild(sectionHeader);

    // Header: explain what these mean
    const help = document.createElement("div");
    help.className = "muted";
    help.style.cssText = "font-size:10px;padding:0 0 6px;line-height:1.4";
    help.innerHTML = "Bars show <strong>P(can cast | card is in hand on target turn)</strong>. Red = high miss rate. Drawn-card frequency in parens. Late-turn metrics now factor in mana-fix bank (self-Wildfire, FoR self-sac).";
    el.appendChild(help);

    // Conditional rows
    STAT_METRICS.forEach(([key, label]) => {
      const e = stats[key];
      if (!e || e.castable_given_in_hand_pct === null) return;
      const pct = e.castable_given_in_hand_pct;
      const inHand = e.had_in_hand_pct;
      let cls = pct >= 65 ? "good" : pct >= 30 ? "mid" : "bad";
      const row = document.createElement("div");
      row.className = "stat-row " + cls;
      row.innerHTML = `<span class="label">${label} <span class="muted" style="font-size:10px">(${inHand.toFixed(0)}%)</span></span>` +
        `<span class="bar"><span style="width:${Math.min(pct, 100)}%"></span></span>` +
        `<span class="pct">${pct.toFixed(0)}%</span>`;
      el.appendChild(row);
    });

    // Section divider
    const div = document.createElement("div");
    div.className = "muted";
    div.style.cssText = "font-size:10px;padding:8px 0 4px;letter-spacing:1.5px;text-transform:uppercase";
    div.textContent = "Game-state probabilities";
    el.appendChild(div);

    const misc = stats.misc || {};
    MISC_METRICS.forEach(([key, label, kind]) => {
      const v = misc[key];
      if (v === undefined) return;
      let cls = "mid";
      if (kind === "good_high") cls = v >= 70 ? "good" : v >= 30 ? "mid" : "bad";
      else if (kind === "good_mid") cls = v >= 30 ? "good" : v >= 15 ? "mid" : "bad";
      else if (kind === "flood") cls = v < 15 ? "good" : v < 25 ? "mid" : "flag";
      const row = document.createElement("div");
      row.className = "stat-row " + cls;
      row.innerHTML = `<span class="label">${label}</span>` +
        `<span class="bar"><span style="width:${Math.min(v, 100)}%"></span></span>` +
        `<span class="pct">${v.toFixed(0)}%</span>`;
      el.appendChild(row);
    });

    renderManaFixCatalog(deckId);
  }

  // Importance weights for "best build" calculation.
  // High = critical to deck function, Med = useful, Low = edge case.
  const METRIC_IMPORTANCE = {
    erode_T1:          { weight: 3, label: "Erode T1" },
    path_T1:           { weight: 3, label: "Path T1" },
    galvanic_T1:       { weight: 2, label: "Galvanic T1" },
    phantom_T2:        { weight: 1, label: "Phantom T2 (aspirational)" },
    phantom_T3:        { weight: 3, label: "Phantom T3" },
    phelia_T2:         { weight: 2, label: "Phelia T2 (flash)" },
    phelia_T3:         { weight: 2, label: "Phelia T3" },
    wildfire_T2:       { weight: 4, label: "Wildfire T2 (engine)" },
    pof_T2:            { weight: 4, label: "PoF T2 (engine)" },
    phlage_T3_removal: { weight: 3, label: "Phlage T3 as removal" },
    warp_qr_T2:        { weight: 3, label: "Warp QR T2" },
    warp_qr_T3:        { weight: 4, label: "Warp QR T3 (real plan)" },
    hardcast_qr_T5:    { weight: 2, label: "Hardcast QR T5" },
    hardcast_qr_T6:    { weight: 2, label: "Hardcast QR T6" },
    wos_T4:            { weight: 2, label: "Wrath of Skies T4" },
    roku_T4:           { weight: 1, label: "Roku T4" },
    phlage_escape_T7:  { weight: 1, label: "Escape Phlage T7 (rare)" },
  };

  function renderCompareTable(activeId) {
    const el = document.getElementById("stats");

    const note = document.createElement("div");
    note.className = "muted";
    note.style.cssText = "font-size:10px;padding:0 0 6px;line-height:1.4";
    note.innerHTML = "P(can cast | held). <strong>W</strong> = my guess at importance (1=low, 4=critical). Tell me which weights are wrong and I'll update.";
    el.appendChild(note);

    const ids = ["source", "phelia", "pure", "roku"];
    const labels = { source: "Cor", phelia: "Phe", pure: "Pur", roku: "Rok" };

    const table = document.createElement("table");
    table.className = "compare-table";
    let head = "<thead><tr><th>Metric</th><th class='w'>W</th>";
    ids.forEach(id => { head += `<th class="${id===activeId?'active':''}">${labels[id]}</th>`; });
    head += "</tr></thead><tbody>";
    table.innerHTML = head;
    const tbody = table.querySelector("tbody");

    Object.entries(METRIC_IMPORTANCE).forEach(([key, info]) => {
      const tr = document.createElement("tr");
      let row = `<td>${info.label}</td><td class="w">${info.weight}</td>`;
      ids.forEach(id => {
        const e = (typeof STATS !== "undefined") ? STATS[id]?.[key] : null;
        const pct = e?.castable_given_in_hand_pct;
        if (pct === null || pct === undefined) {
          row += '<td class="muted">—</td>';
        } else {
          const cls = pct >= 65 ? "good" : pct >= 30 ? "mid" : "bad";
          const active = id === activeId ? " active" : "";
          row += `<td class="${cls}${active}">${pct.toFixed(0)}</td>`;
        }
      });
      tr.innerHTML = row;
      tbody.appendChild(tr);
    });

    // Compute weighted score per deck
    const scores = {};
    ids.forEach(id => {
      let total = 0, denom = 0;
      Object.entries(METRIC_IMPORTANCE).forEach(([key, info]) => {
        const pct = STATS?.[id]?.[key]?.castable_given_in_hand_pct;
        if (pct == null) return;
        total += pct * info.weight;
        denom += info.weight;
      });
      scores[id] = denom ? total / denom : 0;
    });
    const scoreRow = document.createElement("tr");
    let sr = '<td><strong>Weighted score</strong></td><td class="w">—</td>';
    ids.forEach(id => {
      const s = scores[id];
      const active = id === activeId ? " active" : "";
      sr += `<td class="${s >= 50 ? 'good' : s >= 35 ? 'mid' : 'bad'}${active}"><strong>${s.toFixed(1)}</strong></td>`;
    });
    scoreRow.innerHTML = sr;
    scoreRow.style.borderTop = "2px solid var(--line-2)";
    tbody.appendChild(scoreRow);

    el.appendChild(table);
  }

  // Catalog of in-game mana-fixing tricks available to the deck
  function renderManaFixCatalog(deckId) {
    const el = document.getElementById("stats");
    const div = document.createElement("div");
    div.className = "muted";
    div.style.cssText = "font-size:10px;padding:14px 0 4px;letter-spacing:1.5px;text-transform:uppercase";
    div.textContent = "In-game mana fixing tricks";
    el.appendChild(div);

    const tricks = [
      { name: "Self-Cleansing Wildfire", cost: "{1}{R}", desc: "Wildfire your own non-basic → fetch ANY basic UNTAPPED + cantrip. Targets: Sacred Foundry, Hallowed Fountain, Sunken Citadel, Cori Mountain Monastery, etc.", availableIn: ["source","phelia","pure","roku"] },
      { name: "Field of Ruin self-sac", cost: "{1}, T, sac", desc: "Sac own Field of Ruin → opp's non-basic destroyed + BOTH players search basic UNTAPPED.", availableIn: ["source","phelia","pure","roku"] },
      { name: "Sunken Citadel + FoR T1→T2", cost: "play sequence", desc: "T1 Sunken Citadel (UU only on land abilities) → T2 pay 1 from Citadel to activate Field of Ruin → both get basic. Effectively converts 2 lands → 1 utility-color basic + breaks opp non-basic.", availableIn: ["source","pure","roku"] },
      { name: "Roku Chapter II", cost: "—", desc: "After Roku resolves Chapter I, next upkeep adds 1 mana of any color. The U-source for hardcast QR.", availableIn: ["source","pure","roku"] },
      { name: "Flashback (the card)", cost: "{R}", desc: "Target instant/sorcery in yard gains flashback at mana cost. Flash back a Wildfire from yard for {1}{R} = +1 self-fix attempt.", availableIn: ["source"] },
      { name: "Demolition Field self-sac (NOT a fix)", cost: "{2}, T, sac", desc: "Only kills same-name non-basics; doesn't give you a basic. Engine piece, not a fix.", availableIn: ["source","phelia","pure","roku"] },
    ];

    tricks.forEach(t => {
      const isAvailable = t.availableIn.includes(deckId);
      const row = document.createElement("div");
      row.style.cssText = "padding: 6px 8px; margin-bottom: 4px; border-radius: 4px; background: " + (isAvailable ? "var(--bg-3)" : "rgba(255,255,255,0.02)") + "; font-size: 11px; line-height: 1.4; opacity: " + (isAvailable ? 1 : 0.4) + ";";
      row.innerHTML = `<div style="color: ${isAvailable ? 'var(--accent)' : 'var(--muted)'}; font-weight: 600; font-size: 11px;">${t.name} <span class="muted" style="font-weight: normal; font-family: monospace; font-size: 10px;">${t.cost}</span></div>` +
        `<div class="muted" style="font-size: 10px; margin-top: 2px;">${t.desc}</div>`;
      el.appendChild(row);
    });
  }

  function renderCardList(elId, cards) {
    const el = document.getElementById(elId);
    el.innerHTML = "";
    // Group by role
    const byRole = {};
    cards.forEach(([name, qty]) => {
      const c = CARDS[name] || { role: "?" };
      const role = c.role || "?";
      (byRole[role] = byRole[role] || []).push([name, qty, c]);
    });
    const order = ["finisher", "blink", "removal", "ld", "counter", "engine", "lock", "mana", "hate", "land"];
    order.forEach((role) => {
      if (!byRole[role]) return;
      const h = document.createElement("div");
      h.className = "muted";
      h.style.cssText = "font-size:10px;letter-spacing:1.5px;text-transform:uppercase;padding:8px 8px 4px;color:" + (ROLE_COLOR[role] || "#888");
      h.textContent = ROLE_LABEL[role] || role;
      el.appendChild(h);
      byRole[role].forEach(([name, qty, c]) => {
        const row = document.createElement("div");
        row.className = "card-row";
        row.dataset.name = name;
        row.dataset.role = role;
        row.innerHTML = `<span class="qty">${qty}</span><span class="name">${name}</span><span class="cost">${c.cost || ""}</span>`;
        row.addEventListener("click", () => {
          highlightCard(name);
          showCardDetail(name);
        });
        el.appendChild(row);
      });
    });
  }

  function renderCurve(cards) {
    const buckets = [0, 0, 0, 0, 0, 0, 0]; // 0..6+
    cards.forEach(([name, qty]) => {
      const c = CARDS[name];
      if (!c || c.role === "land") return;
      const i = Math.min(c.cmc, 6);
      buckets[i] += qty;
    });
    const max = Math.max(...buckets) || 1;
    const el = document.getElementById("curve");
    el.innerHTML = "";
    buckets.forEach((ct, i) => {
      const row = document.createElement("div");
      row.className = "curve-row";
      const label = i === 6 ? "6+" : `${i}`;
      row.innerHTML = `<span class="label">${label}</span><div class="bar" style="width:${(ct / max) * 100}%"></div><span class="ct">${ct}</span>`;
      el.appendChild(row);
    });
  }

  // --- Graph ---
  function renderGraph(deck) {
    // Unique cards (mainboard) excluding hidden roles
    const seen = new Set();
    const nodes = [];
    deck.mainboard.forEach(([name, qty]) => {
      if (seen.has(name)) return;
      const c = CARDS[name];
      if (!c) return;
      if (hiddenRoles.has(c.role)) return;
      seen.add(name);
      nodes.push({
        data: {
          id: name,
          label: `${name}\n×${qty}`,
          name,
          qty,
          role: c.role,
          color: ROLE_COLOR[c.role] || "#888",
          cmc: c.cmc || 0,
        },
      });
    });

    // Synergy edges from the deck definition
    const edges = (deck.synergies || [])
      .filter(([a, b]) => seen.has(a) && seen.has(b))
      .map(([a, b, label], i) => ({
        data: { id: `e${i}`, source: a, target: b, label: label || "" },
      }));

    if (cy) cy.destroy();
    cy = cytoscape({
      container: document.getElementById("cy"),
      elements: { nodes, edges },
      wheelSensitivity: 0.2,
      style: [
        {
          selector: "node",
          style: {
            "background-color": "data(color)",
            "border-width": 1,
            "border-color": "#1a1825",
            label: "data(label)",
            "text-wrap": "wrap",
            "text-max-width": 130,
            "text-valign": "center",
            "text-halign": "center",
            color: "#0e0d12",
            "font-size": 10,
            "font-weight": 600,
            "text-outline-color": "data(color)",
            "text-outline-width": 0,
            width: 110,
            height: 50,
            shape: "round-rectangle",
          },
        },
        {
          selector: "node[role = 'finisher']",
          style: {
            "border-width": 3,
            "border-color": "#d4a843",
            width: 130,
            height: 60,
            "font-size": 11,
          },
        },
        {
          selector: "node:selected",
          style: { "border-width": 4, "border-color": "#d4a843" },
        },
        {
          selector: "node.dim",
          style: { opacity: 0.18 },
        },
        {
          selector: "edge",
          style: {
            "curve-style": "bezier",
            "line-color": "#3a3645",
            "target-arrow-color": "#3a3645",
            "target-arrow-shape": "triangle",
            "arrow-scale": 0.8,
            width: 1.5,
            label: "data(label)",
            "font-size": 8,
            "text-rotation": "autorotate",
            color: "#9994ad",
            "text-background-color": "#0e0d12",
            "text-background-opacity": 0.85,
            "text-background-padding": 2,
            "text-background-shape": "round-rectangle",
          },
        },
        {
          selector: "edge.hl",
          style: {
            "line-color": "#d4a843",
            "target-arrow-color": "#d4a843",
            width: 2.5,
            "z-index": 99,
          },
        },
        {
          selector: "edge.dim",
          style: { opacity: 0.1 },
        },
      ],
      layout: {
        name: "dagre",
        rankDir: "LR",
        nodeSep: 30,
        rankSep: 80,
        edgeSep: 20,
        animate: false,
      },
    });

    cy.on("tap", "node", (evt) => {
      const name = evt.target.data("name");
      highlightCard(name);
      showCardDetail(name);
    });
    cy.on("tap", (evt) => {
      if (evt.target === cy) {
        clearHighlight();
        hideCardDetail();
      }
    });

    renderLegend(deck);
  }

  function renderLegend(deck) {
    const el = document.getElementById("legend");
    el.innerHTML = "";
    // gather roles in this deck
    const roles = new Set();
    deck.mainboard.forEach(([name]) => {
      const c = CARDS[name];
      if (c) roles.add(c.role);
    });
    Array.from(roles).forEach((r) => {
      const li = document.createElement("span");
      li.className = "li" + (hiddenRoles.has(r) ? " off" : "");
      li.dataset.role = r;
      li.innerHTML = `<span class="swatch" style="background:${ROLE_COLOR[r] || "#888"}"></span>${ROLE_LABEL[r] || r}`;
      li.addEventListener("click", () => {
        if (hiddenRoles.has(r)) hiddenRoles.delete(r);
        else hiddenRoles.add(r);
        renderGraph(DECKS[activeDeckId]);
      });
      el.appendChild(li);
    });
  }

  function highlightCard(name) {
    if (!cy) return;
    cy.elements().removeClass("hl dim");
    const node = cy.getElementById(name);
    if (!node || node.empty()) {
      // not in graph (e.g. land); just update sidebar
      document.querySelectorAll(".card-row").forEach((r) => r.classList.toggle("active", r.dataset.name === name));
      return;
    }
    cy.elements().addClass("dim");
    const neighborhood = node.closedNeighborhood();
    neighborhood.removeClass("dim");
    neighborhood.edgesWith(neighborhood).addClass("hl");
    node.connectedEdges().addClass("hl");
    cy.animate({ center: { eles: node }, duration: 250 });

    document.querySelectorAll(".card-row").forEach((r) => r.classList.toggle("active", r.dataset.name === name));
  }

  function clearHighlight() {
    if (cy) cy.elements().removeClass("hl dim");
    document.querySelectorAll(".card-row").forEach((r) => r.classList.remove("active"));
  }

  function showCardDetail(name) {
    const c = CARDS[name];
    const el = document.getElementById("card-detail");
    if (!c) {
      el.hidden = true;
      return;
    }
    el.hidden = false;
    const ptLine = c.pt ? ` • ${c.pt}` : "";
    el.innerHTML = `
      <button class="close" aria-label="close">×</button>
      <h4>${name} <span style="color:var(--muted);font-size:11px;font-weight:400">${c.cost || ""}</span></h4>
      <div class="ct">${c.type}${ptLine} • ${c.set || ""}</div>
      <div class="ot">${c.text || ""}</div>
    `;
    el.querySelector(".close").addEventListener("click", () => {
      el.hidden = true;
      clearHighlight();
    });
  }
  function hideCardDetail() {
    document.getElementById("card-detail").hidden = true;
  }

  // Boot
  loadDeck(Object.keys(DECKS)[0]);
})();
