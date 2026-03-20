import React, { useEffect, useState, useRef } from 'react';

/**
 * CognitiveFX Component
 * Provides magical visual overlays based on chat commands.
 */
export default function CognitiveFX({ fx, children, interactive = false }) {
    const [activeFX, setActiveFX] = useState(fx);
    const canvasRef = useRef(null);

    useEffect(() => {
        setActiveFX(fx);
    }, [fx]);

    // Particle System for Snow/Rain/Flowers
    useEffect(() => {
        if (!activeFX || activeFX === 'none') return;
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        let animationFrame;

        const particles = [];
        const particleCount = activeFX === 'snow' ? 50 : (activeFX === 'storm' ? 100 : 30);

        const createParticle = () => {
            const p = {
                x: Math.random() * canvas.width,
                y: Math.random() * canvas.height,
                vX: (Math.random() - 0.5) * 1,
                vY: activeFX === 'snow' ? Math.random() * 1 + 0.5 : (activeFX === 'storm' ? Math.random() * 3 + 2 : Math.random() * 0.5 + 0.2),
                size: activeFX === 'snow' ? Math.random() * 3 + 1 : (activeFX === 'storm' ? 1 : Math.random() * 8 + 4),
                opacity: Math.random() * 0.5 + 0.3,
                char: activeFX === 'flowers' ? ['🌸', '🌹', '🌷', '🌻'][Math.floor(Math.random() * 4)] : null
            };
            return p;
        };

        for (let i = 0; i < particleCount; i++) particles.push(createParticle());

        const animate = () => {
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            particles.forEach(p => {
                if (p.char) {
                    ctx.font = `${p.size}px serif`;
                    ctx.globalAlpha = p.opacity;
                    ctx.fillText(p.char, p.x, p.y);
                } else {
                    ctx.beginPath();
                    ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
                    ctx.fillStyle = activeFX === 'snow' ? `rgba(255, 255, 255, ${p.opacity})` : `rgba(173, 216, 230, ${p.opacity})`;
                    ctx.fill();
                }

                p.x += p.vX;
                p.y += p.vY;

                if (p.y > canvas.height) {
                    p.y = -10;
                    p.x = Math.random() * canvas.width;
                }
            });

            // Special Storm Lightning
            if (activeFX === 'storm' && Math.random() > 0.98) {
                ctx.fillStyle = 'rgba(255, 255, 255, 0.4)';
                ctx.fillRect(0, 0, canvas.width, canvas.height);
            }

            animationFrame = requestAnimationFrame(animate);
        };

        const resize = () => {
            if (canvas.parentElement) {
                canvas.width = canvas.parentElement.clientWidth;
                canvas.height = canvas.parentElement.clientHeight;
            }
        };
        window.addEventListener('resize', resize);
        resize();
        animate();

        return () => {
            cancelAnimationFrame(animationFrame);
            window.removeEventListener('resize', resize);
        };
    }, [activeFX]);

    const getOverlayStyle = () => {
        switch (activeFX) {
            case 'purpleSky':
                return {
                    background: 'radial-gradient(circle at top, rgba(147, 51, 234, 0.3), transparent)',
                    mixBlendMode: 'overlay',
                    pointerEvents: 'none'
                };
            case 'storm':
                return {
                    background: 'rgba(15, 23, 42, 0.4)',
                    mixBlendMode: 'multiply',
                    pointerEvents: 'none'
                };
            case 'beach':
                return {
                    background: 'linear-gradient(to top, rgba(14, 165, 233, 0.3), transparent 60%)',
                    mixBlendMode: 'soft-light',
                    pointerEvents: 'none',
                    backdropFilter: 'blur(1px)'
                };
            default:
                return { pointerEvents: 'none' };
        }
    };

    return (
        <div style={{ position: 'relative', width: '100%', height: '100%', overflow: 'hidden', pointerEvents: 'none' }}>
            <div style={{ pointerEvents: interactive ? 'auto' : 'none', width: '100%', height: '100%' }}>
                {children}
            </div>

            {/* Particle Layer */}
            {(['snow', 'storm', 'flowers'].includes(activeFX)) && (
                <canvas
                    ref={canvasRef}
                    style={{
                        position: 'absolute',
                        top: 0,
                        left: 0,
                        width: '100%',
                        height: '100%',
                        pointerEvents: 'none',
                        zIndex: 5
                    }}
                />
            )}

            {/* CSS Overlay Layer */}
            {activeFX && activeFX !== 'none' && (
                <div
                    style={{
                        position: 'absolute',
                        top: 0,
                        left: 0,
                        width: '100%',
                        height: '100%',
                        zIndex: 6,
                        transition: 'all 1s ease',
                        pointerEvents: 'none',
                        ...getOverlayStyle()
                    }}
                />
            )}
        </div>
    );
}
