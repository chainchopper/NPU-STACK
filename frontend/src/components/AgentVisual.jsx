import React, { useEffect, useRef } from "react";

/**
 * AgentVisual - A premium 3D-accelerated visual for the NPU-STACK Agent.
 * Uses CSS 3D transforms for orbital rings and a Canvas-based glowing core.
 */
export default function AgentVisual({ size = 48, status = "online" }) {
    const canvasRef = useRef(null);
    const requestRef = useRef();

    // Canvas animation for the central "energy" core
    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext("2d");
        let frame = 0;

        const animate = () => {
            frame++;
            const { width, height } = canvas;
            ctx.clearRect(0, 0, width, height);

            const centerX = width / 2;
            const centerY = height / 2;
            const baseRadius = width * 0.3;

            // Draw glowing background
            const gradient = ctx.createRadialGradient(
                centerX, centerY, 0,
                centerX, centerY, width / 2
            );

            const themeColor = status === "online" ? "rgba(0, 255, 180" : "rgba(255, 80, 80";
            gradient.addColorStop(0, `${themeColor}, 0.8)`);
            gradient.addColorStop(0.5, `${themeColor}, 0.2)`);
            gradient.addColorStop(1, `${themeColor}, 0)`);

            ctx.fillStyle = gradient;
            ctx.beginPath();
            ctx.arc(centerX, centerY, width / 2, 0, Math.PI * 2);
            ctx.fill();

            // Draw "plasma" particles
            for (let i = 0; i < 3; i++) {
                const angle = (frame * 0.02) + (i * Math.PI * 2 / 3);
                const offsetX = Math.cos(angle * 1.5) * (baseRadius * 0.5);
                const offsetY = Math.sin(angle * 2) * (baseRadius * 0.5);

                ctx.beginPath();
                ctx.arc(centerX + offsetX, centerY + offsetY, baseRadius * 0.6, 0, Math.PI * 2);
                ctx.fillStyle = `${themeColor}, 0.4)`;
                ctx.fill();
            }

            // Draw central core
            ctx.beginPath();
            ctx.arc(centerX, centerY, baseRadius * (0.8 + Math.sin(frame * 0.05) * 0.1), 0, Math.PI * 2);
            ctx.fillStyle = status === "online" ? "#00ffb4" : "#ff5050";
            ctx.shadowBlur = 15;
            ctx.shadowColor = ctx.fillStyle;
            ctx.fill();
            ctx.shadowBlur = 0;

            requestRef.current = requestAnimationFrame(animate);
        };

        animate();
        return () => cancelAnimationFrame(requestRef.current);
    }, [status]);

    return (
        <div
            className="relative flex items-center justify-center transform-gpu"
            style={{ width: size, height: size, perspective: "1000px" }}
        >
            {/* Outer Rotating Ring */}
            <div
                className="absolute inset-0 border-2 rounded-full border-primary/30 border-t-primary animate-spin-3d-x"
            />

            {/* Middle Rotating Ring */}
            <div
                className="absolute inset-[15%] border border-primary/40 border-b-primary animate-spin-3d-y"
            />

            {/* Internal Glitchy Ring */}
            <div
                className="absolute inset-[25%] border-2 border-dashed rounded-full border-primary/20 animate-spin-slow"
            />

            {/* The Core Canvas */}
            <canvas
                ref={canvasRef}
                width={128}
                height={128}
                style={{ width: "70%", height: "70%", zIndex: 1 }}
            />

            {/* Glossy Overlay */}
            <div className="absolute inset-0 rounded-full bg-gradient-to-tr from-white/10 to-transparent pointer-events-none" />
        </div>
    );
}
