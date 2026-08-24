import { useMemo } from 'react';
import { ReactFlow, Background, type Edge, type Node } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import type { NearbyStationBenchmark } from '../site-feasibility/siteFeasibilityTypes';
import { buildGraph, pressureSummary, type Pressure } from './competitiveLandscape';

type Props = {
  site: { id: string; label: string; score: number };
  stations: NearbyStationBenchmark[];
};

/**
 * The candidate site and what it would be competing with, as a diagram.
 *
 * WHY A DIAGRAM AND NOT A LIST
 *
 * NearbyStationsTab already lists the same stations, and a list answers "which
 * ones are there". It does not answer "am I hemmed in", which is the question a
 * score of 70 leaves open. Here the ring radius tracks real distance, so a
 * competitor 400 m away sits against the centre node and one 4 km out sits on
 * the rim. Being surrounded looks like being surrounded.
 *
 * WEB ONLY, WITH A NATIVE SIBLING
 *
 * React Flow is DOM-based and the planner renders on Expo too: apps/mobile and
 * apps/web both mount the same AppRouter. The bundler picks this file on web
 * and SiteConnectionGraph.tsx on native, the same split LeafletMap already uses.
 *
 * READ-ONLY BY CONSTRUCTION
 *
 * Every interaction that would change the graph is disabled. This is a
 * statement about real geography; a planner dragging a station 2 km to the left
 * would produce a picture that contradicts the distances written on its own
 * edges.
 */
export function SiteConnectionGraph({ site, stations }: Props) {
  const { nodes, edges } = useMemo(() => {
    const graph = buildGraph(site, stations);
    const rfNodes: Node[] = graph.nodes.map((n) => ({
      id: n.id,
      position: { x: n.x, y: n.y },
      data: {
        label: (
          <div style={{ lineHeight: 1.25 }}>
            <div style={{ fontWeight: 700, fontSize: 12 }}>{n.label}</div>
            {n.sublabel ? (
              <div style={{ fontSize: 10, opacity: 0.75, marginTop: 2 }}>{n.sublabel}</div>
            ) : null}
          </div>
        )
      },
      style: n.kind === 'site' ? SITE_STYLE : stationStyle(n.pressure ?? 'low'),
      draggable: false,
      selectable: false,
      connectable: false
    }));
    const rfEdges: Edge[] = graph.edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      label: e.label,
      animated: e.pressure === 'high',
      style: { stroke: EDGE_COLOUR[e.pressure], strokeWidth: e.pressure === 'high' ? 2 : 1.2 },
      labelStyle: { fill: '#26383D', fontSize: 11, fontWeight: 600 },
      labelBgStyle: { fill: '#FFFFFF', fillOpacity: 0.9 }
    }));
    return { nodes: rfNodes, edges: rfEdges };
  }, [site, stations]);

  return (
    <div>
      <div style={{ color: '#8A979B', fontSize: 11, fontWeight: 700, letterSpacing: 0.6 }}>
        COMPETITIVE LANDSCAPE
      </div>
      <div style={{ color: '#55656A', fontSize: 12, marginTop: 4, marginBottom: 8 }}>
        {pressureSummary(stations)}
      </div>
      {/* React Flow needs a container with real dimensions or it renders nothing. */}
      <div style={{
        height: 320, width: '100%', borderRadius: 10,
        border: '1px solid #DDE5E7', backgroundColor: '#FFFFFF', overflow: 'hidden'
      }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          fitView
          fitViewOptions={{ padding: 0.25 }}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          panOnDrag
          zoomOnScroll={false}
          zoomOnDoubleClick={false}
          proOptions={{ hideAttribution: false }}
        >
          <Background gap={18} size={1} color="#EDF1F2" />
        </ReactFlow>
      </div>
      <div style={{ color: '#8A979B', fontSize: 10, lineHeight: 1.5, marginTop: 8 }}>
        Distance, operator, power and connector count come from the station records.
        Sessions and revenue are not shown here: those figures are generated, and this
        diagram is about what physically exists.
      </div>
    </div>
  );
}

const SITE_STYLE = {
  background: '#00565F', border: '2px solid #00424A', borderRadius: 10,
  color: '#FFFFFF', padding: '8px 12px', width: 150
};

const PRESSURE_FILL: Record<Pressure, string> = {
  high: '#FEE2E2', moderate: '#FEF3C7', low: '#ECFDF5'
};
const PRESSURE_BORDER: Record<Pressure, string> = {
  high: '#EF4444', moderate: '#F59E0B', low: '#10B981'
};
const EDGE_COLOUR: Record<Pressure, string> = {
  high: '#EF4444', moderate: '#F59E0B', low: '#94A3B8'
};

function stationStyle(pressure: Pressure) {
  return {
    background: PRESSURE_FILL[pressure],
    border: `1.5px solid ${PRESSURE_BORDER[pressure]}`,
    borderRadius: 8,
    color: '#26383D',
    padding: '6px 10px',
    width: 150
  };
}
