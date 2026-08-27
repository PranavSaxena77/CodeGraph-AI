import { useEffect, useMemo, useState } from 'react'

import { Icon, Spinner } from './Ui.jsx'

const STRUCTURAL_METRICS = [
  ['files', 'Python files'],
  ['classes', 'Classes'],
  ['functions', 'Functions'],
  ['methods', 'Methods'],
  ['imports', 'Imports'],
  ['resolvedCalls', 'Resolved calls'],
  ['chunks', 'Semantic chunks'],
  ['dimension', 'Vector dimensions'],
]

const NODE_ORDER = ['Snapshot', 'File', 'Class', 'Function', 'Method']
const RELATIONSHIP_ORDER = ['IMPORTS', 'DECLARES', 'CONTAINS', 'CALLS', 'INHERITS', 'INHERITS_FROM']

export function MetricsPreview({ metrics, stages }) {
  const available = STRUCTURAL_METRICS.filter(([key]) => Number.isInteger(metrics?.[key]))
  const graphCountsReady = Number.isInteger(metrics?.nodes) && Number.isInteger(metrics?.relationships)
  const activeStage = ['analysis', 'graph', 'vector'].find((stage) => stages[stage] === 'running')

  return (
    <section className="panel visual-preview" aria-labelledby="visual-preview-title">
      <div className="compact-panel-heading"><div><h2 id="visual-preview-title">Live Visual Preview</h2><p>Backend-derived graph output</p></div>{activeStage && <span className="panel-running"><Spinner />{activeStage}</span>}</div>
      {graphCountsReady
        ? <ActualCountPlot nodes={metrics.nodes} relationships={metrics.relationships} />
        : <div className="preview-state preview-state--loading"><span className="preview-state__glyph"><Icon name="activity" size={22} /></span><strong>{activeStage ? 'Awaiting persisted graph counts' : 'No graph metrics yet'}</strong><p>{activeStage ? 'This view remains indeterminate until the backend reports real node and relationship totals.' : 'Run the graph pipeline to populate this preview.'}</p></div>}
      {available.length > 0 && <dl className="measured-output" aria-label="Measured pipeline output">{available.map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{metrics[key].toLocaleString()}</dd></div>)}</dl>}
    </section>
  )
}

function ActualCountPlot({ nodes, relationships }) {
  const maximum = Math.max(1, nodes, relationships)
  const counts = [
    ['nodes', 'Nodes', nodes],
    ['relationships', 'Relationships', relationships],
  ]
  return <div className="count-plot" aria-label={`Actual graph counts: ${nodes} nodes and ${relationships} relationships`}><div className="count-plot__legend">{counts.map(([key, label]) => <span key={key}><i className={`count-key count-key--${key}`} />{label}</span>)}</div><div className="count-plot__chart">{counts.map(([key, label, value]) => <div className="count-column" key={key}><div><i><b className={`count-column__bar count-column__bar--${key}`} style={{ height: `${(value / maximum) * 100}%` }} /></i><code>{value.toLocaleString()}</code></div><span>{label}</span></div>)}</div><dl className="count-plot__totals"><div><dt>Total Nodes</dt><dd>{nodes.toLocaleString()}</dd></div><div><dt>Total Relationships</dt><dd>{relationships.toLocaleString()}</dd></div></dl></div>
}

export function GraphPreview({ preview, graphState }) {
  const [hoveredId, setHoveredId] = useState('')
  const [selectedId, setSelectedId] = useState('')
  const [expanded, setExpanded] = useState(false)
  const nodes = preview.data?.nodes ?? []
  const relationships = preview.data?.relationships ?? []
  const graph = useMemo(() => buildGraphModel(nodes, relationships), [nodes, relationships])

  useEffect(() => {
    if (!expanded) return undefined
    const closeOnEscape = (event) => { if (event.key === 'Escape') setExpanded(false) }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [expanded])

  const activeId = hoveredId || selectedId
  return (
    <section className="panel graph-preview" aria-labelledby="graph-preview-title">
      <GraphHeading nodes={nodes} relationships={relationships} onExpand={() => setExpanded(true)} />
      {nodes.length > 0 ? <GraphContent graph={graph} activeId={activeId} selectedId={selectedId} onHover={setHoveredId} onSelect={setSelectedId} /> : <GraphEmptyState preview={preview} graphState={graphState} />}
      {expanded && <div className="graph-modal" onMouseDown={(event) => { if (event.target === event.currentTarget) setExpanded(false) }}><section aria-label="Expanded Graph Structure Preview" aria-modal="true" className="graph-modal__dialog" role="dialog"><div className="compact-panel-heading"><div><h2>Graph Structure Preview</h2><p>Bounded persisted neighborhood · {nodes.length} nodes</p></div><button aria-label="Close expanded graph" className="icon-button" onClick={() => setExpanded(false)} type="button"><Icon name="close" /></button></div><GraphContent expanded graph={graph} activeId={activeId} selectedId={selectedId} onHover={setHoveredId} onSelect={setSelectedId} /></section></div>}
    </section>
  )
}

function GraphHeading({ nodes, relationships, onExpand }) {
  return <div className="compact-panel-heading"><div><h2 id="graph-preview-title">Graph Structure Preview</h2><p>Bounded persisted neighborhood</p></div>{nodes.length > 0 && <div className="graph-preview__header-actions"><span>{nodes.length} nodes · {relationships.length} edges</span><button className="button button--secondary button--compact" onClick={onExpand} type="button"><Icon name="expand" size={13} />Expand</button></div>}</div>
}

function GraphContent({ graph, activeId, selectedId, onHover, onSelect, expanded = false }) {
  const activeNode = graph.nodes.find((node) => node.id === activeId)
  const connectedIds = activeId ? new Set([activeId, ...(graph.neighbors.get(activeId) ?? [])]) : null
  return <><div className={`graph-canvas ${expanded ? 'graph-canvas--expanded' : ''}`} onMouseLeave={() => onHover('')} role="img" aria-label={`Persisted graph preview with ${graph.nodes.length} nodes and ${graph.relationships.length} relationships`}><svg viewBox="0 0 720 300" preserveAspectRatio="xMidYMid meet"><g className="graph-edges">{graph.relationships.map((relationship) => { const source = graph.positions.get(relationship.source_id); const target = graph.positions.get(relationship.target_id); if (!source || !target) return null; const connected = !activeId || relationship.source_id === activeId || relationship.target_id === activeId; return <line className={`graph-edge graph-edge--${relationship.relationship_type.toLowerCase()} ${activeId && !connected ? 'graph-edge--dimmed' : ''} ${activeId && connected ? 'graph-edge--active' : ''}`} key={relationship.id} x1={source.x} y1={source.y} x2={target.x} y2={target.y}><title>{relationship.relationship_type}</title></line> })}</g><g className="graph-nodes">{graph.nodes.map((node) => { const point = graph.positions.get(node.id); const dimmed = connectedIds && !connectedIds.has(node.id); const active = node.id === activeId; return <g aria-label={graphNodeLabel(node)} className={`graph-node graph-node--${node.node_type.toLowerCase()} ${dimmed ? 'graph-node--dimmed' : ''} ${active ? 'graph-node--active' : ''} ${node.id === selectedId ? 'graph-node--selected' : ''}`} data-node-id={node.id} key={node.id} onBlur={() => onHover('')} onClick={() => onSelect(node.id === selectedId ? '' : node.id)} onFocus={() => onHover(node.id)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSelect(node.id === selectedId ? '' : node.id) } }} onMouseEnter={() => onHover(node.id)} role="button" tabIndex="0" transform={`translate(${point.x} ${point.y})`}><circle r={node.radius} /><title>{graphNodeLabel(node)}</title></g> })}</g></svg>{activeNode && <GraphTooltip node={activeNode} relationships={graph.relationships.filter((item) => item.source_id === activeNode.id || item.target_id === activeNode.id)} />}</div><RelationshipSummary counts={graph.relationshipCounts} /><NodeLegend nodes={graph.nodes} /></>
}

function GraphTooltip({ node, relationships }) {
  const counts = countRelationships(relationships)
  return <aside className="graph-tooltip"><strong>{graphNodeLabel(node)}</strong><span>{node.node_type}</span><small>{relationships.length} visible {relationships.length === 1 ? 'relationship' : 'relationships'}</small>{Object.entries(counts).length > 0 && <code>{Object.entries(counts).map(([type, count]) => `${displayRelationship(type)} ${count}`).join(' · ')}</code>}</aside>
}

function RelationshipSummary({ counts }) {
  const entries = RELATIONSHIP_ORDER.filter((type) => counts[type]).map((type) => [type, counts[type]])
  if (entries.length === 0) return null
  return <div className="relationship-summary" aria-label="Visible relationship counts">{entries.map(([type, count]) => <span key={type}><code>{displayRelationship(type)}</code><b>{count}</b></span>)}</div>
}

function NodeLegend({ nodes }) {
  return <div className="graph-legend" aria-label="Graph node legend">{NODE_ORDER.filter((type) => nodes.some((node) => node.node_type === type)).map((type) => <span key={type}><i className={`graph-node-key graph-node-key--${type.toLowerCase()}`} />{type}</span>)}</div>
}

function GraphEmptyState({ preview, graphState }) {
  const isLoading = preview.loading || graphState === 'running'
  return <div className={`preview-state ${isLoading ? 'preview-state--loading' : ''}`}>{isLoading ? <Spinner label="Loading persisted graph preview" /> : <span className="preview-state__glyph"><Icon name="graph" size={22} /></span>}<strong>{preview.error ? 'Graph preview unavailable' : isLoading ? 'Persisting graph structure' : 'No persisted graph yet'}</strong><p>{preview.error || (isLoading ? 'The preview will appear after Neo4j confirms persistence.' : 'Run the code graph stage to load a bounded real neighborhood.')}</p></div>
}

function buildGraphModel(nodes, relationships) {
  const degrees = new Map(nodes.map((node) => [node.id, 0]))
  const neighbors = new Map(nodes.map((node) => [node.id, []]))
  relationships.forEach((relationship) => {
    if (!degrees.has(relationship.source_id) || !degrees.has(relationship.target_id)) return
    degrees.set(relationship.source_id, degrees.get(relationship.source_id) + 1)
    degrees.set(relationship.target_id, degrees.get(relationship.target_id) + 1)
    neighbors.get(relationship.source_id).push(relationship.target_id)
    neighbors.get(relationship.target_id).push(relationship.source_id)
  })
  return {
    nodes: nodes.map((node) => ({ ...node, radius: node.node_type === 'Snapshot' ? 10 : 5 + Math.min(4, Math.sqrt(degrees.get(node.id) ?? 0) * 1.35) })),
    relationships,
    positions: layoutNodes(nodes),
    neighbors,
    relationshipCounts: countRelationships(relationships),
  }
}

function layoutNodes(nodes) {
  const positions = new Map()
  const root = nodes.find((node) => node.node_type === 'Snapshot')
  if (root) positions.set(root.id, { x: 360, y: 150 })
  const clusterAngles = { File: -150, Class: -72, Function: 6, Method: 84, Snapshot: 162 }
  NODE_ORDER.forEach((type) => {
    const group = nodes.filter((node) => node.node_type === type && node.id !== root?.id)
    if (group.length === 0) return
    const angle = (clusterAngles[type] * Math.PI) / 180
    const center = { x: 360 + Math.cos(angle) * 190, y: 150 + Math.sin(angle) * 88 }
    group.forEach((node, index) => {
      const ring = Math.floor(index / 10)
      const indexInRing = index % 10
      const ringCount = Math.min(10, group.length - ring * 10)
      const nodeAngle = (indexInRing / ringCount) * Math.PI * 2 + ring * .37
      const radiusX = 20 + ring * 17
      const radiusY = 13 + ring * 11
      positions.set(node.id, { x: center.x + Math.cos(nodeAngle) * radiusX, y: center.y + Math.sin(nodeAngle) * radiusY })
    })
  })
  nodes.filter((node) => !positions.has(node.id)).forEach((node, index) => positions.set(node.id, { x: 360 + Math.cos(index) * 220, y: 150 + Math.sin(index) * 105 }))
  return positions
}

function countRelationships(relationships) {
  return relationships.reduce((counts, relationship) => ({ ...counts, [relationship.relationship_type]: (counts[relationship.relationship_type] ?? 0) + 1 }), {})
}

function displayRelationship(type) {
  return type === 'INHERITS_FROM' ? 'INHERITS' : type
}

function graphNodeLabel(node) {
  return node.qualified_name || node.symbol_name || node.file_path || `${node.node_type} ${node.id}`
}
