#!/usr/bin/env node
/**
 * dump-graph.ts — Export the service-graph as plain JSON
 *
 * Serialises NODES, EDGES, and LIFE_EVENTS out of the TS module system into a
 * single JSON file, so the graph can be consumed outside the MCP/Node runtime —
 * specifically, loaded into pandas alongside the govuk-knowledge-graph
 * BigQuery subgraph for comparison.

 *
 * Usage:
 *   npx tsx dump-graph.ts [output-path]
 *   (defaults to ./service-graph-export.json)
*/

import { writeFileSync } from 'node:fs';
import { resolve, relative, isAbsolute } from 'node:path';
import { NODES, EDGES, LIFE_EVENTS, DEPT_CONTACTS } from './graph-data.js';

/**
 * Best-effort derivation of the GOV.UK base_path from a service's govuk_url.
 *
 * This is the join key that bridges the two graphs: service-graph node IDs
 * (e.g. "dwp-pip") have no equivalent on the content-store side, but base_path
 * lines up directly with publishing_api_editions_current.base_path in
 * BigQuery. Everything downstream depends on this mapping being right, so it's
 * surfaced explicitly (with a warning list) rather than silently dropped.
 */
function derivedBasePath(govuk_url: string): string | null {
  try {
    const url = new URL(govuk_url);
    if (!url.hostname.endsWith('gov.uk')) return null;
    return url.pathname.replace(/\/$/, '') || '/';
  } catch {
    return null;
  }
}

/**
 * True if the service's govuk_url is not on the GOV.UK content platform
 * (e.g. mygov.scot, gov.wales, nhs.uk, or a third-party site like
 * motability.co.uk). These services are correctly part of the journey graph
 * but structurally can't appear in a BigQuery subgraph built from
 * publishing_api_editions_current, since that only covers GOV.UK content.
 */
function isOffPlatform(govuk_url: string): boolean {
  try {
    const url = new URL(govuk_url);
    return !url.hostname.endsWith('gov.uk');
  } catch {
    return true; // unparseable URL is off-platform by definition
  }
}

const nodes = Object.values(NODES).map(node => ({
  ...node,
  base_path: derivedBasePath(node.govuk_url),
  off_platform: isOffPlatform(node.govuk_url),
}));

const edges = EDGES.map(e => ({ from: e.from, to: e.to, type: e.type }));

const lifeEvents = LIFE_EVENTS.map(evt => ({
  id: evt.id,
  name: evt.name,
  desc: evt.desc,
  entryNodes: evt.entryNodes,
}));

const missingBasePath = nodes.filter(n => !n.base_path).map(n => n.id);

const output = {
  exportedAt: new Date().toISOString(),
counts: {
  nodes: nodes.length,
  edges: edges.length,
  lifeEvents: lifeEvents.length,
  nodesMissingBasePath: missingBasePath.length,
  nodesOffPlatform: nodes.filter(n => n.off_platform).length,
},
  nodes,
  edges,
  life_events: lifeEvents,
  dept_contacts: DEPT_CONTACTS,
};

const outDir = process.cwd();
const requestedPath = process.argv[2] ?? './service-graph-export.json';
const outPath = resolve(outDir, requestedPath);

const rel = relative(outDir, outPath);
if (rel.startsWith('..') || isAbsolute(rel)) {
  throw new Error(`Refusing to write outside of ${outDir}: ${outPath}`);
}

writeFileSync(outPath, JSON.stringify(output, null, 2));

console.log(
  `Wrote ${nodes.length} nodes, ${edges.length} edges, ${lifeEvents.length} life events -> ${outPath}`
);
if (missingBasePath.length) {
  console.warn(
    `Warning: ${missingBasePath.length} node(s) had a govuk_url that didn't resolve to a gov.uk base_path:`,
    missingBasePath
  );
}
