/**
 * ContextWizard — per-tab contextual help overlay
 *
 * Usage:
 *   <ContextWizard id="conversion" steps={STEPS} />
 *
 * Props:
 *   id        {string}   unique key used to persist dismiss state in localStorage
 *   steps     {Array}    { title, body, icon? } objects — one per wizard step
 *   accentVar {string?}  CSS variable name for accent colour (default --accent-blue)
 */

import { useState, useEffect } from 'react';
import { X, ChevronLeft, ChevronRight, HelpCircle, CheckCircle } from 'lucide-react';

const LS_KEY = (id) => `npu_wizard_dismissed_${id}`;

export default function ContextWizard({ id, steps = [], accentVar = '--accent-blue' }) {
    const [visible, setVisible] = useState(false);
    const [step, setStep] = useState(0);
    const [dismissed, setDismissed] = useState(false);

    // On mount — check if the user already dismissed this wizard
    useEffect(() => {
        const done = localStorage.getItem(LS_KEY(id)) === 'true';
        setDismissed(done);
        if (!done) setVisible(true); // auto-open on first visit
    }, [id]);

    if (!steps.length) return null;

    const dismiss = (forever = false) => {
        if (forever) localStorage.setItem(LS_KEY(id), 'true');
        setVisible(false);
        setDismissed(forever);
    };

    const accent = `var(${accentVar})`;
    const current = steps[step];

    return (
        <>
            {/* Floating "?" re-open button — shown when wizard is closed */}
            {!visible && (
                <button
                    title="Show guide"
                    onClick={() => { setStep(0); setVisible(true); }}
                    style={{
                        position: 'fixed', bottom: 90, right: 20, zIndex: 1000,
                        width: 40, height: 40, borderRadius: '50%',
                        background: `color-mix(in srgb, ${accent} 15%, var(--bg-card))`,
                        border: `1px solid color-mix(in srgb, ${accent} 40%, transparent)`,
                        color: accent, cursor: 'pointer',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        boxShadow: `0 0 0 4px color-mix(in srgb, ${accent} 8%, transparent)`,
                        transition: 'transform 0.15s',
                    }}
                    onMouseEnter={e => e.currentTarget.style.transform = 'scale(1.1)'}
                    onMouseLeave={e => e.currentTarget.style.transform = 'scale(1)'}
                >
                    <HelpCircle size={18} />
                </button>
            )}

            {/* Wizard panel */}
            {visible && (
                <div style={{
                    position: 'fixed',
                    bottom: 80,
                    right: 20,
                    zIndex: 1001,
                    width: 340,
                    borderRadius: 16,
                    background: 'var(--bg-card)',
                    border: `1px solid color-mix(in srgb, ${accent} 30%, var(--border))`,
                    boxShadow: `0 8px 40px rgba(0,0,0,0.45), 0 0 0 1px color-mix(in srgb, ${accent} 10%, transparent)`,
                    overflow: 'hidden',
                    animation: 'wizardSlideIn 0.2s ease',
                }}>
                    {/* Header */}
                    <div style={{
                        padding: '12px 16px',
                        borderBottom: `1px solid var(--border)`,
                        display: 'flex',
                        alignItems: 'center',
                        gap: 8,
                        background: `color-mix(in srgb, ${accent} 6%, var(--bg-card))`,
                    }}>
                        <span style={{ color: accent, display: 'flex' }}>
                            {current.icon ?? <HelpCircle size={16} />}
                        </span>
                        <span style={{ fontWeight: 700, fontSize: 14, flex: 1 }}>{current.title}</span>
                        <button onClick={() => dismiss(false)} style={{
                            background: 'none', border: 'none', color: 'var(--text-muted)',
                            cursor: 'pointer', padding: 2, display: 'flex',
                        }}>
                            <X size={16} />
                        </button>
                    </div>

                    {/* Body */}
                    <div style={{ padding: '16px', fontSize: 13, lineHeight: 1.6, color: 'var(--text-secondary)' }}>
                        {current.body}
                    </div>

                    {/* Progress dots */}
                    {steps.length > 1 && (
                        <div style={{ display: 'flex', justifyContent: 'center', gap: 6, paddingBottom: 4 }}>
                            {steps.map((_, i) => (
                                <span key={i} onClick={() => setStep(i)} style={{
                                    width: i === step ? 16 : 6, height: 6,
                                    borderRadius: 3, cursor: 'pointer', transition: 'all 0.2s',
                                    background: i === step ? accent : 'var(--border)',
                                }} />
                            ))}
                        </div>
                    )}

                    {/* Footer */}
                    <div style={{
                        padding: '10px 16px 14px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: 8,
                    }}>
                        <button
                            onClick={() => setStep(s => Math.max(0, s - 1))}
                            disabled={step === 0}
                            style={{
                                background: 'var(--bg-input)', border: '1px solid var(--border)',
                                borderRadius: 8, color: step === 0 ? 'var(--text-muted)' : 'var(--text-primary)',
                                height: 32, width: 32, display: 'flex', alignItems: 'center', justifyContent: 'center',
                                cursor: step === 0 ? 'default' : 'pointer',
                            }}
                        >
                            <ChevronLeft size={16} />
                        </button>

                        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                            {step + 1} / {steps.length}
                        </span>

                        {step < steps.length - 1 ? (
                            <button
                                onClick={() => setStep(s => s + 1)}
                                style={{
                                    background: accent, border: 'none', borderRadius: 8,
                                    color: '#fff', padding: '0 14px', height: 32,
                                    display: 'flex', alignItems: 'center', gap: 6,
                                    cursor: 'pointer', fontWeight: 600, fontSize: 13,
                                }}
                            >
                                Next <ChevronRight size={14} />
                            </button>
                        ) : (
                            <button
                                onClick={() => dismiss(true)}
                                style={{
                                    background: accent, border: 'none', borderRadius: 8,
                                    color: '#fff', padding: '0 14px', height: 32,
                                    display: 'flex', alignItems: 'center', gap: 6,
                                    cursor: 'pointer', fontWeight: 600, fontSize: 13,
                                }}
                            >
                                <CheckCircle size={14} /> Got it!
                            </button>
                        )}
                    </div>
                </div>
            )}

            {/* Slide-in keyframe */}
            <style>{`
                @keyframes wizardSlideIn {
                    from { opacity: 0; transform: translateY(12px) scale(0.97); }
                    to   { opacity: 1; transform: translateY(0) scale(1); }
                }
            `}</style>
        </>
    );
}
