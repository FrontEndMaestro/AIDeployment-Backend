import { useEffect, useRef } from 'react';
import * as THREE from 'three';

type ThreeBackgroundVariant = 'auth' | 'dashboard';

interface ThreeBackgroundProps {
  variant?: ThreeBackgroundVariant;
}

export const ThreeBackground: React.FC<ThreeBackgroundProps> = ({
  variant = 'auth',
}) => {
  const mountRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = mountRef.current;
    if (!el) return;

    const isDashboard = variant === 'dashboard';
    const nodeCount = isDashboard ? 70 : 90;
    const maxDist = isDashboard ? 8 : 10;
    const drift = isDashboard ? 0.01 : 0.012;
    const pointOpacity = isDashboard ? 0.55 : 0.7;
    const lineOpacity = isDashboard ? 0.09 : 0.12;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(el.clientWidth, el.clientHeight);
    renderer.setClearColor(0x000000, 0);
    el.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(
      60,
      el.clientWidth / el.clientHeight,
      0.1,
      1000
    );
    camera.position.z = isDashboard ? 30 : 28;

    const positions: THREE.Vector3[] = [];
    const velocities: THREE.Vector3[] = [];

    const geom = new THREE.BufferGeometry();
    const pos = new Float32Array(nodeCount * 3);
    const colors = new Float32Array(nodeCount * 3);

    const palette = [
      new THREE.Color(0x22d3ee),
      new THREE.Color(0x3b82f6),
      new THREE.Color(0xa855f7),
      new THREE.Color(0x10b981),
    ];

    for (let i = 0; i < nodeCount; i++) {
      const p = new THREE.Vector3(
        (Math.random() - 0.5) * 50,
        (Math.random() - 0.5) * 35,
        (Math.random() - 0.5) * 20
      );

      positions.push(p);
      velocities.push(
        new THREE.Vector3((Math.random() - 0.5) * drift, (Math.random() - 0.5) * drift, 0)
      );

      pos[i * 3] = p.x;
      pos[i * 3 + 1] = p.y;
      pos[i * 3 + 2] = p.z;

      const c = palette[Math.floor(Math.random() * palette.length)];
      colors[i * 3] = c.r;
      colors[i * 3 + 1] = c.g;
      colors[i * 3 + 2] = c.b;
    }

    geom.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    geom.setAttribute('color', new THREE.BufferAttribute(colors, 3));

    const nodeMat = new THREE.PointsMaterial({
      size: isDashboard ? 0.24 : 0.28,
      vertexColors: true,
      transparent: true,
      opacity: pointOpacity,
      sizeAttenuation: true,
    });

    const points = new THREE.Points(geom, nodeMat);
    scene.add(points);

    const edgeGeom = new THREE.BufferGeometry();
    const maxEdges = nodeCount * 8;
    const edgePos = new Float32Array(maxEdges * 6);

    edgeGeom.setAttribute('position', new THREE.BufferAttribute(edgePos, 3));

    const edgeMat = new THREE.LineBasicMaterial({
      color: 0x22d3ee,
      transparent: true,
      opacity: lineOpacity,
      linewidth: 1,
    });

    const lines = new THREE.LineSegments(edgeGeom, edgeMat);
    scene.add(lines);

    const mouse = { x: 0, y: 0 };
    const onMouseMove = (e: MouseEvent) => {
      mouse.x = (e.clientX / window.innerWidth - 0.5) * 2;
      mouse.y = (e.clientY / window.innerHeight - 0.5) * 2;
    };

    window.addEventListener('mousemove', onMouseMove);

    const onResize = () => {
      if (!el) return;
      camera.aspect = el.clientWidth / el.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(el.clientWidth, el.clientHeight);
    };

    window.addEventListener('resize', onResize);

    let frame = 0;
    let animId: number;

    const animate = () => {
      animId = requestAnimationFrame(animate);
      frame++;

      for (let i = 0; i < nodeCount; i++) {
        const p = positions[i];
        const v = velocities[i];
        p.addScaledVector(v, 1);

        if (Math.abs(p.x) > 26) v.x *= -1;
        if (Math.abs(p.y) > 18) v.y *= -1;

        pos[i * 3] = p.x;
        pos[i * 3 + 1] = p.y;
        pos[i * 3 + 2] = p.z;
      }

      geom.attributes.position.needsUpdate = true;

      let edgeIndex = 0;
      for (let i = 0; i < nodeCount && edgeIndex < maxEdges - 1; i++) {
        for (let j = i + 1; j < nodeCount && edgeIndex < maxEdges - 1; j++) {
          const distance = positions[i].distanceTo(positions[j]);
          if (distance < maxDist) {
            edgePos[edgeIndex * 6] = positions[i].x;
            edgePos[edgeIndex * 6 + 1] = positions[i].y;
            edgePos[edgeIndex * 6 + 2] = positions[i].z;
            edgePos[edgeIndex * 6 + 3] = positions[j].x;
            edgePos[edgeIndex * 6 + 4] = positions[j].y;
            edgePos[edgeIndex * 6 + 5] = positions[j].z;
            edgeIndex++;
          }
        }
      }

      edgeGeom.setDrawRange(0, edgeIndex * 2);
      edgeGeom.attributes.position.needsUpdate = true;

      const xTarget = mouse.x * (isDashboard ? 1.6 : 2);
      const yTarget = -mouse.y * (isDashboard ? 1.2 : 1.5);
      camera.position.x += (xTarget - camera.position.x) * 0.015;
      camera.position.y += (yTarget - camera.position.y) * 0.015;
      camera.lookAt(scene.position);

      points.rotation.z = frame * (isDashboard ? 0.0003 : 0.0004);
      lines.rotation.z = frame * (isDashboard ? 0.0003 : 0.0004);

      renderer.render(scene, camera);
    };

    animate();

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('resize', onResize);
      renderer.dispose();

      if (el.contains(renderer.domElement)) {
        el.removeChild(renderer.domElement);
      }
    };
  }, [variant]);

  return (
    <div
      ref={mountRef}
      className="absolute inset-0 pointer-events-none"
      style={{ zIndex: 0 }}
    />
  );
};

export default ThreeBackground;
