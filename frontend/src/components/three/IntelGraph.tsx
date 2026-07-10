"use client";

/* 3D Meeting Intelligence Graph — a layered knowledge network that slowly
   rotates with glowing nodes and pulsing connections. Layers flow left→right:
   Company → Meetings → Decisions → Insights → Outcome. Parametric: pass your
   own layers, or use the sensible default. Lazy + client-only via Lazy.tsx. */

import { Canvas, useFrame } from "@react-three/fiber";
import { Line, Text } from "@react-three/drei";
import { useMemo, useRef } from "react";
import * as THREE from "three";

const ACCENT = "#6366f1";
const IRIS = "#a78bfa";
const TEAL = "#a5b4fc";

export interface GraphLayer {
  name: string;
  nodes: string[];
  color?: string;
}

const DEFAULT_LAYERS: GraphLayer[] = [
  { name: "Company", nodes: ["Account"], color: IRIS },
  { name: "Meetings", nodes: ["Discovery", "Demo", "Pricing"], color: ACCENT },
  { name: "Decisions", nodes: ["Budget", "Timeline"], color: TEAL },
  { name: "Insights", nodes: ["Champion", "Risk"], color: ACCENT },
  { name: "Outcome", nodes: ["Closed Won"], color: "#2ed573" },
];

type Placed = { pos: THREE.Vector3; label: string; color: string; layer: number };

function buildGraph(layers: GraphLayer[]) {
  const spanX = 7;
  const placed: Placed[] = [];
  layers.forEach((layer, li) => {
    const x = -spanX / 2 + (spanX * li) / Math.max(1, layers.length - 1);
    const n = layer.nodes.length;
    layer.nodes.forEach((label, ni) => {
      const y = n === 1 ? 0 : (ni - (n - 1) / 2) * 1.5;
      const z = n === 1 ? 0 : Math.sin(ni * 1.7) * 0.6;
      placed.push({ pos: new THREE.Vector3(x, y, z), label, color: layer.color ?? ACCENT, layer: li });
    });
  });
  // connect every node to every node in the next layer
  const edges: Array<[THREE.Vector3, THREE.Vector3]> = [];
  for (let li = 0; li < layers.length - 1; li++) {
    const a = placed.filter((p) => p.layer === li);
    const b = placed.filter((p) => p.layer === li + 1);
    a.forEach((pa) => b.forEach((pb) => edges.push([pa.pos, pb.pos])));
  }
  return { placed, edges };
}

function Node({ p }: { p: Placed }) {
  const ref = useRef<THREE.Mesh>(null);
  useFrame((state) => {
    if (!ref.current) return;
    const s = 1 + Math.sin(state.clock.elapsedTime * 2 + p.pos.x) * 0.08;
    ref.current.scale.setScalar(s);
  });
  return (
    <group position={p.pos}>
      <mesh ref={ref}>
        <sphereGeometry args={[0.16, 24, 24]} />
        <meshBasicMaterial color={p.color} toneMapped={false} />
      </mesh>
      <mesh>
        <sphereGeometry args={[0.28, 24, 24]} />
        <meshBasicMaterial color={p.color} transparent opacity={0.12} toneMapped={false} />
      </mesh>
      <Text position={[0, -0.42, 0]} fontSize={0.22} color="#cfcfd4" anchorX="center" anchorY="middle">
        {p.label}
      </Text>
    </group>
  );
}

function Graph({ layers }: { layers: GraphLayer[] }) {
  const group = useRef<THREE.Group>(null);
  const { placed, edges } = useMemo(() => buildGraph(layers), [layers]);

  useFrame((state) => {
    if (!group.current) return;
    group.current.rotation.y = Math.sin(state.clock.elapsedTime * 0.18) * 0.5;
    const { x, y } = state.pointer;
    group.current.rotation.x += (y * 0.18 - group.current.rotation.x) * 0.04;
    group.current.position.x += (x * 0.4 - group.current.position.x) * 0.04;
  });

  return (
    <group ref={group}>
      {edges.map(([a, b], i) => (
        <Line
          key={i}
          points={[a, b]}
          color={ACCENT}
          lineWidth={1}
          transparent
          opacity={0.18}
        />
      ))}
      {placed.map((p, i) => (
        <Node key={i} p={p} />
      ))}
    </group>
  );
}

export default function IntelGraph({
  layers = DEFAULT_LAYERS,
  className = "",
}: {
  layers?: GraphLayer[];
  className?: string;
}) {
  return (
    <div className={className}>
      <Canvas camera={{ position: [0, 0, 8.5], fov: 42 }} dpr={[1, 2]} gl={{ alpha: true, antialias: true }}>
        <ambientLight intensity={0.8} />
        <Graph layers={layers} />
      </Canvas>
    </div>
  );
}
