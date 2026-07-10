"use client";

/* The AI Revenue Orb — the platform's signature object. A slowly-evolving
   distorted sphere wrapped in a particle field and orbiting knowledge nodes.
   Rotates on its own, leans toward the pointer, and emits a soft teal glow.
   Rendered lazily + client-only via three/Lazy.tsx. */

import { Canvas, useFrame, type ThreeElements } from "@react-three/fiber";
import { Float, MeshDistortMaterial, Sphere } from "@react-three/drei";
import { useMemo, useRef } from "react";
import * as THREE from "three";

const ACCENT = "#6366f1";
const IRIS = "#a78bfa";

function ParticleField({ count = 900, radius = 3.4 }: { count?: number; radius?: number }) {
  const ref = useRef<THREE.Points>(null);
  const positions = useMemo(() => {
    const arr = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      // distribute in a spherical shell, slightly fuzzy
      const r = radius * (0.78 + Math.random() * 0.5);
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      arr[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      arr[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
      arr[i * 3 + 2] = r * Math.cos(phi);
    }
    return arr;
  }, [count, radius]);

  useFrame((_, dt) => {
    if (ref.current) ref.current.rotation.y += dt * 0.045;
  });

  return (
    <points ref={ref}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <pointsMaterial
        size={0.022}
        color={ACCENT}
        transparent
        opacity={0.7}
        sizeAttenuation
        depthWrite={false}
      />
    </points>
  );
}

function OrbitNode({ radius, speed, offset, color, size }: {
  radius: number;
  speed: number;
  offset: number;
  color: string;
  size: number;
}) {
  const ref = useRef<THREE.Mesh>(null);
  useFrame((state) => {
    const t = state.clock.elapsedTime * speed + offset;
    if (ref.current) {
      ref.current.position.set(
        Math.cos(t) * radius,
        Math.sin(t * 0.8) * radius * 0.35,
        Math.sin(t) * radius,
      );
    }
  });
  return (
    <mesh ref={ref}>
      <sphereGeometry args={[size, 16, 16]} />
      <meshBasicMaterial color={color} toneMapped={false} />
    </mesh>
  );
}

function Core() {
  const group = useRef<THREE.Group>(null);

  useFrame((state) => {
    if (!group.current) return;
    group.current.rotation.y += 0.0016;
    // lean toward pointer for a parallax / "responds to you" feel
    const { x, y } = state.pointer;
    group.current.rotation.x += (y * 0.25 - group.current.rotation.x) * 0.04;
    group.current.rotation.z += (-x * 0.12 - group.current.rotation.z) * 0.04;
  });

  return (
    <group ref={group}>
      {/* glowing distorted core */}
      <Float speed={1.4} rotationIntensity={0.4} floatIntensity={0.7}>
        <Sphere args={[1.35, 96, 96]}>
          <MeshDistortMaterial
            color={ACCENT}
            emissive={ACCENT}
            emissiveIntensity={0.35}
            roughness={0.18}
            metalness={0.65}
            distort={0.38}
            speed={1.6}
          />
        </Sphere>
        {/* wireframe shell */}
        <Sphere args={[1.62, 32, 32]}>
          <meshBasicMaterial color={IRIS} wireframe transparent opacity={0.14} />
        </Sphere>
      </Float>

      <ParticleField />

      <OrbitNode radius={2.2} speed={0.5} offset={0} color={ACCENT} size={0.07} />
      <OrbitNode radius={2.6} speed={0.35} offset={2.1} color={IRIS} size={0.06} />
      <OrbitNode radius={2.0} speed={0.62} offset={4.0} color="#a5b4fc" size={0.05} />
      <OrbitNode radius={2.9} speed={0.28} offset={1.2} color={IRIS} size={0.045} />
    </group>
  );
}

export default function RevenueOrb({ className = "" }: { className?: string }) {
  return (
    <div className={className}>
      <Canvas
        camera={{ position: [0, 0, 6], fov: 45 }}
        dpr={[1, 2]}
        gl={{ antialias: true, alpha: true }}
      >
        <ambientLight intensity={0.6} />
        <pointLight position={[4, 4, 4]} intensity={2.2} color={ACCENT} />
        <pointLight position={[-4, -2, -3]} intensity={1.4} color={IRIS} />
        <Core />
      </Canvas>
    </div>
  );
}
